'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getAuthHeaders } from '@/lib/auth'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''

const DEFAULT_LANGUAGE = 'zh'
const DEFAULT_THEME = 'light'
const DEFAULT_PROVIDER = 'openai'

type Provider = 'openai' | 'deepseek' | 'minimax'

interface UserInfo {
  id: string
  email: string
  username: string
  full_name: string | null
  bio: string | null
  preferred_language: string
  theme: string
  is_active: boolean
}

export default function ProfilePage() {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const [fullName, setFullName] = useState('')
  const [bio, setBio] = useState('')
  const [preferredLanguage, setPreferredLanguage] = useState<string | null>(null)
  const [theme, setTheme] = useState<string | null>(null)
  const [aiProvider, setAiProvider] = useState<Provider>(() => {
    if (typeof window === 'undefined') return DEFAULT_PROVIDER as Provider
    const stored = window.localStorage.getItem('ai_provider')
    if (stored === 'openai' || stored === 'deepseek' || stored === 'minimax') return stored
    return DEFAULT_PROVIDER as Provider
  })

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
        const data: UserInfo = await res.json()
        setUser(data)
        setFullName(data.full_name ?? '')
        setBio(data.bio ?? '')
        setPreferredLanguage(data.preferred_language ?? DEFAULT_LANGUAGE)
        setTheme(data.theme ?? DEFAULT_THEME)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '无法获取用户信息')
      } finally {
        setLoading(false)
      }
    }
    fetchUser()
  }, [router])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const res = await fetch(`${API_URL}/api/v1/users/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          full_name: fullName || null,
          bio: bio || null,
          preferred_language: preferredLanguage ?? DEFAULT_LANGUAGE,
          theme: theme ?? DEFAULT_THEME,
        }),
      })
      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          router.push('/login')
          return
        }
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `HTTP ${res.status}`)
      }
      const data: UserInfo = await res.json()
      setUser(data)
      window.localStorage.setItem('ai_provider', aiProvider)
      setSuccessMsg('个人信息已更新')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '保存失败，请重试')
    } finally {
      setSaving(false)
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
      <div className="max-w-2xl mx-auto px-6 py-10">
        {loading && (
          <p className="text-gray-500 text-sm" aria-label="loading">加载中…</p>
        )}

        {!loading && (
          <>
            <section className="mb-8">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-3xl font-bold text-gray-800">个人设置</h2>
                <a
                  href="/dashboard"
                  className="text-sm text-blue-600 hover:underline"
                  aria-label="back to dashboard"
                >
                  ← 返回主页
                </a>
              </div>
              <p className="text-gray-500">查看和修改您的账号信息。</p>
            </section>

            <section className="bg-white rounded-xl shadow-sm border p-8">
              {/* Read-only info */}
              <div className="mb-6 space-y-3">
                <div>
                  <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">用户名</span>
                  <p className="text-gray-800 mt-1">{user?.username}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">邮箱</span>
                  <p className="text-gray-800 mt-1">{user?.email}</p>
                </div>
              </div>

              <hr className="mb-6" />

              {/* Editable form */}
              <form onSubmit={handleSave} className="space-y-5">
                <div>
                  <label
                    htmlFor="full_name"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    全名
                  </label>
                  <input
                    id="full_name"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="请输入您的全名"
                  />
                </div>

                <div>
                  <label
                    htmlFor="bio"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    个人简介
                  </label>
                  <textarea
                    id="bio"
                    value={bio}
                    onChange={(e) => setBio(e.target.value)}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                    placeholder="介绍一下您自己…"
                  />
                </div>

                <div>
                  <label
                    htmlFor="preferred_language"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    首选语言
                  </label>
                  <select
                    id="preferred_language"
                    value={preferredLanguage ?? DEFAULT_LANGUAGE}
                    onChange={(e) => setPreferredLanguage(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="zh">中文</option>
                    <option value="en">English</option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="theme"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    界面主题
                  </label>
                  <select
                    id="theme"
                    value={theme ?? DEFAULT_THEME}
                    onChange={(e) => setTheme(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="light">浅色</option>
                    <option value="dark">深色</option>
                  </select>
                </div>

                <div>
                  <span className="block text-sm font-medium text-gray-700 mb-2">AI 提供商</span>
                  <div className="flex items-center gap-6">
                    {(['openai', 'deepseek', 'minimax'] as Provider[]).map((p) => (
                      <label key={p} className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="radio"
                          name="ai_provider"
                          value={p}
                          checked={aiProvider === p}
                          onChange={() => setAiProvider(p)}
                          aria-label={p}
                        />
                        <span className="capitalize text-sm text-gray-700">{p}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {error && (
                  <p className="text-red-500 text-sm" role="alert">⚠️ {error}</p>
                )}

                {successMsg && (
                  <p className="text-green-600 text-sm" role="status">✅ {successMsg}</p>
                )}

                <button
                  type="submit"
                  disabled={saving}
                  className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium disabled:opacity-50"
                  aria-label="save profile"
                >
                  {saving ? '保存中…' : '保存更改'}
                </button>
              </form>
            </section>
          </>
        )}
      </div>
    </main>
  )
}
