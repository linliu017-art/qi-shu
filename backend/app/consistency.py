"""Version-bound content checking: verified quotes only, no automated edits."""
import json, os, time
from pathlib import Path
from typing import Literal
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from .database import SessionLocal
from .membership import member_role
from .model_settings import model_key, model_settings
from .models import ConsistencyCheck, ConsistencyIssue, QueuedJob

class CheckFailure(Exception): pass

class Issue(BaseModel):
    category: Literal['名称','数字日期','术语','范围','需求覆盖','待确认承诺','引用依据']
    description: str = Field(min_length=1,max_length=1000)
    location_quote: str = Field(default='',max_length=1000)
    evidence_quote: str = Field(min_length=1,max_length=1000)

class Findings(BaseModel):
    issues: list[Issue] = Field(max_length=40)

def all_strings(value):
    if isinstance(value,str):
        return [value]
    if isinstance(value,dict):
        return [s for v in value.values() for s in all_strings(v)]
    if isinstance(value,list):
        return [s for v in value for s in all_strings(v)]
    return []

def validate_findings(result: Findings, content: str, context: str):
    sources=[content,*all_strings(json.loads(context))]
    for issue in result.issues:
        if not issue.description.strip() or not issue.evidence_quote.strip():
            raise CheckFailure('检查结果缺少可核对的依据。')
        if issue.location_quote and issue.location_quote not in content:
            raise CheckFailure('检查结果中的方案原句无法定位。')
        if not issue.location_quote and issue.category != '需求覆盖':
            raise CheckFailure('检查结果缺少方案原句。')
        if not any(issue.evidence_quote in source for source in sources):
            raise CheckFailure('检查结果中的依据原句无法定位。')

def ensure_running(db, task_id):
    locked=db.execute(update(ConsistencyCheck).where(ConsistencyCheck.id==task_id,ConsistencyCheck.status=='running').values(status='running'))
    if locked.rowcount!=1:
        db.rollback();return False
    job=db.scalar(select(QueuedJob).where(QueuedJob.kind=='consistency',QueuedJob.target_id==task_id))
    if job and not member_role(db,job.project_id,job.user_id):
        db.execute(update(ConsistencyCheck).where(ConsistencyCheck.id==task_id,ConsistencyCheck.status=='running').values(status='cancelled',error='提交人已失去项目权限，任务已停止。'))
        db.commit();return False
    return True

def run_consistency_check(task_id):
    with SessionLocal() as db:
        claimed=db.execute(update(ConsistencyCheck).where(ConsistencyCheck.id==task_id,ConsistencyCheck.status=='pending').values(status='running'))
        db.commit()
        if claimed.rowcount!=1:return
        task=db.get(ConsistencyCheck,task_id);started=time.monotonic()
        try:
            key=model_key();allowed,limit=model_settings(db)
            if not key or task.model_name not in allowed or limit<1:raise CheckFailure('模型未配置或不在允许列表中。')
            output_limit=int(os.environ.get('QISHU_MAX_OUTPUT_TOKENS','16384'))
            if not 1<=output_limit<=393216:raise CheckFailure('模型输出长度配置无效。')
            prompt=(Path(__file__).parent/'prompts'/'consistency_v1.txt').read_text(encoding='utf-8')
            payload={'model':task.model_name,'max_tokens':output_limit,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'},'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps({'方案原文':task.content,'需求事实与待确认事项':json.loads(task.context)},ensure_ascii=False)}]}
            for attempt in range(min(3,limit)):
                if not ensure_running(db,task_id):return
                allowed,current_limit=model_settings(db);db.refresh(task)
                if task.model_name not in allowed or task.calls>=current_limit:raise CheckFailure('模型不再允许使用或已达到调用次数上限。')
                db.execute(update(ConsistencyCheck).where(ConsistencyCheck.id==task_id,ConsistencyCheck.status=='running').values(calls=task.calls+1));db.commit()
                try:
                    response=httpx.post('https://api.deepseek.com/chat/completions',headers={'Authorization':'Bearer '+key},json=payload,timeout=300)
                    if 400<=response.status_code<500 and response.status_code!=429:raise CheckFailure('模型账号、余额或请求配置有误。')
                    response.raise_for_status();body=response.json();usage=body.get('usage') or {}
                    db.execute(update(ConsistencyCheck).where(ConsistencyCheck.id==task_id).values(prompt_tokens=usage.get('prompt_tokens'),completion_tokens=usage.get('completion_tokens')));db.commit()
                    choice=body['choices'][0]
                    if choice.get('finish_reason')=='length':raise CheckFailure('模型输出被截断，请缩小范围后重试。')
                    findings=Findings.model_validate_json(choice['message']['content']);validate_findings(findings,task.content,task.context)
                    if not ensure_running(db,task_id):return
                    for item in findings.issues:
                        db.add(ConsistencyIssue(check_id=task_id,category=item.category,description=item.description,location_quote=item.location_quote,evidence_quote=item.evidence_quote))
                    changed=db.execute(update(ConsistencyCheck).where(ConsistencyCheck.id==task_id,ConsistencyCheck.status=='running').values(status='completed',error=''))
                    if changed.rowcount!=1:db.rollback();return
                    db.commit();break
                except (httpx.TimeoutException,httpx.NetworkError,httpx.HTTPStatusError):
                    if attempt==min(3,limit)-1:raise CheckFailure('模型服务暂时不可用，请稍后重新发起。') from None
                    time.sleep(1)
        except Exception as exc:
            db.rollback();message=str(exc) if isinstance(exc,CheckFailure) else '检查失败，请检查输入后重新发起。'
            db.execute(update(ConsistencyCheck).where(ConsistencyCheck.id==task_id,ConsistencyCheck.status=='running').values(status='failed',error=message[:500]));db.commit()
        finally:
            db.execute(update(ConsistencyCheck).where(ConsistencyCheck.id==task_id).values(elapsed_ms=max(0,round((time.monotonic()-started)*1000))));db.commit()
