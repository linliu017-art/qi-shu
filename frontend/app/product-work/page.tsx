'use client';
import { useEffect, useState } from 'react';
import ProductWork from '../ProductWork';

type Project = {id:string;name:string;state:string};
export default function ProductWorkPage() {
  const [projects,setProjects]=useState<Project[]>([]);
  const [initial,setInitial]=useState<string|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    const requested=new URLSearchParams(window.location.search).get('project') || '';
    fetch('/api/v1/projects').then(async r=>{if(!r.ok)throw new Error('无法加载项目。');return r.json() as Promise<Project[]>;})
      .then(rows=>{setProjects(rows);setInitial(rows.some(p=>p.id===requested)?requested:'');})
      .catch(e=>setError(e instanceof Error?e.message:'无法加载项目。'));
  },[]);
  // Full navigation preserves the editor's beforeunload warning.
  // eslint-disable-next-line @next/next/no-html-link-for-pages
  return <main className="workspace-main"><header className="workspace-header"><div className="workspace-brand"><span className="brand-mark">启</span><div><span className="eyebrow">QISHU WORKSPACE</span><h1>启枢 <span>工作台</span></h1></div></div></header><a href="/">← 返回工作台</a>{error && <p role="alert">{error}</p>}{initial!==null && <ProductWork projects={projects} initialProject={initial} />}</main>;
}
