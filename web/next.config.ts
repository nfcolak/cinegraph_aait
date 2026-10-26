import type { NextConfig } from "next";

// The agent runs on a separate Python server (Modal in production). The browser only
// talks to /api on this origin; Next.js proxies it, so no CORS setup is needed.
const API_URL = (process.env.CINEGRAPH_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
