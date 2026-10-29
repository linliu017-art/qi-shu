'use client';

import { useEffect, useRef, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import TurndownService from 'turndown';
import { gfm } from 'turndown-plugin-gfm';

const converter = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced', bulletListMarker: '-' });
converter.use(gfm);

type Props = { content: string; editing: boolean; projectId: string; materialNames: Record<string, string>; legacyMaterialNames?: Record<string, string>; onChange: (content: string) => void };

const uuidPattern = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;

function readableDocument(html: string, materialNames: Record<string, string>, legacyMaterialNames: Record<string, string>, projectId: string, editing: boolean) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  for (const table of doc.querySelectorAll('table')) {
    const header = table.querySelector('thead tr');
    if (!header) continue;
    const headers = Array.from(header.children);
    const missingIndex = headers.findIndex(cell => /^(需补充资料|需要补充资料|还需补充)$/.test(cell.textContent?.trim() || ''));
    if (missingIndex < 0) continue;
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    if (!rows.some(row => (row.children[missingIndex]?.textContent || '').match(uuidPattern))) continue;
    const existingIndex = headers.findIndex(cell => /^(已有资料|已有资料出处)$/.test(cell.textContent?.trim() || ''));
    if (existingIndex < 0) {
      const sourceHeader = doc.createElement('th');
      sourceHeader.textContent = '已有资料';
      header.insertBefore(sourceHeader, header.children[missingIndex]);
    }
    headers[missingIndex].textContent = '还需补充';
    for (const row of rows) {
      const originalCell = row.children[missingIndex];
      if (!originalCell) continue;
      const originalText = originalCell.textContent || '';
      const ids = originalText.match(uuidPattern) || [];
      let sourceCell: Element | null = existingIndex >= 0 ? row.children[existingIndex] : null;
      if (!sourceCell) {
        sourceCell = doc.createElement('td');
        row.insertBefore(sourceCell, originalCell);
      }
      if (ids.length) {
        const names = [...new Set(ids.map(id => materialNames[id.toLowerCase()] || '相关资料待核对'))];
        const previous = sourceCell.textContent?.trim();
        sourceCell.textContent = [previous, ...names].filter(Boolean).join('；');
        const remaining = originalText.replace(uuidPattern, '').replace(/^[\s,，;；、]+|[\s,，;；、]+$/g, '').trim();
        originalCell.textContent = remaining || '待确认';
      } else if (existingIndex < 0) sourceCell.textContent = '未列出';
    }
  }
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    node.nodeValue = (node.nodeValue || '').replace(uuidPattern, id => materialNames[id.toLowerCase()] || '相关信息待核对');
  }
  if (!editing) {
    const byName = new Map<string, string[]>();
    for (const [id, name] of [...Object.entries(materialNames), ...Object.entries(legacyMaterialNames)]) {
      const ids = byName.get(name) || [];
      if (!ids.includes(id)) byName.set(name, [...ids, id]);
    }
    const uniqueNames = [...byName.entries()].filter(([name, ids]) => name.length > 0 && ids.length === 1).sort((a, b) => b[0].length - a[0].length);
    for (const table of doc.querySelectorAll('table')) {
      const headers = Array.from(table.querySelector('thead tr')?.children || []);
      const sourceIndex = headers.findIndex(cell => /^(已有资料|已有资料出处|资料来源)$/.test(cell.textContent?.trim() || ''));
      if (sourceIndex < 0) continue;
      for (const row of table.querySelectorAll('tbody tr')) {
        const cell = row.children[sourceIndex];
        if (!cell) continue;
        const textWalker = doc.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
        const nodes: Node[] = [];
        while (textWalker.nextNode()) nodes.push(textWalker.currentNode);
        for (const node of nodes) {
          if (node.parentElement?.closest('a')) continue;
          let remaining = node.nodeValue || '';
          const fragment = doc.createDocumentFragment();
          let matched = false;
          while (remaining) {
            const candidates = uniqueNames.map(([name, ids]) => ({ name, id: ids[0], at: remaining.indexOf(name) })).filter(x => x.at >= 0).sort((a, b) => a.at - b.at || b.name.length - a.name.length);
            const next = candidates[0];
            if (!next) break;
            matched = true;
            fragment.append(doc.createTextNode(remaining.slice(0, next.at)));
            const link = doc.createElement('a');
            link.href = `/materials/${encodeURIComponent(projectId)}/${encodeURIComponent(next.id)}`;
            link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = next.name;
            fragment.append(link);
            remaining = remaining.slice(next.at + next.name.length);
          }
          if (matched) { fragment.append(doc.createTextNode(remaining)); node.parentNode?.replaceChild(fragment, node); }
        }
      }
    }
  }
  return doc.body.innerHTML;
}

// Remount on switching documents or modes, so typing never replaces the selection.
export default function ProposalDocument({ content, editing, projectId, materialNames, legacyMaterialNames = {}, onChange }: Props) {
  const [initialContent] = useState(content);
  const [html, setHtml] = useState('');
  const editor = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const rendered = marked.parse(initialContent, { async: false, gfm: true });
    const clean = readableDocument(DOMPurify.sanitize(rendered), materialNames, legacyMaterialNames, projectId, editing);
    if (editing && editor.current) editor.current.innerHTML = clean;
    else setHtml(clean);
  }, [initialContent, editing, materialNames, legacyMaterialNames, projectId]);

  if (!editing) return <div className="proposal-document" aria-label="方案初稿内容" dangerouslySetInnerHTML={{ __html: html }} />;
  return <div ref={editor} className="proposal-document proposal-document-edit" role="textbox" aria-label="编辑方案初稿" aria-required="true" aria-multiline="true" contentEditable suppressContentEditableWarning
    onInput={e => onChange(converter.turndown(e.currentTarget.innerHTML))}
    onPaste={e => { e.preventDefault(); document.execCommand('insertText', false, e.clipboardData.getData('text/plain')); }} />;
}
