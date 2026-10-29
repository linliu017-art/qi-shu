"""Generate a bounded candidate from explicitly provided material; no web access."""
import json
import time
from pathlib import Path
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, update
from .database import SessionLocal
from .membership import member_role
from .model_settings import model_key, model_settings
from .models import ProductResearchTask, ProductWork
from .project_lifecycle import current_state

class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    report: str = Field(min_length=1, max_length=100000)

class AcceptanceCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=200)
    prerequisite: str = Field(min_length=1, max_length=10000)
    action: str = Field(min_length=1, max_length=10000)
    expected: str = Field(min_length=1, max_length=10000)
    quote: str = Field(min_length=3, max_length=3000)

class RequirementCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    quote: str = Field(min_length=1, max_length=3000)

class RequirementCandidates(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    requirements: list[RequirementCandidate] = Field(max_length=50)

def still_authorized(db, task):
    work = db.get(ProductWork, task.work_id)
    if not work or work.creator_id != task.actor_id or work.project_id != task.project_id:
        return False
    if task.project_id and ((task.actor_id != 'local-user' and not member_role(db, task.project_id, task.actor_id)) or current_state(db, task.project_id)[0] != 'active'):
        return False
    from .main import research_sources_available
    if not research_sources_available(db, task):
        return False
    return True

def run_research(task_id: str):
    try:
        _run_research(task_id)
    except Exception:
        with SessionLocal() as db:
            db.execute(update(ProductResearchTask).where(ProductResearchTask.id == task_id,
                ProductResearchTask.status.in_(['pending', 'running'])).values(
                    status='failed', error='研究未完成，请检查模型设置后重试。'))
            db.commit()

def _run_research(task_id: str):
    with SessionLocal() as db:
        claimed = db.execute(update(ProductResearchTask).where(ProductResearchTask.id == task_id,
            ProductResearchTask.status == 'pending').values(status='running'))
        db.commit()
        if claimed.rowcount != 1:
            return
        task = db.get(ProductResearchTask, task_id)
        if not task or not still_authorized(db, task):
            db.execute(update(ProductResearchTask).where(ProductResearchTask.id == task_id,
                ProductResearchTask.status == 'running').values(status='cancelled', error='权限或项目状态已变化，任务已停止。'))
            db.commit(); return
        key = model_key()
        allowed, _ = model_settings(db)
        if not key or task.model not in allowed:
            db.execute(update(ProductResearchTask).where(ProductResearchTask.id == task_id,
                ProductResearchTask.status == 'running').values(status='failed', error='模型配置不可用。'))
            db.commit(); return
        if task.prompt_version not in ('product_research_v1', 'product_research_v2', 'product_initiation_v1', 'product_prd_v1', 'product_prd_edit_v1', 'product_requirement_extract_v1', 'product_acceptance_v1'):
            task.status = 'failed'; task.error = '研究规则版本不可用。'; db.commit(); return
        try:
            prompt = (Path(__file__).parent / 'prompts' / f'{task.prompt_version}.txt').read_text(encoding='utf-8')
        except OSError:
            db.execute(update(ProductResearchTask).where(ProductResearchTask.id == task_id,
                ProductResearchTask.status == 'running').values(status='failed', error='研究规则暂不可用。'))
            db.commit(); return
        payload = {'model':task.model, 'max_tokens':6000, 'thinking':{'type':'disabled'},
                   'response_format':{'type':'json_object'}, 'messages':[{'role':'system','content':prompt},
                   {'role':'user','content':json.dumps({'研究目标':task.goal,'用户提供材料':task.source_text}, ensure_ascii=False)}]}
        candidate = None
        started = time.monotonic()
        prompt_tokens = completion_tokens = None
        for attempt in range(2):
            db.expire_all()
            current = db.get(ProductResearchTask, task_id)
            if not current or current.status != 'running':
                return
            if not still_authorized(db, current):
                db.execute(update(ProductResearchTask).where(ProductResearchTask.id == task_id,
                    ProductResearchTask.status == 'running').values(status='cancelled', error='权限或项目状态已变化，任务已停止。'))
                db.commit(); return
            try:
                response = httpx.post('https://api.deepseek.com/chat/completions',
                    headers={'Authorization':'Bearer '+key}, json=payload, timeout=90)
                response.raise_for_status()
                body = response.json()
                usage = body.get('usage') or {}
                for key_name in ('prompt_tokens', 'completion_tokens'):
                    value = usage.get(key_name)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        if key_name == 'prompt_tokens': prompt_tokens = (prompt_tokens or 0) + value
                        else: completion_tokens = (completion_tokens or 0) + value
                choice = body['choices'][0]
                if choice.get('finish_reason') == 'length':
                    raise ValueError('truncated')
                if task.prompt_version == 'product_requirement_extract_v1':
                    parsed = RequirementCandidates.model_validate_json(choice['message']['content'])
                    if any(not item.title.strip() or len(item.quote.strip()) < 3 or item.quote not in task.source_text for item in parsed.requirements):
                        raise ValueError('invalid citation')
                    candidate = parsed.model_dump_json()
                elif task.prompt_version == 'product_acceptance_v1':
                    parsed = AcceptanceCandidate.model_validate_json(choice['message']['content'])
                    if not all(getattr(parsed, name).strip() for name in ('title','prerequisite','action','expected')) or len(parsed.quote.strip()) < 3 or parsed.quote not in task.source_text:
                        raise ValueError('invalid citation')
                    candidate = parsed.model_dump_json()
                else:
                    candidate = Candidate.model_validate_json(choice['message']['content']).report
                if task.prompt_version == 'product_prd_edit_v1':
                    from .product_sections import validate_replacement
                    spec = json.loads(task.edit_spec)
                    if not validate_replacement(candidate, int(spec['level'])):
                        raise ValueError('unsafe section')
                break
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError):
                candidate = None
                if attempt == 1:
                    break
            except Exception:
                break
        db.expire_all()
        task = db.get(ProductResearchTask, task_id)
        if not task or task.status != 'running':
            return
        if not still_authorized(db, task):
            values = {'status':'cancelled', 'error':'权限或项目状态已变化，结果未保存。'}
        elif candidate:
            values = {'status':'completed', 'result':candidate}
        else:
            values = {'status':'failed', 'error':'研究生成未完成，请检查模型配置后重试。'}
        values.update(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                      elapsed_ms=max(0, round((time.monotonic() - started)*1000)))
        db.execute(update(ProductResearchTask).where(ProductResearchTask.id == task_id,
                   ProductResearchTask.status == 'running').values(**values))
        db.commit()
