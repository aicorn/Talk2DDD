'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''

export default function RegisterPage() {
  const router = useRouter()

  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${API_URL}/api/v1/users/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          email,
          username,
          full_name: fullName || undefined,
          password,
        }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? `HTTP ${res.status}`)
      }

      router.push('/login')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '注册失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 bg-gray-50">
      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
        <h1 className="text-3xl font-bold text-blue-600 mb-2 text-center">🎯 Talk2DDD</h1>
        <h2 className="text-xl font-semibold text-gray-700 mb-6 text-center">注册</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              邮箱
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="your@email.com"
              disabled={loading}
            />
          </div>

          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
              用户名
            </label>
            <input
              id="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="your_username"
              disabled={loading}
            />
          </div>

          <div>
            <label htmlFor="fullName" className="block text-sm font-medium text-gray-700 mb-1">
              姓名（可选）
            </label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="张三"
              disabled={loading}
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              密码
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="至少 8 位"
              disabled={loading}
            />
          </div>

          {error && (
            <p className="text-red-500 text-sm" role="alert">
              ⚠️ {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
          >
            {loading ? '注册中…' : '注册'}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-gray-500">
          已有账号？{' '}
          <a href="/login" className="text-blue-600 hover:underline">
            立即登录
          </a>
        </p>
      </div>
    </main>
  )
}
