'use client';
import { useEffect, useState } from 'react';
import RequiredMark from './RequiredMark';

type Revision = {id:string; proposed_text:string; original_text:string; status:string; base_version:number};
type Props = {projectId:string; requirementId:string; version:number; isOwner:boolean; onChange:()=>Promise<void>};

export default function RequirementRevision({projectId,requirementId,version,isOwner,onChange}:Props) {
  const [items,setItems]=useState<Revision[]>([]);
  const [text,setText]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const base=`/api/v1/projects/${encodeURIComponent(projectId)}`;
  const path=`${base}/requirements/${encodeURIComponent(requirementId)}/revisions`;
  async function request<T>(url:string,options?:RequestInit):Promise<T> {
    const response=await fetch(url,options); const value=await response.json();
    if(!response.ok) throw new Error(value.error?.message || '操作未完成，请重试。');
    return value as T;
  }
  useEffect(()=>{
    const controller=new AbortController();
    fetch(path,{signal:controller.signal}).then(async response=>{if(!response.ok)throw new Error('无法读取修订建议。');return response.json() as Promise<Revision[]>;}).then(setItems).catch(e=>{if(e.name!=='AbortError')setMessage(e.message);});
    return ()=>controller.abort();
  },[path,version]);
  async function submit() {
    try {setBusy(true);setMessage('');await request(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,version})});setText('');setItems(await request<Revision[]>(path));setMessage('建议已提交，原需求保持不变。');} catch(e){setMessage(e instanceof Error?e.message:'提交失败。');} finally {setBusy(false);}
  }
  async function decide(item:Revision,decision:'accept'|'reject') {
    try {setBusy(true);setMessage('');await request(`${base}/requirement-revisions/${encodeURIComponent(item.id)}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision})});await onChange();setItems(await request<Revision[]>(path));setMessage(decision==='accept'?'建议已采用。需要使用新内容时，请重新生成需求清单。':'建议已驳回。');}catch(e){setMessage(e instanceof Error?e.message:'处理失败。');}finally{setBusy(false);}
  }
  return <details><summary>需求修订建议{items.some(x=>x.status==='pending') ? `（待处理 ${items.filter(x=>x.status==='pending').length}）` : ''}</summary>
    <p>提交建议不会改变已确认需求；由负责人决定是否采用。</p>
    <label><RequiredMark />建议修改后的需求<textarea aria-required="true" value={text} maxLength={3000} onChange={e=>setText(e.target.value)} /></label>
    <button type="button" disabled={busy || !text.trim()} onClick={()=>void submit()}>提交修订建议</button>
    {items.map(item=><article className="consistency-issue" key={item.id}><p>原内容：{item.original_text}</p><p>建议：{item.proposed_text}</p><p>状态：{({pending:'待处理',accepted:'已采用',rejected:'已驳回'} as Record<string,string>)[item.status]}</p>{isOwner && item.status==='pending' && <div className="row"><button type="button" disabled={busy} onClick={()=>void decide(item,'accept')}>采用建议</button><button type="button" className="secondary" disabled={busy} onClick={()=>void decide(item,'reject')}>驳回建议</button></div>}</article>)}
    {message && <p role="status">{message}</p>}
  </details>;
}
