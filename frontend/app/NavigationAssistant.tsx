'use client';
import { useState } from 'react';

export type NavIntent = 'projects'|'new_project'|'worklist'|'review_todos'|'materials'|'requirements'|'proposal'|'review'|'project_settings'|'workspace_settings'|'unknown';
type Project = {id:string; name:string; state:string};
type Result = {intent:NavIntent; project_hint:string};
const labels: Record<NavIntent,string> = {projects:'查看项目',new_project:'新建项目',worklist:'我的待办',review_todos:'待审核方案',materials:'项目资料',requirements:'整理并确认需求',proposal:'生成方案',review:'审核与导出',project_settings:'项目设置',workspace_settings:'工作台设置',unknown:'暂未识别'};
const projectIntents = new Set<NavIntent>(['materials','requirements','proposal','review','project_settings']);

function localIntent(text:string, projects:Project[]):Result {
  const v=text.trim(); let intent:NavIntent='unknown';
  if (/(待审核|待审|需要审核|需要审批).*(方案|事项|待办)|(?:方案|事项).*(待审核|待审|需要审核|需要审批)/.test(v)) intent='review_todos';
  else if (/(新建|创建|新增|建立).{0,8}项目/.test(v)) intent='new_project';
  else if (/(工作台|账号|账户|模型).{0,5}(设置|管理)/.test(v)) intent='workspace_settings';
  else if (/(项目成员|项目设置|成员管理|项目管理)/.test(v)) intent='project_settings';
  else if (/(待办|任务列表|我负责的)/.test(v)) intent='worklist';
  else if (/(审核|导出|审阅|下载).{0,8}(方案|word|文档)|(方案|word).{0,8}(审核|导出|审阅|下载)/i.test(v)) intent='review';
  else if (/(生成|查看|预览|写|制作).{0,8}(方案|初稿)|(方案|初稿).{0,8}(生成|查看|预览)/.test(v)) intent='proposal';
  else if (/(需求|待确认问题)/.test(v)) intent='requirements';
  else if (/(资料|文件|文档|访谈|上传)/.test(v)) intent='materials';
  else if (/(项目)/.test(v)) intent='projects';
  const named=projects.filter(p=>p.state!=='trash' && p.name && v.includes(p.name));
  return {intent,project_hint:named.length===1 ? named[0].name : ''};
}

export default function NavigationAssistant({projects,currentProject,onNavigate}:{projects:Project[];currentProject:string;onNavigate:(intent:NavIntent,projectId?:string)=>boolean}) {
  const [open,setOpen]=useState(false),[text,setText]=useState(''),[result,setResult]=useState<Result|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[allProjects,setAllProjects]=useState(false);
  const eligible=projects.filter(p=>p.state!=='trash');
  const matches=(result?.project_hint ? eligible.filter(p=>p.name.toLowerCase().includes(result.project_hint.toLowerCase())) : []);
  async function search(){
    if(!text.trim()||busy)return;
    const value=localIntent(text,eligible);setAllProjects(false);setResult(null);
    if(value.intent!=='unknown'){setResult(value);setMessage('请选择要前往的位置。');return;}
    try {setBusy(true);setMessage('正在查找…');const response=await fetch('/api/v1/navigation/interpret',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text.trim(),confirm_external_use:true})});const data=await response.json();if(!response.ok)throw new Error(data.error?.message||'暂时无法识别。');setResult({intent:data.intent,project_hint:data.project_hint});setMessage(data.intent==='unknown'?'暂时没找到对应入口，请换个说法。':'查找完成，请选择要前往的位置。');}
    catch(e){setMessage(e instanceof Error?e.message:'暂时无法识别，请重试。');}finally{setBusy(false);}
  }
  function go(intent:NavIntent,id?:string){if(onNavigate(intent,id))setOpen(false);}
  const projectSearch=result?.intent==='projects' && (!!result.project_hint || /(找|查找|打开|进入|上次)/.test(text));
  const target=!!result && (projectIntents.has(result.intent) || projectSearch);
  const current=eligible.find(p=>p.id===currentProject);
  let candidates:Project[]=[];
  if(target){
    if(allProjects)candidates=eligible;
    else if(result?.project_hint)candidates=matches;
    else if(projectSearch)candidates=eligible;
    else if(text.includes('项目') && !/(当前项目|这个项目|本项目)/.test(text))candidates=eligible;
    else if(current)candidates=[current];
    else candidates=eligible;
  }
  return <div className="nav-assistant">
    <button className="nav-assistant-trigger" type="button" aria-expanded={open} aria-controls="nav-assistant-panel" onClick={()=>setOpen(!open)}>✦ 智能助手</button>
    {open && <div id="nav-assistant-panel" className="nav-assistant-panel" role="region" aria-label="智能导航助手">
      <div className="nav-assistant-heading"><div><strong>有什么可以帮你？</strong><p>告诉我想做什么，我帮你找到入口。</p></div><button className="nav-assistant-close" aria-label="关闭智能助手" type="button" onClick={()=>setOpen(false)}>×</button></div>
      <form onSubmit={e=>{e.preventDefault();void search();}}><label htmlFor="nav-assistant-input">你想去哪里</label><textarea id="nav-assistant-input" maxLength={200} disabled={busy} value={text} onChange={e=>{setText(e.target.value);setResult(null);setMessage('');}} placeholder="例如：查看待审核的方案" /><div className="nav-assistant-actions"><button type="submit" disabled={busy || !text.trim()}>{busy?'查找中…':'搜索'}</button></div></form>
      <p className="nav-assistant-hint">本地未匹配时，输入文字会发送给 DeepSeek，可能产生费用；请勿输入密码、密钥或敏感资料。</p>
      {message && <p className="nav-assistant-message" role="status">{message}</p>}
      {result && result.intent!=='unknown' && !target && <button className="nav-assistant-result" type="button" onClick={()=>go(result.intent)}>前往：{labels[result.intent]} →</button>}
      {target && candidates.length===0 && <p className="nav-assistant-hint">{result?.project_hint?'没有找到有权访问的匹配项目。':'暂无可访问的项目，请先创建或加入项目。'}</p>}
      {target && candidates.map(p=><button key={p.id} className="nav-assistant-result" type="button" onClick={()=>go(result!.intent==='projects'?'materials':result!.intent,p.id)}><span>{p.name}{p.state==='archived'?'（已归档）':''}</span><span>{projectSearch?'进入项目':labels[result!.intent]} →</span></button>)}
      {target && !result?.project_hint && !allProjects && candidates.length===1 && current && eligible.length>1 && <button className="nav-assistant-other" type="button" onClick={()=>setAllProjects(true)}>选择其他项目</button>}
    </div>}
  </div>;
}
