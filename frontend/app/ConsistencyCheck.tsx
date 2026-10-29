'use client';
import RequiredMark from './RequiredMark';

import { useCallback, useEffect, useState } from 'react';

type Issue = { id:string; category:string; description:string; location_quote:string; location_chapter:string; location_line:number|null; location_ambiguous:boolean; evidence_quote:string; evidence_kind:string; status:string; decision_note:string; decision_actor:string; decided_at:string|null; version:number };
type Check = { id:string; base_version:number; stale:boolean; source_warning:string; status:string; error:string; calls:number; prompt_tokens:number|null; completion_tokens:number|null; model_name:string; created_at:string; issues:Issue[] };
type Config = { model_ready:boolean; allowed_models:string[] };
const statuses:Record<string,string> = {pending:'等待中',running:'检查中',completed:'检查完成',failed:'检查失败',interrupted:'已中断',cancelled:'已取消'};
const issueStatuses:Record<string,string> = {pending:'待处理',resolved:'已处理',dismissed:'不采纳'};
async function request<T>(url:string, options?:RequestInit):Promise<T> {
  const response=await fetch(url,options);const data=await response.json();
  if(!response.ok)throw new Error(data.error?.message || '操作未完成，请重试。');
  return data as T;
}
export default function ConsistencyCheck({ projectId,proposalId,version,unsaved }:{projectId:string;proposalId:string;version:number;unsaved:boolean}) {
  const root=`/api/v1/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposalId)}`;
  const [open,setOpen]=useState(false);const [checks,setChecks]=useState<Check[]>([]);const [selected,setSelected]=useState('');
  const [config,setConfig]=useState<Config|null>(null);
  const [notes,setNotes]=useState<Record<string,string>>({});const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
  const refresh=useCallback(async()=>{
    const [rows,settings]=await Promise.all([request<Check[]>(`${root}/consistency-checks`),request<Config>('/api/v1/config')]);
    setChecks(rows);setConfig(settings);setSelected(old=>rows.some(x=>x.id===old)?old:rows[0]?.id || '');
  },[root]);
  useEffect(()=>{if(!open)return;const timer=setTimeout(()=>{void refresh().catch(e=>setMessage(e instanceof Error?e.message:'加载失败。'));},0);return()=>clearTimeout(timer);},[open,refresh]);
  useEffect(()=>{if(!open || !checks.some(c=>['pending','running'].includes(c.status)))return;const timer=setTimeout(()=>{void refresh().catch(e=>setMessage(e instanceof Error?e.message:'刷新失败。'));},1500);return()=>clearTimeout(timer);},[checks,open,refresh]);
  const current=checks.find(c=>c.id===selected);
  async function start(){
    if(!window.confirm('将当前已保存方案正文、生成时的已确认需求、已核对事实和未解决问题发送给模型服务商，可能产生模型费用。确认继续吗？'))return;
    try{setBusy(true);setMessage('');const check=await request<Check>(`${root}/consistency-checks`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version,confirm_external_use:true})});await refresh();setSelected(check.id);setMessage('检查任务已提交。');}
    catch(e){setMessage(e instanceof Error?e.message:'检查未完成。');}finally{setBusy(false);}
  }
  async function decide(issue:Issue,status:'resolved'|'dismissed'|'pending'){
    if(!current)return;const note=(notes[issue.id] ?? issue.decision_note).trim();
    try{setBusy(true);setMessage('');await request(`/api/v1/projects/${encodeURIComponent(projectId)}/consistency-checks/${encodeURIComponent(current.id)}/issues/${encodeURIComponent(issue.id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({check_version:current.base_version,issue_version:issue.version,status,note})});await refresh();setMessage('处理记录已保存；方案和审核状态未自动改变。');}
    catch(e){setMessage(e instanceof Error?e.message:'处理未完成。');}finally{setBusy(false);}
  }
  return <div className="consistency-panel">
    <button className="secondary" type="button" onClick={()=>setOpen(!open)}>{open?'收起方案内容检查':'检查方案内容'}</button>
    {open && <div className="consistency-body">
      <h3>检查方案内容</h3><p>检查名称、数字日期、术语、范围、需求覆盖和待确认事项等可能存在的问题，并核对资料依据是否可用。结果仅供人工判断，可能遗漏或误报。</p>
      <p>将发送当前方案正文及生成方案时的已确认需求、已核对事实和未解决问题；调用会产生费用。</p>
      {unsaved && <p>请先保存修改，再进行检查。</p>}
      <button type="button" disabled={busy || unsaved || !config?.allowed_models.length || !config.model_ready} onClick={start}>开始检查</button>
      {message && <p role="status">{message}</p>}
      {checks.length>0 && <><label>检查记录<select value={selected} onChange={e=>setSelected(e.target.value)}>{checks.map(c=><option key={c.id} value={c.id}>版本 {c.base_version} · {statuses[c.status]||c.status} · {new Date(c.created_at).toLocaleString('zh-CN')}</option>)}</select></label>
        {current && <><p>检查版本：{current.base_version}。{statuses[current.status] || current.status}；模型调用 {current.calls} 次，输入 {current.prompt_tokens ?? '未知'}，输出 {current.completion_tokens ?? '未知'}。{current.error}</p>
          {current.stale && <p className="detail-feedback">方案或依据已变化，这次检查仅供查看；请针对当前版本重新检查。</p>}
          {current.source_warning && <p className="detail-feedback">资料依据核对提示：{current.source_warning}</p>}
          {current.status==='completed' && current.issues.length===0 && <p>未发现可定位的问题，仍需人工审核；检查可能遗漏问题。</p>}
          {current.issues.map((issue,i)=><div className="consistency-issue" key={issue.id}>
            <strong>{i+1}. {issue.category} · {issueStatuses[issue.status] || issue.status}</strong><p>{issue.description}</p>
            <p><strong>位置：</strong>{issue.location_chapter ? `${issue.location_chapter} · ` : ''}{issue.location_line ? `第 ${issue.location_line} 行` : issue.location_ambiguous ? '原句在多处出现，请逐处核对' : '未定位到方案原句'}</p><p><strong>方案原句：</strong>{issue.location_quote || '未找到对应内容，请结合整份方案核对。'}</p>
            <p><strong>核对依据（{issue.evidence_kind}）：</strong>{issue.evidence_quote}</p>
            {issue.decision_actor && <p>处理人：{issue.decision_actor}；{issue.decided_at?new Date(issue.decided_at).toLocaleString('zh-CN'):''}</p>}
            <label><RequiredMark />处理说明（标记已处理或不采纳时必填）<textarea aria-required="true" value={notes[issue.id] ?? issue.decision_note} maxLength={2000} onChange={e=>setNotes(old=>({...old,[issue.id]:e.target.value}))} placeholder="记录核对结果或不采纳的原因" disabled={current.stale}/></label>
            <div className="row"><button type="button" disabled={busy || unsaved || current.stale || !(notes[issue.id] ?? issue.decision_note).trim()} onClick={()=>decide(issue,'resolved')}>标记已处理</button><button type="button" className="secondary" disabled={busy || unsaved || current.stale || !(notes[issue.id] ?? issue.decision_note).trim()} onClick={()=>decide(issue,'dismissed')}>不采纳</button>{issue.status!=='pending' && <button type="button" className="secondary" disabled={busy || unsaved || current.stale} onClick={()=>decide(issue,'pending')}>恢复待处理</button>}</div>
          </div>)}
        </>}
      </>}
    </div>}
  </div>;
}
