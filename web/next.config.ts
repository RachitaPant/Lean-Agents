import type { NextConfig } from "next";

// In production, Vercel Services route /api/* to the Python service (see ../vercel.json).
// In local dev, proxy /api/* to the FastAPI server: uvicorn server.app:app --port 8000
const nextConfig: NextConfig = {
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    const api = process.env.API_DEV_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default nextConfig;
