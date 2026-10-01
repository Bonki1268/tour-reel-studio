import type { NextConfig } from "next";

// 前端一律呼叫同源 /api/*，由 Next.js 轉到後端（spec 0015 待決事項 2）
const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiBase}/:path*` }];
  },
};

export default nextConfig;
