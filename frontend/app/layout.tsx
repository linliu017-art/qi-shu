import type { Metadata } from 'next';
import './globals.css';
import AuthGate from './AuthGate';
export const metadata: Metadata = { title: '启枢 · 工作台', description: '从资料到方案，清晰协作' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body><AuthGate>{children}</AuthGate></body></html>;
}
