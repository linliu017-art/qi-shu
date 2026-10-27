from contextlib import asynccontextmanager
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import BackgroundTasks, Depends, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Literal
from .database import Base, DATA_DIR, SessionLocal, engine
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
from .models import AdditionalCitation, AnalysisTask, Baseline, BaselineFacts, BaselineQuestions, ExtractedFact, FactReview, FactReviewEvent, Material, MaterialOriginal, ModelConsent, OpenQuestion, Project, ProposalDraft, ProposalExportEvent, ProposalReviewEvent, ProposalRevision, QuestionDecision, Requirement, RequirementDecision, TaskAttempt, TaskAttemptTiming, TaskConfig, TaskPricing, TaskSegment, new_id
from .parsing import ParseError, parse_content
from .analysis import align_quote, execute_task, split_offsets
from .proposal import run_proposal
from .proposal_review import SourceCheckError, questions_for, source_snapshot
from .proposal_docx import build_docx
import json
import os
import hashlib
import sqlite3
from uuid import uuid4
from decimal import Decimal

@asynccontextmanager
async def lifespan(app: FastAPI):
    root = Path(__file__).resolve().parents[1]
    migration = Config(str(root / 'alembic.ini'))
    migration.set_main_option('script_location', str(root / 'alembic'))
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
        tables = inspect(connection).get_table_names()
    if tables and revision is None:
        raise RuntimeError('数据库没有迁移版本，需先备份并检查后才能继续。')
    head = ScriptDirectory.from_config(migration).get_current_head()
    if revision and revision != head and engine.url.get_backend_name() == 'sqlite' and engine.url.database not in (None, ':memory:'):
        backup_dir = DATA_DIR / 'backups'
        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup_path = backup_dir / f'pre-migration-{uuid4()}.sqlite3'
        with sqlite3.connect(engine.url.database) as source, sqlite3.connect(backup_path) as target:
            source.backup(target)
        backup_path.chmod(0o600)
    with engine.begin() as connection:
        migration.attributes['connection'] = connection
        command.upgrade(migration, 'head')
    with SessionLocal() as db:
        for task in db.scalars(select(AnalysisTask).where(AnalysisTask.status.in_(["pending", "running"]))):
            task.status = "interrupted"
            task.error = "服务中断，请重新发起整理。"
        for draft in db.scalars(select(ProposalDraft).where(ProposalDraft.status.in_(["pending", "running"]))):
            draft.status = "interrupted"
            draft.error = "服务中断，请重新生成初稿。"
        db.commit()
    yield

app = FastAPI(title='qi-shu 本地工作台', lifespan=lifespan)

@app.middleware('http')
async def safe_error_boundary(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        return JSONResponse(status_code=500, content={'error': {'code': 'INTERNAL_ERROR', 'message': '操作未完成，请稍后重试。'}})

class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status

@app.exception_handler(ApiError)
async def api_error(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={'error': {'code': exc.code, 'message': exc.message}})

@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={'error': {'code': 'HTTP_ERROR', 'message': '请求无法完成。'}})

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={'error': {'code': 'INVALID_INPUT', 'message': '输入不符合要求，请检查后重试。'}})

def db_session():
    with SessionLocal() as db:
        yield db

class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    background: str = Field(default='', max_length=10000)

class ProjectOutput(BaseModel):
    id: str
    name: str
    background: str

class MaterialOutput(BaseModel):
    id: str
    filename: str
    characters: int
    text: str
    warning: str = ""
    preview_truncated: bool = False

def project_or_404(db: Session, project_id: str):
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == 'local-user'))
    if not project:
        raise ApiError('NOT_FOUND', '找不到这个项目。', 404)
    return project

@app.post('/api/v1/projects', response_model=ProjectOutput, status_code=201)
def create_project(body: ProjectInput, db: Session = Depends(db_session)):
    if not body.name.strip():
        raise ApiError('INVALID_INPUT', '请填写项目名称。', 422)
    project = Project(name=body.name.strip(), background=body.background)
    db.add(project)
    db.commit()
    return ProjectOutput(id=project.id, name=project.name, background=project.background)

@app.get('/api/v1/projects', response_model=list[ProjectOutput])
def list_projects(db: Session = Depends(db_session)):
    projects = db.scalars(select(Project).where(Project.owner_id == 'local-user').order_by(Project.created_at.desc()))
    return [ProjectOutput(id=p.id, name=p.name, background=p.background) for p in projects]

@app.post('/api/v1/projects/{project_id}/materials', response_model=MaterialOutput, status_code=201)
async def upload_material(project_id: str, file: UploadFile = File(...), db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    name = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    if not name or len(name) > 255 or any(ord(c) < 32 for c in name):
        raise ApiError('INVALID_FILENAME', '文件名不正确。', 422)
    if Path(name).suffix.lower() not in {'.txt', '.md', '.pdf', '.docx'}:
        raise ApiError('UNSUPPORTED_FORMAT', '不支持此格式。', 422)
    limit = 100 * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise ApiError('FILE_TOO_LARGE', '文件不能超过 100 MB。', 413)
    try:
        material_text, note = await run_in_threadpool(parse_content, name, content)
    except ParseError as exc:
        raise ApiError('INVALID_FILE', str(exc), 422) from None
    material_id = new_id()
    originals = DATA_DIR / 'materials'
    originals.mkdir(mode=0o700, parents=True, exist_ok=True)
    stored = originals / material_id
    try:
        with stored.open('xb') as handle:
            handle.write(content)
        stored.chmod(0o600)
        material = Material(id=material_id, project_id=project_id, filename=name, text=material_text, warning=note)
        db.add(material)
        db.add(MaterialOriginal(material_id=material_id, filename_on_disk=material_id, byte_size=len(content), sha256=hashlib.sha256(content).hexdigest()))
        db.commit()
    except Exception:
        db.rollback()
        stored.unlink(missing_ok=True)
        raise ApiError('SAVE_FAILED', '资料保存失败，请重试。', 500) from None
    return MaterialOutput(id=material.id, filename=material.filename, characters=len(material.text), text=material.text[:10000], warning=note, preview_truncated=len(material.text) > 10000)

@app.get('/api/v1/projects/{project_id}/materials', response_model=list[MaterialOutput])
def list_materials(project_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    materials = db.scalars(select(Material).where(Material.project_id == project_id, Material.owner_id == 'local-user').order_by(Material.created_at))
    return [MaterialOutput(id=m.id, filename=m.filename, characters=len(m.text), text=m.text[:10000], warning=m.warning, preview_truncated=len(m.text) > 10000) for m in materials]

class TaskInput(BaseModel):
    material_ids: list[str] = Field(min_length=1)
    model_name: str = "deepseek-flash"
    confirm_external_use: bool = False

class ExternalApproval(BaseModel):
    confirm_external_use: bool = False

class TaskOutput(BaseModel):
    id: str
    status: str
    error: str
    segments_total: int = 0
    segments_completed: int = 0
    calls: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    usage_complete: bool = False
    estimated_cost_usd: float | None = None
    model_name: str = ""
    elapsed_ms: int | None = None

def task_output(db: Session, task: AnalysisTask):
    segments = list(db.scalars(select(TaskSegment).where(TaskSegment.task_id == task.id)))
    attempts = list(db.scalars(select(TaskAttempt).where(TaskAttempt.task_id == task.id)))
    prompt = [a.prompt_tokens for a in attempts if a.prompt_tokens is not None]
    completion = [a.completion_tokens for a in attempts if a.completion_tokens is not None]
    config = db.get(TaskConfig, task.id)
    complete = bool(attempts) and all(a.prompt_tokens is not None and a.completion_tokens is not None for a in attempts)
    estimate = None
    # Peak, uncached pricing is an upper-rate estimate for successful Flash calls, not a bill.
    timings = list(db.scalars(select(TaskAttemptTiming).where(TaskAttemptTiming.attempt_id.in_([a.id for a in attempts])))) if attempts else []
    elapsed = sum(t.elapsed_ms for t in timings) if timings else None
    pricing = db.get(TaskPricing, task.id)
    if complete and pricing:
        estimate = float((Decimal(sum(prompt)) * Decimal(pricing.input_per_million) + Decimal(sum(completion)) * Decimal(pricing.output_per_million)) / Decimal(1000000))
    return TaskOutput(id=task.id, status=task.status, error=task.error, segments_total=len(segments), segments_completed=sum(s.status == 'completed' for s in segments), calls=len(attempts), prompt_tokens=sum(prompt) if prompt else None, completion_tokens=sum(completion) if completion else None, usage_complete=complete, estimated_cost_usd=estimate, model_name=config.model_name if config else '', elapsed_ms=elapsed)

class ReviewInput(BaseModel):
    status: str
    text: str = Field(min_length=1, max_length=3000)
    version: int

class CitationOutput(BaseModel):
    material_id: str
    quote: str

def citations(db: Session, project_id: str, kind: str, item_id: str):
    rows = db.scalars(select(AdditionalCitation).where(AdditionalCitation.project_id == project_id, AdditionalCitation.item_type == kind, AdditionalCitation.item_id == item_id))
    return [CitationOutput(material_id=r.material_id, quote=r.quote) for r in rows]

class RequirementOutput(BaseModel):
    id: str
    text: str
    original_text: str
    material_id: str
    quote: str
    status: str
    version: int
    related_sources: list[CitationOutput] = []

def req_output(row: Requirement, db: Session):
    return RequirementOutput(id=row.id, text=row.text, original_text=row.original_text, material_id=row.material_id, quote=row.quote, status=row.status, version=row.version, related_sources=citations(db, row.project_id, "requirement", row.id))

@app.post('/api/v1/projects/{project_id}/requirement-tasks', response_model=TaskOutput, status_code=202)
def start_task(project_id: str, body: TaskInput, background: BackgroundTasks, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    if not os.environ.get('DEEPSEEK_API_KEY', '').strip():
        raise ApiError('MODEL_NOT_CONFIGURED', '请先在本机配置模型密钥。', 400)
    if not body.confirm_external_use:
        raise ApiError('CONFIRMATION_REQUIRED', '请先确认资料发送和模型费用。', 400)
    allowed_models = [x.strip() for x in os.environ.get('DEEPSEEK_ALLOWED_MODELS', 'deepseek-flash').split(',') if x.strip()]
    if body.model_name not in allowed_models:
        raise ApiError('MODEL_NOT_ALLOWED', '此模型未在允许列表中。', 422)
    ids = list(dict.fromkeys(body.material_ids))
    materials = list(db.scalars(select(Material).where(Material.project_id == project_id, Material.id.in_(ids))))
    if len(materials) != len(ids):
        raise ApiError('INVALID_MATERIAL', '所选资料不存在。', 422)
    task = AnalysisTask(project_id=project_id, material_ids=json.dumps(ids))
    db.add(task)
    db.flush()
    db.add(TaskConfig(task_id=task.id, model_name=body.model_name))
    db.add(ModelConsent(task_id=task.id, action='start'))
    if body.model_name == 'deepseek-flash':
        db.add(TaskPricing(task_id=task.id, input_per_million='0.30', output_per_million='1.20', pricing_date='2026-10-27', pricing_reference='https://api-docs.deepseek.com/quick_start/pricing/'))
    position = 0
    for material in materials:
        for start, end in split_offsets(material.text):
            db.add(TaskSegment(task_id=task.id, material_id=material.id, position=position, start=start, end=end))
            position += 1
    db.commit()
    background.add_task(execute_task, task.id)
    return task_output(db, task)

@app.get('/api/v1/projects/{project_id}/requirement-tasks/{task_id}', response_model=TaskOutput)
def get_task(project_id: str, task_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    task = db.scalar(select(AnalysisTask).where(AnalysisTask.id == task_id, AnalysisTask.project_id == project_id))
    if not task:
        raise ApiError('NOT_FOUND', '找不到整理任务。', 404)
    return task_output(db, task)

@app.get('/api/v1/projects/{project_id}/requirements', response_model=list[RequirementOutput])
def list_requirements(project_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    return [req_output(r, db) for r in db.scalars(select(Requirement).where(Requirement.project_id == project_id))]

@app.patch('/api/v1/projects/{project_id}/requirements/{requirement_id}', response_model=RequirementOutput)
def review_requirement(project_id: str, requirement_id: str, body: ReviewInput, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    row = db.scalar(select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == project_id))
    if not row:
        raise ApiError('NOT_FOUND', '找不到这条需求。', 404)
    if body.version != row.version:
        raise ApiError('VERSION_CONFLICT', '内容已更新，请刷新后重试。', 409)
    if body.status not in ('pending', 'confirmed', 'rejected') or not body.text.strip():
        raise ApiError('INVALID_INPUT', '请填写需求并选择有效状态。', 422)
    if row.status == body.status and row.text == body.text.strip():
        return req_output(row, db)
    before_text, before_status = row.text, row.status
    changed = db.execute(update(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == project_id, Requirement.version == body.version).values(text=body.text.strip(), status=body.status, version=body.version + 1))
    if changed.rowcount != 1:
        db.rollback()
        raise ApiError('VERSION_CONFLICT', '内容已更新，请刷新后重试。', 409)
    db.add(RequirementDecision(requirement_id=row.id, from_version=body.version, old_text=before_text, new_text=body.text.strip(), old_status=before_status, new_status=body.status))
    db.commit()
    db.refresh(row)
    return req_output(row, db)

class BaselineCreated(BaseModel):
    id: str
    count: int

@app.post('/api/v1/projects/{project_id}/baselines', response_model=BaselineCreated, status_code=201)
def create_baseline(project_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    rows = list(db.scalars(select(Requirement).where(Requirement.project_id == project_id, Requirement.status == 'confirmed')))
    if not rows:
        raise ApiError('NO_CONFIRMED_REQUIREMENTS', '请先确认至少一条需求。', 422)
    baseline = Baseline(project_id=project_id, snapshot=json.dumps([req_output(r, db).model_dump() for r in rows], ensure_ascii=False))
    db.add(baseline)
    db.flush()
    questions = list(db.scalars(select(OpenQuestion).where(OpenQuestion.project_id == project_id, OpenQuestion.status != 'resolved')))
    pending_questions = []
    for question in questions:
        decision = db.scalar(select(QuestionDecision).where(QuestionDecision.question_id == question.id).order_by(QuestionDecision.created_at.desc()))
        pending_questions.append({'id': question.id, 'text': question.text, 'status': question.status, 'material_id': question.material_id, 'quote': question.quote, 'answer': decision.answer if decision else '', 'related_sources': [c.model_dump() for c in citations(db, project_id, 'question', question.id)]})
    db.add(BaselineQuestions(baseline_id=baseline.id, snapshot=json.dumps(pending_questions, ensure_ascii=False)))
    reviewed = list(db.scalars(select(ExtractedFact).join(FactReview, FactReview.fact_id == ExtractedFact.id).where(ExtractedFact.project_id == project_id, FactReview.status == 'reviewed').order_by(ExtractedFact.id)))
    db.add(BaselineFacts(baseline_id=baseline.id, snapshot=json.dumps([fact_output(f, db).model_dump() for f in reviewed], ensure_ascii=False)))
    db.commit()
    return {'id': baseline.id, 'count': len(rows)}

class BaselineQuestionOutput(BaseModel):
    id: str
    text: str
    status: str
    material_id: str
    quote: str
    answer: str
    related_sources: list[CitationOutput] = []

class BaselineFactOutput(BaseModel):
    id: str
    text: str
    material_id: str
    quote: str
    related_sources: list[CitationOutput] = []
    review_status: Literal['reviewed']
    review_version: int

class BaselineOutput(BaseModel):
    id: str
    requirements: list[RequirementOutput]
    questions: list[BaselineQuestionOutput] = []
    facts: list[BaselineFactOutput] = []
    facts_snapshot_available: bool = False

@app.get('/api/v1/projects/{project_id}/baselines', response_model=list[BaselineOutput])
def list_baselines(project_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    rows = db.scalars(select(Baseline).where(Baseline.project_id == project_id).order_by(Baseline.created_at.desc()))
    result = []
    for row in rows:
        questions = db.get(BaselineQuestions, row.id)
        facts = db.get(BaselineFacts, row.id)
        result.append(BaselineOutput(id=row.id, requirements=json.loads(row.snapshot), questions=json.loads(questions.snapshot) if questions else [], facts=json.loads(facts.snapshot) if facts else [], facts_snapshot_available=bool(facts)))
    return result

@app.get('/api/v1/projects/{project_id}/materials/{material_id}/original')
def download_original(project_id: str, material_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    material = db.scalar(select(Material).where(Material.id == material_id, Material.project_id == project_id, Material.owner_id == 'local-user'))
    if not material:
        raise ApiError('NOT_FOUND', '找不到这份资料。', 404)
    record = db.get(MaterialOriginal, material.id)
    if not record or record.filename_on_disk != material.id:
        raise ApiError('ORIGINAL_UNAVAILABLE', '原文件不可用。', 404)
    path = DATA_DIR / 'materials' / record.filename_on_disk
    if not path.is_file():
        raise ApiError('ORIGINAL_UNAVAILABLE', '原文件不可用。', 404)
    return FileResponse(path, filename=material.filename, media_type='application/octet-stream')

@app.get('/api/v1/projects/{project_id}/requirement-tasks', response_model=list[TaskOutput])
def list_tasks(project_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    tasks = list(db.scalars(select(AnalysisTask).where(AnalysisTask.project_id == project_id, AnalysisTask.owner_id == 'local-user').order_by(AnalysisTask.created_at.desc())))
    return [task_output(db, task) for task in tasks]

@app.post('/api/v1/projects/{project_id}/requirement-tasks/{task_id}/resume', response_model=TaskOutput)
def resume_task(project_id: str, task_id: str, body: ExternalApproval, background: BackgroundTasks, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    task = db.scalar(select(AnalysisTask).where(AnalysisTask.id == task_id, AnalysisTask.project_id == project_id, AnalysisTask.owner_id == 'local-user'))
    if not task:
        raise ApiError('NOT_FOUND', '找不到整理任务。', 404)
    if not os.environ.get('DEEPSEEK_API_KEY', '').strip():
        raise ApiError('MODEL_NOT_CONFIGURED', '请先在本机配置模型密钥。', 400)
    if not body.confirm_external_use:
        raise ApiError('CONFIRMATION_REQUIRED', '请先确认继续发送资料和模型费用。', 400)
    if task.status not in ('failed', 'interrupted', 'paused_limit'):
        raise ApiError('INVALID_STATE', '当前任务不能继续。', 409)
    count = db.scalar(select(func.count()).select_from(TaskAttempt).where(TaskAttempt.task_id == task.id))
    if count >= int(os.environ.get('QISHU_MAX_REQUESTS', '50')):
        raise ApiError('CALL_LIMIT', '已达到调用次数上限，需要先调整上限。', 409)
    changed = db.execute(update(AnalysisTask).where(AnalysisTask.id == task.id, AnalysisTask.status.in_(['failed', 'interrupted', 'paused_limit'])).values(status='pending', error=''))
    if changed.rowcount != 1:
        db.rollback()
        raise ApiError('INVALID_STATE', '任务状态已变化，请刷新。', 409)
    db.add(ModelConsent(task_id=task.id, action='resume'))
    db.commit()
    db.refresh(task)
    background.add_task(execute_task, task.id)
    return task_output(db, task)

class ConfigOutput(BaseModel):
    model_ready: bool
    allowed_models: list[str]
    max_requests: int
    max_output_tokens: int

@app.get('/api/v1/config', response_model=ConfigOutput)
def get_config():
    return ConfigOutput(model_ready=bool(os.environ.get('DEEPSEEK_API_KEY', '').strip()), allowed_models=[x.strip() for x in os.environ.get('DEEPSEEK_ALLOWED_MODELS', 'deepseek-flash').split(',') if x.strip()], max_requests=int(os.environ.get('QISHU_MAX_REQUESTS', '50')), max_output_tokens=int(os.environ.get('QISHU_MAX_OUTPUT_TOKENS', '16384')))

class QuestionOutput(BaseModel):
    id: str
    text: str
    material_id: str
    quote: str
    status: str
    answer: str = ""
    related_sources: list[CitationOutput] = []

@app.get('/api/v1/projects/{project_id}/questions', response_model=list[QuestionOutput])
def list_questions(project_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    rows = db.scalars(select(OpenQuestion).where(OpenQuestion.project_id == project_id))
    result = []
    for row in rows:
        latest = db.scalar(select(QuestionDecision).where(QuestionDecision.question_id == row.id).order_by(QuestionDecision.created_at.desc()))
        result.append(QuestionOutput(id=row.id, text=row.text, material_id=row.material_id, quote=row.quote, status=row.status, answer=latest.answer if latest else '', related_sources=citations(db, project_id, 'question', row.id)))
    return result

class MaterialPage(BaseModel):
    text: str
    offset: int
    next_offset: int | None
    total_characters: int

@app.get('/api/v1/projects/{project_id}/materials/{material_id}/content', response_model=MaterialPage)
def material_content(project_id: str, material_id: str, offset: int = 0, limit: int = 10000, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    if offset < 0 or not 1 <= limit <= 10000:
        raise ApiError('INVALID_INPUT', '查看范围不正确。', 422)
    material = db.scalar(select(Material).where(Material.project_id == project_id, Material.id == material_id, Material.owner_id == 'local-user'))
    if not material:
        raise ApiError('NOT_FOUND', '找不到这份资料。', 404)
    end = min(len(material.text), offset + limit)
    return MaterialPage(text=material.text[offset:end], offset=offset, next_offset=end if end < len(material.text) else None, total_characters=len(material.text))

class QuestionDecisionInput(BaseModel):
    status: str
    answer: str = Field(default='', max_length=5000)

@app.patch('/api/v1/projects/{project_id}/questions/{question_id}', response_model=QuestionOutput)
def decide_question(project_id: str, question_id: str, body: QuestionDecisionInput, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    row = db.scalar(select(OpenQuestion).where(OpenQuestion.id == question_id, OpenQuestion.project_id == project_id))
    if not row:
        raise ApiError('NOT_FOUND', '找不到这个问题。', 404)
    if body.status not in ('pending', 'answered', 'resolved') or (body.status != 'pending' and not body.answer.strip()):
        raise ApiError('INVALID_INPUT', '请填写说明并选择有效状态。', 422)
    row.status = body.status
    db.add(QuestionDecision(question_id=row.id, action=body.status, answer=body.answer.strip()))
    db.commit()
    return QuestionOutput(id=row.id, text=row.text, material_id=row.material_id, quote=row.quote, status=row.status, answer=body.answer.strip(), related_sources=citations(db, project_id, 'question', row.id))

class RequirementHistoryOutput(BaseModel):
    old_text: str
    new_text: str
    old_status: str
    new_status: str
    from_version: int
    actor: str
    created_at: str

@app.get('/api/v1/projects/{project_id}/requirements/{requirement_id}/history', response_model=list[RequirementHistoryOutput])
def requirement_history(project_id: str, requirement_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    row = db.scalar(select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == project_id))
    if not row:
        raise ApiError('NOT_FOUND', '找不到这条需求。', 404)
    records = db.scalars(select(RequirementDecision).where(RequirementDecision.requirement_id == row.id).order_by(RequirementDecision.created_at))
    return [RequirementHistoryOutput(old_text=r.old_text, new_text=r.new_text, old_status=r.old_status, new_status=r.new_status, from_version=r.from_version, actor=r.actor, created_at=r.created_at.isoformat()) for r in records]

class FactOutput(BaseModel):
    id: str
    text: str
    material_id: str
    quote: str
    related_sources: list[CitationOutput] = []
    review_status: Literal['pending', 'reviewed'] = 'pending'
    review_version: int = 0

class FactReviewInput(BaseModel):
    review_status: Literal['pending', 'reviewed']
    review_version: int = Field(ge=0)

def fact_output(row: ExtractedFact, db: Session):
    review = db.get(FactReview, row.id)
    return FactOutput(id=row.id, text=row.text, material_id=row.material_id, quote=row.quote,
                      related_sources=citations(db, row.project_id, 'fact', row.id),
                      review_status=review.status if review else 'pending',
                      review_version=review.version if review else 0)

@app.get('/api/v1/projects/{project_id}/facts', response_model=list[FactOutput])
def list_facts(project_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    rows = db.scalars(select(ExtractedFact).where(ExtractedFact.project_id == project_id))
    return [fact_output(row, db) for row in rows]

@app.patch('/api/v1/projects/{project_id}/facts/{fact_id}/review', response_model=FactOutput)
def review_fact(project_id: str, fact_id: str, body: FactReviewInput, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    row = db.scalar(select(ExtractedFact).where(ExtractedFact.id == fact_id, ExtractedFact.project_id == project_id))
    if not row:
        raise ApiError('NOT_FOUND', '找不到这条资料事实。', 404)
    current = db.get(FactReview, row.id)
    old_status = current.status if current else 'pending'
    old_version = current.version if current else 0
    if body.review_version != old_version:
        raise ApiError('VERSION_CONFLICT', '核对状态已变化，请刷新后重试。', 409)
    if body.review_status == old_status:
        return fact_output(row, db)
    try:
        if current is None:
            db.add(FactReview(fact_id=row.id, status=body.review_status, version=1))
        else:
            changed = db.execute(update(FactReview).where(FactReview.fact_id == row.id, FactReview.version == body.review_version).values(status=body.review_status, version=body.review_version + 1))
            if changed.rowcount != 1:
                db.rollback()
                raise ApiError('VERSION_CONFLICT', '核对状态已变化，请刷新后重试。', 409)
        db.add(FactReviewEvent(fact_id=row.id, old_status=old_status, new_status=body.review_status))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError('VERSION_CONFLICT', '核对状态已变化，请刷新后重试。', 409) from None
    db.expire_all()
    return fact_output(row, db)

# 方案初稿：当前只有一份虚构示例模板，不执行自动检索。
TEMPLATE_PATH = Path(__file__).resolve().parents[2] / 'docs/PRD/ToG公司内部工作台/samples/虚构建设项目/05-信息化建设方案示例模板.md'
EXAMPLE_PATH = Path(__file__).resolve().parents[2] / 'docs/PRD/ToG公司内部工作台/samples/虚构建设项目/04-虚构参考案例.txt'

class ProposalInput(BaseModel):
    baseline_id: str = Field(min_length=1, max_length=36)
    template_id: Literal['demo-v1']
    model_name: str = Field(default='deepseek-flash', max_length=100)
    include_example: bool = False
    confirm_external_use: bool = False

class ProposalOutput(BaseModel):
    id: str
    baseline_id: str
    template_id: str
    status: str
    content: str
    error: str
    version: int
    calls: int
    prompt_tokens: int | None
    completion_tokens: int | None
    elapsed_ms: int | None
    model_name: str
    created_at: str

class ProposalEdit(BaseModel):
    content: str = Field(min_length=1, max_length=100000)
    version: int = Field(ge=1)

def proposal_output(row: ProposalDraft):
    return ProposalOutput(id=row.id, baseline_id=row.baseline_id, template_id=row.template_id, status=row.status, content=row.content, error=row.error, version=row.version, calls=row.calls, prompt_tokens=row.prompt_tokens, completion_tokens=row.completion_tokens, elapsed_ms=row.elapsed_ms, model_name=row.model_name, created_at=row.created_at.isoformat())

@app.get('/api/v1/proposal-templates')
def proposal_templates():
    return [{'id': 'demo-v1', 'name': '信息化建设方案示例模板（虚构）', 'version': 'V1'}]

@app.get('/api/v1/projects/{project_id}/proposals', response_model=list[ProposalOutput])
def list_proposals(project_id: str, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    return [proposal_output(x) for x in db.scalars(select(ProposalDraft).where(ProposalDraft.project_id == project_id).order_by(ProposalDraft.created_at.desc()))]

@app.post('/api/v1/projects/{project_id}/proposals', response_model=ProposalOutput, status_code=202)
def create_proposal(project_id: str, body: ProposalInput, background: BackgroundTasks, db: Session = Depends(db_session)):
    project = project_or_404(db, project_id)
    if not body.confirm_external_use:
        raise ApiError('CONFIRMATION_REQUIRED', '请先确认资料发送和模型费用。', 400)
    if not os.environ.get('DEEPSEEK_API_KEY', '').strip():
        raise ApiError('MODEL_NOT_CONFIGURED', '请先在本机配置模型密钥。', 400)
    allowed = [x.strip() for x in os.environ.get('DEEPSEEK_ALLOWED_MODELS', 'deepseek-flash').split(',') if x.strip()]
    if body.model_name not in allowed:
        raise ApiError('MODEL_NOT_ALLOWED', '此模型未在允许列表中。', 422)
    baseline = db.scalar(select(Baseline).where(Baseline.id == body.baseline_id, Baseline.project_id == project_id))
    if not baseline:
        raise ApiError('NOT_FOUND', '找不到这份需求清单。', 404)
    requirements = json.loads(baseline.snapshot)
    if not requirements:
        raise ApiError('NO_CONFIRMED_REQUIREMENTS', '请选择含有已确认需求的清单。', 422)
    questions = db.get(BaselineQuestions, baseline.id)
    material_names = {m.id: m.filename for m in db.scalars(select(Material).where(Material.project_id == project_id))}
    def readable_sources(entry):
        sources = [entry] + entry.get('related_sources', [])
        return [{'资料名称': material_names.get(source.get('material_id'), '来源资料待核对'), '原文': source.get('quote', '')}
                for source in sources if source.get('material_id') or source.get('quote')]
    readable_requirements = [{'需求内容': entry.get('text', ''), '已有资料出处': readable_sources(entry)} for entry in requirements]
    status_names = {'pending': '待确认', 'answered': '已答复，问题尚未解决', 'resolved': '已解决'}
    facts_record = db.get(BaselineFacts, baseline.id)
    baseline_facts = json.loads(facts_record.snapshot) if facts_record else []
    readable_facts = [{'事实内容': entry.get('text', ''), '已有资料出处': [{'资料名称': source['资料名称']} for source in readable_sources(entry)]} for entry in baseline_facts]
    readable_questions = [{'问题': entry.get('text', ''), '状态': status_names.get(entry.get('status'), '待确认'),
                           '答复': entry.get('answer', ''), '已有资料出处': readable_sources(entry)}
                          for entry in (json.loads(questions.snapshot) if questions else [])]
    payload = {'项目名称': project.name, '已确认需求': readable_requirements, '已核对资料事实': readable_facts, '未解决问题': readable_questions}
    if body.include_example:
        payload['虚构参考案例（仅供方法参考，不是项目事实或业绩）'] = EXAMPLE_PATH.read_text(encoding='utf-8')
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) > 60000:
        raise ApiError('INPUT_TOO_LARGE', '需求清单过长，请先缩小范围后再生成。', 422)
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    draft = ProposalDraft(project_id=project_id, baseline_id=baseline.id, template_id=body.template_id, template_snapshot=template, input_snapshot=serialized, model_name=body.model_name)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    background.add_task(run_proposal, draft.id)
    return proposal_output(draft)

@app.patch('/api/v1/projects/{project_id}/proposals/{draft_id}', response_model=ProposalOutput)
def edit_proposal(project_id: str, draft_id: str, body: ProposalEdit, db: Session = Depends(db_session)):
    project_or_404(db, project_id)
    draft = db.scalar(select(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.project_id == project_id))
    if not draft:
        raise ApiError('NOT_FOUND', '找不到这份初稿。', 404)
    if draft.status != 'completed':
        raise ApiError('INVALID_STATE', '初稿生成完成后才能修改。', 409)
    if draft.version != body.version:
        raise ApiError('VERSION_CONFLICT', '初稿已更新，请刷新后重试。', 409)
    if not body.content.strip():
        raise ApiError('INVALID_INPUT', '初稿内容不能为空。', 422)
    if draft.content == body.content:
        return proposal_output(draft)
    old_content = draft.content
    result = db.execute(update(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.project_id == project_id, ProposalDraft.version == body.version).values(content=body.content, version=body.version+1))
    if result.rowcount != 1:
        db.rollback()
        raise ApiError('VERSION_CONFLICT', '初稿已更新，请刷新后重试。', 409)
    db.add(ProposalRevision(draft_id=draft_id, version=body.version, content=old_content))
    db.commit()
    db.refresh(draft)
    return proposal_output(draft)

class ReviewDecisionInput(BaseModel):
    question_id: str = Field(min_length=1, max_length=100)
    issue_text: str = Field(default='', max_length=3000)
    classification: Literal['critical', 'general', 'not_classified']
    disposition: Literal['resolved', 'noncommit', 'general_approved']
    reason: str = Field(min_length=1, max_length=2000)

class ReviewActionInput(BaseModel):
    version: int = Field(ge=1)
    action: Literal['submit', 'approve', 'return']
    note: str = Field(default='', max_length=2000)
    decisions: list[ReviewDecisionInput] = Field(default_factory=list, max_length=200)
    other_critical_checked: bool = False

class ReviewQuestionOutput(BaseModel):
    id: str
    text: str
    answer: str
    status: str

class ReviewOutput(BaseModel):
    version: int
    status: str
    last_action: str = ''
    baseline_created_at: str
    baseline_requirements_count: int
    message: str = ''
    questions: list[ReviewQuestionOutput]
    note: str = ''
    decisions: list[ReviewDecisionInput] = []
    updated_at: str | None = None

class ReviewHistoryOutput(BaseModel):
    version: int
    action: str
    note: str
    decisions: list[ReviewDecisionInput]
    created_at: str

class ExportInput(BaseModel):
    version: int = Field(ge=1)
    kind: Literal['draft', 'approved']


def proposal_or_404(db: Session, project_id: str, draft_id: str):
    project_or_404(db, project_id)
    row = db.scalar(select(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.project_id == project_id, ProposalDraft.owner_id == 'local-user'))
    if not row:
        raise ApiError('NOT_FOUND', '找不到这份方案。', 404)
    if row.status != 'completed':
        raise ApiError('INVALID_STATE', '方案生成完成后才能审核或导出。', 409)
    return row


def latest_review(db: Session, draft: ProposalDraft):
    return db.scalar(select(ProposalReviewEvent).where(ProposalReviewEvent.draft_id == draft.id, ProposalReviewEvent.project_id == draft.project_id, ProposalReviewEvent.version == draft.version).order_by(ProposalReviewEvent.created_at.desc(), ProposalReviewEvent.id.desc()))


def checked_sources(db: Session, draft: ProposalDraft):
    try:
        return source_snapshot(db, draft, TEMPLATE_PATH, EXAMPLE_PATH)
    except SourceCheckError as exc:
        raise ApiError('SOURCE_REVIEW_REQUIRED', str(exc), 409) from None


def lock_proposal_version(db: Session, draft: ProposalDraft, version: int):
    if draft.version != version:
        raise ApiError('VERSION_CONFLICT', '方案已更新，请刷新后重试。', 409)
    updated = db.execute(update(ProposalDraft).where(ProposalDraft.id == draft.id, ProposalDraft.project_id == draft.project_id, ProposalDraft.version == version, ProposalDraft.status == 'completed').values(version=version))
    if updated.rowcount != 1:
        db.rollback()
        raise ApiError('VERSION_CONFLICT', '方案已更新，请刷新后重试。', 409)


def review_output(db: Session, draft: ProposalDraft):
    try:
        questions = questions_for(db, draft)
    except SourceCheckError as exc:
        raise ApiError('SOURCE_REVIEW_REQUIRED', str(exc), 409) from None
    event = latest_review(db, draft)
    baseline = db.scalar(select(Baseline).where(Baseline.id == draft.baseline_id, Baseline.project_id == draft.project_id))
    if not baseline:
        raise ApiError('NOT_FOUND', '找不到方案使用的需求清单。', 404)
    status = event.action if event else 'draft'
    message = ''
    if event and event.action in ('submitted', 'approved'):
        try:
            now_sources = source_snapshot(db, draft, TEMPLATE_PATH, EXAMPLE_PATH)
            if now_sources != json.loads(event.sources):
                status, message = 'needs_review', '方案依据发生变化，请重新核对后再提交审核。'
        except (SourceCheckError, ValueError):
            status, message = 'needs_review', '方案依据暂时无法核对，请检查资料后重新提交审核。'
    return ReviewOutput(version=draft.version, status=status, last_action=event.action if event else '', baseline_created_at=utc_iso(baseline.created_at), baseline_requirements_count=len(json.loads(baseline.snapshot)), message=message,
        questions=[ReviewQuestionOutput(id=q['id'], text=q['text'], answer=q.get('answer', ''), status=q.get('status', 'pending')) for q in questions],
        note=event.note if event else '', decisions=json.loads(event.decisions) if event else [],
        updated_at=utc_iso(event.created_at) if event else None)

def utc_iso(value):
    from datetime import timezone
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()

@app.get('/api/v1/projects/{project_id}/proposals/{draft_id}/review', response_model=ReviewOutput)
def get_proposal_review(project_id: str, draft_id: str, db: Session = Depends(db_session)):
    return review_output(db, proposal_or_404(db, project_id, draft_id))

@app.get('/api/v1/projects/{project_id}/proposals/{draft_id}/review-history', response_model=list[ReviewHistoryOutput])
def get_proposal_review_history(project_id: str, draft_id: str, db: Session = Depends(db_session)):
    draft = proposal_or_404(db, project_id, draft_id)
    events = db.scalars(select(ProposalReviewEvent).where(ProposalReviewEvent.draft_id == draft.id, ProposalReviewEvent.project_id == project_id).order_by(ProposalReviewEvent.created_at.desc(), ProposalReviewEvent.id.desc()))
    return [ReviewHistoryOutput(version=e.version, action=e.action, note=e.note, decisions=json.loads(e.decisions), created_at=utc_iso(e.created_at)) for e in events]

@app.post('/api/v1/projects/{project_id}/proposals/{draft_id}/review', response_model=ReviewOutput)
def act_on_proposal_review(project_id: str, draft_id: str, body: ReviewActionInput, db: Session = Depends(db_session)):
    draft = proposal_or_404(db, project_id, draft_id)
    lock_proposal_version(db, draft, body.version)
    event = latest_review(db, draft)
    try:
        questions = questions_for(db, draft)
    except SourceCheckError as exc:
        raise ApiError('SOURCE_REVIEW_REQUIRED', str(exc), 409) from None
    if body.action == 'submit':
        sources = checked_sources(db, draft)
        if event and event.action in ('submitted', 'approved') and json.loads(event.sources) == sources:
            raise ApiError('INVALID_STATE', '当前版本已经提交审核。', 409)
        action, decisions, note = 'submitted', [], ''
    else:
        if not event or event.action != 'submitted':
            raise ApiError('INVALID_STATE', '请先提交当前版本审核。', 409)
        if not body.note.strip():
            raise ApiError('INVALID_INPUT', '请填写审核意见。', 422)
        if body.action == 'return':
            try:
                sources = json.loads(event.sources)
            except ValueError:
                sources = {}
            action, decisions, note = 'returned', [], body.note.strip()
        else:
            sources = checked_sources(db, draft)
            if sources != json.loads(event.sources):
                raise ApiError('SOURCE_REVIEW_REQUIRED', '方案依据发生变化，请重新提交审核。', 409)
            if not body.other_critical_checked:
                raise ApiError('CONFIRMATION_REQUIRED', '请确认方案中没有其他未处理的关键问题。', 400)
            expected = {q['id'] for q in questions}
            supplied = {d.question_id for d in body.decisions}
            extra = [d for d in body.decisions if d.question_id not in expected]
            if not expected.issubset(supplied) or len(body.decisions) != len(supplied) or any(not d.question_id.startswith('extra-') or not d.issue_text.strip() for d in extra):
                raise ApiError('UNRESOLVED_QUESTIONS', '请逐项处理需求清单中的待确认问题。', 409)
            if any(not d.reason.strip() or (d.disposition == 'general_approved' and d.classification != 'general') for d in body.decisions):
                raise ApiError('UNRESOLVED_QUESTIONS', '请填写处理说明；关键问题不能按一般事项保留。', 409)
            action, decisions, note = 'approved', [d.model_dump() for d in body.decisions], body.note.strip()
    db.add(ProposalReviewEvent(project_id=project_id, draft_id=draft.id, version=draft.version, action=action, note=note, decisions=json.dumps(decisions, ensure_ascii=False), sources=json.dumps(sources, ensure_ascii=False, sort_keys=True)))
    db.commit()
    return review_output(db, draft)

@app.post('/api/v1/projects/{project_id}/proposals/{draft_id}/export')
def export_proposal(project_id: str, draft_id: str, body: ExportInput, db: Session = Depends(db_session)):
    from urllib.parse import quote
    draft = proposal_or_404(db, project_id, draft_id)
    lock_proposal_version(db, draft, body.version)
    event = latest_review(db, draft)
    if body.kind == 'approved':
        if not event or event.action != 'approved':
            raise ApiError('NOT_APPROVED', '当前版本尚未审核通过，只能导出草稿。', 409)
        sources = checked_sources(db, draft)
        if sources != json.loads(event.sources):
            raise ApiError('SOURCE_REVIEW_REQUIRED', '方案依据发生变化，请重新审核。', 409)
    baseline = db.scalar(select(Baseline).where(Baseline.id == draft.baseline_id, Baseline.project_id == project_id))
    if not baseline:
        raise ApiError('NOT_FOUND', '找不到方案使用的需求清单。', 404)
    try:
        requirements = json.loads(baseline.snapshot)
        try:
            questions = questions_for(db, draft)
        except SourceCheckError:
            if body.kind == 'approved':
                raise
            questions = [{'text': '这份旧清单没有待确认问题记录，请人工核实。', 'answer': ''}]
        if body.kind == 'approved':
            decision_map = {item['question_id']: item for item in json.loads(event.decisions)}
            questions = [{**q, 'review': decision_map.get(q['id'], {})} for q in questions]
            question_ids = {q['id'] for q in questions}
            questions.extend({'text': item['issue_text'], 'answer': '', 'review': item} for item in decision_map.values() if item['question_id'] not in question_ids and item.get('issue_text'))
        materials = {m.id: m for m in db.scalars(select(Material).where(Material.project_id == project_id, Material.owner_id == 'local-user'))}
        names, citations, original_valid = {}, [], {}
        fact_record = db.get(BaselineFacts, baseline.id)
        baseline_facts = json.loads(fact_record.snapshot) if fact_record else []
        for entry in requirements + questions + baseline_facts:
            for ref in [entry] + (entry.get('related_sources') or []):
                material = materials.get(ref.get('material_id'))
                if material:
                    names[material.id.lower()] = material.filename
                    if material.id not in original_valid:
                        original = db.get(MaterialOriginal, material.id)
                        path = DATA_DIR / 'materials' / material.id
                        valid = bool(original and original.filename_on_disk == material.id and path.is_file())
                        if valid:
                            digest = hashlib.sha256()
                            with path.open('rb') as handle:
                                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                                    digest.update(chunk)
                            valid = digest.hexdigest() == original.sha256
                        original_valid[material.id] = valid
                    if ref.get('quote') and original_valid[material.id] and align_quote(ref['quote'], material.text):
                        citations.append((material.filename, ref['quote']))
                    elif ref.get('quote'):
                        citations.append((material.filename, '资料不可用或已变化，请核对。'))
        from datetime import timezone
        created = baseline.created_at if baseline.created_at.tzinfo else baseline.created_at.replace(tzinfo=timezone.utc)
        baseline_description = f'{len(requirements)} 条需求，生成于 {created.astimezone().strftime("%Y-%m-%d %H:%M")}'
        output = build_docx(draft.content, body.kind, draft.version, questions, names, citations, baseline_description)
    except (ValueError, TypeError, SourceCheckError):
        raise ApiError('EXPORT_FAILED', '方案内容暂时无法导出，请检查后重试。', 422) from None
    except Exception:
        raise ApiError('EXPORT_FAILED', '导出失败，请稍后重试。', 500) from None
    db.add(ProposalExportEvent(project_id=project_id, draft_id=draft.id, version=draft.version, kind=body.kind))
    db.commit()
    filename = '方案草稿.docx' if body.kind == 'draft' else '已审核方案.docx'
    return Response(content=output, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename)})
