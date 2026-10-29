'use client';
import RequiredMark from './RequiredMark';

import { useEffect, useState } from 'react';
import ConsistencyCheck from './ConsistencyCheck';

type Question = { id: string; text: string; answer: string; status: string };
type Decision = { question_id: string; issue_text?: string; classification: 'critical' | 'general' | 'not_classified' | ''; disposition: 'resolved' | 'noncommit' | 'general_approved' | ''; reason: string };
type Review = { version: number; status: string; last_action: string; baseline_created_at: string; baseline_requirements_count: number; message: string; questions: Question[]; note: string; updated_at: string | null };
type History = { version: number; action: string; note: string; decisions: Decision[]; created_at: string; actor_name:string };

type Props = { projectId: string; proposalId: string; version: number; unsaved: boolean; canReview: boolean; onStatusChange: (status: string) => void; onDirtyChange: (dirty: boolean) => void };
const labels: Record<string, string> = { draft: '草稿，尚未提交审核', submitted: '已提交，待审核', approved: '已审核通过（本机试用）', returned: '已退回修改', needs_review: '资料有变化，需要重新核对' };

export default function ProposalReview({ projectId, proposalId, version, unsaved, canReview, onStatusChange, onDirtyChange }: Props) {
  const root = `/api/v1/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposalId)}`;
  const [review, setReview] = useState<Review | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [extraQuestions, setExtraQuestions] = useState<Question[]>([]);
  const [note, setNote] = useState('');
  const [returnNote, setReturnNote] = useState('');
  const [mode, setMode] = useState<'overview' | 'return' | 'approve'>('overview');
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [history, setHistory] = useState<History[]>([]);
  const [preview, setPreview] = useState<{url: string; version: number; kind: 'draft' | 'approved'} | null>(null);
  useEffect(() => { return () => { if (preview) URL.revokeObjectURL(preview.url); }; }, [preview]);
  const reviewDirty = (review?.status === 'submitted' || review?.last_action === 'submitted') && (!!note.trim() || !!returnNote.trim() || checked || extraQuestions.length > 0 || Object.keys(decisions).length > 0);

  useEffect(() => {
    onDirtyChange(!!reviewDirty);
    if (!reviewDirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [reviewDirty, onDirtyChange]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${root}/review`, { signal: controller.signal }).then(async r => {
      const data = await r.json();
      if (!r.ok) throw new Error(data.error?.message || '无法读取审核信息。');
      setReview(data); onStatusChange(data.status);
    }).catch(e => { if (e.name !== 'AbortError') setMessage(e.message || '无法读取审核信息。'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    fetch(`${root}/review-history`, { signal: controller.signal }).then(async r => { if (r.ok) setHistory(await r.json()); }).catch(() => {});
    return () => controller.abort();
  }, [root, version, onStatusChange]);

  const stale = !!review && review.version !== version;
  async function action(kind: 'submit' | 'approve' | 'return') {
    if (unsaved || stale) return;
    const list = [...(review?.questions || []), ...extraQuestions].map(q => ({ ...decisions[q.id], ...(q.id.startsWith('extra-') ? { issue_text: q.text } : {}) })).filter(d => d.question_id);
    try {
      setBusy(true); setMessage('');
      const response = await fetch(`${root}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version, action: kind, note: kind === 'return' ? returnNote : note, decisions: kind === 'approve' ? list : [], other_critical_checked: checked }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || '操作没有完成，请重试。');
      setReview(data); setPreview(null); onStatusChange(data.status); setDecisions({}); setExtraQuestions([]); setNote(''); setReturnNote(''); setMode('overview'); setChecked(false);
      setMessage(kind === 'submit' ? '已提交当前版本审核。' : kind === 'approve' ? '当前版本审核通过。' : '已退回修改。');
      fetch(`${root}/review-history`).then(async r => { if (r.ok) setHistory(await r.json()); }).catch(() => {});
    } catch (e) { setMessage(e instanceof Error ? e.message : '操作没有完成，请重试。'); }
    finally { setBusy(false); }
  }
  async function exportWord(kind: 'draft' | 'approved') {
    if (unsaved || stale) return;
    try {
      setBusy(true); setMessage('');
      const response = await fetch(`${root}/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version, kind }) });
      if (!response.ok) { const data = await response.json(); throw new Error(data.error?.message || '导出失败，请重试。'); }
      const blob = await response.blob();
      const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = kind === 'draft' ? '方案草稿.docx' : '已审核方案.docx'; document.body.appendChild(link); link.click(); link.remove();
      const url = link.href; setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage(kind === 'draft' ? '已生成 Word 草稿。' : '已生成审核通过的 Word。');
    } catch (e) { setMessage(e instanceof Error ? e.message : '导出失败，请重试。'); }
    finally { setBusy(false); }
  }
  async function previewWord() {
    if (unsaved || stale) return;
    try {
      setBusy(true); setMessage('');
      const kind = review?.status === 'approved' ? 'approved' : 'draft';
      const response = await fetch(`${root}/document-preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version, kind }) });
      if (!response.ok) { const data = await response.json(); throw new Error(data.error?.message || '无法生成分页预览。'); }
      setPreview({url: URL.createObjectURL(await response.blob()), version, kind});
      setMessage(`已生成${kind === 'approved' ? '已审核版' : '草稿'}分页预览，请逐页核对；不同办公软件显示可能略有差异。`);
    } catch (e) { setMessage(e instanceof Error ? e.message : '无法生成分页预览。'); }
    finally { setBusy(false); }
  }
  function setDecision(q: Question, patch: Partial<Decision>) {
    setDecisions(old => ({ ...old, [q.id]: { ...(old[q.id] || { question_id: q.id, classification: '', disposition: '', reason: '' }), ...patch } }));
  }
  const complete = !!review && [...review.questions, ...extraQuestions].every(q => {
    const d = decisions[q.id];
    return q.text.trim() && d && d.classification && d.disposition && d.reason.trim() && !(d.disposition === 'general_approved' && d.classification !== 'general');
  });

  return <section className="review-section">
    <h2>审核与导出</h2>
    <p>审核记录关联当前保存的方案版本；负责人审核，项目成员可以提交和导出。</p>
    <ConsistencyCheck projectId={projectId} proposalId={proposalId} version={version} unsaved={unsaved} />
    {loading ? <p>正在读取审核状态……</p> : review ? <>
      <p><strong>第 {version} 版：</strong>{labels[review.status] || '状态待核对'}。{review.message}</p>
      <p>依据的需求清单：{review.baseline_requirements_count} 条需求，生成于 {new Date(review.baseline_created_at).toLocaleString('zh-CN')}。</p>
      {review.note && <p>最近审核意见：{review.note}</p>}
      {stale && <p>方案已在其他页面更新，请保存好内容后刷新本页。</p>}
      {unsaved && <p>请先保存方案修改，再审核或导出。</p>}
      {!canReview && review.status === 'submitted' && <p>方案已提交，等待项目负责人审核。</p>}
      {(review.status === 'submitted' || (review.status === 'needs_review' && review.last_action === 'submitted')) && <fieldset className="review-panel" disabled={!canReview || busy || unsaved || stale}>
        {mode === 'overview' && <>
          <h3>先看看这些问题</h3>
          <p>这些问题来自生成方案时的需求清单。如果有问题需要修改，可以直接退回；确认可以通过后，再说明每条问题怎么处理。</p>
          {review.questions.length === 0 ? <p>这份清单没有记录待确认问题。</p> : <ol className="review-overview">{review.questions.map(q => <li key={q.id}><strong>{q.text}</strong>{q.answer && <p>之前的答复：{q.answer}</p>}</li>)}</ol>}
          <div className="row"><button className="secondary" type="button" onClick={() => setMode('return')}>退回修改</button>{review.status === 'submitted' && <button type="button" onClick={() => setMode('approve')}>继续审核通过</button>}</div>
        </>}
        {mode === 'return' && <>
          <h3>退回修改</h3><p>告诉编写人需要改什么，就可以退回，不用先处理每条问题。</p>
          <label><RequiredMark />退回原因<textarea aria-required="true" value={returnNote} onChange={e => setReturnNote(e.target.value)} placeholder="例如：请先确认是否需要对接 OA" /></label>
          <div className="row review-form-actions"><button disabled={!returnNote.trim()} onClick={() => action('return')}>确认退回</button><button className="secondary" type="button" onClick={() => setMode('overview')}>返回</button></div>
        </>}
        {mode === 'approve' && <>
          <h3>确认问题怎么处理</h3>
          <p>确认方案可以通过后，逐条说明处理结果。重要问题需要解决，或在方案中明确不作承诺；只有不影响主要结论的一般问题才能暂时保留。</p>
          {[...review.questions, ...extraQuestions].map((q, index) => {
            const d = decisions[q.id] || { question_id: q.id, classification: '', disposition: '', reason: '' };
            const hint = d.disposition === 'resolved' ? '例如：负责人已确认处理结果' : d.disposition === 'noncommit' ? '例如：方案第 3 节已写明暂不承诺对接' : '说明为什么不影响方案、由谁同意保留';
            return <div className="review-question" key={q.id}>
              {q.id.startsWith('extra-') ? <><label><RequiredMark />方案中发现的问题<textarea aria-required="true" value={q.text} onChange={e => setExtraQuestions(old => old.map(x => x.id === q.id ? { ...x, text: e.target.value } : x))} placeholder="描述还需要处理的问题" /></label><button className="secondary" type="button" onClick={() => { setExtraQuestions(old => old.filter(x => x.id !== q.id)); setDecisions(old => { const next = { ...old }; delete next[q.id]; return next; }); }}>移除这条</button></> : <strong>{index + 1}. {q.text}</strong>}{q.answer && <p>之前的答复：{q.answer}</p>}
              <label><RequiredMark />这条问题怎么处理<select aria-required="true" value={d.disposition} onChange={e => { const value = e.target.value as Decision['disposition']; setDecision(q, { disposition: value, classification: value === 'general_approved' ? 'general' : value ? 'not_classified' : '' }); }}><option value="">请选择</option><option value="resolved">已经解决</option><option value="noncommit">方案已写明暂不承诺</option><option value="general_approved">一般问题，同意暂时保留</option></select></label>
              {d.disposition && <label><RequiredMark />处理说明<textarea aria-required="true" value={d.reason} onChange={e => setDecision(q, { reason: e.target.value })} placeholder={hint} /></label>}
            </div>;
          })}
          <button className="secondary" type="button" onClick={() => setExtraQuestions(old => [...old, { id: `extra-${crypto.randomUUID()}`, text: '', answer: '', status: 'pending' }])}>添加方案中发现的问题</button>
          <label><RequiredMark />审核意见<textarea aria-required="true" value={note} onChange={e => setNote(e.target.value)} placeholder="填写本次审核结论" /></label>
          <label className="review-checkbox"><input aria-required="true" type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} /> <span><RequiredMark />我已核对方案中的其他重要事项，没有未处理的关键问题。</span></label>
          {(!note.trim() || !checked || !complete) && <p className="review-help">请处理每条问题、填写审核意见，并确认其他重要事项。</p>}
          <div className="row"><button disabled={!note.trim() || !checked || !complete} onClick={() => action('approve')}>确认审核通过</button><button className="secondary" type="button" onClick={() => setMode('overview')}>返回</button></div>
        </>}
      </fieldset>}
    </> : <p>审核信息暂时不可用，草稿仍可尝试导出。</p>}
    {message && <p className="detail-feedback" role="status">{message}</p>}
    {history.length > 0 && <details className="review-history"><summary>查看审核记录</summary>{history.map((entry, index) => <div className="review-history-entry" key={`${entry.created_at}-${index}`}><strong>第 {entry.version} 版 · {({ submitted: '提交审核', approved: '审核通过', returned: '退回修改' } as Record<string, string>)[entry.action] || '审核记录'}</strong><p>{new Date(entry.created_at).toLocaleString('zh-CN')} · {entry.actor_name}{entry.note ? ` · 意见：${entry.note}` : ''}</p>{entry.decisions.map((d, i) => <p key={i}>{review?.questions.find(q => q.id === d.question_id)?.text || d.issue_text || '问题处理'}：{({ resolved: '已解决', noncommit: '已明确不作承诺', general_approved: '一般事项批准保留' } as Record<string, string>)[d.disposition] || '已处理'}，{d.reason}</p>)}</div>)}</details>}
    <div className="row review-exports">{review && ['draft','returned','needs_review'].includes(review.status) && <button disabled={busy || unsaved || stale} onClick={() => action('submit')}>提交当前版本审核</button>}<button className="secondary" disabled={busy || unsaved || stale} onClick={previewWord}>预览 Word 分页</button><button className="secondary" disabled={busy || unsaved || stale} onClick={() => exportWord('draft')}>导出 Word 草稿</button>{review?.status === 'approved' && <button disabled={busy || unsaved || stale} onClick={() => exportWord('approved')}>导出已审核 Word</button>}</div>
    {preview && preview.version === version && preview.kind === (review?.status === 'approved' ? 'approved' : 'draft') && <div><h3>Word {preview.kind === 'approved' ? '已审核版' : '草稿'}分页预览</h3><p>请逐页检查换页、表格及文字显示。手机上可在新窗口打开预览。</p><iframe title={`Word ${preview.kind === 'approved' ? '已审核版' : '草稿'}分页预览`} src={`${preview.url}#view=FitH`} style={{width: '100%', height: 640, border: '1px solid #ddd'}} /><p><a href={preview.url} target="_blank" rel="noopener noreferrer">在新窗口打开预览</a></p></div>}
  </section>;
}
