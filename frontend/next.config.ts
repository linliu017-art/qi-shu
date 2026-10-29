import type { NextConfig } from 'next';
const config: NextConfig = {
  async rewrites() { return [{ source: '/api/:path*', destination: `${process.env.QISHU_BACKEND_URL || 'http://127.0.0.1:8766'}/api/:path*` }]; },
};
export default config;
