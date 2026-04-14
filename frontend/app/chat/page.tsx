'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getAuthHeaders } from '@/lib/auth'

type Provider = 'openai' | 'deepseek' | 'minimax'

interface Message {
  role: 'user' | 'assistant' | 'system'
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
  phase_document: PhaseDocument | null
  tech_stack_preferences: TechStackPreferences | null
  phase_changed?: boolean
}

interface TechChoice {
  name: string
  category: string
  version?: string
  reason?: string
  proficiency: 'FAMILIAR' | 'LEARNING' | 'UNFAMILIAR'
}

interface TechStackPreferences {
  confirmed: boolean
  skipped: boolean
  summary: string
  frontend: TechChoice[]
  backend: TechChoice[]
  database: TechChoice[]
  infrastructure: TechChoice[]
  messaging: TechChoice[]
  custom: TechChoice[]
}

const PHASE_KEYS = [
  'ICEBREAK',
  'REQUIREMENT',
  'DOMAIN_EXPLORE',
  'MODEL_DESIGN',
  'REVIEW_REFINE',
] as const

const PHASE_LABELS: Record<string, string> = {
  ICEBREAK: '破冰引入',
  REQUIREMENT: '需求收集',
  DOMAIN_EXPLORE: '领域探索',
  MODEL_DESIGN: '模型设计',
  REVIEW_REFINE: '审阅完善',
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''
const THINK_PREVIEW_LEN = 60

/**
 * Base timeout (ms) for frontend fetch calls to the agent API.
 * Used for the initial POST /chat/async call; still doubled on timeout retry.
 */
const FETCH_TIMEOUT_BASE_MS = 150_000 // 150 s

/**
 * Timeout (ms) for each individual GET /tasks/{id} poll request.
 * Polls are lightweight so 30 s is more than sufficient.
 */
const POLL_REQUEST_TIMEOUT_MS = 30_000 // 30 s

/**
 * Interval (ms) between consecutive polls while a task is still pending.
 */
const POLL_INTERVAL_MS = 2_000 // 2 s

/**
 * Maximum total time (ms) the frontend will keep polling before giving up.
 * Ten minutes should comfortably cover the longest AI responses.
 */
const MAX_POLLING_MS = 600_000 // 10 min

interface TaskStatusResponse {
  task_id: string
  status: string // "pending" | "completed" | "failed"
  result: AgentChatResponse | null
  error: string | null
}

/**
 * Checks whether a failed API response is an authentication error (401/403).
 * Returns the error message to throw, or null if it's not auth-related.
 */
function parseApiError(res: Response, body: { detail?: string }): string {
  if (res.status === 401 || res.status === 403) {
    // Return a sentinel that callers can recognise
    return '__AUTH_ERROR__'
  }
  return body.detail ?? `HTTP ${res.status}`
}

/**
 * `fetch` wrapper that aborts the request after `timeoutMs` milliseconds.
 * Throws a `DOMException` with name `"TimeoutError"` on expiry so callers
 * can distinguish a timeout from other network failures.
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new DOMException('Request timed out', 'TimeoutError')), timeoutMs)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Poll GET /tasks/{taskId} until the task completes, fails, or the total
 * polling budget (MAX_POLLING_MS) is exhausted.
 *
 * The first poll fires immediately so that fast responses (e.g. in tests or
 * when the backend is already done) are returned without any delay.
 */
async function pollTaskResult(taskId: string): Promise<AgentChatResponse> {
  const deadline = Date.now() + MAX_POLLING_MS

  while (Date.now() < deadline) {
    const res = await fetchWithTimeout(
      `${API_URL}/api/v1/agent/tasks/${taskId}`,
      { headers: getAuthHeaders() },
      POLL_REQUEST_TIMEOUT_MS,
    )

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(parseApiError(res, data))
    }

    const statusData: TaskStatusResponse = await res.json()

    if (statusData.status === 'completed' && statusData.result) {
      return statusData.result
    }

    if (statusData.status === 'failed') {
      throw new Error(statusData.error ?? '任务处理失败，请重试')
    }

    // Still pending — wait before the next poll
    await new Promise<void>((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
  }

  throw new DOMException(
    `轮询超时（等待 ${Math.round(MAX_POLLING_MS / 60_000)} 分钟无响应），请点击「重试」`,
    'TimeoutError',
  )
}

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
  // Fallback using getRandomValues for cryptographic security
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40 // UUID version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80 // UUID variant 1
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'))
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`
}

/** Read `?session=<uuid>` from the current URL if present. */
function getSessionIdFromUrl(): string | null {
  if (typeof window === 'undefined') return null
  return new URLSearchParams(window.location.search).get('session')
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

const TECH_QUICK_PICKS: Record<string, string[]> = {
  frontend: ['React', 'Vue 3', 'Angular', 'Next.js', '小程序', '无前端'],
  backend: ['Java/Spring Boot', 'Python/FastAPI', 'Python/Django', 'Node.js/Express', 'Go', '.NET'],
  database: ['PostgreSQL', 'MySQL', 'MongoDB', 'Oracle', 'SQLite', 'Redis'],
  infrastructure: ['Docker', 'Kubernetes', '阿里云', 'AWS', 'GCP', '裸金属'],
  messaging: ['Kafka', 'RabbitMQ', 'Redis Streams', '不需要'],
}
const TECH_CATEGORY_LABELS: Record<string, string> = {
  frontend: '前端',
  backend: '后端',
  database: '数据库',
  infrastructure: '基础设施',
  messaging: '消息队列',
}

function TechStackPanel({
  preferences,
  onSelectQuickPick,
  onSkip,
}: {
  preferences: TechStackPreferences | null
  onSelectQuickPick: (text: string) => void
  onSkip: () => void
}) {
  if (preferences?.confirmed) return null // already confirmed — don't show picker

  return (
    <div className="mb-2 border rounded-lg bg-blue-50 p-3 text-sm" aria-label="tech stack quick pick">
      <p className="font-medium text-blue-700 mb-2">🛠️ 请选择你们的技术栈偏好（可点击快捷选项或直接输入）</p>
      {Object.entries(TECH_QUICK_PICKS).map(([category, options]) => (
        <div key={category} className="mb-1.5">
          <span className="text-xs text-gray-500 mr-1">{TECH_CATEGORY_LABELS[category] ?? category}：</span>
          {options.map((opt) => (
            <button
              key={opt}
              onClick={() => onSelectQuickPick(`${TECH_CATEGORY_LABELS[category] ?? category}用 ${opt}`)}
              className="mr-1 mb-1 px-2 py-0.5 text-xs rounded-full bg-white border border-blue-200 text-blue-700 hover:bg-blue-100"
            >
              {opt}
            </button>
          ))}
        </div>
      ))}
      <button
        onClick={onSkip}
        className="mt-1 px-3 py-1 text-xs rounded-full bg-gray-100 border border-gray-300 text-gray-600 hover:bg-gray-200"
      >
        跳过，由 AI 帮我推荐
      </button>
    </div>
  )
}

export default function ChatPage() {
  const router = useRouter()
  const [provider] = useState<Provider>(getStoredProvider)
  const [sessionId] = useState<string>(() => getSessionIdFromUrl() ?? generateSessionId())
  const [isResume] = useState<boolean>(() => getSessionIdFromUrl() !== null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null)
  // Agent state
  const [phase, setPhase] = useState<string>('ICEBREAK')
  const [progress, setProgress] = useState<number>(0)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [phaseDocument, setPhaseDocument] = useState<PhaseDocument | null>(null)
  const [showPhaseDoc, setShowPhaseDoc] = useState(false)
  const [techStackPreferences, setTechStackPreferences] = useState<TechStackPreferences | null>(null)
  const [showTechStackPicker, setShowTechStackPicker] = useState(false)
  const [phaseChanging, setPhaseChanging] = useState(false)
  // Fetch timeout in ms; doubles automatically when a retry follows a timeout.
  const fetchTimeoutMs = useRef<number>(FETCH_TIMEOUT_BASE_MS)
  // True when the most recent failure was a timeout; drives the doubling logic.
  const lastErrorWasTimeout = useRef<boolean>(false)

  // Auth guard: redirect to /login when no token is present
  useEffect(() => {
    const headers = getAuthHeaders()
    if (!headers.Authorization) {
      router.push('/login')
    }
  }, [router])

  // When resuming an existing session, restore messages + phase state + phase document
  useEffect(() => {
    if (!isResume) return
    async function restoreSession() {
      setRestoring(true)
      try {
        const headers = { ...getAuthHeaders() }

        // 1. Load message history
        const msgsRes = await fetch(
          `${API_URL}/api/v1/agent/sessions/${sessionId}/messages`,
          { headers }
        )
        if (msgsRes.ok) {
          const msgsData = await msgsRes.json()
          setMessages(
            (msgsData.messages ?? []).map(
              (m: { role: string; content: string }) => ({
                role: m.role as 'user' | 'assistant',
                content: m.content,
              })
            )
          )
        }

        // 2. Load context (phase + progress)
        const ctxRes = await fetch(
          `${API_URL}/api/v1/agent/context/${sessionId}`,
          { headers }
        )
        if (ctxRes.ok) {
          const ctxData = await ctxRes.json()
          const currentPhase: string = ctxData.current_phase ?? 'ICEBREAK'
          setPhase(currentPhase)
          setProgress(ctxData.progress ?? 0)

          // 3. Load the phase document for the current phase
          const pdRes = await fetch(
            `${API_URL}/api/v1/agent/phase-document/${sessionId}/${currentPhase}`,
            { headers }
          )
          if (pdRes.ok) {
            const pdData = await pdRes.json()
            if (pdData.content) {
              setPhaseDocument({
                phase: pdData.phase,
                title: pdData.title,
                content: pdData.content,
                rendered_at: pdData.rendered_at,
                turn_count: pdData.turn_count,
              })
              setShowPhaseDoc(true)
            }
          }
        }
      } catch (err) {
        // Non-critical: session restore failure degrades gracefully to an empty chat.
        // Log for debugging but do not surface an error to the user.
        console.warn('[ChatPage] Failed to restore session:', err)
      } finally {
        setRestoring(false)
      }
    }
    restoreSession()
  // isResume and sessionId are stable constants initialised once from the URL;
  // API_URL is a module-level constant — all are safe to include as deps.
  }, [isResume, sessionId])

  async function sendMessage(overrideText?: string) {
    const trimmed = (overrideText ?? input).trim()
    if (!trimmed || loading || phaseChanging) return

    const userMessage: Message = { role: 'user', content: trimmed }
    const next = [...messages, userMessage]
    setMessages(next)
    setInput('')
    setLoading(true)
    setError(null)

    try {
      // Step 1: submit the chat task and receive a task ID immediately.
      const startRes = await fetchWithTimeout(
        `${API_URL}/api/v1/agent/chat/async`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders(),
          },
          body: JSON.stringify({ session_id: sessionId, message: trimmed, provider }),
        },
        fetchTimeoutMs.current,
      )

      if (!startRes.ok) {
        const data = await startRes.json().catch(() => ({}))
        throw new Error(parseApiError(startRes, data))
      }

      const startData: { task_id: string; status: string } = await startRes.json()

      // Step 2: poll until the task completes (or times out / fails).
      const data: AgentChatResponse = await pollTaskResult(startData.task_id)

      setMessages([...next, { role: 'assistant', content: data.reply }])
      setPhase(data.phase)
      setProgress(data.progress)
      setSuggestions(data.suggestions ?? [])
      setLastFailedMessage(null)
      lastErrorWasTimeout.current = false
      fetchTimeoutMs.current = FETCH_TIMEOUT_BASE_MS
      if (data.tech_stack_preferences !== undefined) {
        setTechStackPreferences(data.tech_stack_preferences)
      }
      // Show tech stack picker in MODEL_DESIGN when not yet confirmed
      if (data.phase === 'MODEL_DESIGN' && data.tech_stack_preferences && !data.tech_stack_preferences.confirmed) {
        setShowTechStackPicker(true)
      } else {
        setShowTechStackPicker(false)
      }
      if (data.phase_document) {
        setPhaseDocument(data.phase_document)
        setShowPhaseDoc(true)
      }
    } catch (err: unknown) {
      const isTimeout =
        err instanceof DOMException && err.name === 'TimeoutError'
      const msg = isTimeout
        ? err.message
        : err instanceof Error
          ? err.message
          : '发生未知错误，请重试'
      if (msg === '__AUTH_ERROR__') {
        router.push('/login')
        return
      }
      lastErrorWasTimeout.current = isTimeout
      setError(msg)
      setLastFailedMessage(trimmed)
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

  /** Re-send the last failed message: remove its bubble then replay it. */
  function retryLastMessage() {
    if (!lastFailedMessage || loading) return
    // If the previous attempt timed out, double the timeout for this retry.
    if (lastErrorWasTimeout.current) {
      fetchTimeoutMs.current = fetchTimeoutMs.current * 2
    }
    // Capture the value before clearing state so sendMessage receives the
    // correct text even after the state updates are batched.
    const msgToRetry = lastFailedMessage
    // Remove the last user bubble that was appended when the message first failed
    setMessages((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].role === 'user') {
        return prev.slice(0, -1)
      }
      return prev
    })
    setError(null)
    setLastFailedMessage(null)
    sendMessage(msgToRetry)
  }

  async function switchPhase(direction: 'next' | 'back') {
    if (phaseChanging || loading) return
    setPhaseChanging(true)
    setError(null)

    // Immediately pre-fetch the new phase document so the right panel updates
    // without waiting for the AI response (which can take 20-30 s).
    const nextIndex = direction === 'next' ? phaseIndex + 1 : phaseIndex - 1
    const nextPhaseKey =
      nextIndex >= 0 && nextIndex < PHASE_KEYS.length ? PHASE_KEYS[nextIndex] : null
    if (nextPhaseKey) {
      try {
        const pdRes = await fetch(
          `${API_URL}/api/v1/agent/phase-document/${sessionId}/${nextPhaseKey}`,
          { headers: getAuthHeaders() },
        )
        if (pdRes.ok) {
          const pdData = await pdRes.json()
          if (pdData.content) {
            setPhaseDocument({
              phase: pdData.phase,
              title: pdData.title,
              content: pdData.content,
              rendered_at: pdData.rendered_at,
              turn_count: pdData.turn_count,
            })
            setShowPhaseDoc(true)
          }
        }
      } catch (e) {
        // Non-critical: the main switch-phase response will update the panel
        console.debug('[switchPhase] pre-fetch phase document failed', e)
      }
    }

    try {
      const res = await fetchWithTimeout(
        `${API_URL}/api/v1/agent/switch-phase`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders(),
          },
          body: JSON.stringify({ session_id: sessionId, direction, provider }),
        },
        fetchTimeoutMs.current,
      )

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(parseApiError(res, data))
      }

      const data: AgentChatResponse = await res.json()

      // Insert a system notification banner followed by the AI intro message
      const phaseLabel = data.phase_label ?? data.phase
      const systemNotice: Message = {
        role: 'system',
        content: `🔄 已切换至「${phaseLabel}」阶段`,
      }
      const aiMsg: Message = { role: 'assistant', content: data.reply }
      setMessages((prev) => [...prev, systemNotice, aiMsg])

      // Update phase state
      setPhase(data.phase)
      setProgress(data.progress)
      setSuggestions(data.suggestions ?? [])
      if (data.tech_stack_preferences !== undefined) {
        setTechStackPreferences(data.tech_stack_preferences)
      }
      if (data.phase === 'MODEL_DESIGN' && data.tech_stack_preferences && !data.tech_stack_preferences.confirmed) {
        setShowTechStackPicker(true)
      } else {
        setShowTechStackPicker(false)
      }
      // Update the phase document panel with the post-switch document (includes knowledge extracted from AI intro)
      if (data.phase_document) {
        setPhaseDocument(data.phase_document)
      }
      setShowPhaseDoc(true)
    } catch (err: unknown) {
      const isTimeout = err instanceof DOMException && err.name === 'TimeoutError'
      const msg = isTimeout
        ? `阶段切换请求超时（等待 ${Math.round(fetchTimeoutMs.current / 1000)} 秒无响应），请重试`
        : err instanceof Error
          ? err.message
          : '阶段切换失败，请重试'
      if (msg === '__AUTH_ERROR__') {
        router.push('/login')
        return
      }
      setError(msg)
    } finally {
      setPhaseChanging(false)
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
        {/* Previous phase button */}
        <button
          onClick={() => switchPhase('back')}
          disabled={phaseChanging || loading || phaseIndex === 0}
          className="shrink-0 flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg bg-white border border-gray-300 text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label={phaseChanging ? '切换阶段中，请稍候' : '上一阶段'}
          aria-busy={phaseChanging}
          title="切换到上一阶段"
        >
          {phaseChanging ? <span aria-hidden="true">⏳</span> : <span aria-hidden="true">←</span>} 上一阶段
        </button>

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

        {/* Next phase button */}
        <button
          onClick={() => switchPhase('next')}
          disabled={phaseChanging || loading || phaseIndex === PHASE_KEYS.length - 1}
          className="shrink-0 flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg bg-white border border-gray-300 text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label={phaseChanging ? '切换阶段中，请稍候' : '下一阶段'}
          aria-busy={phaseChanging}
          title="切换到下一阶段"
        >
          下一阶段 {phaseChanging ? <span aria-hidden="true">⏳</span> : <span aria-hidden="true">→</span>}
        </button>

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
            {restoring && (
              <p className="text-gray-400 text-sm text-center mt-8">正在恢复对话历史…</p>
            )}
            {!restoring && messages.length === 0 && (
              <p className="text-gray-400 text-sm text-center mt-8">发送消息开始对话 ✨</p>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${
                  msg.role === 'system'
                    ? 'justify-center'
                    : msg.role === 'user'
                    ? 'justify-end'
                    : 'justify-start'
                }`}
              >
                {msg.role === 'system' ? (
                  // Phase-switch system notification banner
                  <div className="w-full text-center py-1">
                    <span className="inline-block px-4 py-1 text-xs text-blue-600 bg-blue-50 border border-blue-200 rounded-full font-medium">
                      {msg.content}
                    </span>
                  </div>
                ) : msg.role === 'user' ? (
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

          {/* Tech stack quick-pick panel — shown in MODEL_DESIGN before confirmation */}
          {showTechStackPicker && (
            <TechStackPanel
              preferences={techStackPreferences}
              onSelectQuickPick={(text) => sendMessage(text)}
              onSkip={() => sendMessage('/techstack skip')}
            />
          )}

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
            <div className="flex items-center gap-2 mb-2 flex-wrap" role="alert">
              <p className="text-red-500 text-sm">⚠️ {error}</p>
              {lastFailedMessage && (
                <button
                  onClick={retryLastMessage}
                  disabled={loading}
                  className="flex items-center gap-1 px-3 py-1 text-xs bg-red-50 text-red-600 border border-red-200 rounded-full hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed"
                  aria-label="retry last message"
                >
                  🔄 重试
                </button>
              )}
            </div>
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
              disabled={loading || phaseChanging}
              aria-label="message input"
            />
            <button
              onClick={() => sendMessage()}
              disabled={loading || phaseChanging || !input.trim()}
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
              <div className="px-4 py-2 border-t text-xs text-gray-400 shrink-0 flex items-center justify-between">
                <span>
                  第 {phaseDocument.turn_count} 轮 ·{' '}
                  {new Date(phaseDocument.rendered_at).toLocaleTimeString()}
                </span>
                <a
                  href="/projects"
                  className="text-blue-500 hover:text-blue-700 hover:underline"
                  aria-label="查看我的项目"
                >
                  查看我的项目 →
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  )
}
