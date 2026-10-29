"""One confirmed Aliyun OpenSearch query; external text is untrusted."""
import json, os, re, time
from datetime import datetime, timezone
from urllib.parse import urlparse, quote
import httpx
from sqlalchemy import update
from .database import SessionLocal
from .models import ProductResearchTask
from .product_research import still_authorized

def search_settings():
    key=os.environ.get('ALIYUN_SEARCH_API_KEY','').strip()
    host=os.environ.get('ALIYUN_SEARCH_ENDPOINT','').strip().rstrip('/')
    workspace=os.environ.get('ALIYUN_SEARCH_WORKSPACE','default').strip()
    try:
        parsed=urlparse(host); port=parsed.port
    except ValueError:return None
    if (not key or parsed.scheme!='https' or not parsed.hostname or
        not parsed.hostname.endswith('.opensearch.aliyuncs.com') or parsed.username or parsed.password or
        port not in (None,443) or parsed.path not in ('','/') or parsed.query or parsed.fragment or
        not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',workspace)):
        return None
    return key,host,workspace

def run_web_search(task_id):
    try:_run_web_search(task_id)
    except Exception:
        with SessionLocal() as db:
            db.execute(update(ProductResearchTask).where(ProductResearchTask.id==task_id,ProductResearchTask.status.in_(['pending','running'])).values(status='failed',error='搜索未完成，请检查服务配置后重试。'))
            db.commit()

def _run_web_search(task_id):
    with SessionLocal() as db:
        claimed=db.execute(update(ProductResearchTask).where(ProductResearchTask.id==task_id,ProductResearchTask.status=='pending').values(status='running'))
        db.commit()
        if claimed.rowcount!=1:return
        task=db.get(ProductResearchTask,task_id);settings=search_settings()
        if not task or not still_authorized(db,task):
            db.execute(update(ProductResearchTask).where(ProductResearchTask.id==task_id,ProductResearchTask.status=='running').values(status='cancelled',error='权限或项目状态已变化，任务已停止。'));db.commit();return
        if not settings:
            db.execute(update(ProductResearchTask).where(ProductResearchTask.id==task_id,ProductResearchTask.status=='running').values(status='failed',error='搜索服务未配置。'));db.commit();return
        key,host,workspace=settings
        started=time.monotonic();result=None
        try:
            response=httpx.post(f'{host}/v3/openapi/workspaces/{quote(workspace,safe="")}/web-search/ops-web-search-001',
                headers={'Authorization':'Bearer '+key},json={'query':task.source_text,'query_rewrite':False,'top_k':5,'content_type':'mainText','way':'pro'},timeout=30)
            response.raise_for_status();payload=response.json()
            if not isinstance(payload,dict) or payload.get('code') or not isinstance(payload.get('result'),dict) or not isinstance(payload['result'].get('search_result'),list):raise ValueError('invalid response')
            entries=[]
            for entry in payload['result']['search_result'][:5]:
                if not isinstance(entry,dict):continue
                link=entry.get('link');parsed=urlparse(link) if isinstance(link,str) else None
                if not parsed or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:continue
                info=entry.get('meta_info') if isinstance(entry.get('meta_info'),dict) else {}
                def text_field(value,limit):return value[:limit] if isinstance(value,str) else ''
                entries.append({'title':text_field(entry.get('title'),500),'url':link[:2000],
                    'snippet':text_field(entry.get('snippet'),2000),'content':text_field(entry.get('content'),6000),
                    'published_at':text_field(info.get('publishedTime'),100)})
            result=json.dumps({'items':entries,'searched_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False)
        except (httpx.HTTPError,ValueError,TypeError):result=None
        db.expire_all();task=db.get(ProductResearchTask,task_id)
        if not task or task.status!='running':return
        if not still_authorized(db,task):values={'status':'cancelled','error':'权限或项目状态已变化，结果未保存。'}
        elif result is None:values={'status':'failed','error':'搜索未完成，请检查服务配置或稍后重试；请求可能产生费用。'}
        else:values={'status':'completed','result':result,'error':''}
        values['elapsed_ms']=max(0,round((time.monotonic()-started)*1000))
        db.execute(update(ProductResearchTask).where(ProductResearchTask.id==task_id,ProductResearchTask.status=='running').values(**values));db.commit()
