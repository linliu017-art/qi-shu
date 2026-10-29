'use client';
import RequiredMark from './RequiredMark';
import RequirementRevision from './RequirementRevision';
import Worklist from './Worklist';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import ProposalReview from './ProposalReview';
import CollaborationPanel from './CollaborationPanel';
import ProjectDashboard from './ProjectDashboard';
import OutlineEditor, { UsedOutline } from './OutlineEditor';
import NavigationAssistant, { type NavIntent } from './NavigationAssistant';

type Project = { id: string; name: string; background: string; role:string; state:string; state_version:number };
type Material = { id: string; filename: string; display_name: string; text: string; warning: string; characters: number; preview_truncated: boolean; group_id:string; version:number; state:string; state_version:number };
type MaterialPage = { text: string; offset: number; next_offset: number | null; total_characters: number };
type Citation = { material_id: string; quote: string; location?: string };
type Item = { related_sources: Citation[]; id: string; text: string; original_text: string; quote: string; material_id: string; status: string; version: number; origin:string };
type Task = { id: string; status: string; error: string; segments_total: number; segments_completed: number; calls: number; prompt_tokens: number | null; completion_tokens: number | null; usage_complete: boolean; estimated_cost_usd: number | null; model_name: string; elapsed_ms: number | null; requirement_count:number; fact_count:number; question_count:number };
type Question = { related_sources: Citation[]; id: string; text: string; material_id: string; quote: string; status: string; answer: string; version:number };
type Fact = { id: string; text: string; material_id: string; quote: string; related_sources: Citation[]; review_status: 'pending' | 'reviewed'; review_version: number };
type Config = { model_ready: boolean; allowed_models: string[]; max_requests: number; max_output_tokens: number };
type Baseline = { id: string; requirements: Item[]; questions: Question[]; facts: Fact[]; facts_snapshot_available: boolean };
type Category = 'requirements' | 'facts' | 'questions';
type History = { old_text: string; new_text: string; old_status: string; new_status: string; created_at: string; actor_name:string };
type Proposal = { id: string; baseline_id: string; template_id: string; status: string; content: string; error: string; version: number; calls: number; prompt_tokens: number | null; completion_tokens: number | null; elapsed_ms: number | null; model_name: string; created_at: string };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch('/api/v1' + path, init);
  const value = await r.json();
  if (!r.ok) throw new Error(value.error?.message || '操作失败，请重试。');
  return value as T;
}
const json = (value: object): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
function proposalLabel(p: Proposal, index: number, count: number) {
  const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(p.created_at) ? p.created_at : `${p.created_at}Z`;
  const date = new Date(timestamp);
  const time = Number.isNaN(date.getTime()) ? '时间未知' : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date);
  const status = ({pending:'等待中',running:'生成中',completed:'已生成',failed:'生成失败',interrupted:'已中断',cancelled:'已取消'} as Record<string,string>)[p.status] || p.status;
  return `初稿 ${count - index} · ${time} · ${status}${index === 0 ? ' · 最新' : ''}`;
}

export default function Home() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [hasIdentity, setHasIdentity] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [sidebarCreating, setSidebarCreating] = useState(false);
  const [showWorklist, setShowWorklist] = useState(false);
  const [worklistFilter, setWorklistFilter] = useState('');
  const [managementView, setManagementView] = useState<'none'|'workspace'|'project'>('none');
  const [step, setStep] = useState(1);
  const stepTitles = ['选择项目和资料', '整理并确认需求', '生成方案', '审核与导出'];
  function selectProject(id: string) {
    setProject(id);
    try {
      if (id) localStorage.setItem('qishu:last-project', id); else localStorage.removeItem('qishu:last-project');
      const saved = Number(localStorage.getItem(`qishu:step:${id}`));
      setStep(id && saved >= 1 && saved <= 4 ? saved : 1);
    } catch { setStep(1); }
  }
  function openFromDashboard(id: string) {
    if ((Object.keys(drafts).length > 0 || Object.keys(questionDrafts).length > 0 || paste.trim() || manualRequirement.trim() || manualQuote.trim() || manualSource || reviewDirty || outlineDirty) && !window.confirm('有未保存的输入，切换项目会清空。确认切换？')) return false;
    if (id !== project) { setMaterials([]); setItems([]); setBaselines([]); setQuestions([]); setFacts([]); setSelected([]); setProposals([]); setTask(null); }
    setPreferredTaskId(''); setCategory('requirements'); setChosen({ requirements: '', facts: '', questions: '' }); setDrafts({}); setQuestionDrafts({}); setProposalId(''); setReviewDirty(false); setBaselineId(''); setOutlineChoice(null); setOutlineDirty(false); setHistories({}); setPages({}); setPaste(''); setManualRequirement(''); setManualSource(''); setManualQuote(''); setTemplateId('demo-v1'); setCaseIds([]);
    selectProject(id); setStep(1); setManagementView('none'); setShowDashboard(false); setShowWorklist(false);
    return true;
  }
  function showProjects() {
    if ((Object.keys(drafts).length > 0 || Object.keys(questionDrafts).length > 0 || paste.trim() || manualRequirement.trim() || manualQuote.trim() || manualSource || reviewDirty || outlineDirty) && !window.confirm('有未保存的输入，返回项目首页可能丢失。确认返回？')) return;
    void reloadProjects().catch(showError); setManagementView('none'); setShowWorklist(false); setShowDashboard(isAdmin);
    window.scrollTo({top:0, behavior:'smooth'});
  }
  function openManagement(view:'workspace'|'project') {
    if (managementView === 'none' && (Object.keys(drafts).length > 0 || Object.keys(questionDrafts).length > 0 || paste.trim() || manualRequirement.trim() || manualQuote.trim() || manualSource || reviewDirty || outlineDirty) && !window.confirm('有未保存的输入，离开当前工作区可能丢失。确认继续？')) return;
    setShowWorklist(false); setManagementView(view); window.scrollTo({top:0, behavior:'smooth'});
  }
  function goStep(next: number) {
    setStep(next); setMessage('');
    try { if (project) localStorage.setItem(`qishu:step:${project}`, String(next)); } catch {}
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  function assistantNavigate(intent:NavIntent, target?:string):boolean {
    const dirty=Object.keys(drafts).length>0 || Object.keys(questionDrafts).length>0 || !!paste.trim() || !!manualRequirement.trim() || !!manualQuote.trim() || !!manualSource || reviewDirty || outlineDirty;
    if (intent==='projects' || intent==='new_project' || intent==='worklist' || intent==='review_todos' || intent==='workspace_settings') {
      if (dirty && !window.confirm('有未保存的输入，离开当前工作区可能丢失。确认继续？')) return false;
      setManagementView(intent==='workspace_settings'?'workspace':'none');
      setShowWorklist(intent==='worklist'||intent==='review_todos');
      setWorklistFilter(intent==='review_todos'?'review':'');
      setShowDashboard((intent==='projects'||intent==='new_project') && isAdmin);
      if ((intent==='projects'||intent==='new_project') && !isAdmin) setStep(1);
      if (intent==='new_project') { if (!isAdmin && project) setSidebarCreating(true); setTimeout(()=>{if(isAdmin) window.dispatchEvent(new Event('qishu:create-project')); else document.getElementById(project?'sidebar-project-name':'new-project-name')?.focus();},100); }
      window.scrollTo({top:0,behavior:'smooth'}); return true;
    }
    if (!target || !projects.some(p=>p.id===target && p.state!=='trash')) {setMessage('找不到有权访问的项目，请刷新后重试。');return false;}
    if (intent==='project_settings' && target===project && dirty && !window.confirm('有未保存的输入，离开当前工作区可能丢失。确认继续？'))return false;
    if (target!==project && !openFromDashboard(target)) return false;
    if (target===project) { setShowDashboard(false);setShowWorklist(false);setManagementView('none'); }
    if (intent==='project_settings') {
      setManagementView('project');return true;
    }
    const next=({materials:1,requirements:2,proposal:3,review:4} as Partial<Record<NavIntent,number>>)[intent];
    if(!next)return false;
    setStep(next);try{localStorage.setItem(`qishu:step:${target}`,String(next));}catch{}window.scrollTo({top:0,behavior:'smooth'});return true;
  }
  const [name, setName] = useState('');
  const [materials, setMaterials] = useState<Material[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [task, setTask] = useState<Task | null>(null);
  const [preferredTaskId, setPreferredTaskId] = useState('');
  const [baselines, setBaselines] = useState<Baseline[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [category, setCategory] = useState<Category>('requirements');
  const [chosen, setChosen] = useState<Record<Category, string>>({ requirements: '', facts: '', questions: '' });
  const [pages, setPages] = useState<Record<string, {text: string; next: number | null}>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [questionDrafts, setQuestionDrafts] = useState<Record<string, string>>({});
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [proposalId, setProposalId] = useState('');
  const [reviewDirty, setReviewDirty] = useState(false);
  const [, setReviewStatus] = useState('draft');
  function selectProposal(id: string) {
    if (reviewDirty && !window.confirm('审核内容还没提交，切换方案会丢失这些内容。确认切换？')) return;
    setReviewDirty(false); setProposalId(id);
  }
  const [baselineId, setBaselineId] = useState('');
  const [outlineChoice, setOutlineChoice] = useState<{id:string;baselineId:string}|null>(null);
  const [outlineDirty, setOutlineDirty] = useState(false);
  const [includeExample, setIncludeExample] = useState(false);
  const [templateId, setTemplateId] = useState('demo-v1');
  const [caseIds, setCaseIds] = useState<string[]>([]);
  const [histories, setHistories] = useState<Record<string, History[]>>({});
  const [config, setConfig] = useState<Config | null>(null);
  const [model, setModel] = useState('deepseek-flash');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [paste, setPaste] = useState('');
  const [manualRequirement, setManualRequirement] = useState('');
  const [manualSource, setManualSource] = useState('');
  const [manualQuote, setManualQuote] = useState('');
  useEffect(() => {
    const openSettings = () => { assistantNavigate('workspace_settings'); };
    window.addEventListener('qishu:workspace-settings', openSettings);
    return () => window.removeEventListener('qishu:workspace-settings', openSettings);
  });
  const showError = (e: unknown) => setMessage(e instanceof Error ? e.message : '操作失败，请重试。');
  async function reloadProjects() { setProjects(await api<Project[]>('/projects')); }
  async function reloadProject(id: string) {
    const [m, r, b, q, f] = await Promise.all([api<Material[]>(`/projects/${id}/materials`), api<Item[]>(`/projects/${id}/requirements`), api<Baseline[]>(`/projects/${id}/baselines`), api<Question[]>(`/projects/${id}/questions`), api<Fact[]>(`/projects/${id}/facts`)]);
    setMaterials(m); setItems(r); setBaselines(b); setQuestions(q); setFacts(f);
  }
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedProject = query.get('step') === '4' ? query.get('project') : null;
    const requestedProposal = requestedProject ? query.get('proposal') : null;
    fetch('/api/v1/auth/me').then(async response => response.ok ? response.json() : null).then(identity => {
      if (identity) setHasIdentity(true);
      if (query.get('view') === 'workspace-settings') setManagementView('workspace');
      if (identity?.is_admin) { setIsAdmin(true); if (!requestedProject) setShowDashboard(true); }
    }).catch(() => {});
    api<Project[]>('/projects').then(list => {
      setProjects(list);
      if (requestedProject) {
        if (list.some(p => p.id === requestedProject)) {
          selectProject(requestedProject); setStep(4); setProposalId(requestedProposal || '');
          try { localStorage.setItem(`qishu:step:${requestedProject}`, '4'); } catch {}
        } else setMessage('找不到这个项目，请重新选择。');
        window.history.replaceState(null, '', window.location.pathname);
      } else {
        try { const id = localStorage.getItem('qishu:last-project'); if (id && list.some(p => p.id === id)) selectProject(id); } catch {}
      }
    }).catch(showError);
    api<Config>('/config').then(c => { setConfig(c); if (c.allowed_models.length) setModel(c.allowed_models[0]); }).catch(showError);
  }, []);
  useEffect(() => {
    if (!project) return;
    let current = true;
    Promise.all([api<Material[]>(`/projects/${project}/materials`), api<Item[]>(`/projects/${project}/requirements`), api<Baseline[]>(`/projects/${project}/baselines`), api<Question[]>(`/projects/${project}/questions`), api<Fact[]>(`/projects/${project}/facts`), api<Task[]>(`/projects/${project}/requirement-tasks`), api<Proposal[]>(`/projects/${project}/proposals`)])
      .then(([m, r, b, q, f, tasks, drafts]) => { if (!current) return; setMaterials(m); setItems(r); setBaselines(b); setQuestions(q); setFacts(f); setSelected(m.filter(x => x.state !== "withdrawn" && !m.some(other => other.group_id === x.group_id && other.state !== "withdrawn" && other.version > x.version)).map(x => x.id)); setTask(tasks.find(t=>t.id===preferredTaskId) || tasks[0] || null); setProposals(drafts); }).catch(e => { if (current) showError(e); });
    return () => { current = false; };
  }, [project, preferredTaskId]);
  useEffect(() => {
    if (!project || reviewDirty) return;
    const refresh = () => api<Proposal[]>(`/projects/${project}/proposals`).then(setProposals).catch(showError);
    window.addEventListener('focus', refresh);
    return () => window.removeEventListener('focus', refresh);
  }, [project, reviewDirty]);
  useEffect(() => {
    if (!project || !proposals.some(p => ['pending', 'running'].includes(p.status))) return;
    const t = setTimeout(() => api<Proposal[]>(`/projects/${project}/proposals`).then(setProposals).catch(showError), 1500);
    return () => clearTimeout(t);
  }, [project, proposals]);
  useEffect(() => {
    if (!task || !['pending', 'running'].includes(task.status) || !project) return;
    const t = setTimeout(() => api<Task>(`/projects/${project}/requirement-tasks/${task.id}`).then(next => {
      setTask(next); if (['completed', 'failed', 'interrupted', 'paused_limit', 'cancelled'].includes(next.status)) reloadProject(project).catch(showError);
    }).catch(showError), 1500);
    return () => clearTimeout(t);
  }, [task, project]);
  function sources(item: {material_id: string; quote: string; location?:string; related_sources: Citation[]}) {
    return <div className="source">{[{ material_id: item.material_id, quote: item.quote, location: item.location }, ...(item.related_sources || [])].map((source, i) => <p key={i}>出处：{materials.find(x => x.id === source.material_id)?.display_name || '资料'}{source.location ? ` · ${source.location}` : ''}<br />“{source.quote}”</p>)}</div>;
  }
  async function create() {
    if ((Object.keys(drafts).length > 0 || Object.keys(questionDrafts).length > 0 || paste.trim() || manualRequirement.trim() || manualQuote.trim() || manualSource || reviewDirty || outlineDirty) && !window.confirm('有未保存的输入，新建项目会清空。确认继续？')) return;
    try { setBusy(true); const p = await api<Project>('/projects', json({ name })); await reloadProjects(); setPreferredTaskId(''); setCategory('requirements'); setChosen({ requirements: '', facts: '', questions: '' }); setDrafts({}); setQuestionDrafts({}); setProposalId(''); setReviewDirty(false); setBaselineId(''); setOutlineChoice(null); setOutlineDirty(false); setProposals([]); setHistories({}); setPages({}); setPaste(''); setManualRequirement(''); setManualSource(''); setManualQuote(''); setTemplateId('demo-v1'); setCaseIds([]); selectProject(p.id); setManagementView('none'); setShowDashboard(false); setName(''); setMessage('项目已创建。'); } catch (e) { showError(e); } finally { setBusy(false); }
  }
  async function upload(file: File, previousId?:string) {
    try {
      setBusy(true);
      const base = `/projects/${project}/materials${previousId ? `/${previousId}/versions` : ''}`;
      const send = async (allowDuplicate:boolean) => { const form = new FormData(); form.append('file', file); return api<Material>(base + (allowDuplicate ? '?allow_duplicate=true' : ''), {method:'POST', body:form}); };
      let m:Material;
      try { m = await send(false); } catch(e) {
        if (!(e instanceof Error) || !e.message.startsWith('本项目已有内容相同的资料') || !window.confirm('本项目已有内容相同的资料。是否仍然添加？取消可继续使用已有资料。')) throw e;
        m = await send(true);
      }
      await reloadProject(project); setSelected(prev => [...prev.filter(id => !previousId || !materials.some(old => old.id === id && old.group_id === m.group_id)), m.id]); setMessage(m.warning || '资料已保存。'); return {ok:true,error:''};
    } catch(e) {showError(e); return {ok:false,error:e instanceof Error ? e.message : '处理失败'};} finally {setBusy(false);}
  }
  async function changeMaterialState(material:Material) {
    try {
      setBusy(true);
      const action = material.state === 'withdrawn' ? 'restore' : 'withdraw';
      if (action === 'withdraw') {
        if (templateId === material.id && outlineDirty && !window.confirm('该资料正被选为模板，提纲有未保存的修改；撤回会丢失这些修改。确认继续？')) return;
        const impact = await api<{requirements:number;baselines:number;proposals:number;active_tasks:number;affected_requirements:string[]}>(`/projects/${project}/materials/${material.id}/impact`);
        if (!window.confirm(`这份资料关联 ${impact.requirements} 条需求、${impact.baselines} 份清单和 ${impact.proposals} 份方案。${impact.affected_requirements.length ? `\n关联需求：\n${impact.affected_requirements.map(x=>`· ${x}`).join('\n')}${impact.requirements > impact.affected_requirements.length ? '\n（其余需求未展开）' : ''}` : ''}\n撤回后不能用于新任务，历史方案需要重新核对。确认撤回？`)) return;
      } else if (!window.confirm('确认恢复这份资料？历史方案仍需重新核对。')) return;
      await api(`/projects/${project}/materials/${material.id}/${action}`, json({state_version:material.state_version,confirm:true}));
      if (action === 'withdraw') {
        setSelected(prev => prev.filter(id => id !== material.id));
        setCaseIds(prev => prev.filter(id => id !== material.id));
        if (templateId === material.id) { setTemplateId('demo-v1'); setOutlineChoice(null); setOutlineDirty(false); }
      }
      await reloadProject(project); setMessage(action === 'withdraw' ? '资料已撤回。' : '资料已恢复。');
    } catch(e) {showError(e);} finally {setBusy(false);}
  }
  async function loadMore(m: Material) {
    const offset = pages[m.id]?.next ?? m.text.length;
    try {
      const page = await api<MaterialPage>(`/projects/${project}/materials/${m.id}/content?offset=${offset}`);
      setPages(prev => ({ ...prev, [m.id]: { text: (prev[m.id]?.text ?? m.text) + page.text, next: page.next_offset } }));
    } catch (e) { showError(e); }
  }
  async function uploadBatch(files: File[]) {
    if (files.length > 10) { setMessage('每次最多选择 10 个文件，请分批添加。'); return; }
    let success = 0;
    const failures: string[] = [];
    for (const file of files) {
      const result = await upload(file);
      if (result.ok) success++; else failures.push(`${file.name}：${result.error}`);
    }
    setMessage(`已保存 ${success}/${files.length} 个文件。${failures.length ? `未完成：${failures.join('；')}` : '请查看每份资料的读取提醒。'}`);
  }
  async function analyse() {
    const names = materials.filter(m => selected.includes(m.id)).map(m => m.display_name || m.filename).join('、');
    if (!window.confirm(`将把以下资料发送给 DeepSeek 进行整理：${names}。模型按用量计费；本任务最多请求 ${config?.max_requests ?? 50} 次，含重试。确认继续吗？`)) return;
    try { setBusy(true); const t = await api<Task>(`/projects/${project}/requirement-tasks`, json({ material_ids: selected, model_name: model, confirm_external_use: true })); setTask(t); setMessage('已提交，正在整理。'); } catch (e) { showError(e); } finally { setBusy(false); }
  }
  async function review(item: Item, status: string, saveDraft = true) {
    try { setBusy(true); await api(`/projects/${project}/requirements/${item.id}`, { ...json({ status, text: saveDraft ? drafts[item.id] ?? item.text : item.text, version: item.version }), method: 'PATCH' }); if (saveDraft) setDrafts(prev => { const next = { ...prev }; delete next[item.id]; return next; }); await reloadProject(project); setMessage(status === 'pending' && item.status === 'confirmed' ? '已撤销确认。已生成的需求清单不会自动改变。' : '处理结果已保存。'); } catch (e) { showError(e); } finally { setBusy(false); }
  }
  async function reviewFact(fact: Fact) {
    const nextStatus = fact.review_status === 'reviewed' ? 'pending' : 'reviewed';
    try {
      setBusy(true);
      await api(`/projects/${project}/facts/${fact.id}/review`, { ...json({ review_status: nextStatus, review_version: fact.review_version }), method: 'PATCH' });
      await reloadProject(project);
      setMessage(nextStatus === 'reviewed' ? '已标记为核对完成。' : '已撤销核对标记。');
    } catch (e) { showError(e); } finally { setBusy(false); }
  }
  async function resume() {
    if (!task) return;
    if (!window.confirm(`继续处理未完成的资料将使用 ${model}，再次发送给 DeepSeek 并产生模型费用。历史调用次数和结果会保留；不同型号费用可能未知。确认继续吗？`)) return;
    try { setBusy(true); const t = await api<Task>(`/projects/${project}/requirement-tasks/${task.id}/resume`, json({ confirm_external_use: true, model_name:model })); setTask(t); setMessage('已继续整理。'); } catch (e) { showError(e); } finally { setBusy(false); }
  }
  async function loadHistory(item: Item) {
    try { const entries = await api<History[]>(`/projects/${project}/requirements/${item.id}/history`); setHistories(prev => ({ ...prev, [item.id]: entries })); } catch (e) { showError(e); }
  }
  async function decideQuestion(question: Question, status: string) {
    try {
      setBusy(true);
      await api(`/projects/${project}/questions/${question.id}`, { ...json({ status, answer: questionDrafts[question.id] ?? question.answer, version: question.version }), method: 'PATCH' });
      setQuestionDrafts(prev => { const next = { ...prev }; delete next[question.id]; return next; });
      await reloadProject(project); setMessage('问题的处理结果已保存。');
    } catch (e) { showError(e); } finally { setBusy(false); }
  }
  async function baseline() {
    try { setBusy(true); const value = await api<{ count: number }>(`/projects/${project}/baselines`, json({})); await reloadProject(project); setMessage(`已生成需求清单，包含 ${value.count} 条已确认需求。`); } catch (e) { showError(e); } finally { setBusy(false); }
  }
  async function generateProposal() {
    const chosenBaseline = baselines.find(b => b.id === (baselineId || baselines[0]?.id));
    if (!chosenBaseline || (outlineChoice && outlineChoice.baselineId !== chosenBaseline.id) || outlineDirty) return;
    if (!window.confirm(`${outlineChoice ? "将把你保存的提纲（包含章节名称、写作要求和计划关联的需求）、" : "将把"}项目名称、所选清单中的 ${chosenBaseline.requirements.length} 条已确认需求、${chosenBaseline.facts.length} 条已核对资料事实、${chosenBaseline.questions.length} 个未解决问题，以及相关资料名称、需求和问题的原文摘录、${templateId === 'demo-v1' ? '虚构示例模板' : `所选模板“${materials.find(m=>m.id===templateId)?.display_name || '资料'}”的全文`}${caseIds.length ? `、所选案例（${caseIds.map(id=>materials.find(m=>m.id===id)?.display_name || '资料').join('、')}）的全文` : ''}${includeExample ? '和虚构参考案例' : ''}发送给 DeepSeek。可在页面查看清单中事实的具体内容；事实的原文、未核对事实和原始资料全文不会作为事实发送；需求和问题的原文摘录可能包含相关上下文。生成会产生模型费用。确认继续吗？`)) return;
    try {
      setBusy(true);
      const p = await api<Proposal>(`/projects/${project}/proposals`, json({ baseline_id: chosenBaseline.id, ...(outlineChoice ? {outline_id: outlineChoice.id} : {}), template_id: templateId, case_ids: caseIds, model_name: model, include_example: includeExample, confirm_external_use: true }));
      setProposals(old => [p, ...old]); setProposalId(p.id); setMessage('已开始生成方案初稿。');
    } catch (e) { showError(e); } finally { setBusy(false); }
  }
  const entries = category === 'requirements' ? items : category === 'facts' ? facts : questions;
  const activeId = entries.some(entry => entry.id === chosen[category]) ? chosen[category] : entries[0]?.id;
  const activeRequirement = category === 'requirements' ? items.find(item => item.id === activeId) : undefined;
  const activeFact = category === 'facts' ? facts.find(item => item.id === activeId) : undefined;
  const activeQuestion = category === 'questions' ? questions.find(item => item.id === activeId) : undefined;
  const activeProposal = proposals.find(p => p.id === proposalId) || proposals[0];
  const isOwner = projects.find(p => p.id === project)?.role !== 'member';
  const statusLabels: Record<string, string> = { pending: '待确认', confirmed: '已确认', rejected: '已驳回', answered: '已答复', resolved: '已解决' };
  const categories: { id: Category; title: string; count: number }[] = [
    { id: 'requirements', title: '需求建议', count: items.length },
    { id: 'facts', title: '资料事实', count: facts.length },
    { id: 'questions', title: '待确认问题', count: questions.length },
  ];
  return <main className="workspace-main">
    <header className="workspace-header"><div className="workspace-brand"><span className="brand-mark">启</span><div><span className="eyebrow">QISHU WORKSPACE</span><h1>启枢 <span>工作台</span></h1></div></div><p>从资料到方案，让协作更清晰。</p></header>
    <NavigationAssistant projects={projects} currentProject={project} onNavigate={assistantNavigate} />
    {hasIdentity && <nav className="workspace-rail" aria-label="工作台导航"><button type="button" aria-label="我的项目" title="我的项目" aria-current={!showWorklist && managementView==='none'?'page':undefined} className={!showWorklist && managementView==='none'?'rail-active':''} onClick={showProjects}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/></svg></button><button type="button" aria-label="我的待办" title="我的待办" aria-current={showWorklist && managementView==='none'?'page':undefined} className={showWorklist && managementView==='none'?'rail-active':''} onClick={()=>{if ((Object.keys(drafts).length || Object.keys(questionDrafts).length || paste.trim() || manualRequirement.trim() || manualQuote.trim() || manualSource || reviewDirty || outlineDirty) && !window.confirm('有未保存内容，离开可能丢失。确认继续？')) return; setManagementView('none');setShowDashboard(false);setWorklistFilter('');setShowWorklist(true);window.scrollTo({top:0,behavior:'smooth'});}}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="3.5" width="16" height="17" rx="3"/><path d="m8.5 12 2.4 2.4 4.7-5"/></svg></button></nav>}
    {hasIdentity && <button type="button" className="secondary product-work-entry" onClick={()=>{if ((Object.keys(drafts).length || Object.keys(questionDrafts).length || paste.trim() || manualRequirement.trim() || manualQuote.trim() || manualSource || reviewDirty || outlineDirty) && !window.confirm('有未保存的内容，离开可能丢失。确认继续？')) return; router.push('/product-work');}}>产品工作</button>}
    {showWorklist && managementView==='none' && <Worklist key={worklistFilter} initialKind={worklistFilter} onOpen={(id,next,target,kind)=>{if(openFromDashboard(id)){setStep(next);if(target && (kind==='review' || kind==='proposal' || kind==='returned'))setProposalId(target);if(target && kind==='analysis')setPreferredTaskId(target);else setPreferredTaskId('');try{localStorage.setItem(`qishu:step:${id}`,String(next));}catch{}}}} />}
    {showDashboard && !showWorklist && managementView==='none' && <ProjectDashboard projects={projects} onOpen={openFromDashboard} name={name} onName={setName} onCreate={()=>void create()} busy={busy} />}
    {managementView!=='none' && <button type="button" className="secondary dashboard-back" onClick={()=>setManagementView('none')}>{managementView==='project'?'← 返回项目':'← 返回工作台'}</button>}
    <CollaborationPanel view={managementView} project={project} projects={projects} onChange={async()=>{const [list,nextConfig]=await Promise.all([api<Project[]>('/projects'),api<Config>('/config')]);setProjects(list);setConfig(nextConfig);if(!nextConfig.allowed_models.includes(model)) setModel(nextConfig.allowed_models[0] || '');if(project && !list.some(p=>p.id===project && p.state!=='trash')) selectProject('');}} />
    <div className={`project-workspace${project?'':' no-project'}`} hidden={showDashboard || showWorklist || managementView!=='none'}>
    {(isAdmin || (hasIdentity && project)) && <div className="project-toolbar">{isAdmin && <button type="button" className="secondary" onClick={showProjects}>← 返回项目首页</button>}{hasIdentity && project && <button type="button" className="secondary" onClick={()=>openManagement('project')}>项目设置</button>}{hasIdentity && project && <button type="button" className="secondary" onClick={()=>{if ((Object.keys(drafts).length || Object.keys(questionDrafts).length || paste.trim() || manualRequirement.trim() || manualQuote.trim() || manualSource || reviewDirty || outlineDirty) && !window.confirm('有未保存的内容，离开可能丢失。确认继续？')) return; router.push('/product-work?project='+encodeURIComponent(project));}}>产品工作</button>}</div>}
    {project && <aside className="project-sidebar"><div className="sidebar-title"><div><span className="eyebrow">YOUR WORKSPACE</span><h2>我的项目</h2></div><button className="add-project-icon" aria-label="新建项目" aria-expanded={sidebarCreating} onClick={()=>setSidebarCreating(!sidebarCreating)}>＋</button></div><p>选择一个项目，继续你的工作。</p>{sidebarCreating && <div className="sidebar-create"><label htmlFor="sidebar-project-name"><RequiredMark />项目名称</label><input id="sidebar-project-name" value={name} onChange={e=>setName(e.target.value)} placeholder="输入项目名称" /><div className="row"><button type="button" disabled={busy || !name.trim()} onClick={()=>void create()}>创建项目</button><button type="button" className="secondary" onClick={()=>setSidebarCreating(false)}>取消</button></div></div>}<div className="sidebar-projects">{projects.filter(p=>p.state!=='trash').map(p=><button type="button" key={p.id} className={`sidebar-project ${p.id===project?'selected':''}`} onClick={()=>{if(p.id!==project)openFromDashboard(p.id);}}><span className="project-monogram">{p.name.slice(0,1)}</span><strong>{p.name}</strong><span>{p.role==='owner'?'负责人':'成员'} · {p.state==='archived'?'已归档':'进行中'}</span></button>)}</div></aside>}
    <div className="workspace-content"><div className="workflow-hero"><span className="eyebrow">PROJECT WORKSPACE</span><h2>{projects.find(p=>p.id===project)?.name || '选择项目，开始工作'}</h2><p>从调研资料到方案交付，把每一步都整理清楚。</p><nav className="workflow-steps" aria-label="工作步骤">{stepTitles.map((title, index) => <button key={title} type="button" className={`workflow-step ${step === index + 1 ? 'is-current' : ''}`} aria-current={step === index + 1 ? 'step' : undefined} disabled={!project && index > 0} onClick={() => goStep(index + 1)}><span className="step-number">{String(index + 1).padStart(2,'0')}</span><span>{title}</span></button>)}</nav></div>
    {project && step !== 1 && <p className="current-project">当前项目：{projects.find(p => p.id === project)?.name || '加载中'}</p>}
    {message && <div className="notice" role="status">{message}</div>}
    <div hidden={step !== 1}><section hidden={!!project}><h2>选择项目</h2>
      <div className="project-row">
        <label className="project-existing">已有项目<select value={project} onChange={e => { if ((Object.keys(drafts).length > 0 || Object.keys(questionDrafts).length > 0 || paste.trim() || manualRequirement.trim() || manualQuote.trim() || manualSource || reviewDirty || outlineDirty) && !window.confirm('有未保存的输入，切换项目会清空。确认切换？')) return; selectProject(e.target.value); setPreferredTaskId(''); setCategory('requirements'); setChosen({ requirements: '', facts: '', questions: '' }); setDrafts({}); setQuestionDrafts({}); setProposalId(''); setReviewDirty(false); setBaselineId(''); setProposals([]); setHistories({}); setPages({}); setPaste(''); setManualRequirement(''); setManualSource(''); setManualQuote(''); setTemplateId('demo-v1'); setCaseIds([]); setTask(null); }}><option value="">请选择</option>{projects.filter(p=>p.state!=='trash').map(p => <option key={p.id} value={p.id}>{p.name}{p.state==='archived'?'（已归档）':''}</option>)}</select></label>
        <div className="project-create"><label htmlFor="new-project-name"><RequiredMark />新建项目</label><div className="project-create-controls"><input aria-required="true" id="new-project-name" value={name} onChange={e => setName(e.target.value)} placeholder="输入项目名称" aria-label="项目名称" /><button disabled={busy || !name.trim()} onClick={create}>新建</button></div></div>
      </div>
    </section>
    {project && <><section><h2>添加调研资料</h2><p>支持 TXT、Markdown、文字版 PDF 和 DOCX；暂不支持识别图片和扫描件。</p><label className="file">选择文件<input type="file" accept=".txt,.md,.pdf,.docx" multiple disabled={busy} onChange={e => { const files = Array.from(e.target.files || []); if (files.length) uploadBatch(files); e.target.value = ''; }} /></label>
      <div className="materials" aria-label="已添加的资料"><div className="materials-heading"><strong>已添加的资料 <span>{materials.length} 份</span></strong>{materials.length > 0 && <span><RequiredMark />整理时至少勾选一份资料</span>}</div>
        {materials.length === 0 ? <p className="materials-empty">还没有添加资料，选择文件后会显示在这里。</p> : materials.map(m => <div key={m.id} className="material"><div className="material-main"><label className="material-select"><input type="checkbox" disabled={m.state === "withdrawn"} checked={selected.includes(m.id)} onChange={e => setSelected(e.target.checked ? [...selected, m.id] : selected.filter(id => id !== m.id))} /><span className="material-name">{m.display_name || m.filename}</span></label><span className="material-added">{m.state === "withdrawn" ? "已撤回" : "已添加"}</span></div><div className="row"><label className="file">上传新版本<input type="file" accept=".txt,.md,.pdf,.docx" disabled={busy || m.state === 'withdrawn'} onChange={e=>{const file=e.target.files?.[0]; if(file) void upload(file,m.id); e.target.value='';}} /></label>{isOwner && <button type="button" className="secondary" disabled={busy} onClick={()=>void changeMaterialState(m)}>{m.state === 'withdrawn' ? '恢复资料' : '撤回资料'}</button>}</div>{m.warning && <p className="material-warning">{m.warning}</p>}{m.filename.toLowerCase().endsWith('.pdf') && <p><a href={`/api/v1/projects/${project}/materials/${m.id}/pdf-preview`} target="_blank" rel="noopener noreferrer">打开 PDF 原件，逐页对照</a></p>}<details><summary>查看读取的文字</summary><pre>{pages[m.id]?.text ?? m.text}</pre>{m.preview_truncated && (pages[m.id] ? pages[m.id].next !== null : true) && <button className="secondary" onClick={() => loadMore(m)}>继续查看文字</button>} <a href={`/api/v1/projects/${project}/materials/${m.id}/original`}>下载原文件</a></details></div>)}
      </div><label><RequiredMark />或粘贴文字（保存文字时必填）<textarea aria-required="true" value={paste} onChange={e => setPaste(e.target.value)} placeholder="在这里粘贴调研资料" /></label><button disabled={busy || !paste.trim()} onClick={async () => { if ((await upload(new File([paste], '粘贴资料.txt', { type: 'text/plain' }))).ok) setPaste(''); }}>保存文字</button><div className="workflow-actions"><button type="button" onClick={() => goStep(2)}>下一步：整理并确认需求</button></div></section></>}</div>
    {project && <><div hidden={step !== 2}><section><h2>整理并确认需求</h2><p>只整理勾选的资料。AI 的结果需要你核对，确认后才会进入需求清单。</p><label><RequiredMark />模型<select aria-required="true" value={model} onChange={e => setModel(e.target.value)}>{config?.allowed_models.map(m => <option key={m} value={m}>{m}</option>)}</select></label><p>{config?.model_ready ? '模型已配置；开始整理会产生调用费用。' : '模型尚未配置，暂时不能整理。'}</p><button disabled={busy || selected.length === 0 || !config?.model_ready} onClick={analyse}>开始整理</button>{task && <div><p>任务状态：{({ completed: '已完成', failed: '未完成', interrupted: '已中断', cancelled: '已取消', paused_limit: '已达调用上限', pending: '等待中', running: '处理中' } as Record<string, string>)[task.status] || task.status}。已处理 {task.segments_completed}/{task.segments_total} 段，调用 {task.calls} 次，已记录模型耗时 {task.elapsed_ms === null ? "未知" : `${(task.elapsed_ms / 1000).toFixed(1)} 秒`}。{task.error}</p><p>输入：{task.prompt_tokens ?? '未知'}，输出：{task.completion_tokens ?? '未知'}；费用{task.estimated_cost_usd !== null ? `峰值费率估算 $${task.estimated_cost_usd}，实际以账单为准` : '未知，部分调用可能未返回用量'}。</p>{['failed','interrupted','paused_limit','cancelled'].includes(task.status) && <button disabled={busy} onClick={resume}>继续未完成部分</button>}</div>}
      {task?.status === 'completed' && task.requirement_count === 0 && task.fact_count === 0 && task.question_count === 0 && <p role="status">本次没有提取出需求、事实或问题。请对照原文核验；空结果不代表资料中没有需要处理的内容。</p>}
      <details><summary>人工新增需求</summary><label><RequiredMark />需求内容<textarea aria-required="true" value={manualRequirement} maxLength={3000} onChange={e=>setManualRequirement(e.target.value)} /></label><details><summary>关联资料原文（选填）</summary><label>选择资料<select value={manualSource} onChange={e=>setManualSource(e.target.value)}><option value="">不关联资料</option>{materials.filter(m=>m.state !== 'withdrawn').map(m=><option key={m.id} value={m.id}>{m.display_name || m.filename}</option>)}</select></label><label>资料中的原文<textarea value={manualQuote} maxLength={3000} onChange={e=>setManualQuote(e.target.value)} placeholder="请粘贴所选资料中的原文" /></label><p>选择资料时需填写原文，系统会检查原文是否存在。</p></details><button type="button" disabled={busy || !manualRequirement.trim() || (!!manualSource !== !!manualQuote.trim())} onClick={async()=>{try{setBusy(true);await api(`/projects/${project}/requirements/manual`,json({text:manualRequirement,material_id:manualSource || null,quote:manualQuote}));setManualRequirement('');setManualSource('');setManualQuote('');await reloadProject(project);setMessage('人工需求已添加，待项目负责人确认。');}catch(e){showError(e);}finally{setBusy(false);}}}>添加需求</button></details>
      <div className="results-heading"><div><h3>整理结果</h3><p>先选一个分类，再点一条查看内容和出处。</p></div></div>
      <div className="results-workspace">
        <aside className="results-list" aria-label="整理结果列表">
          <div className="category-tabs" aria-label="结果分类">
            {categories.map(c => <button key={c.id} type="button" className={`category-tab ${category === c.id ? 'is-active' : ''}`} aria-pressed={category === c.id} onClick={() => { setCategory(c.id); setMessage(''); }}>{c.title}<span>{c.count}</span></button>)}
          </div>
          <div className="list-heading"><strong>{categories.find(c => c.id === category)?.title}</strong><span>{entries.length} 条</span></div>
          <div className="result-entries">
            {entries.length === 0 ? <p className="list-empty">这个分类还没有内容。</p> : entries.map((entry, index) => {
              const status = category === 'facts' ? ((entry as Fact).review_status === 'reviewed' ? '已核对' : '待核对') : statusLabels[(entry as Item | Question).status] || '待确认';
              const hasDraft = category === 'requirements' ? drafts[entry.id] !== undefined && drafts[entry.id] !== entry.text : category === 'questions' ? questionDrafts[entry.id] !== undefined && questionDrafts[entry.id] !== (entry as Question).answer : false;
              return <button type="button" key={entry.id} className={`result-entry ${activeId === entry.id ? 'is-selected' : ''}`} aria-pressed={activeId === entry.id} onClick={() => { setChosen(prev => ({ ...prev, [category]: entry.id })); setMessage(''); }}>
                <span className="entry-index">{String(index + 1).padStart(2, '0')}</span><span className="entry-body"><span className="entry-title">{entry.text}</span><span className="entry-meta">{status}{hasDraft ? ' · 有未保存修改' : ''}</span></span>
              </button>;
            })}
          </div>
        </aside>
        <div className="result-detail" aria-label="当前结果详情">
          {!activeId && <div className="detail-empty"><strong>暂无内容</strong><p>{task?.status === 'completed' ? '这个分类没有内容，可以切换到其他分类查看。' : '添加资料并完成整理后，就可以在这里查看结果。'}</p></div>}
          {activeRequirement && <article className="detail-card" key={activeRequirement.id}>
            <div className="detail-header"><div><span className="detail-kicker">需求建议</span><h3>查看并处理需求</h3></div><span className={`detail-status status-${activeRequirement.status}`}>{statusLabels[activeRequirement.status] || '待确认'}</span></div>
            <p className="detail-hint">可以直接修改内容，确认后才会进入需求清单。</p>
            <label className="detail-label"><RequiredMark />需求内容<textarea aria-required="true" aria-label="需求内容" value={drafts[activeRequirement.id] ?? activeRequirement.text} onChange={e => { const value = e.target.value; setDrafts(prev => { const next = { ...prev }; if (value === activeRequirement.text) delete next[activeRequirement.id]; else next[activeRequirement.id] = value; return next; }); }} /></label>
            <h4>原文出处</h4>{activeRequirement.origin === 'manual' && <p>来源：人工输入</p>}{activeRequirement.material_id && sources(activeRequirement)}
            <details className="history" onToggle={e => { if (e.currentTarget.open) loadHistory(activeRequirement); }}><summary>查看最初建议和修改记录</summary><p>最初建议：{activeRequirement.original_text}</p>{histories[activeRequirement.id]?.map((entry, i) => <p key={i}>{entry.old_text} → {entry.new_text}（{entry.new_status} · {entry.actor_name}）</p>)}</details>
            {(message === '处理结果已保存。' || message.startsWith('已撤销确认。')) && <p className="detail-feedback">{message}</p>}
            <div className="row detail-actions">
              <button disabled={!isOwner || busy || !(drafts[activeRequirement.id] ?? activeRequirement.text).trim() || (activeRequirement.status === 'confirmed' && drafts[activeRequirement.id] === undefined)} onClick={() => review(activeRequirement, 'confirmed')}>{activeRequirement.status === 'confirmed' ? (drafts[activeRequirement.id] === undefined ? '已确认' : '保存修改') : '确认需求'}</button>
              {activeRequirement.status !== 'rejected' && <button className="secondary" disabled={!isOwner || busy || !(drafts[activeRequirement.id] ?? activeRequirement.text).trim()} onClick={() => review(activeRequirement, 'rejected')}>驳回</button>}
              {activeRequirement.status === 'pending' ? <button className="secondary" disabled={busy || drafts[activeRequirement.id] === undefined || !drafts[activeRequirement.id].trim()} onClick={() => review(activeRequirement, 'pending')}>保存为待确认</button> : <button className="secondary" disabled={!isOwner || busy} onClick={() => review(activeRequirement, 'pending', false)}>{activeRequirement.status === 'confirmed' ? '撤销确认' : '撤销驳回'}</button>}
            </div>{activeRequirement.status === 'confirmed' && <RequirementRevision key={activeRequirement.id} projectId={project} requirementId={activeRequirement.id} version={activeRequirement.version} isOwner={isOwner} onChange={()=>reloadProject(project)} />}
          </article>}
          {activeFact && <article className="detail-card" key={activeFact.id}>
            <div className="detail-header"><div><span className="detail-kicker">资料事实</span><h3>查看资料中提到的内容</h3></div><span className={`detail-status ${activeFact.review_status === 'reviewed' ? 'status-reviewed' : ''}`}>{activeFact.review_status === 'reviewed' ? '已核对' : '待核对'}</span></div>
            <p className="detail-hint">由 AI 整理，请对照原文核实。标记已核对后，新生成的清单会保存这条事实，用于生成方案；不代表待定事项已作决定。</p><div className="fact-content">{activeFact.text}</div><h4>原文出处</h4>{sources(activeFact)}
            {(message === '已标记为核对完成。' || message === '已撤销核对标记。') && <p className="detail-feedback" role="status">{message}</p>}
            <div className="row detail-actions"><button className={activeFact.review_status === 'reviewed' ? 'secondary' : undefined} disabled={busy} onClick={() => reviewFact(activeFact)}>{activeFact.review_status === 'reviewed' ? '撤销核对' : '标记已核对'}</button></div>
          </article>}
          {activeQuestion && <article className="detail-card" key={activeQuestion.id}>
            <div className="detail-header"><div><span className="detail-kicker">待确认问题</span><h3>查看并回答问题</h3></div><span className={`detail-status status-${activeQuestion.status}`}>{statusLabels[activeQuestion.status] || '待确认'}</span></div>
            <div className="question-content">{activeQuestion.text}</div><h4>原文出处</h4>{sources(activeQuestion)}
            <label className="detail-label"><RequiredMark />答复或处理说明<textarea aria-required="true" aria-label="问题说明" value={questionDrafts[activeQuestion.id] ?? activeQuestion.answer} onChange={e => { const value = e.target.value; setQuestionDrafts(prev => { const next = { ...prev }; if (value === activeQuestion.answer) delete next[activeQuestion.id]; else next[activeQuestion.id] = value; return next; }); }} placeholder="填写答复或处理说明" /></label>
            <p className="detail-hint">保存答复只记录内容；确认问题处理完后，再标记已解决。</p>
            {message === '问题的处理结果已保存。' && <p className="detail-feedback">{message}</p>}
            <div className="row detail-actions"><button disabled={busy || (!isOwner && activeQuestion.status==='resolved') || !(questionDrafts[activeQuestion.id] ?? activeQuestion.answer).trim()} onClick={() => decideQuestion(activeQuestion, 'answered')}>保存答复</button><button className="secondary" disabled={!isOwner || busy || !(questionDrafts[activeQuestion.id] ?? activeQuestion.answer).trim()} onClick={() => decideQuestion(activeQuestion, 'resolved')}>标记已解决</button></div>
          </article>}
        </div>
      </div>
      {!isOwner && <p>需求确认、问题解决和生成需求清单由项目负责人完成。</p>}<button className="finish" disabled={!isOwner || busy || !items.some(x => x.status === 'confirmed')} onClick={baseline}>生成已确认需求清单</button>{baselines.map((b, index) => <details key={b.id}><summary>已确认需求清单 {baselines.length - index}（{b.requirements.length} 条需求，{b.facts.length} 条已核对事实）</summary><ul>{b.requirements.map(r => <li key={r.id}>{r.text}</li>)}</ul>{!b.facts_snapshot_available ? <p>这份旧清单没有保存资料事实；如需使用，请重新生成清单。</p> : b.facts.length > 0 ? <><p>已核对的资料事实：</p><ul>{b.facts.map(f => <li key={f.id}>{f.text}（出处：{materials.find(m => m.id === f.material_id)?.display_name || '资料待核对'}）</li>)}</ul></> : <p>这份清单没有已核对的资料事实。</p>}{b.questions.length > 0 && <><p>生成清单时仍未解决的问题：</p><ul>{b.questions.map(q => <li key={q.id}>{q.text} {q.answer && `（${q.answer}）`}</li>)}</ul></>}</details>)}<div className="workflow-actions"><button className="secondary" type="button" onClick={() => goStep(1)}>上一步</button><button type="button" onClick={() => goStep(3)}>下一步：生成方案</button></div></section></div>
      <div hidden={step !== 3}><section><h2>生成方案初稿</h2><p>选择一份已确认需求清单，参考模板生成初稿。生成时使用清单里的已确认需求、已核对事实、未解决问题及其出处；事实原文、未核对的事实和原始资料全文不会作为事实发送。</p>
        {baselines.length === 0 ? <p>请先确认需求并生成需求清单。</p> : <>
          <label><RequiredMark />需求清单<select aria-required="true" value={baselineId || baselines[0]?.id || ''} onChange={e => { if (outlineDirty && !window.confirm('提纲有未保存的修改，切换需求清单会丢失这些修改。确认切换？')) return; setOutlineChoice(null); setOutlineDirty(false); setBaselineId(e.target.value); }}>{baselines.map((b, index) => <option key={b.id} value={b.id}>需求清单 {baselines.length - index}（{b.requirements.length} 条需求）</option>)}</select></label>
          <p>需求清单保留生成时的内容；如果后来修改或撤销需求或核对状态，请重新生成清单并选择新版本。</p>
          {(() => { const b = baselines.find(x => x.id === (baselineId || baselines[0]?.id)); return b && <div className="baseline-facts"><p>本次使用：{b.requirements.length} 条已确认需求、{b.facts.length} 条已核对事实、{b.questions.length} 个待确认问题。当前还有 {facts.filter(f => f.review_status !== 'reviewed').length} 条事实待核对，不会作为事实发送；需求或问题中可能提到相同内容。</p>{!b.facts_snapshot_available ? <p>这份旧清单没有保存事实，如需使用已核对事实，请重新生成清单。</p> : b.facts.length > 0 && <details><summary>查看已核对事实和原文出处</summary>{b.facts.map(f => <div key={f.id}><p>{f.text}</p>{sources(f)}</div>)}</details>}</div>; })()}
          <label>方案模板<select value={templateId} onChange={e=>{if(outlineDirty && !window.confirm('提纲有未保存的修改，切换模板会丢失这些修改。确认切换？'))return;setOutlineChoice(null);setOutlineDirty(false);setTemplateId(e.target.value);}}><option value="demo-v1">信息化建设方案示例模板（虚构）</option>{materials.filter(m=>m.state==='active').map(m=><option key={m.id} value={m.id}>{m.display_name || m.filename}</option>)}</select></label>{templateId !== "demo-v1" && <p>将使用所选模板读取出的文字；如果未识别出章节，提纲编辑会显示示例章节供调整。</p>}
          <details><summary>选择项目中的参考案例（选填）</summary><p>仅发送勾选的资料作为参考，生成内容仍需人工核对。</p>{materials.filter(m=>m.state==='active').map(m=><label className="outline-requirement" key={m.id}><input type="checkbox" checked={caseIds.includes(m.id)} onChange={e=>setCaseIds(e.target.checked?[...caseIds,m.id]:caseIds.filter(id=>id!==m.id))}/><span>{m.display_name || m.filename}</span></label>)}{materials.filter(m=>m.state==='active').length===0 && <p>项目暂无可用资料。</p>}</details>
          {(() => { const b=baselines.find(x=>x.id===(baselineId || baselines[0]?.id)); return b && <OutlineEditor key={`${project}-${b.id}-${templateId}`} projectId={project} baselineId={b.id} templateId={templateId} requirements={b.requirements} onChoice={setOutlineChoice} onDirty={setOutlineDirty} />; })()}
          <label><input type="checkbox" checked={includeExample} onChange={e => setIncludeExample(e.target.checked)} /> 参考虚构案例（仅供写法参考）</label>
          <p>将使用{outlineChoice ? "已保存的提纲" : "默认模板提纲"}、所选清单中的需求、已核对事实和未解决问题，以及{templateId === 'demo-v1' ? '虚构模板' : '所选项目模板'}{caseIds.length ? `和 ${caseIds.length} 份项目参考案例` : ''}{includeExample ? '和虚构案例' : ''}；生成时会发送给 DeepSeek 并产生模型费用。</p>
          <button disabled={busy || outlineDirty || (!!outlineChoice && outlineChoice.baselineId !== (baselineId || baselines[0]?.id)) || !config?.model_ready || proposals.some(p => ['pending','running'].includes(p.status))} onClick={generateProposal}>生成方案初稿</button>
        </>}
        {proposals.length > 0 && <><label>查看初稿<select value={activeProposal?.id || ''} onChange={e => selectProposal(e.target.value)}>{proposals.map((p, i) => <option key={p.id} value={p.id}>{proposalLabel(p, i, proposals.length)}</option>)}</select></label>
          {activeProposal && <div className="proposal-result"><p>状态：{({pending:'等待中',running:'生成中',completed:'已生成，待人工核对',failed:'生成失败',interrupted:'已中断'} as Record<string,string>)[activeProposal.status] || activeProposal.status}。{activeProposal.error}</p>
            <p>调用 {activeProposal.calls} 次，输入 {activeProposal.prompt_tokens ?? '未知'}，输出 {activeProposal.completion_tokens ?? '未知'}；耗时 {activeProposal.elapsed_ms === null ? '未知' : `${(activeProposal.elapsed_ms / 1000).toFixed(1)} 秒`}。费用以账单为准。</p>
            {activeProposal.status === 'completed' && <UsedOutline projectId={project} proposalId={activeProposal.id} />}
            {activeProposal.status === 'completed' && <a className="proposal-preview-link" href={`/proposals/${encodeURIComponent(project)}/${encodeURIComponent(activeProposal.id)}`} target="_blank" rel="noopener noreferrer">预览方案初稿 ↗</a>}
          </div>}
        </>}
        <div className="workflow-actions"><button className="secondary" type="button" onClick={() => goStep(2)}>上一步</button><button type="button" onClick={() => goStep(4)}>下一步：审核与导出</button></div>
      </section></div>
      <div hidden={step !== 4}><section><h2>选择要审核的方案</h2>
        {proposals.length === 0 ? <p>还没有方案，请先到上一步生成方案。</p> : <><label><RequiredMark />选择方案<select aria-required="true" value={activeProposal?.id || ''} onChange={e => selectProposal(e.target.value)}>{proposals.map((p, i) => <option key={p.id} value={p.id}>{proposalLabel(p, i, proposals.length)}</option>)}</select></label>
        {activeProposal?.status !== 'completed' && <p>方案生成完成后，就可以审核。</p>}</>}
      </section>
      {activeProposal?.status === 'completed' && <ProposalReview key={`${project}-${activeProposal.id}-${activeProposal.version}`} projectId={project} proposalId={activeProposal.id} version={activeProposal.version} unsaved={false} canReview={isOwner} onStatusChange={setReviewStatus} onDirtyChange={setReviewDirty} />}</div></>}
    </div>
    {project && <aside className="project-overview"><section><div className="overview-title"><h2>项目概览</h2>{hasIdentity && <button type="button" className="secondary" onClick={()=>openManagement('project')}>项目设置</button>}</div><div className="overview-project"><span className="project-monogram">{(projects.find(p=>p.id===project)?.name || '项').slice(0,1)}</span><div><strong>{projects.find(p=>p.id===project)?.name}</strong><p>{isOwner?'项目负责人':'项目成员'}</p></div></div><div className="overview-line"><span>当前步骤</span><strong>{stepTitles[step-1]}</strong></div><div className="overview-line"><span>项目资料</span><strong>{materials.length} 份</strong></div></section><section><h2>项目待办</h2><div className="overview-task"><strong>待确认需求</strong><span>{items.filter(item=>item.status==='pending').length} 条</span></div><div className="overview-task"><strong>待确认问题</strong><span>{questions.filter(question=>question.status!=='resolved').length} 条</span></div></section><div className="overview-note"><strong>按你的节奏推进</strong><p>先核对资料和需求，再生成方案。每一步都可以保存并稍后继续。</p></div></aside>}
    </div>
  </main>;
}
