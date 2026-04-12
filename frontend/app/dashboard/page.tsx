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

interface ConversationSummary {
  session_id: string
  title: string | null
  phase: string
  phase_label: string
  turn_count: number
  updated_at: string
}

export default function DashboardPage() {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sessions, setSessions] = useState<ConversationSummary[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

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

  // Fetch session list once the user is confirmed authenticated
  useEffect(() => {
    if (!user) return
    async function fetchSessions() {
      setSessionsLoading(true)
      try {
        const res = await fetch(`${API_URL}/api/v1/agent/sessions`, {
          headers: getAuthHeaders(),
        })
        if (res.ok) {
          const data = await res.json()
          setSessions(data.conversations ?? [])
        }
      } catch {
        // Non-critical: silently ignore session list errors
      } finally {
        setSessionsLoading(false)
      }
    }
    fetchSessions()
  }, [user])

  async function handleDeleteSession(sessionId: string) {
    setDeletingId(sessionId)
    try {
      const res = await fetch(`${API_URL}/api/v1/agent/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      if (res.ok) {
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId))
      }
    } catch {
      // Silently ignore network errors
    } finally {
      setDeletingId(null)
    }
  }

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
              <h2 className="text-3xl font-bold text-gray-800 mb-2">
                欢迎回来{user ? `，${user.username ?? user.email}` : ''}！
              </h2>
              <p className="text-gray-500">开始使用 AI 助手来创建和管理您的 DDD 文档。</p>
            </section>

            {/* Quick actions */}
            <section aria-label="quick actions">
              <h3 className="text-lg font-semibold text-gray-700 mb-4">快速入口</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <a
                  href="/chat"
                  className="block bg-white rounded-xl shadow-sm border p-6 hover:shadow-md transition-shadow"
                  aria-label="go to chat"
                >
                  <div className="text-3xl mb-3">🤖</div>
                  <h4 className="text-base font-semibold text-gray-800 mb-1">AI 对话</h4>
                  <p className="text-sm text-gray-500">与 AI 助手对话，生成 DDD 文档</p>
                </a>

                <a
                  href="/projects"
                  className="block bg-white rounded-xl shadow-sm border p-6 hover:shadow-md transition-shadow"
                  aria-label="go to projects"
                >
                  <div className="text-3xl mb-3">📁</div>
                  <h4 className="text-base font-semibold text-gray-800 mb-1">我的项目</h4>
                  <p className="text-sm text-gray-500">管理您的 DDD 项目和文档</p>
                </a>

                <a
                  href="/profile"
                  className="block bg-white rounded-xl shadow-sm border p-6 hover:shadow-md transition-shadow"
                  aria-label="go to profile"
                >
                  <div className="text-3xl mb-3">⚙️</div>
                  <h4 className="text-base font-semibold text-gray-800 mb-1">个人设置</h4>
                  <p className="text-sm text-gray-500">查看和修改账号信息</p>
                </a>
              </div>
            </section>

            {/* Session history */}
            <section className="mt-10" aria-label="session history">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-700">历史对话</h3>
              </div>

              {sessionsLoading && (
                <p className="text-gray-400 text-sm" aria-label="sessions loading">加载历史对话中…</p>
              )}

              {!sessionsLoading && sessions.length === 0 && (
                <p className="text-gray-400 text-sm">暂无历史对话，点击上方「AI 对话」开始。</p>
              )}

              {!sessionsLoading && sessions.length > 0 && (
                <ul className="space-y-3" aria-label="session list">
                  {sessions.map((s) => (
                    <li
                      key={s.session_id}
                      className="flex items-center justify-between bg-white rounded-xl border px-5 py-4 shadow-sm"
                      aria-label={`session ${s.session_id}`}
                    >
                      <div className="min-w-0 flex-1 mr-4">
                        <p className="text-sm font-medium text-gray-800 truncate">
                          {s.title ?? 'AI Agent 对话'}
                        </p>
                        <p className="text-xs text-gray-400 mt-0.5">
                          {s.phase_label} · 第 {s.turn_count} 轮 ·{' '}
                          {new Date(s.updated_at).toLocaleString('zh-CN', {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <a
                          href={`/chat?session=${s.session_id}`}
                          className="px-3 py-1 text-xs bg-blue-50 text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-100"
                          aria-label={`resume session ${s.session_id}`}
                        >
                          继续
                        </a>
                        <button
                          onClick={() => handleDeleteSession(s.session_id)}
                          disabled={deletingId === s.session_id}
                          className="px-3 py-1 text-xs bg-red-50 text-red-500 border border-red-200 rounded-lg hover:bg-red-100 disabled:opacity-50"
                          aria-label={`delete session ${s.session_id}`}
                        >
                          {deletingId === s.session_id ? '删除中…' : '删除'}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  )
}
