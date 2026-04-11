'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getAuthHeaders } from '@/lib/auth'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''

interface UserInfo {
  id: string
  email: string
  username: string
  is_active: boolean
}

export default function ProjectsPage() {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchUser() {
      try {
        const res = await fetch(`${API_URL}/api/v1/users/me`, {
          headers: getAuthHeaders(),
        })
        if (!res.ok) {
          if (res.status === 401 || res.status === 403) {
            router.push('/login')
            return
          }
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail ?? `HTTP ${res.status}`)
        }
        const data = await res.json()
        setUser(data)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '无法获取用户信息')
      } finally {
        setLoading(false)
      }
    }
    fetchUser()
  }, [])

  function handleLogout() {
    document.cookie = 'access_token=; path=/; max-age=0; SameSite=Lax'
    router.push('/login')
  }

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-blue-600">🎯 Talk2DDD</h1>
          <div className="flex items-center gap-4">
            {user && (
              <span className="text-sm text-gray-600">
                👤 {user.username ?? user.email}
              </span>
            )}
            <button
              onClick={handleLogout}
              className="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
              aria-label="logout"
            >
              退出登录
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-6 py-10">
        {loading && (
          <p className="text-gray-500 text-sm" aria-label="loading">加载中…</p>
        )}

        {error && (
          <p className="text-red-500 text-sm" role="alert">⚠️ {error}</p>
        )}

        {!loading && (
          <>
            <section className="mb-8">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-3xl font-bold text-gray-800">我的项目</h2>
                <a
                  href="/dashboard"
                  className="text-sm text-blue-600 hover:underline"
                  aria-label="back to dashboard"
                >
                  ← 返回主页
                </a>
              </div>
              <p className="text-gray-500">管理您的 DDD 项目和文档。</p>
            </section>

            {/* Projects placeholder */}
            <section aria-label="projects list">
              <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
                <div className="text-5xl mb-4">📁</div>
                <h3 className="text-xl font-semibold text-gray-700 mb-2">暂无项目</h3>
                <p className="text-gray-500 mb-6">开始创建您的第一个 DDD 项目，与 AI 助手协作生成文档。</p>
                <a
                  href="/chat"
                  className="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
                  aria-label="start new project"
                >
                  开始新项目
                </a>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  )
}
