import type { NextConfig } from "next";
import path from "path";

// Sent with every page. A full script Content-Security-Policy needs a nonce on
// Next.js's inline scripts, so this policy only blocks framing, plugins and
// redirected forms; the other headers cover sniffing, referrers and HTTPS.
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  {
    key: "Content-Security-Policy",
    value:
      "frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'",
  },
];

const nextConfig: NextConfig = {
  // VERCEL_ENV is server-only by default. Expose only the environment label
  // so shared auth configuration can fail closed in Preview builds.
  env: {
    NEXT_PUBLIC_NFNIT_VERCEL_ENV: process.env.VERCEL_ENV ?? "local",
  },
  turbopack: {
    root: path.resolve(__dirname, ".."),
  },
  poweredByHeader: false,
  async headers() {
    return [
      { source: "/:path*", headers: SECURITY_HEADERS },
      // Demo models are stored gzipped (backend/demos/build.py): Vercel does
      // not compress GLB files, and gzip makes them about 70% smaller. The
      // browser decodes them, so the viewer still receives a plain GLB.
      {
        source: "/demos/:slug/:file*.glb.gz",
        headers: [
          { key: "Content-Type", value: "model/gltf-binary" },
          { key: "Content-Encoding", value: "gzip" },
        ],
      },
    ];
  },
};

export default nextConfig;
