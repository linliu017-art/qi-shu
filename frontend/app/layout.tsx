import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'qi-shu · 工作台', description: '从资料整理需求' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
