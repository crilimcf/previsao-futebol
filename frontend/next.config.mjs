/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "media.api-sports.io" },
      { protocol: "https", hostname: "media-1.api-sports.io" },
      { protocol: "https", hostname: "media-2.api-sports.io" },
      { protocol: "https", hostname: "media-3.api-sports.io" },
      { protocol: "https", hostname: "**.api-sports.io" }, // barbatruque p/ variações
    ],
  },
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
