'use client';
import RequiredMark from './RequiredMark';
import ProjectActivity from './ProjectActivity';
import { useCallback, useEffect, useState } from 'react';

type User = { id:string; username:string; active:boolean; is_admin:boolean };
type Project = { id:string; name:string; role:string; state:string; state_version:number };
type Member = { user_id:string; username:string; active:boolean; role:string };
type Job = { id:string; kind:string; target_id:string; status:string; can_cancel:boolean };
type Usage = {actor_name:string;calls:number;known_prompt_tokens:number;known_completion_tokens:number;usage_complete:boolean;estimated_cost_usd:number|null};
type TrashItem = { project_id:string; name:string; materials:number; requirements:number; proposals:number };
type Handoff = {project_id:string;name:string;previous_owner:string;candidates:Member[]};
type LegacyProject = {project_id:string;name:string};

async function request<T>(path:string, method='GET', body?:object):Promise<T> {
  const response = await fetch('/api/v1' + path, { method, ...(body ? {headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {}) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.error?.message || '操作失败，请重试。'); }
  return response.status === 204 ? undefined as T : response.json();
}

export default function CollaborationPanel({project, projects, onChange, view}:{project:string; projects:Project[]; onChange:()=>Promise<void>; view:'workspace'|'project'|'none'}) {
  const [me,setMe]=useState<User|null>(null);
  const [users,setUsers]=useState<User[]>([]);
  const [members,setMembers]=useState<Member[]>([]);
  const [jobs,setJobs]=useState<Job[]>([]);
  const [usage,setUsage]=useState<Usage[]>([]);
  const [backups,setBackups]=useState<{id:string}[]>([]);
  const [trash,setTrash]=useState<TrashItem[]>([]);
  const [handoffs,setHandoffs]=useState<Handoff[]>([]);
  const [handoffChoices,setHandoffChoices]=useState<Record<string,string>>({});
  const [legacy,setLegacy]=useState<LegacyProject[]>([]);
  const [legacyChoices,setLegacyChoices]=useState<Record<string,string>>({});
  const [pendingPurges,setPendingPurges]=useState<{id:string;status:string}[]>([]);
  const [selected,setSelected]=useState('');
  const [name,setName]=useState('');
  const [password,setPassword]=useState('');
  const [resetUser,setResetUser]=useState('');
  const [resetPassword,setResetPassword]=useState('');
  const [limit,setLimit]=useState('');
  const [modelNames,setModelNames]=useState('');
  const [requestLimit,setRequestLimit]=useState('50');
  const [keyReady,setKeyReady]=useState(false);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const current=projects.find(p=>p.id===project);
  const refresh=useCallback(async()=>{
    const identity=await request<User>('/auth/me'); setMe(identity);
    setUsers(await request<User[]>(identity.is_admin?'/accounts':'/directory'));
    if(identity.is_admin){ const value=await request<{max_running:number|null}>('/queue/settings'); setLimit(value.max_running?.toString() || ''); const settings=await request<{allowed_models:string[];max_requests:number;key_configured:boolean}>('/admin/model-settings');setModelNames(settings.allowed_models.join('\n'));setRequestLimit(String(settings.max_requests));setKeyReady(settings.key_configured);setBackups(await request<{id:string}[]>('/admin/backups')); setTrash(await request<TrashItem[]>('/admin/trash')); setHandoffs(await request<Handoff[]>('/admin/handoffs')); setLegacy(await request<LegacyProject[]>('/admin/legacy-projects')); setPendingPurges(await request<{id:string;status:string}[]>('/admin/purges')); }
    if(project && current?.state !== 'trash') {
      const [m,j,u]=await Promise.all([request<Member[]>(`/projects/${project}/members`),request<Job[]>(`/projects/${project}/queue`),request<Usage[]>(`/projects/${project}/usage`)]);
      setMembers(m); setJobs(j); setUsage(u);
    } else { setMembers([]); setJobs([]); setUsage([]); }
  },[project,current?.state]);
  useEffect(()=>{ Promise.resolve().then(refresh).catch(()=>{}); },[refresh]);
  useEffect(()=>{
    if(!project || !jobs.some(j=>['queued','running','cancel_requested'].includes(j.status))) return;
    const timer=setTimeout(()=>Promise.all([request<Job[]>(`/projects/${project}/queue`),request<Usage[]>(`/projects/${project}/usage`)]).then(([j,u])=>{setJobs(j);setUsage(u);}).catch(()=>{}),2000);
    return ()=>clearTimeout(timer);
  },[jobs,project]);
  async function act(fn:()=>Promise<unknown>, success:string, refreshNow=true){setBusy(true);setMessage('');try{await fn();await onChange();if(refreshNow) await refresh();setMessage(success);}catch(e){setMessage(e instanceof Error?e.message:'操作失败。');try{await onChange();await refresh();}catch{ /* 保留原错误，等待下次刷新。 */ }}finally{setBusy(false);}}
  if(!me || view==='none') return null;
  return <section className="management-page"><h2>{view==='workspace'?'工作台设置':'项目设置'}</h2><p>{view==='workspace'?'管理工作台账号、模型和备份。':`当前项目：${current?.name || '未选择'}。项目成员共享本项目的资料和方案。`}</p>
    {message && <p role="status">{message}</p>}
    {view==='workspace' && me.is_admin && <details open><summary>账号和任务设置</summary>
      <label><RequiredMark />新账号<input aria-required="true" value={name} onChange={e=>setName(e.target.value)} maxLength={100}/></label>
      <label><RequiredMark />初始密码（至少 12 个字符）<input aria-required="true" type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="new-password"/></label>
      <button disabled={busy || !name.trim() || password.length<12} onClick={()=>act(async()=>{await request('/accounts','POST',{username:name,password});setName('');setPassword('');},'账号已创建。')}>创建账号</button>
      <ul>{users.map(u=><li key={u.id}>{u.username} · {u.active?'已启用':'已停用'} {u.is_admin?'· 管理员':''} <button className="secondary" disabled={busy || u.id===me.id} onClick={()=>{if(window.confirm(`确认${u.active?'停用':'启用'} ${u.username}？`)) void act(()=>request(`/accounts/${u.id}/${u.active?'disable':'enable'}`,'POST'),'账号状态已更新。');}}>{u.active?'停用':'启用'}</button></li>)}</ul>
      <label><RequiredMark />需要重设密码的账号<select aria-required="true" value={resetUser} onChange={e=>setResetUser(e.target.value)}><option value="">请选择</option>{users.map(u=><option key={u.id} value={u.id}>{u.username}</option>)}</select></label><label><RequiredMark />新密码（至少 12 个字符）<input aria-required="true" type="password" autoComplete="new-password" value={resetPassword} onChange={e=>setResetPassword(e.target.value)}/></label><button className="secondary" disabled={busy || !resetUser || resetPassword.length<12} onClick={()=>{if(window.confirm('确认重设密码并让该账号重新登录？')) void act(async()=>{try{await request(`/accounts/${resetUser}/password`,'POST',{password:resetPassword});}finally{setResetPassword('');}},'密码已重设，旧会话已退出。');}}>重设密码</button>
      <h3>待交接项目</h3>{handoffs.length===0?<p>没有负责人停用的项目。</p>:handoffs.map(h=><div key={h.project_id}><p>{h.name}：原负责人 {h.previous_owner} 已停用。选择的账号将获得项目访问权。</p><label><RequiredMark />接任账号<select aria-required="true" value={handoffChoices[h.project_id]||''} onChange={e=>setHandoffChoices({...handoffChoices,[h.project_id]:e.target.value})}><option value="">请选择</option>{h.candidates.map(m=><option key={m.user_id} value={m.user_id}>{m.username}</option>)}</select></label><button className="secondary" disabled={busy || !handoffChoices[h.project_id]} onClick={()=>{const reason=window.prompt('请填写调整负责人原因（必填）');if(reason?.trim() && window.confirm('确认调整负责人并授予项目访问权？')) void act(()=>request(`/admin/projects/${h.project_id}/handoff`,'POST',{user_id:handoffChoices[h.project_id],reason}),'负责人已调整。');}}>调整负责人</button>{h.candidates.length===0 && <p>暂无已启用账号。</p>}</div>)}
      <h3>待分配的旧项目</h3><p>本机旧项目不会自动归属于新账号。分配后，选中的账号将获得项目资料访问权；旧操作记录仍保留原有身份。</p>{legacy.length===0?<p>没有待分配的旧项目。</p>:legacy.map(p=><div key={p.project_id}><p>{p.name}</p><label><RequiredMark />项目负责人<select aria-required="true" value={legacyChoices[p.project_id]||''} onChange={e=>setLegacyChoices({...legacyChoices,[p.project_id]:e.target.value})}><option value="">请选择</option>{users.filter(u=>u.active).map(u=><option key={u.id} value={u.id}>{u.username}</option>)}</select></label><button className="secondary" disabled={busy || !legacyChoices[p.project_id]} onClick={()=>{const reason=window.prompt('请填写分配原因（必填）');if(reason?.trim() && window.confirm('确认分配旧项目并授予该账号访问权？')) void act(()=>request(`/admin/projects/${p.project_id}/assign`,'POST',{user_id:legacyChoices[p.project_id],reason}),'旧项目已分配。');}}>分配项目</button></div>)}
      <label>同时运行的任务上限（留空表示不设上限）<input type="number" min="1" max="1000" value={limit} onChange={e=>setLimit(e.target.value)}/></label><button disabled={busy} onClick={()=>act(()=>request('/queue/settings','PUT',{max_running:limit?Number(limit):null}),'任务设置已保存。')}>保存任务设置</button>
      <h3>模型设置</h3><p>模型密钥{keyReady?'已配置':'尚未配置'}，由服务端配置，不在网页输入。</p><label><RequiredMark />允许使用的 DeepSeek 型号，每行一个<textarea aria-required="true" value={modelNames} onChange={e=>setModelNames(e.target.value)}/></label><label><RequiredMark />每个任务最多请求次数（包含重试）<input aria-required="true" type="number" min="1" max="1000" value={requestLimit} onChange={e=>setRequestLimit(e.target.value)}/></label><button disabled={busy || !modelNames.trim() || !requestLimit} onClick={()=>act(()=>request('/admin/model-settings','PUT',{allowed_models:modelNames.split('\n').map(x=>x.trim()).filter(Boolean),max_requests:Number(requestLimit)}),'模型设置已保存。')}>保存模型设置</button>
      <h3>本机备份</h3><p>备份包括项目数据库和资料原件，不包括密钥。恢复会创建独立副本，不覆盖当前数据。</p><button disabled={busy} onClick={()=>act(()=>request('/admin/backups','POST'),'备份已创建并校验。')}>创建备份</button>
      {backups.map((backup,index)=><p key={backup.id}>备份 {index+1} <button className="secondary" disabled={busy} onClick={()=>act(async()=>{const copy=await request<{id:string}>(`/admin/backups/${backup.id}/restore-copy`,'POST'); return copy;},'备份已恢复到独立目录，当前工作区未改变。')}>恢复为副本</button></p>)}
      <h3>管理员清理回收站</h3><p>清理会删除项目及其原件，无法从回收站恢复；系统会先创建一份本机备份，该备份仍保留数据。</p>{trash.length===0?<p>没有可清理的项目。</p>:trash.map(item=><p key={item.project_id}>{item.name}：{item.materials} 份资料、{item.requirements} 条需求、{item.proposals} 份方案 <button className="secondary" disabled={busy} onClick={()=>{const confirmed=window.prompt(`将清理“${item.name}”及其数据。备份仍会保留数据。请完整输入项目名称以确认（必填）。`);if(confirmed===item.name && window.confirm('确认清理？此操作不可通过回收站撤销。')) void act(async()=>{const result=await request<{status:string}>(`/admin/projects/${item.project_id}/purge`,'POST',{confirmed_name:confirmed,confirm:true});if(result.status!=='completed') throw new Error('数据库已清理，但部分原件清理待重试；请检查本机存储。');},'项目已清理，清理前备份已保留。');}}>永久清理</button></p>)}
      {pendingPurges.map(job=><p key={job.id}>有一项已确认的原件清理尚未完成。<button className="secondary" disabled={busy} onClick={()=>act(async()=>{const result=await request<{status:string}>(`/admin/purges/${job.id}/retry`,'POST');if(result.status!=='completed') throw new Error('原件清理仍未完成，请检查本机存储。');},'原件清理已完成。')}>重试清理</button></p>)}
    </details>}
    {view==='project' && current && current.state!=='trash' && <details open><summary>项目成员与状态</summary>
      <p>我的角色：{current.role==='owner'?'负责人':'成员'}；项目状态：{current.state==='archived'?'已归档':'进行中'}</p>
      <ul>{members.map(m=><li key={m.user_id}>{m.username} · {m.role==='owner'?'负责人':'成员'}{!m.active?' · 已停用':''}{current.role==='owner' && m.role==='member' && <button className="secondary" disabled={busy} onClick={()=>{if(window.confirm(`确认移除 ${m.username}？`)) void act(()=>request(`/projects/${project}/members/${m.user_id}`,'DELETE'),'成员已移除。');}}>移除</button>}</li>)}</ul>
      {current.role==='owner' && current.state==='active' && <><label><RequiredMark />选择账号<select aria-required="true" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">请选择</option>{users.filter(u=>u.active).map(u=><option value={u.id} key={u.id}>{u.username}</option>)}</select></label><button disabled={!selected || busy} onClick={()=>act(()=>request(`/projects/${project}/members`,'POST',{user_id:selected}),'成员已添加。')}>添加成员</button> <button disabled={!selected || busy} className="secondary" onClick={()=>{const reason=window.prompt('请填写负责人转交原因（必填）');if(reason?.trim() && window.confirm('确认转交负责人？')) void act(()=>request(`/projects/${project}/transfer`,'POST',{user_id:selected,reason}),'负责人已转交。');}}>转交负责人</button></>}
      {current.role==='owner' && <p><button disabled={busy} className="secondary" onClick={()=>act(()=>request(`/projects/${project}/${current.state==='active'?'archive':'unarchive'}`,'POST',{version:current.state_version}),current.state==='active'?'项目已归档。':'项目已恢复。',false)}>{current.state==='active'?'归档项目':'取消归档'}</button> <button disabled={busy} className="secondary" onClick={()=>{if(window.confirm('确认将项目移入回收站？项目可以恢复。')) void act(()=>request(`/projects/${project}/trash`,'POST',{version:current.state_version,confirm:true}),'项目已移入回收站。',false);}}>移入回收站</button></p>}
      <h3>任务队列</h3>{jobs.length===0?<p>暂无任务。</p>:<ul>{jobs.map(j=><li key={j.id}>{j.kind==='requirements'?'需求整理':j.kind==='section_edit'?'章节修改':j.kind==='consistency'?'方案内容检查':'方案生成'} · {({queued:'等待中',running:'运行中',cancel_requested:'正在取消',completed:'已完成',failed:'失败',interrupted:'中断',cancelled:'已取消'} as Record<string,string>)[j.status] || j.status}{j.can_cancel && <button className="secondary" disabled={busy} onClick={()=>{if(j.status==='queued' || window.confirm('已发出的模型请求可能产生费用；取消后不会采用迟到的结果。确认取消？')) void act(()=>request(`/projects/${project}/queue/${j.id}/cancel`,'POST'),j.status==='queued'?'任务已取消。':'已请求取消，请等待当前请求结束。');}}>取消任务</button>}</li>)}</ul>}
      <h3>项目用量</h3><p>按任务实际发起人汇总；金额为估算而非账单，缺少价格或用量时显示未知。</p>{usage.length===0?<p>暂无模型调用记录。</p>:<ul>{usage.map((u,i)=><li key={`${u.actor_name}-${i}`}>{u.actor_name}：{u.calls} 次请求，已知输入 {u.known_prompt_tokens}、输出 {u.known_completion_tokens} tokens；{u.usage_complete?'用量完整':'用量不完整'}；估算费用 {u.estimated_cost_usd===null?'未知':`$${u.estimated_cost_usd.toFixed(6)}`}</li>)}</ul>}
    </details>}
    {view==='project' && project && <ProjectActivity projectId={project} />}
    {view==='workspace' && projects.some(p=>p.state==='trash' && p.role==='owner') && <details><summary>回收站</summary>{projects.filter(p=>p.state==='trash' && p.role==='owner').map(p=><p key={p.id}>{p.name} <button className="secondary" disabled={busy} onClick={()=>act(()=>request(`/projects/${p.id}/restore`,'POST',{version:p.state_version}),'项目已恢复。')}>恢复</button></p>)}</details>}
    {view==='workspace' && !me.is_admin && !projects.some(p=>p.state==='trash' && p.role==='owner') && <p>目前没有可管理的工作台事项。</p>}
  </section>;
}
