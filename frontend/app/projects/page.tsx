'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getAuthHeaders } from '@/lib/auth'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''

const DOC_TYPE_LABELS: Record<string, string> = {
  BUSINESS_REQUIREMENT: '业务需求文档',
  DOMAIN_MODEL: '领域模型文档',
  UBIQUITOUS_LANGUAGE: '通用语言术语表',
  USE_CASES: '用例说明文档',
  TECH_ARCHITECTURE: '技术架构文档',
  PHASE_ICEBREAK: '项目简介',
  PHASE_REQUIREMENT: '业务需求草稿',
  PHASE_DOMAIN_EXPLORE: '领域概念词汇表',
  PHASE_MODEL_DESIGN: '领域模型草稿',
  PHASE_REVIEW_REFINE: '审阅完善记录',
}

interface UserInfo {
  id: string
  email: string
  username: string
  is_active: boolean
}

interface DocumentSummary {
  id: string
  document_type: string
  version_number: number
  is_current: boolean
  created_at: string
  content_preview: string
}

interface ProjectSummary {
  id: string
  name: string
  description: string | null
  domain_name: string | null
  status: string
  created_at: string
  document_count: number
  documents?: DocumentSummary[]
}

export default function ProjectsPage() {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedProject, setExpandedProject] = useState<string | null>(null)
  const [projectDocuments, setProjectDocuments] = useState<Record<string, DocumentSummary[]>>({})
  const [viewingDoc, setViewingDoc] = useState<{ content: string; title: string } | null>(null)
  const [deletingProject, setDeletingProject] = useState<string | null>(null)

  useEffect(() => {
    async function fetchData() {
      try {
        const [userRes, projectsRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/users/me`, { headers: getAuthHeaders() }),
          fetch(`${API_URL}/api/v1/projects`, { headers: getAuthHeaders() }),
        ])

        if (!userRes.ok) {
          if (userRes.status === 401 || userRes.status === 403) {
            router.push('/login')
            return
          }
          const body = await userRes.json().catch(() => ({}))
          throw new Error(body.detail ?? `HTTP ${userRes.status}`)
        }
        setUser(await userRes.json())

        if (projectsRes.ok) {
          setProjects(await projectsRes.json())
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [router])

  async function toggleProject(projectId: string) {
    if (expandedProject === projectId) {
      setExpandedProject(null)
      return
    }
    setExpandedProject(projectId)
    if (!projectDocuments[projectId]) {
      try {
        const res = await fetch(`${API_URL}/api/v1/projects/${projectId}`, {
          headers: getAuthHeaders(),
        })
        if (res.ok) {
          const data: ProjectSummary = await res.json()
          setProjectDocuments((prev) => ({
            ...prev,
            [projectId]: data.documents ?? [],
          }))
        }
      } catch {
        // ignore
      }
    }
  }

  async function viewDocument(projectId: string, docId: string, docType: string) {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/projects/${projectId}/documents/${docId}/content`,
        { headers: getAuthHeaders() }
      )
      if (res.ok) {
        const data = await res.json()
        setViewingDoc({ content: data.content, title: DOC_TYPE_LABELS[docType] ?? docType })
      }
    } catch {
      // ignore
    }
  }

  async function deleteProject(projectId: string) {
    if (!confirm('确认删除此项目及其所有文档？')) return
    setDeletingProject(projectId)
    try {
      const res = await fetch(`${API_URL}/api/v1/projects/${projectId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      if (res.ok || res.status === 204) {
        setProjects((prev) => prev.filter((p) => p.id !== projectId))
        if (expandedProject === projectId) setExpandedProject(null)
      }
    } catch {
      // ignore
    } finally {
      setDeletingProject(null)
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

      {/* Document viewer modal */}
      {viewingDoc && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <h2 className="text-lg font-bold text-gray-800">📄 {viewingDoc.title}</h2>
              <button
                onClick={() => setViewingDoc(null)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                aria-label="close"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              <pre className="whitespace-pre-wrap text-sm text-gray-700 font-mono leading-relaxed">
                {viewingDoc.content}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="max-w-5xl mx-auto px-6 py-10">
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
          <p className="text-gray-500">查看由 AI 对话生成并保存的 DDD 文档项目。</p>
        </section>

        {loading && (
          <p className="text-gray-500 text-sm" aria-label="loading">加载中…</p>
        )}

        {error && (
          <p className="text-red-500 text-sm" role="alert">⚠️ {error}</p>
        )}

        {!loading && projects.length === 0 && (
          <section aria-label="projects list">
            <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
              <div className="text-5xl mb-4">📁</div>
              <h3 className="text-xl font-semibold text-gray-700 mb-2">暂无项目</h3>
              <p className="text-gray-500 mb-6">
                开始与 AI 助手对话并生成 DDD 文档，文档将自动保存到此处。
              </p>
              <a
                href="/chat"
                className="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
                aria-label="start new project"
              >
                开始 AI 对话
              </a>
            </div>
          </section>
        )}

        {!loading && projects.length > 0 && (
          <section aria-label="projects list" className="space-y-4">
            {projects.map((proj) => (
              <div key={proj.id} className="bg-white rounded-xl shadow-sm border overflow-hidden">
                {/* Project header row */}
                <div className="flex items-center justify-between px-6 py-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-800 truncate">{proj.name}</h3>
                    {proj.description && (
                      <p className="text-sm text-gray-500 mt-0.5 truncate">{proj.description}</p>
                    )}
                    <p className="text-xs text-gray-400 mt-1">
                      {proj.document_count} 份文档 · 创建于{' '}
                      {new Date(proj.created_at).toLocaleDateString('zh-CN')}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 ml-4 shrink-0">
                    <button
                      onClick={() => toggleProject(proj.id)}
                      className="px-3 py-1.5 text-sm bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors"
                    >
                      {expandedProject === proj.id ? '收起 ▲' : '查看文档 ▼'}
                    </button>
                    <button
                      onClick={() => deleteProject(proj.id)}
                      disabled={deletingProject === proj.id}
                      className="px-3 py-1.5 text-sm bg-red-50 text-red-500 rounded-lg hover:bg-red-100 transition-colors disabled:opacity-50"
                    >
                      {deletingProject === proj.id ? '删除中…' : '删除'}
                    </button>
                  </div>
                </div>

                {/* Document list (expanded) */}
                {expandedProject === proj.id && (
                  <div className="border-t bg-gray-50 px-6 py-4">
                    {!projectDocuments[proj.id] ? (
                      <p className="text-sm text-gray-400">加载文档中…</p>
                    ) : projectDocuments[proj.id].filter((d) => d.is_current).length === 0 ? (
                      <p className="text-sm text-gray-400">暂无生成文档</p>
                    ) : (
                      <div className="space-y-2">
                        {projectDocuments[proj.id]
                          .filter((d) => d.is_current)
                          .map((doc) => (
                            <div
                              key={doc.id}
                              className="flex items-center justify-between bg-white rounded-lg border px-4 py-3"
                            >
                              <div className="flex-1 min-w-0">
                                <span className="text-sm font-medium text-gray-700">
                                  📄 {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}
                                </span>
                                <span className="ml-2 text-xs text-gray-400">
                                  v{doc.version_number} ·{' '}
                                  {new Date(doc.created_at).toLocaleString('zh-CN')}
                                </span>
                              </div>
                              <button
                                onClick={() => viewDocument(proj.id, doc.id, doc.document_type)}
                                className="ml-4 px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors shrink-0"
                              >
                                查看
                              </button>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </section>
        )}
      </div>
    </main>
  )
}

