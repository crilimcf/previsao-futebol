/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    // habilita logos da API-Football (teams/players/leagues)
    remotePatterns: [
      { protocol: "https", hostname: "media.api-sports.io" },
      { protocol: "https", hostname: "media-*.api-sports.io" },
      { protocol: "https", hostname: "*.api-sports.io" },
    ],
  },
};

module.exports = nextConfig;
