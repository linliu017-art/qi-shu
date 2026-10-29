'use client';
import {useEffect,useState} from 'react';
type Event={action:string;actor:string;created_at:string;object_type:string};
export default function ProjectActivity({projectId}:{projectId:string}) {
  const [events,setEvents]=useState<Event[]|null>(null);const [error,setError]=useState('');
  useEffect(()=>{const c=new AbortController();fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/activity`,{signal:c.signal}).then(async r=>{if(!r.ok)throw new Error('无法读取操作记录。');return r.json() as Promise<Event[]>;}).then(setEvents).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>c.abort();},[projectId]);
  return <details><summary>项目操作记录</summary><p>只显示系统已记录的操作，早期未记录的动作无法补回。</p>{error&&<p role="alert">{error}</p>}{events===null&&!error&&<p>正在读取……</p>}{events?.length===0&&<p>暂无可显示记录。</p>}{events?.map((item,i)=><p key={`${item.created_at}-${i}`}>{new Date(item.created_at).toLocaleString('zh-CN')} · {item.actor} · {item.object_type}：{item.action}</p>)}</details>;
}
