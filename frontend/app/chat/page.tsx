'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getAuthHeaders } from '@/lib/auth'

type Provider = 'openai' | 'deepseek' | 'minimax'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface PhaseDocument {
  phase: string
  title: string
  content: string
  rendered_at: string
  turn_count: number
}

interface AgentChatResponse {
  reply: string
  session_id: string
  phase: string
  phase_label: string
  progress: number
  suggestions: string[]
  extracted_concepts: Array<{ name: string; type: string; confidence: number }>
  stale_documents: string[]
  pending_documents: string[]
  phase_document: PhaseDocument | null
}

const PHASE_KEYS = [
  'ICEBREAK',
  'REQUIREMENT',
  'DOMAIN_EXPLORE',
  'MODEL_DESIGN',
  'DOC_GENERATE',
  'REVIEW_REFINE',
] as const

const PHASE_LABELS: Record<string, string> = {
  ICEBREAK: '破冰引入',
  REQUIREMENT: '需求收集',
  DOMAIN_EXPLORE: '领域探索',
  MODEL_DESIGN: '模型设计',
  DOC_GENERATE: '文档生成',
  REVIEW_REFINE: '审阅完善',
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''
const THINK_PREVIEW_LEN = 60

function getStoredProvider(): Provider {
  if (typeof window === 'undefined') return 'openai'
  const stored = window.localStorage.getItem('ai_provider')
  if (stored === 'openai' || stored === 'deepseek' || stored === 'minimax') return stored
  return 'openai'
}

function generateSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // Fallback for environments without crypto.randomUUID
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/** Split assistant content into optional <think> block + main reply */
function parseContent(content: string): { thinking: string | null; reply: string } {
  const match = content.match(/^<think>([\s\S]*?)<\/think>([\s\S]*)$/i)
  if (match) {
    return { thinking: match[1].trim(), reply: match[2].trim() }
  }
  return { thinking: null, reply: content }
}

function ThinkBlock({ thinking }: { thinking: string }) {
  const [open, setOpen] = useState(false)
  const preview =
    thinking.length > THINK_PREVIEW_LEN
      ? thinking.slice(0, THINK_PREVIEW_LEN) + '…'
      : thinking
  return (
    <div className="mb-2 rounded border border-gray-200 bg-gray-50 text-xs text-gray-400">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-1.5 text-left hover:bg-gray-100 rounded"
        aria-expanded={open}
      >
        <span className="truncate flex-1 mr-2">{open ? '思考过程' : preview}</span>
        <span className="shrink-0">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="px-3 pb-2 whitespace-pre-wrap leading-relaxed">{thinking}</div>}
    </div>
  )
}

export default function ChatPage() {
  const router = useRouter()
  const [provider] = useState<Provider>(getStoredProvider)
  const [sessionId] = useState<string>(generateSessionId)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Agent state
  const [phase, setPhase] = useState<string>('ICEBREAK')
  const [progress, setProgress] = useState<number>(0)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [phaseDocument, setPhaseDocument] = useState<PhaseDocument | null>(null)
  const [showPhaseDoc, setShowPhaseDoc] = useState(false)

  async function sendMessage(overrideText?: string) {
    const trimmed = (overrideText ?? input).trim()
    if (!trimmed || loading) return

    const userMessage: Message = { role: 'user', content: trimmed }
    const next = [...messages, userMessage]
    setMessages(next)
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${API_URL}/api/v1/agent/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ session_id: sessionId, message: trimmed, provider }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? `HTTP ${res.status}`)
      }

      const data: AgentChatResponse = await res.json()
      setMessages([...next, { role: 'assistant', content: data.reply }])
      setPhase(data.phase)
      setProgress(data.progress)
      setSuggestions(data.suggestions ?? [])
      if (data.phase_document) {
        setPhaseDocument(data.phase_document)
        setShowPhaseDoc(true)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '发生未知错误，请重试')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const phaseIndex = PHASE_KEYS.indexOf(phase as (typeof PHASE_KEYS)[number])

  return (
    <main className="flex flex-col h-screen">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-white shrink-0">
        <h1 className="text-xl font-bold text-blue-600">🤖 Talk2DDD AI 助手</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPhaseDoc((v) => !v)}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 border rounded-lg hover:bg-gray-100"
            aria-label="toggle phase document"
          >
            📋 {showPhaseDoc ? '收起文档' : '查看阶段文档'}
          </button>
          <button
            onClick={() => router.push('/dashboard')}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 border rounded-lg hover:bg-gray-100"
          >
            ← 返回 Dashboard
          </button>
        </div>
      </div>

      {/* Phase navigation bar */}
      <div className="flex items-center gap-1.5 px-4 py-2 bg-gray-50 border-b overflow-x-auto shrink-0" aria-label="phase navigation">
        {PHASE_KEYS.map((p, i) => (
          <span
            key={p}
            className={`px-2.5 py-0.5 text-xs rounded-full whitespace-nowrap font-medium ${
              p === phase
                ? 'bg-blue-600 text-white'
                : i < phaseIndex
                ? 'bg-green-100 text-green-700'
                : 'bg-gray-100 text-gray-400'
            }`}
          >
            P{i + 1} {PHASE_LABELS[p]}
          </span>
        ))}
        <div className="ml-auto flex items-center gap-2 shrink-0 pl-2">
          <div className="w-20 h-1.5 bg-gray-200 rounded-full overflow-hidden" aria-label="progress bar">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-300"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
          <span className="text-xs text-gray-500">{Math.round(progress * 100)}%</span>
        </div>
      </div>

      {/* Body: chat column + optional phase document panel */}
      <div className="flex flex-1 min-h-0">
        {/* Chat column */}
        <div className="flex flex-col flex-1 min-w-0 p-4">
          {/* Chat history */}
          <div
            className="flex-1 overflow-y-auto border rounded-lg p-4 mb-3 space-y-3 bg-gray-50"
            aria-label="chat history"
          >
            {messages.length === 0 && (
              <p className="text-gray-400 text-sm text-center mt-8">发送消息开始对话 ✨</p>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'user' ? (
                  <div className="max-w-[75%] rounded-lg px-4 py-2 text-sm bg-blue-600 text-white">
                    {msg.content}
                  </div>
                ) : (
                  (() => {
                    const { thinking, reply } = parseContent(msg.content)
                    return (
                      <div className="max-w-[75%]">
                        {thinking && <ThinkBlock thinking={thinking} />}
                        <div className="rounded-lg px-4 py-2 text-sm bg-white border text-gray-800 prose prose-sm max-w-none">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{reply}</ReactMarkdown>
                        </div>
                      </div>
                    )
                  })()
                )}
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-white border rounded-lg px-4 py-2 text-sm text-gray-400">
                  思考中…
                </div>
              </div>
            )}
          </div>

          {/* Suggestion chips */}
          {suggestions.length > 0 && !loading && (
            <div className="flex flex-wrap gap-1 mb-2" aria-label="suggestions">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(s)}
                  className="px-2 py-1 text-xs bg-blue-50 text-blue-600 rounded-full border border-blue-200 hover:bg-blue-100"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {error && (
            <p className="text-red-500 text-sm mb-2" role="alert">
              ⚠️ {error}
            </p>
          )}

          {/* Input area */}
          <div className="flex gap-2">
            <textarea
              className="flex-1 border rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
              rows={2}
              placeholder="输入消息，按 Enter 发送（Shift+Enter 换行）"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              aria-label="message input"
            />
            <button
              onClick={() => sendMessage()}
              disabled={loading || !input.trim()}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
              aria-label="send message"
            >
              发送
            </button>
          </div>
        </div>

        {/* Phase document side panel */}
        {showPhaseDoc && (
          <div
            className="w-96 border-l bg-white flex flex-col min-h-0 shrink-0"
            aria-label="phase document panel"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
              <h2 className="text-sm font-semibold text-gray-700">
                📄 {phaseDocument?.title ?? '阶段文档'}
              </h2>
              <button
                onClick={() => setShowPhaseDoc(false)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                aria-label="close phase document"
              >
                ×
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 prose prose-sm max-w-none text-gray-700">
              {phaseDocument ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {phaseDocument.content}
                </ReactMarkdown>
              ) : (
                <p className="text-gray-400 text-sm">暂无阶段文档，请继续对话。</p>
              )}
            </div>
            {phaseDocument && (
              <div className="px-4 py-2 border-t text-xs text-gray-400 shrink-0">
                第 {phaseDocument.turn_count} 轮 ·{' '}
                {new Date(phaseDocument.rendered_at).toLocaleTimeString()}
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  )
}
