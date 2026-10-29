'use client';
import {useEffect,useState} from 'react';
type ImageRow={id:string;filename:string;created_at:string};
async function load<T>(path:string,init?:RequestInit):Promise<T>{const r=await fetch('/api/v1'+path,init);if(!r.ok){const d=await r.json();throw Error(d.error?.message||'操作失败')}return r.json() as Promise<T>}
export default function CompetitorImages({id,version,editable,blocked,onDirtyChange,onUpdated}:{id:string;version:number;editable:boolean;blocked:boolean;onDirtyChange:(v:boolean)=>void;onUpdated:(row:unknown)=>void}){
 const [images,setImages]=useState<ImageRow[]>([]),[file,setFile]=useState<File|null>(null),[revision,setRevision]=useState(0),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;load<ImageRow[]>(`/product-work/${id}/images`).then(rows=>{if(active)setImages(rows)}).catch(e=>{if(active)setMessage(e.message)});return()=>{active=false}},[id,version]);
 async function upload(){if(!file)return;setBusy(true);try{const form=new FormData();form.set('file',file);form.set('version',String(version));const row=await load(`/product-work/${id}/images`,{method:'POST',body:form});setFile(null);setRevision(x=>x+1);onDirtyChange(false);onUpdated(row);setMessage('截图已保存。')}catch(e){setMessage(e instanceof Error?e.message:'上传失败')}finally{setBusy(false)}}
 return <section><h3>竞品截图</h3><p>截图由用户提供，不代表系统实测；不会自动发送给模型。支持 PNG、JPEG、WebP，单张不超过 5 MiB。</p>{images.map(x=><div key={x.id}><a href={`/api/v1/product-work/${id}/images/${x.id}`} target="_blank" rel="noreferrer">{x.filename}</a>
{/* eslint-disable-next-line @next/next/no-img-element */}
<img src={`/api/v1/product-work/${id}/images/${x.id}`} alt={x.filename} style={{display:'block',maxWidth:'100%',maxHeight:240}} /></div>)}{editable&&<><label>选择截图<input key={revision} type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>{const chosen=e.target.files?.[0]||null;setFile(chosen);onDirtyChange(!!chosen)}}/></label><button disabled={busy||blocked||!file} onClick={()=>void upload()}>上传截图</button>{blocked&&<p>请先处理报告或对比中未保存的内容。</p>}</>}{message&&<p role="status">{message}</p>}</section>
}
