/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    return [
      {
        // Proxy all /api/* requests to the backend (server-side).
        // :path* captures the full sub-path after /api/, e.g. /api/v1/users/login.
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
