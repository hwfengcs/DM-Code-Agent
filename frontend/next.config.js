/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 配置后端 API 代理
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:5000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
