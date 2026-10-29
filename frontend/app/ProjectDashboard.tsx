'use client';
import RequiredMark from './RequiredMark';
import { useEffect, useState } from 'react';

type Project = {id:string; name:string; role:string; state:string};
type Todo = {pending_requirements:number; pending_reviews:number; needs_review:number; unknown_reviews:number};
type Props = {projects:Project[]; onOpen:(id:string)=>void; name:string; onName:(name:string)=>void; onCreate:()=>void; busy:boolean};

export default function ProjectDashboard({projects,onOpen,name,onName,onCreate,busy}:Props) {
  const [todos,setTodos] = useState<Record<string,Todo | null>>({});
  const [creating,setCreating] = useState(false);
  useEffect(()=>{const open=()=>{setCreating(true);setTimeout(()=>document.getElementById('dashboard-project-name')?.focus(),0);};window.addEventListener('qishu:create-project',open);return ()=>window.removeEventListener('qishu:create-project',open);},[]);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(projects.filter(p => p.state !== 'trash').map(async p => {
      try {
        const response = await fetch(`/api/v1/projects/${encodeURIComponent(p.id)}/todo`, {signal:controller.signal});
        return [p.id, response.ok ? await response.json() as Todo : null] as const;
      } catch { return [p.id, null] as const; }
    })).then(entries => { if (!controller.signal.aborted) setTodos(Object.fromEntries(entries)); });
    return () => controller.abort();
  },[projects]);
  return <section className="project-dashboard" aria-label="管理员项目首页">
    <div className="dashboard-intro"><div><span className="eyebrow">YOUR WORKSPACE</span><h2>我的项目 <button type="button" className="add-project-icon" aria-label="新建项目" aria-expanded={creating} onClick={()=>setCreating(!creating)}>＋</button></h2><p>选择一个项目，继续你的工作。</p></div></div>
    {creating && <div className="dashboard-create"><label htmlFor="dashboard-project-name"><RequiredMark />项目名称</label><div><input aria-required="true" id="dashboard-project-name" value={name} onChange={e=>onName(e.target.value)} placeholder="输入项目名称" /><button type="button" disabled={busy || !name.trim()} onClick={onCreate}>创建项目</button><button type="button" className="secondary" onClick={()=>setCreating(false)}>取消</button></div></div>}
    <div className="dashboard-heading"><h3>已有项目</h3><span>{projects.filter(p=>p.state!=='trash').length} 个项目</span></div>
    {projects.filter(p=>p.state!=='trash').length === 0 ? <p>还没有项目，可以从上方创建一个。</p> : <div className="dashboard-grid">{projects.filter(p=>p.state!=='trash').map(p=> {
      const todo = todos[p.id];
      return <article className="project-card" key={p.id}><div className="project-card-top"><span>{p.role==='owner'?'负责人':'成员'}</span><span>{p.state==='archived'?'已归档':'进行中'}</span></div><h4>{p.name}</h4>
        {todo === undefined ? <p>正在读取项目进度…</p> : todo === null ? <p>项目进度暂时无法读取，请进入项目查看。</p> : <div className="project-todos"><span>待确认需求 <strong>{todo.pending_requirements}</strong></span><span>待审核方案 <strong>{todo.pending_reviews}</strong></span>{todo.needs_review > 0 && <span>需重新核对 <strong>{todo.needs_review}</strong></span>}{todo.unknown_reviews > 0 && <span>审核状态待核实 <strong>{todo.unknown_reviews}</strong></span>}</div>}
        <button type="button" className="secondary" onClick={()=>onOpen(p.id)}>进入项目 →</button></article>;
    })}</div>}
  </section>;
}
