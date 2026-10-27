'use client';

import { use, useEffect, useState } from 'react';

type Material = { id: string; filename: string; warning: string };
type Page = { text: string; next_offset: number | null; total_characters: number };

export default function MaterialPreview({ params }: { params: Promise<{ projectId: string; materialId: string }> }) {
  const { projectId, materialId } = use(params);
  const root = `/api/v1/projects/${encodeURIComponent(projectId)}/materials`;
  const [material, setMaterial] = useState<Material | null>(null);
  const [text, setText] = useState('');
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetch(root, { signal: controller.signal }), fetch(`${root}/${encodeURIComponent(materialId)}/content?offset=0`, { signal: controller.signal })])
      .then(async ([listResponse, contentResponse]) => {
        const [list, content] = await Promise.all([listResponse.json(), contentResponse.json()]);
        if (!listResponse.ok || !contentResponse.ok) throw new Error(content.error?.message || list.error?.message || '无法读取资料，请重试。');
        const found = (list as Material[]).find(item => item.id === materialId);
        if (!found) throw new Error('找不到这份资料。');
        setMaterial(found); setText((content as Page).text); setNextOffset((content as Page).next_offset);
      }).catch(e => { if (e.name !== 'AbortError') setError(e.message || '无法读取资料，请重试。'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [root, materialId]);

  async function loadMore() {
    if (nextOffset === null || busy) return;
    try {
      setBusy(true); setError('');
      const response = await fetch(`${root}/${encodeURIComponent(materialId)}/content?offset=${nextOffset}`);
      const page = await response.json();
      if (!response.ok) throw new Error(page.error?.message || '无法读取后续内容，请重试。');
      setText(old => old + (page as Page).text); setNextOffset((page as Page).next_offset);
    } catch (e) { setError(e instanceof Error ? e.message : '无法读取后续内容，请重试。'); }
    finally { setBusy(false); }
  }

  return <main className="proposal-preview-page">
    <header><div><span className="eyebrow">QI SHU · 资料原文</span><h1>{material?.filename || '查看资料'}</h1><p>可关闭此页面，回到方案预览。</p></div></header>
    {error && <div className="notice" role="status">{error}</div>}
    <section>
      {loading ? <p>正在读取资料……</p> : material ? <>
        {material.warning && <p>{material.warning}</p>}
        <pre className="material-original">{text || '这份资料没有可显示的文字。'}</pre>
        {nextOffset !== null && <button className="secondary" disabled={busy} onClick={loadMore}>继续查看文字</button>}
        <p><a href={`${root}/${encodeURIComponent(materialId)}/original`}>下载原文件</a></p>
      </> : <p>资料暂时无法显示。</p>}
    </section>
  </main>;
}
