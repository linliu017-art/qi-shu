"""Bounded section editing: model produces candidates only; deterministic code applies them."""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from .database import SessionLocal
from .membership import member_role
from .model_settings import model_key, model_settings
from .models import QueuedJob, SectionEdit
from .proposal import rejects_unmentioned_as_excluded

HEADING = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*(?:\r?\n|$)')
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')


def sections(content: str) -> list[dict]:
    found = []
    offset = 0
    fence = None
    previous = ''
    for line in content.splitlines(keepends=True):
        marker = FENCE.match(line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
        elif fence is None:
            if re.search(r'<\s*/?\s*h[1-6](?:\s|>|/)', line, re.I) or (previous.strip() and re.fullmatch(r' {0,3}(?:=+|-+)\s*', line)):
                return []
            match = HEADING.match(line)
            if match:
                level = len(match.group(1))
                for section in found:
                    if section['end'] is None and section['level'] >= level:
                        section['end'] = offset
                start = offset + len(line)
                ident = hashlib.sha256(f'{offset}:{level}:{match.group(2)}'.encode()).hexdigest()[:24]
                found.append({'id': ident, 'title': match.group(2), 'level': level, 'start': start, 'end': None})
        offset += len(line)
        previous = line
    if fence is not None:
        return []
    for section in found:
        if section['end'] is None:
            section['end'] = len(content)
    return found


def valid_candidate(value: str, level: int) -> bool:
    if rejects_unmentioned_as_excluded(value) or re.search(r'(?:待确认|未确认|尚未确认|尚待确认).{0,60}(?:不纳入|暂不纳入|不建设|不实施)', value):
        return False
    if not value.strip() or len(value) > 100000:
        return False
    # Disallow fenced blocks here: an unclosed fence could alter following chapters.
    previous = ''
    for line in value.splitlines():
        if re.search(r'<\s*/?\s*[a-zA-Z]', line) or (previous.strip() and re.fullmatch(r' {0,3}(?:=+|-+)\s*', line)):
            return False
        if FENCE.match(line):
            return False
        match = HEADING.match(line)
        if match and len(match.group(1)) <= level:
            return False
        previous = line
    return True


class EditFailure(Exception):
    pass


class Candidate(BaseModel):
    content: str = Field(min_length=1, max_length=100000)
    suggestions: list[str] = Field(default_factory=list, max_length=20)


def ensure_running(db, task_id):
    locked = db.execute(update(SectionEdit).where(SectionEdit.id == task_id, SectionEdit.status == 'running').values(status='running'))
    if locked.rowcount != 1:
        db.rollback()
        return False
    job = db.scalar(select(QueuedJob).where(QueuedJob.kind == 'section_edit', QueuedJob.target_id == task_id))
    if job and not member_role(db, job.project_id, job.user_id):
        db.execute(update(SectionEdit).where(SectionEdit.id == task_id, SectionEdit.status == 'running')
                   .values(status='cancelled', error='提交人已失去项目权限，任务已停止。'))
        db.commit()
        return False
    return True


def run_section_edit(task_id: str):
    with SessionLocal() as db:
        claimed = db.execute(update(SectionEdit).where(SectionEdit.id == task_id, SectionEdit.status == 'pending').values(status='running'))
        db.commit()
        if claimed.rowcount != 1:
            return
        task = db.get(SectionEdit, task_id)
        started = time.monotonic()
        try:
            key = model_key()
            allowed, limit = model_settings(db)
            if not key or task.model_name not in allowed or limit < 1:
                raise EditFailure('模型未配置或不在允许列表中。')
            output_limit = int(os.environ.get('QISHU_MAX_OUTPUT_TOKENS', '16384'))
            if not 1 <= output_limit <= 393216:
                raise EditFailure('模型输出长度配置无效。')
            prompt = (Path(__file__).parent / 'prompts' / 'section_edit_v1.txt').read_text(encoding='utf-8')
            payload = {'model': task.model_name, 'max_tokens': output_limit, 'thinking': {'type':'disabled'},
                'response_format': {'type':'json_object'}, 'messages': [
                    {'role':'system','content':prompt},
                    {'role':'user','content':json.dumps({'章节标题':task.section_title,'章节正文':task.original,'修改要求':task.instruction,'已确认依据和待确认事项':json.loads(task.context)},ensure_ascii=False)}]}
            for attempt in range(min(3, limit)):
                if not ensure_running(db, task_id):
                    return
                allowed, current_limit = model_settings(db)
                db.refresh(task)
                if task.model_name not in allowed or task.calls >= current_limit:
                    raise EditFailure('模型不再允许使用或已达到调用次数上限。')
                db.execute(update(SectionEdit).where(SectionEdit.id == task_id, SectionEdit.status == 'running').values(calls=task.calls + 1))
                db.commit()
                try:
                    response = httpx.post('https://api.deepseek.com/chat/completions', headers={'Authorization':'Bearer '+key}, json=payload, timeout=300)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        raise EditFailure('模型账号、余额或请求配置有误。')
                    response.raise_for_status()
                    result = response.json()
                    usage = result.get('usage') or {}
                    # Store usage even if the candidate cannot be used.
                    db.execute(update(SectionEdit).where(SectionEdit.id == task_id).values(prompt_tokens=usage.get('prompt_tokens'),completion_tokens=usage.get('completion_tokens')))
                    db.commit()
                    choice = result['choices'][0]
                    if choice.get('finish_reason') == 'length':
                        raise EditFailure('模型输出被截断，请调整要求后重新发起。')
                    candidate = Candidate.model_validate_json(choice['message']['content'])
                    if not valid_candidate(candidate.content, task.section_level) or any(len(x)>2000 for x in candidate.suggestions):
                        raise EditFailure('候选内容的章节边界或格式无效，请重新发起。')
                    if not ensure_running(db, task_id):
                        return
                    db.execute(update(SectionEdit).where(SectionEdit.id == task_id, SectionEdit.status == 'running')
                               .values(candidate=candidate.content, suggestions=json.dumps(candidate.suggestions,ensure_ascii=False), status='completed', error=''))
                    db.commit()
                    break
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                    if attempt == min(3, limit) - 1:
                        raise EditFailure('模型服务暂时不可用，请稍后重新发起。') from None
                    time.sleep(1)
        except Exception as exc:
            db.rollback()
            message = str(exc) if isinstance(exc, EditFailure) else '章节修改失败，请检查输入后重新发起。'
            db.execute(update(SectionEdit).where(SectionEdit.id == task_id, SectionEdit.status == 'running').values(status='failed',error=message[:500]))
            db.commit()
        finally:
            db.execute(update(SectionEdit).where(SectionEdit.id == task_id).values(elapsed_ms=max(0, round((time.monotonic()-started)*1000))))
            db.commit()
