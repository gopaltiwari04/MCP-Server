import type { NextConfig } from "next";

const orchestratorUrl = (process.env.ORCHESTRATOR_INTERNAL_URL || "http://127.0.0.1:8001").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/orchestrator/:path*",
        destination: `${orchestratorUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
