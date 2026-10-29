"""Bounded public-query comparison. Never execute without explicit paid-use approval."""
import argparse, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import httpx
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.product_web_search import search_settings

CASES=[('飞书 多维表格 功能 官网','feishu.cn'),('钉钉 文档 权限 管理 官网','dingtalk.com'),
       ('Notion pricing official','notion.so'),('Jira Cloud pricing official','atlassian.com'),
       ('语雀 团队 知识库 协作 官网','yuque.com'),('Figma collaboration product official','figma.com')]

def public_result(title,url,content):
    parsed=urlparse(url) if isinstance(url,str) else None
    if not parsed or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:return None
    return {'title':title[:500] if isinstance(title,str) else '', 'url':url[:2000],
            'returned_characters':len(content) if isinstance(content,str) else 0}

def run_case(client,provider,query,domain,settings):
    started=time.monotonic();result={'provider':provider,'query':query,'expected_domain':domain,'ok':False,'results':[]}
    try:
        if provider=='阿里云 Pro':
            key,host,workspace=settings
            response=client.post(f'{host}/v3/openapi/workspaces/{workspace}/web-search/ops-web-search-001',
                headers={'Authorization':'Bearer '+key},json={'query':query,'query_rewrite':False,'top_k':5,'content_type':'mainText','way':'pro'})
            response.raise_for_status();payload=response.json()
            if payload.get('code') or not isinstance(payload.get('result',{}).get('search_result'),list):raise ValueError('invalid')
            values=payload['result']['search_result'][:5]
            items=[public_result(x.get('title'),x.get('link'),x.get('content')) for x in values if isinstance(x,dict)]
            result['content_kind']='网页正文'
        else:
            response=client.post('https://api.wsa.cloud.tencent.com/SearchPro',headers={'Authorization':'Bearer '+settings},json={'Query':query,'Mode':0,'Cnt':10})
            response.raise_for_status();payload=response.json();outer=payload.get('Response',{})
            if not isinstance(outer,dict) or outer.get('Error') or not isinstance(outer.get('Pages'),list):raise ValueError('invalid')
            if outer.get('Version') not in (None,'standard'):raise ValueError('unexpected service version')
            values=[]
            for item in outer['Pages'][:5]:
                try:value=json.loads(item) if isinstance(item,str) else item
                except ValueError:continue
                if isinstance(value,dict):values.append(value)
            items=[public_result(x.get('title'),x.get('url'),x.get('content') or x.get('passage')) for x in values]
            result['content_kind']='摘要'
            result['service_version']=str(outer.get('Version','未知'))[:30]
        result['results']=[item for item in items if item]
        result['official_hit']=any((lambda host:host==domain or host.endswith('.'+domain))(urlparse(item['url']).hostname or '') for item in result['results'])
        result['ok']=True
    except (httpx.HTTPError,ValueError,TypeError,AttributeError):
        result['error']='请求失败或响应格式无效；可能产生费用。'
    result['elapsed_ms']=round((time.monotonic()-started)*1000)
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--confirm-paid',action='store_true');args=parser.parse_args()
    if not args.confirm_paid:print('未执行：需要先确认两家服务的按量费用。');return 2
    load_dotenv(ROOT/'backend'/'.env',override=False)
    aliyun=search_settings();tencent=os.environ.get('TENCENTCLOUD_WSA_APIKEY','').strip()
    if not aliyun or not tencent:print('未执行：两个搜索服务的服务端配置尚未齐全。');return 2
    rows=[]
    with httpx.Client(timeout=30) as client:
        for query,domain in CASES:
            for provider,settings in [('阿里云 Pro',aliyun),('腾讯标准版',tencent)]:
                rows.append(run_case(client,provider,query,domain,settings));time.sleep(.4)
    output={'created_at':datetime.now(timezone.utc).isoformat(),'scope':'6 条公开问题；前五条；不调用模型','results':rows,
            'note':'官网命中仅作参考，相关性、时效与可读性须人工核对；腾讯返回摘要，不等同网页正文。'}
    path=ROOT/'docs'/'evidence'/'竞品搜索评测'/('搜索对照-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2));print('评测记录已保存：',path)
    print('请求数：',len(rows),'成功：',sum(x['ok'] for x in rows),'；质量仍需人工核对。')
    return 0 if all(x['ok'] for x in rows) else 1
if __name__=='__main__':raise SystemExit(main())
