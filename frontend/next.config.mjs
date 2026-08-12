/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig = {
  // The browser only ever talks to this origin; /api/* is proxied to FastAPI server-side.
  // One origin means no CORS to configure, no backend URL baked into client bundles, and
  // the same code path works identically under `npm run dev` and under Docker Compose
  // (where BACKEND_URL points at the backend service instead of localhost).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  // Anthropic may spend extra time compiling a new structured-output grammar on the
  // first request for a schema. Keep the proxy open for that documented cold path;
  // subsequent requests use Anthropic's cached grammar and are much faster.
  experimental: {
    proxyTimeout: 600_000,
  },
  output: "standalone",
};

export default nextConfig;
