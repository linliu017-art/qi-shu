'use client';

import { useEffect, useState } from 'react';
import RequiredMark from './RequiredMark';

type Requirement = {id:string; text:string};
type Chapter = {id:string; title:string; instruction:string; requirement_ids:string[]};
type Outline = {id:string; baseline_id:string; version:number; chapters:Chapter[]; uncovered:Requirement[]; created_at:string};
type OutlineData = {defaults:Chapter[]; defaults_fallback?:boolean; outlines:Outline[]};
type Choice = {id:string; baselineId:string} | null;

type Props = {projectId:string; baselineId:string; templateId:string; requirements:Requirement[]; onChoice:(choice:Choice)=>void; onDirty:(dirty:boolean)=>void};
async function request<T>(url:string, options?:RequestInit):Promise<T>{
  const response=await fetch(url,options);const data=await response.json();
  if(!response.ok)throw new Error(data.error?.message || '提纲操作未完成，请重试。');
  return data as T;
}
function copy(chapters:Chapter[]){return chapters.map(c=>({...c,requirement_ids:[...c.requirement_ids]}));}

export default function OutlineEditor({projectId,baselineId,templateId,requirements,onChoice,onDirty}:Props){
  const [data,setData]=useState<OutlineData|null>(null);
  const [chapters,setChapters]=useState<Chapter[]>([]);
  const [selected,setSelected]=useState('');
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const root=`/api/v1/projects/${encodeURIComponent(projectId)}/outlines`;
  useEffect(()=>{
    const controller=new AbortController();
    request<OutlineData>(`${root}?baseline_id=${encodeURIComponent(baselineId)}&template_id=${encodeURIComponent(templateId)}`,{signal:controller.signal}).then(value=>{
      if(controller.signal.aborted)return;
      setData(value);
      setChapters(copy(value.defaults));setSelected('');
      setDirty(false);onDirty(false);onChoice(null);
    }).catch(e=>{if(e.name!=='AbortError')setMessage(e instanceof Error?e.message:'提纲加载失败。');});
    return ()=>controller.abort();
  },[root,baselineId,templateId,onChoice,onDirty]);
  useEffect(()=>{
    if(!dirty)return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[dirty]);
  function update(next:Chapter[]){setChapters(next);setDirty(true);onDirty(true);onChoice(null);}
  function choose(id:string){
    if(dirty && !window.confirm('当前提纲有未保存的修改，切换会丢失这些修改。确认切换？'))return;
    const found=data?.outlines.find(x=>x.id===id);setSelected(id);setChapters(copy(found?.chapters ?? data?.defaults ?? []));
    setDirty(false);onDirty(false);onChoice(found?{id:found.id,baselineId}:null);setMessage('');
  }
  const covered=new Set(chapters.flatMap(c=>c.requirement_ids));
  const missing=requirements.filter(r=>!covered.has(r.id));
  function modify(id:string, patch:Partial<Chapter>){update(chapters.map(c=>c.id===id?{...c,...patch}:c));}
  function move(index:number,delta:number){const next=copy(chapters);const target=index+delta;if(target<0 || target>=next.length)return;[next[index],next[target]]=[next[target],next[index]];update(next);}
  async function save(){
    if(!chapters.length || chapters.some(c=>!c.title.trim()))return;
    try{
      setBusy(true);setMessage('');
      const saved=await request<Outline>(root,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({baseline_id:baselineId,template_id:templateId,chapters})});
      setData(old=>old?{...old,outlines:[saved,...old.outlines]}:{defaults:[],outlines:[saved]});setSelected(saved.id);setChapters(copy(saved.chapters));setDirty(false);onDirty(false);onChoice({id:saved.id,baselineId});
      setMessage(`提纲版本 ${saved.version} 已保存；已有方案不会改变。`);
    }catch(e){setMessage(e instanceof Error?e.message:'保存提纲失败。');}finally{setBusy(false);}
  }
  return <details className="outline-editor">
    <summary>调整方案提纲（选填）{selected && !dirty ? ` · 已选版本 ${data?.outlines.find(o=>o.id===selected)?.version ?? ""}` : ""}</summary>
    <p>默认按模板生成。需要调整时，可修改章节并保存为新版本。</p>
    {data ? <>
      {data.defaults_fallback && <p>未能识别模板章节，当前显示示例章节供调整；生成仍使用所选模板内容。</p>}
      <label>查看提纲版本<select value={selected} disabled={busy} onChange={e=>choose(e.target.value)}><option value="">默认模板提纲</option>{data.outlines.map(o=><option value={o.id} key={o.id}>提纲版本 {o.version} · {new Date(o.created_at).toLocaleString('zh-CN')}</option>)}</select></label>
      <fieldset disabled={busy} className="outline-chapters">
        {chapters.map((chapter,index)=><div className="outline-chapter" key={chapter.id}>
          <div className="outline-chapter-top"><strong>{index+1}. {chapter.title || "新章节"}</strong><div className="row outline-chapter-actions"><button type="button" className="secondary outline-icon-button" aria-label={`上移章节 ${chapter.title || index+1}`} title="上移章节" disabled={index===0} onClick={()=>move(index,-1)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5m-6 6 6-6 6 6"/></svg></button><button type="button" className="secondary outline-icon-button" aria-label={`下移章节 ${chapter.title || index+1}`} title="下移章节" disabled={index===chapters.length-1} onClick={()=>move(index,1)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14m-6-6 6 6 6-6"/></svg></button><button type="button" className="secondary outline-icon-button" aria-label={`删除章节 ${chapter.title || index+1}`} title="删除章节" disabled={chapters.length===1} onClick={()=>update(chapters.filter(c=>c.id!==chapter.id))}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16M10 11v6m4-6v6M5 7l1 13h12l1-13M9 7V4h6v3"/></svg></button></div></div>
          <details><summary>编辑章节{chapter.instruction ? " · 已填写写作要求" : ""}{chapter.requirement_ids.length ? ` · ${chapter.requirement_ids.length} 项需求` : ""}</summary><label><RequiredMark />章节标题<input aria-required="true" value={chapter.title} maxLength={120} onChange={e=>modify(chapter.id,{title:e.target.value})}/></label>
          <label>写作要求（选填）<textarea value={chapter.instruction} maxLength={1000} onChange={e=>modify(chapter.id,{instruction:e.target.value})} placeholder="例如：重点说明报修流程；未确定内容标明待确认"/></label>
          <details><summary>计划响应的需求（已选 {chapter.requirement_ids.length} 项）</summary><p>可为多个章节安排同一条需求。</p>{requirements.map(req=><label className="outline-requirement" key={req.id}><input type="checkbox" checked={chapter.requirement_ids.includes(req.id)} onChange={e=>modify(chapter.id,{requirement_ids:e.target.checked?[...chapter.requirement_ids,req.id]:chapter.requirement_ids.filter(id=>id!==req.id)})}/><span>{req.text}</span></label>)}</details></details>
        </div>)}
        <button type="button" className="secondary" disabled={chapters.length>=30} onClick={()=>update([...chapters,{id:crypto.randomUUID(),title:'',instruction:'',requirement_ids:[]}])}>添加章节</button>
      </fieldset>
      <details className="outline-coverage"><summary>尚未安排章节的需求：{missing.length} 条</summary>{missing.length>0?<ul>{missing.map(r=><li key={r.id}>{r.text}</li>)}</ul>:<p>已为每条需求安排至少一个章节。</p>}<p>这里显示的是你的编写计划，不代表生成的方案已经覆盖这些需求。</p></details>
      <button type="button" disabled={busy || chapters.length===0 || chapters.some(c=>!c.title.trim())} onClick={save}>保存提纲{selected?'为新版本':''}</button>
      {dirty && <p>提纲有未保存的修改；请先保存再生成方案。</p>}
      {!selected && !dirty && <p>当前使用默认模板，无需保存即可生成方案。</p>}
    </> : <p>正在读取提纲……</p>}
    {message && <p role="status">{message}</p>}
  </details>;
}

export function UsedOutline({projectId,proposalId}:{projectId:string;proposalId:string}){
  const [outline,setOutline]=useState<{version:number|null;chapters:Chapter[];requirement_texts:Record<string,string>}|null>(null);
  useEffect(()=>{
    const controller=new AbortController();
    request<{outline:{version:number|null;chapters:Chapter[];requirement_texts:Record<string,string>}|null}>(`/api/v1/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposalId)}/outline`,{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setOutline(data.outline);}).catch(()=>{});
    return()=>controller.abort();
  },[projectId,proposalId]);
  if(!outline)return null;
  return <details><summary>查看这份方案使用的提纲（版本 {outline.version ?? '未知'}）</summary><ol>{outline.chapters.map(c=><li key={c.id}><strong>{c.title}</strong>{c.instruction && <p>写作要求：{c.instruction}</p>}{c.requirement_ids.length>0 && <><p>计划响应的需求：</p><ul>{c.requirement_ids.map(id=><li key={id}>{outline.requirement_texts[id] || '需求待核对'}</li>)}</ul></>}</li>)}</ol></details>;
}
