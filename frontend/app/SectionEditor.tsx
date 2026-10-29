'use client';
import RequiredMark from './RequiredMark';

import { useCallback, useEffect, useState } from 'react';

type Section = { id: string; title: string; level: number };
type Edit = { id: string; base_version: number; section_title: string; original: string; candidate: string; suggestions: string[]; status: string; error: string; calls: number; prompt_tokens: number | null; completion_tokens: number | null };
type Proposal = { id: string; status: string; content: string; error: string; version: number };
type Revision = { version: number; content: string; created_at: string };
type Config = { model_ready: boolean; allowed_models: string[] };

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error?.message || '操作失败，请重试。');
  return value as T;
}

function Diff({ text, other }: { text: string; other: string }) {
  const otherLines = new Set(other.split('\n'));
  return <pre className="section-diff">{text.split('\n').map((line, index) => <span key={index} className={otherLines.has(line) || !line.trim() ? '' : 'section-diff-changed'}>{line || ' '}{'\n'}</span>)}</pre>;
}

export default function SectionEditor({ projectId, proposal, unsaved, onSaved }: { projectId: string; proposal: Proposal; unsaved: boolean; onSaved: (value: Proposal) => void }) {
  const [open, setOpen] = useState(false);
  const [sections, setSections] = useState<Section[]>([]);
  const [selection, setSelection] = useState('');
  const [instruction, setInstruction] = useState('');
  const [model, setModel] = useState('');
  const [config, setConfig] = useState<Config | null>(null);
  const [edits, setEdits] = useState<Edit[]>([]);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [selectedEdit, setSelectedEdit] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const base = `/api/v1/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposal.id)}`;
  const refresh = useCallback(async () => {
    const [sectionData, editData, configData, revisionData] = await Promise.all([
      request<{version: number; sections: Section[]}>(`${base}/sections`), request<Edit[]>(`${base}/section-edits`), request<Config>('/api/v1/config'), request<Revision[]>(`${base}/revisions`)
    ]);
    if (sectionData.version !== proposal.version) setMessage('方案已被更新，请刷新页面后再发起或接受修改。');
    setSections(sectionData.version === proposal.version ? sectionData.sections : []);
    setEdits(editData); setConfig(configData); setRevisions(revisionData);
    setModel(current => configData.allowed_models.includes(current) ? current : configData.allowed_models[0] || '');
    setSelection(current => sectionData.sections.some(s => s.id === current) ? current : sectionData.sections[0]?.id || '');
    setSelectedEdit(current => editData.some(e => e.id === current) ? current : editData[0]?.id || '');
  }, [base, proposal.version]);
  useEffect(() => { if (!open) return; const timer = setTimeout(() => { void refresh().catch(e => setMessage(e instanceof Error ? e.message : '加载失败')); }, 0); return () => clearTimeout(timer); }, [open, refresh]);
  useEffect(() => {
    if (!open || !edits.some(e => e.status === 'pending' || e.status === 'running')) return;
    const timer = setTimeout(() => { void refresh().catch(e => setMessage(e instanceof Error ? e.message : '刷新失败')); }, 1500);
    return () => clearTimeout(timer);
  }, [open, edits, refresh]);
  const current = edits.find(e => e.id === selectedEdit);
  const post = (url: string, body?: object) => request<unknown>(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body || {}) });
  async function start() {
    if (!window.confirm('将所选章节正文、修改要求、生成方案时的需求依据及未解决问题发送给模型服务商，并产生模型调用费用。确认继续吗？')) return;
    try {
      setBusy(true); setMessage('');
      const item = await post(`${base}/section-edits`, {version:proposal.version, section_id:selection, instruction, model_name:model, confirm_external_use:true}) as Edit;
      await refresh(); setSelectedEdit(item.id); setMessage('修改任务已提交，结果生成后需要你确认。');
    } catch (e) { setMessage(e instanceof Error ? e.message : '提交失败'); } finally { setBusy(false); }
  }
  async function accept() {
    if (!current || !window.confirm('确认将候选内容替换所选章节？方案会生成新版本，需要重新审核。')) return;
    try {
      setBusy(true); setMessage('');
      const value = await post(`/api/v1/projects/${encodeURIComponent(projectId)}/section-edits/${encodeURIComponent(current.id)}/accept`, {version:current.base_version}) as Proposal;
      onSaved(value); setMessage('已接受修改并保存新版本，请重新审核。');
    } catch (e) { setMessage(e instanceof Error ? e.message : '接受失败'); } finally { setBusy(false); }
  }
  async function discard() {
    if (!current) return;
    try { setBusy(true); await post(`/api/v1/projects/${encodeURIComponent(projectId)}/section-edits/${encodeURIComponent(current.id)}/discard`); await refresh(); setMessage('已放弃候选，方案内容没有改变。'); }
    catch (e) { setMessage(e instanceof Error ? e.message : '操作失败'); } finally { setBusy(false); }
  }
  return <div className="section-editor">
    <button className="secondary" onClick={() => setOpen(!open)}>{open ? '收起章节修改' : 'AI 修改章节'}</button>
    {open && <div className="section-editor-panel">
      <h2>AI 修改章节</h2>
      <p>选择一个章节并说明要求。AI 先生成候选，你确认后才会替换；其他章节保持原样。</p>
      {unsaved && <p>请先保存或放弃手动修改，再使用章节修改。</p>}
      {!sections.length && <p>当前方案没有可安全定位的 Markdown 章节，请检查标题格式或刷新页面。</p>}
      <label><RequiredMark />选择章节<select aria-required="true" value={selection} onChange={e => setSelection(e.target.value)}>{sections.map((s, i) => <option key={s.id} value={s.id}>{`${'　'.repeat(s.level-1)}${i+1}. ${s.title}`}</option>)}</select></label>
      <label><RequiredMark />修改要求<textarea aria-required="true" value={instruction} maxLength={3000} onChange={e => setInstruction(e.target.value)} placeholder="例如：补充建设目标，未确认的内容请标注待确认" /></label>
      <label><RequiredMark />模型<select aria-required="true" value={model} onChange={e => setModel(e.target.value)}>{config?.allowed_models.map(m => <option key={m} value={m}>{m}</option>)}</select></label>
      <p>将发送所选章节、修改要求，以及生成方案时的需求依据和未解决问题；调用会产生费用。</p>
      <button disabled={busy || unsaved || !selection || !instruction.trim() || !config?.model_ready || !model} onClick={start}>生成候选修改</button>
      {message && <p role="status">{message}</p>}
      {revisions.length > 0 && <details><summary>查看保存过的旧版本</summary>{revisions.map(r => <details key={r.version}><summary>版本 {r.version} · {new Date(r.created_at).toLocaleString('zh-CN')}</summary><pre className="section-diff">{r.content}</pre></details>)}</details>}
      {edits.length > 0 && <><label>修改记录<select value={selectedEdit} onChange={e => setSelectedEdit(e.target.value)}>{edits.map(e => <option key={e.id} value={e.id}>{e.section_title} · 版本 {e.base_version} · {({pending:'等待中',running:'生成中',completed:'待确认',accepted:'已接受',discarded:'已放弃',failed:'失败',interrupted:'已中断',cancelled:'已取消'} as Record<string,string>)[e.status] || e.status}</option>)}</select></label>
        {current && <><p>状态：{({pending:'等待中',running:'生成中',completed:'待确认',accepted:'已接受',discarded:'已放弃',failed:'失败',interrupted:'已中断',cancelled:'已取消'} as Record<string,string>)[current.status] || current.status}。模型调用 {current.calls} 次；输入 {current.prompt_tokens ?? '未知'}，输出 {current.completion_tokens ?? '未知'}。{current.error}</p>
          {current.candidate && <><p>高亮显示与另一侧不相同的行；请结合上下文核对事实和措辞。</p><div className="section-diff-grid"><div><strong>修改前</strong><Diff text={current.original} other={current.candidate} /></div><div><strong>候选修改</strong><Diff text={current.candidate} other={current.original} /></div></div>
            {current.suggestions.length > 0 && <><strong>其他章节建议（不会自动修改）</strong><ul>{current.suggestions.map((s,i) => <li key={i}>{s}</li>)}</ul></>}
            {current.status === 'completed' && <><div className="row"><button disabled={busy || unsaved || current.base_version !== proposal.version} onClick={accept}>接受修改</button><button className="secondary" disabled={busy} onClick={discard}>放弃候选</button></div>{current.base_version !== proposal.version && <p>方案版本已变化，此候选仅供查看，不能直接接受。</p>}</>}
          </>}
        </>}
      </>}
    </div>}
  </div>;
}
