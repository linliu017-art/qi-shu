'use client';
import RequiredMark from './RequiredMark';
import { ReactNode, useEffect, useRef, useState } from 'react';

type User = { id: string; username: string; is_admin: boolean; active: boolean };

export default function AuthGate({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<'loading' | 'single' | 'setup' | 'login' | 'ready' | 'error'>('loading');
  const [user, setUser] = useState<User | null>(null);
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!accountOpen) return;
    const dismiss = (event: MouseEvent) => { if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setAccountOpen(false); accountRef.current?.querySelector('button')?.focus(); } };
    document.addEventListener('mousedown', dismiss); document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('mousedown', dismiss); document.removeEventListener('keydown', escape); };
  }, [accountOpen]);
  useEffect(() => {
    fetch('/api/v1/auth/me').then(async response => {
      if (response.status === 404) { setMode('single'); return; }
      if (response.status === 401) { const setup = await fetch('/api/v1/auth/setup-status'); if (!setup.ok) throw new Error(); setMode((await setup.json()).setup_required ? 'setup' : 'login'); return; }
      if (!response.ok) throw new Error();
      setUser(await response.json()); setMode('ready');
    }).catch(() => setMode('error'));
  }, []);
  async function signIn(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      const response = await fetch('/api/v1/auth/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({username:name, password}) });
      setPassword('');
      if (!response.ok) { setMessage('登录失败，请检查账号和密码。'); return; }
      setUser(await response.json()); setMode('ready');
    } catch { setPassword(''); setMessage('无法连接工作台，请稍后重试。'); }
    finally { setBusy(false); }
  }
  async function setup(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      const response = await fetch('/api/v1/auth/setup', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:name,password}) });
      setPassword('');
      if (!response.ok) { const data=await response.json().catch(()=>({})); setMessage(data.error?.message || '初始化失败。'); return; }
      setMode('login'); setMessage('管理员已创建，请使用刚才设置的密码登录。');
    } catch { setPassword(''); setMessage('无法连接工作台，请稍后重试。'); }
    finally { setBusy(false); }
  }
  async function signOut() {
    if (!window.confirm('退出后，未保存的编辑可能丢失。确认退出？')) return;
    try { const response = await fetch('/api/v1/auth/logout', {method:'POST'}); if (!response.ok) throw new Error(); setAccountOpen(false); setUser(null); setMode('login'); }
    catch { setMessage('退出失败，请稍后重试。'); }
  }
  if (mode === 'loading') return <main><p>正在连接工作台…</p></main>;
  if (mode === 'error') return <main><p role="alert">无法连接工作台，请检查本地服务。</p></main>;
  if (mode === 'login' || mode === 'setup') return <main className="auth-page"><div className="auth-brand"><span className="brand-mark">启</span><strong>启枢</strong></div><div className="auth-layout"><div className="auth-welcome"><span className="auth-kicker">QISHU WORKSPACE</span><h1>让每一个想法，<br />都有清晰的方向。</h1><p>从调研资料到方案交付，在启枢有条不紊地开展协作。</p><div className="auth-steps"><span>资料整理</span><span>需求确认</span><span>方案协作</span></div></div><section className="auth-card"><span className="eyebrow">WELCOME TO QISHU</span><h2>{mode==='setup'?'设置本机管理员':'欢迎使用启枢'}</h2><p>{mode==='setup'?'首次使用请创建管理员账号；密码只保存在本机。':'使用管理员开通的账号登录。'}</p><form onSubmit={mode==='setup'?setup:signIn}><label><RequiredMark />账号<input autoComplete="username" placeholder="请输入账号" value={name} onChange={e => setName(e.target.value)} required /></label><label><RequiredMark />密码<input type="password" placeholder="请输入密码" minLength={mode==='setup'?12:1} autoComplete={mode==='setup'?'new-password':'current-password'} value={password} onChange={e => setPassword(e.target.value)} required /></label><button disabled={busy}>{busy?'请稍候…':mode==='setup'?'创建管理员':'登录'}</button></form>{message && <p role="alert">{message}</p>}</section></div></main>;
  // A full navigation from the document editor preserves its beforeunload unsaved-change warning.
  // eslint-disable-next-line @next/next/no-html-link-for-pages
  return <>{user && <div className="session-bar"><div className="account-menu-wrap" ref={accountRef}><button type="button" className="account-trigger" aria-label="账号菜单" aria-expanded={accountOpen} aria-controls="account-menu" onClick={()=>setAccountOpen(!accountOpen)}><span className="account-avatar">{user.username.slice(0,1)}</span><span className="account-trigger-name">{user.username}</span><span aria-hidden="true">⌄</span></button>{accountOpen && <div className="account-menu" id="account-menu"><div className="account-summary"><span className="account-avatar">{user.username.slice(0,1)}</span><div><strong>{user.username}</strong><small>{user.is_admin?'管理员':'成员'}</small></div></div><div className="account-menu-divider"/><a href="/?view=workspace-settings" className="account-menu-item" onClick={event=>{setAccountOpen(false);if(window.location.pathname === '/'){event.preventDefault();window.dispatchEvent(new Event('qishu:workspace-settings'));}}}><span aria-hidden="true">⚙</span>设置</a><div className="account-menu-divider"/><button type="button" className="account-menu-item" onClick={()=>void signOut()}><span aria-hidden="true">↪</span>退出登录</button></div>}</div>{message && <span role="alert">{message}</span>}</div>}{children}</>;
}
