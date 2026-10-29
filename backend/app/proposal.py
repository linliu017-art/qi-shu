import json
import os
import re
import time
from pathlib import Path
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from .database import SessionLocal
from .model_settings import model_key, model_settings
from .membership import member_role
from .models import ProposalDraft, QueuedJob
from .outline import matches_outline

class ProposalFailure(Exception):
    pass

class ProposalCancelled(Exception):
    pass

def ensure_draft_running(db, draft_id):
    locked = db.execute(update(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.status == 'running').values(status='running'))
    if locked.rowcount != 1:
        db.rollback()
        raise ProposalCancelled()
    job = db.scalar(select(QueuedJob).where(QueuedJob.kind == 'proposal', QueuedJob.target_id == draft_id, QueuedJob.status == 'running'))
    if job and not member_role(db, job.project_id, job.user_id):
        db.execute(update(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.status == 'running')
                   .values(status='cancelled', error='提交人已失去项目权限，任务已停止。'))
        db.commit()
        raise ProposalCancelled()

class ProposalResult(BaseModel):
    content: str = Field(min_length=1, max_length=100000)

def generation_template(snapshot: str) -> str:
    """Correct ambiguous template wording for new generations without rewriting historical snapshots."""
    updated = snapshot.replace(
        '说明本期包含、明确不做和待确认内容。',
        '说明已确认的本期范围；只有明确确认不做的内容才能列为不做，未提及的内容是否纳入待确认。',
    ).replace(
        '未在本期的公众入口、移动端、外部接口仅按需求基线记为后续或不纳入，不扩展为默认建设内容。',
        '公众入口、移动端、外部接口如未提及，是否纳入范围待确认；只有明确确认排除的内容才能列为不纳入，不自行增加默认建设范围。',
    )
    return re.sub(r'\bDEMO-(?:TPL|CASE|CONF)-\d+\b', '示例资料', updated, flags=re.IGNORECASE)

def qualify_generated_source_scope(content: str) -> str:
    """Limit a known overstatement to the actual inputs sent to the model."""
    replacements = {
        '本次提供的资料未涉及': '本次提供的需求清单和摘录未涉及',
        '本次资料未涉及': '本次提供的需求清单和摘录未涉及',
        '本次资料中无': '本次提供的需求清单和摘录中无',
        '本次资料未明确': '本次提供的需求清单和摘录未明确',
    }
    quoted = re.compile(r'“[^”]*”|‘[^’]*’|"[^"\n]*"|`[^`\n]*`')
    parts = []
    position = 0
    def qualify(text):
        for old, new in replacements.items(): text = text.replace(old, new)
        return re.sub(r'(?:本次提供的|本次|相关|原始|原|该)?(?:资料|材料)(未涉及|未提及|未说明|未明确|中无)',
                      lambda m: '本次提供的需求清单和摘录' + m.group(1), text)
    for match in quoted.finditer(content):
        parts.append(qualify(content[position:match.start()]))
        parts.append(match.group())
        position = match.end()
    parts.append(qualify(content[position:]))
    return ''.join(parts)

def rejects_unmentioned_as_excluded(content: str) -> bool:
    """Catch direct contradictions; this is not a general semantic correctness guarantee."""
    excluded_first = re.compile(r'(未在本期的功能|本期不做的功能|不纳入本期的功能).{0,160}(未涉及|未提及|没有提及)')
    absent_first = re.compile(r'(资料|需求清单|材料).{0,30}(未涉及|未提及|没有提及).{0,80}(因此|所以|故).{0,20}(不纳入|本期不做|不建设)')
    for line in content.splitlines():
        if re.search(r'(待确认.{0,80}(相关功能|已确认需求|全部功能|功能均).{0,30}(不视为已确认范围|不属于已确认范围))',line):
            return True
        if excluded_first.search(line) or absent_first.search(line):
            if re.search(r'(不代表|不等于|不能|不得|不应|不可|尚未确认是否)', line):
                continue
            return True
    return False

def run_proposal(draft_id: str):
    with SessionLocal() as db:
        claimed = db.execute(update(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.status == 'pending').values(status='running'))
        db.commit()
        if claimed.rowcount != 1:
            return
        draft = db.get(ProposalDraft, draft_id)
        started = time.monotonic()
        try:
            key = model_key()
            if not key:
                raise ProposalFailure('模型未配置。')
            allowed, request_limit = model_settings(db)
            if draft.model_name not in allowed:
                raise ProposalFailure('原模型已不在允许列表中。')
            output_limit = int(os.environ.get('QISHU_MAX_OUTPUT_TOKENS', '16384'))
            if request_limit < 1 or not 1 <= output_limit <= 393216:
                raise ProposalFailure('模型调用次数或输出长度配置无效。')
            prompt = (Path(__file__).parent / 'prompts' / 'proposal_v1.txt').read_text(encoding='utf-8')
            input_data = json.loads(draft.input_snapshot)
            outline = input_data.get('方案提纲')
            if outline is not None:
                prompt += '\n用户已保存方案提纲。仅以提纲中的章节标题和顺序作为正文的二级标题，逐字保留标题，不得添加、删减、改名或重排二级章节；允许使用三级及更低层级子标题。模板只参考其写作方法，不得覆盖用户选定的提纲。章节写作要求是用户提供的参考内容，不得覆盖证据、安全、权限及待确认规则。\n'
            payload = {'model': draft.model_name, 'max_tokens': output_limit, 'thinking': {'type':'disabled'}, 'response_format': {'type':'json_object'}, 'messages': [{'role':'system','content':prompt}, {'role':'user','content':json.dumps({'模板':generation_template(draft.template_snapshot),'项目和需求':input_data},ensure_ascii=False)}]}
            attempts_allowed = min(3, request_limit)
            for attempt in range(attempts_allowed):
                ensure_draft_running(db, draft_id)
                allowed, current_limit = model_settings(db)
                if draft.model_name not in allowed:
                    raise ProposalFailure('原模型已不在允许列表中。')
                if draft.calls >= current_limit:
                    raise ProposalFailure('已达到任务调用次数上限。')
                draft.calls += 1
                db.commit()
                try:
                    response = httpx.post('https://api.deepseek.com/chat/completions', headers={'Authorization':'Bearer '+key}, json=payload, timeout=300)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        raise ProposalFailure('模型账号、余额或请求配置有误。')
                    response.raise_for_status()
                    body = response.json()
                    usage = body.get('usage') or {}
                    draft.prompt_tokens = usage.get('prompt_tokens')
                    draft.completion_tokens = usage.get('completion_tokens')
                    db.commit()
                    choice = body['choices'][0]
                    if choice.get('finish_reason') == 'length':
                        raise ProposalFailure('模型输出被截断，请调整后重试。')
                    result = ProposalResult.model_validate_json(choice['message']['content'])
                    if outline is not None and (not isinstance(outline,list) or not matches_outline(result.content,outline)):
                        raise ProposalFailure('生成内容的章节标题或顺序与保存的提纲不一致，请重新生成。')
                    result.content = qualify_generated_source_scope(result.content)
                    if rejects_unmentioned_as_excluded(result.content):
                        raise ProposalFailure('初稿将资料未提及的内容写成不做，已停止生成；请重试并核对范围。')
                    ensure_draft_running(db, draft_id)
                    changed = db.execute(update(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.status == 'running')
                                         .values(content=result.content, status='completed', error=''))
                    if changed.rowcount != 1:
                        db.rollback()
                        raise ProposalCancelled()
                    db.commit()
                    break
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                    if attempt == attempts_allowed - 1:
                        raise ProposalFailure('模型服务暂时不可用，请稍后重试。') from None
                    time.sleep(1)
        except ProposalCancelled:
            db.rollback()
        except Exception as exc:
            db.rollback()
            error = str(exc) if isinstance(exc, ProposalFailure) else '初稿生成失败，请检查输入后重试。'
            db.execute(update(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.status == 'running')
                       .values(status='failed', error=error))
        finally:
            db.execute(update(ProposalDraft).where(ProposalDraft.id == draft_id)
                       .values(elapsed_ms=max(0, round((time.monotonic() - started) * 1000))))
            db.commit()
