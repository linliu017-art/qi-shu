import json
import os
import time
from pathlib import Path
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import update
from .database import SessionLocal
from .models import ProposalDraft

class ProposalFailure(Exception):
    pass

class ProposalResult(BaseModel):
    content: str = Field(min_length=1, max_length=100000)

def run_proposal(draft_id: str):
    with SessionLocal() as db:
        claimed = db.execute(update(ProposalDraft).where(ProposalDraft.id == draft_id, ProposalDraft.status == 'pending').values(status='running'))
        db.commit()
        if claimed.rowcount != 1:
            return
        draft = db.get(ProposalDraft, draft_id)
        started = time.monotonic()
        try:
            key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
            if not key:
                raise ProposalFailure('模型未配置。')
            request_limit = int(os.environ.get('QISHU_MAX_REQUESTS', '50'))
            output_limit = int(os.environ.get('QISHU_MAX_OUTPUT_TOKENS', '16384'))
            if request_limit < 1 or not 1 <= output_limit <= 393216:
                raise ProposalFailure('模型调用次数或输出长度配置无效。')
            prompt = (Path(__file__).parent / 'prompts' / 'proposal_v1.txt').read_text(encoding='utf-8')
            payload = {'model': draft.model_name, 'max_tokens': output_limit, 'thinking': {'type':'disabled'}, 'response_format': {'type':'json_object'}, 'messages': [{'role':'system','content':prompt}, {'role':'user','content':json.dumps({'模板':draft.template_snapshot,'项目和需求':json.loads(draft.input_snapshot)},ensure_ascii=False)}]}
            attempts_allowed = min(3, request_limit)
            for attempt in range(attempts_allowed):
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
                    draft.content, draft.status, draft.error = result.content, 'completed', ''
                    break
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                    if attempt == attempts_allowed - 1:
                        raise ProposalFailure('模型服务暂时不可用，请稍后重试。') from None
                    time.sleep(1)
        except Exception as exc:
            db.rollback()
            draft = db.get(ProposalDraft, draft_id)
            draft.status = 'failed'
            draft.error = str(exc) if isinstance(exc, ProposalFailure) else '初稿生成失败，请检查输入后重试。'
        finally:
            draft.elapsed_ms = max(0, round((time.monotonic() - started) * 1000))
            db.commit()
