'use client';

import { use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import ProposalDocument from '../../../ProposalDocument';
import RequiredMark from '../../../RequiredMark';
import SectionEditor from '../../../SectionEditor';

type Proposal = { id: string; status: string; content: string; error: string; version: number };

export default function ProposalPreview({ params }: { params: Promise<{ projectId: string; proposalId: string }> }) {
  const { projectId, proposalId } = use(params);
  const router = useRouter();
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [materialNames, setMaterialNames] = useState<Record<string, string>>({});
  const [legacyMaterialNames, setLegacyMaterialNames] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const base = `/api/v1/projects/${encodeURIComponent(projectId)}/proposals`;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetch(base, { signal: controller.signal }), fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/materials`, { signal: controller.signal })]).then(async ([r, materialsResponse]) => {
      const [data, materials] = await Promise.all([r.json(), materialsResponse.json()]);
      if (!r.ok) throw new Error(data.error?.message || '无法打开初稿，请重试。');
      if (!materialsResponse.ok) throw new Error(materials.error?.message || '无法读取资料名称，请重试。');
      const found = (data as Proposal[]).find(p => p.id === proposalId);
      if (!found) throw new Error('找不到这份初稿，请回到工作台重新打开。');
      const entries = materials as { id: string; filename: string; display_name?: string }[];
      setMaterialNames(Object.fromEntries(entries.map(m => [m.id.toLowerCase(), m.display_name || m.filename])));
      setLegacyMaterialNames(Object.fromEntries(entries.map(m => [m.id.toLowerCase(), m.filename])));
      setProposal(found);
    }).catch(e => { if (e.name !== 'AbortError') setMessage(e.message || '无法打开初稿，请重试。'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [base, projectId, proposalId]);

  useEffect(() => {
    if (draft === null) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [draft]);

  async function save() {
    if (!proposal || draft === null || !draft.trim()) return;
    try {
      setBusy(true); setMessage('');
      const r = await fetch(`${base}/${encodeURIComponent(proposalId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: draft, version: proposal.version }) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error?.message || '保存失败，请重试。');
      setProposal(data); setDraft(null); setEditing(false); setMessage('方案初稿已保存。');
    } catch (e) { setMessage(e instanceof Error ? e.message : '保存失败，请重试。'); } finally { setBusy(false); }
  }

  return <main className="proposal-preview-page">
    <header><div><span className="eyebrow">QI SHU · 方案预览</span><h1>方案初稿</h1><p>可关闭此页面，回到原来的工作台。</p></div><span className="badge">{draft !== null ? '有未保存修改' : '方案预览'}</span></header>
    {message && <div className="notice" role="status">{message}</div>}
    <section>
      {loading ? <p>正在打开初稿……</p> : !proposal ? <p>初稿暂时无法显示。</p> : proposal.status !== 'completed' ? <p>这份初稿尚未生成完成。{proposal.error}</p> : <>
        <div className="proposal-document-heading"><strong>{editing && <RequiredMark />}方案内容</strong>{draft !== null && <span>有未保存修改</span>}</div>
        <ProposalDocument key={`${proposal.id}-${editing ? 'edit' : 'read'}`} content={draft ?? proposal.content} editing={editing} projectId={projectId} materialNames={materialNames} legacyMaterialNames={legacyMaterialNames} onChange={value => setDraft(value === proposal.content ? null : value)} />
        <div className="row proposal-actions">
          <button className="secondary" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? '查看效果' : '编辑初稿'}</button>
          <button disabled={busy || draft === null || !draft.trim()} onClick={save}>保存修改</button>
          <button className="secondary" disabled={busy || draft !== null} onClick={() => { const query = new URLSearchParams({ project: projectId, proposal: proposalId, step: '4' }); router.push(`/?${query}`); }}>去导出</button>
        </div>
        {draft !== null && <p className="detail-hint">请先保存修改，再去导出。</p>}
        <SectionEditor projectId={projectId} proposal={proposal} unsaved={draft !== null || editing} onSaved={value => { setProposal(value); setDraft(null); setEditing(false); }} />
      </>}
    </section>
  </main>;
}
