import json
import os
import time
from pathlib import Path
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from .database import SessionLocal
from .model_settings import model_key, model_settings
from .membership import member_role
from .models import (AdditionalCitation, AnalysisTask, ExtractedFact, Material, ModelConsent, QueuedJob,
                     OpenQuestion, Requirement, TaskAttempt, TaskAttemptTiming, TaskConfig, TaskSegment)

class TaskFailure(Exception):
    pass

class TaskCancelled(Exception):
    pass

def ensure_task_running(db, task_id):
    locked = db.execute(update(AnalysisTask).where(AnalysisTask.id == task_id, AnalysisTask.status == 'running').values(status='running'))
    if locked.rowcount != 1:
        db.rollback()
        raise TaskCancelled()
    job = db.scalar(select(QueuedJob).where(QueuedJob.kind == 'requirements', QueuedJob.target_id == task_id, QueuedJob.status == 'running'))
    if job and not member_role(db, job.project_id, job.user_id):
        db.execute(update(AnalysisTask).where(AnalysisTask.id == task_id, AnalysisTask.status == 'running')
                   .values(status='cancelled', error='提交人已失去项目权限，任务已停止。'))
        db.commit()
        raise TaskCancelled()

class Citation(BaseModel):
    material_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=3000)

class Candidate(Citation):
    text: str = Field(min_length=1, max_length=3000)
    related_sources: list[Citation] = Field(default_factory=list, max_length=30)

class ModelResult(BaseModel):
    requirements: list[Candidate] = Field(max_length=200)
    questions: list[Candidate] = Field(default_factory=list, max_length=200)
    facts: list[Candidate] = Field(default_factory=list, max_length=200)

SEGMENT_LENGTH = 12000
OVERLAP = 200

def split_offsets(text: str):
    start = 0
    while start < len(text):
        end = min(len(text), start + SEGMENT_LENGTH)
        if end < len(text):
            split = text.rfind('\n', start + SEGMENT_LENGTH // 2, end)
            if split > start:
                end = split + 1
        yield start, end
        if end == len(text):
            break
        start = max(start + 1, end - OVERLAP)

def group_segments(segments, version):
    group, total, ids = [], 0, set()
    for segment in segments:
        size = segment.end - segment.start
        if group and (version == 'requirements_v1' or segment.material_id in ids or total + size > SEGMENT_LENGTH):
            yield group
            group, total, ids = [], 0, set()
        group.append(segment)
        total += size
        ids.add(segment.material_id)
    if group:
        yield group

def align_quote(quote: str, original: str) -> str | None:
    if quote in original:
        return quote
    # Only ignore whitespace; retain and return the exact original substring.
    compact_quote = ''.join(ch for ch in quote if not ch.isspace())
    if not compact_quote:
        return None
    chars, offsets = [], []
    for index, char in enumerate(original):
        if not char.isspace():
            chars.append(char)
            offsets.append(index)
    start = ''.join(chars).find(compact_quote)
    if start < 0:
        return None
    return original[offsets[start]:offsets[start + len(compact_quote) - 1] + 1]

def execute_task(task_id: str):
    with SessionLocal() as db:
        claimed = db.execute(update(AnalysisTask).where(AnalysisTask.id == task_id, AnalysisTask.status == 'pending').values(status='running', error=''))
        db.commit()
        if claimed.rowcount != 1:
            return
        task = db.get(AnalysisTask, task_id)
        try:
            if not db.scalar(select(ModelConsent.id).where(ModelConsent.task_id == task.id)):
                raise TaskFailure('未确认资料发送和费用，任务未执行。')
            key = model_key()
            if not key:
                raise TaskFailure('未配置模型密钥。')
            allowed, cap = model_settings(db)
            max_output = int(os.environ.get('QISHU_MAX_OUTPUT_TOKENS', '16384'))
            if not 1 <= max_output <= 393216 or cap < 1:
                raise TaskFailure('模型调用次数或输出长度配置无效。')
            task_config = db.get(TaskConfig, task.id)
            if not task_config or task_config.prompt_version not in ('requirements_v1', 'requirements_v2', 'requirements_v3', 'requirements_v4', 'requirements_v5', 'requirements_v6'):
                raise TaskFailure('任务配置不存在，无法继续。')
            if task_config.model_name not in allowed:
                raise TaskFailure('原模型已不在允许列表中，请检查配置。')
            prompt = (Path(__file__).parent / 'prompts' / f'{task_config.prompt_version}.txt').read_text(encoding='utf-8')
            segments = list(db.scalars(select(TaskSegment).where(TaskSegment.task_id == task.id, TaskSegment.status == 'pending').order_by(TaskSegment.position)))
            for group in group_segments(segments, task_config.prompt_version):
                contents = {}
                for segment in group:
                    material = db.scalar(select(Material).where(Material.id == segment.material_id, Material.project_id == task.project_id))
                    if not material:
                        raise TaskFailure('所选资料已失效。')
                    contents[material.id] = material.text[segment.start:segment.end]
                aliases = {f'S{index}': material_id for index, material_id in enumerate(contents, 1)}
                model_contents = {alias: contents[material_id] for alias, material_id in aliases.items()} if task_config.prompt_version in ('requirements_v4', 'requirements_v5', 'requirements_v6') else contents
                payload = {'model': task_config.model_name, 'max_tokens': max_output, 'response_format': {'type': 'json_object'}, 'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': json.dumps(model_contents, ensure_ascii=False)}]}
                if task_config.prompt_version in ('requirements_v3', 'requirements_v4', 'requirements_v5', 'requirements_v6'):
                    payload['thinking'] = {'type': 'disabled'}
                for attempt_no in range(3):
                    ensure_task_running(db, task_id)
                    allowed, cap = model_settings(db)
                    if task_config.model_name not in allowed:
                        raise TaskFailure('原模型已不在允许列表中，请检查配置。')
                    attempts = db.scalar(select(func.count()).select_from(TaskAttempt).where(TaskAttempt.task_id == task.id))
                    if attempts >= cap:
                        db.execute(update(AnalysisTask).where(AnalysisTask.id == task_id, AnalysisTask.status == 'running')
                                   .values(status='paused_limit', error='已达到任务调用次数上限，已保存进度。'))
                        db.commit()
                        return
                    job = db.scalar(select(QueuedJob).where(QueuedJob.kind == 'requirements', QueuedJob.target_id == task.id, QueuedJob.status == 'running'))
                    record = TaskAttempt(task_id=task.id, segment_id=group[0].id, model_name=task_config.model_name, actor_id=job.user_id if job else 'local-user')
                    db.add(record)
                    db.commit()
                    try:
                        started = time.monotonic()
                        try:
                            response = httpx.post('https://api.deepseek.com/chat/completions', headers={'Authorization': 'Bearer '+key}, json=payload, timeout=300)
                        finally:
                            db.add(TaskAttemptTiming(attempt_id=record.id, elapsed_ms=max(0, round((time.monotonic() - started) * 1000))))
                            db.commit()
                        if 400 <= response.status_code < 500 and response.status_code != 429:
                            record.status = 'rejected'
                            db.commit()
                            raise TaskFailure('模型账号、余额或请求配置有误，请检查后重试。')
                        response.raise_for_status()
                        body = response.json()
                        usage = body.get('usage') or {}
                        record.prompt_tokens = usage.get('prompt_tokens')
                        record.completion_tokens = usage.get('completion_tokens')
                        record.status = 'received'
                        db.commit()
                        choice = body['choices'][0]
                        if choice.get('finish_reason') == 'length':
                            raise TaskFailure('模型输出被截断，当前段未完成，请调整后重试。')
                        result = ModelResult.model_validate_json(choice['message']['content'])
                        for item in result.requirements + result.questions + result.facts:
                            for source in [item] + item.related_sources:
                                if task_config.prompt_version in ('requirements_v4', 'requirements_v5', 'requirements_v6') and source.material_id in aliases:
                                    source.material_id = aliases[source.material_id]
                                if source.material_id not in contents:
                                    raise TaskFailure('模型结果包含未知资料编号，未保存。')
                                matched = align_quote(source.quote, contents[source.material_id])
                                if matched is None:
                                    raise TaskFailure('模型结果的引用文字不在对应资料中，未保存。')
                                source.quote = matched
                        ensure_task_running(db, task_id)
                        for kind, entries, model in [('requirement', result.requirements, Requirement), ('question', result.questions, OpenQuestion), ('fact', result.facts, ExtractedFact)]:
                            for item in entries:
                                text_column = model.original_text if kind == 'requirement' else model.text
                                existing = db.scalar(select(model.id).where(model.task_id == task.id, model.material_id == item.material_id, text_column == item.text, model.quote == item.quote))
                                if existing:
                                    row_id = existing
                                else:
                                    values = dict(project_id=task.project_id, task_id=task.id, text=item.text, material_id=item.material_id, quote=item.quote)
                                    if kind == 'requirement':
                                        values['original_text'] = item.text
                                    row = model(**values)
                                    db.add(row)
                                    db.flush()
                                    row_id = row.id
                                for source in item.related_sources:
                                    if source.material_id == item.material_id and source.quote == item.quote:
                                        continue
                                    citation = db.scalar(select(AdditionalCitation.id).where(AdditionalCitation.project_id == task.project_id, AdditionalCitation.item_type == kind, AdditionalCitation.item_id == row_id, AdditionalCitation.material_id == source.material_id, AdditionalCitation.quote == source.quote))
                                    if not citation:
                                        db.add(AdditionalCitation(project_id=task.project_id, item_type=kind, item_id=row_id, material_id=source.material_id, quote=source.quote))
                        for segment in group:
                            segment.status = 'completed'
                        db.commit()
                        break
                    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                        record.status = 'failed'
                        db.commit()
                        if attempt_no == 2:
                            raise TaskFailure('模型服务暂时不可用，请稍后重试。') from None
                        time.sleep(1)
                else:
                    raise TaskFailure('模型服务暂时不可用。')
            finished = db.execute(update(AnalysisTask).where(AnalysisTask.id == task_id, AnalysisTask.status == 'running')
                                  .values(status='completed', error=''))
            if finished.rowcount != 1:
                db.rollback()
                return
            db.commit()
        except TaskCancelled:
            db.rollback()
        except Exception as exc:
            db.rollback()
            error = str(exc) if isinstance(exc, TaskFailure) else '整理未完成，模型输出或服务异常，请重试。'
            db.execute(update(AnalysisTask).where(AnalysisTask.id == task_id, AnalysisTask.status == 'running')
                       .values(status='failed', error=error))
            db.commit()
