'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

type Provider = 'openai' | 'deepseek' | 'minimax'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''

export default function ChatPage() {
  const router = useRouter()
  const [provider, setProvider] = useState<Provider>('openai')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  async function sendMessage() {
    const trimmed = input.trim()
    if (!trimmed || loading) return

    const userMessage: Message = { role: 'user', content: trimmed }
    const next = [...messages, userMessage]
    setMessages(next)
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${API_URL}/api/v1/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next, provider }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? `HTTP ${res.status}`)
      }

      const data = await res.json()
      setMessages([...next, { role: 'assistant', content: data.reply }])
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

  return (
    <main className="flex flex-col h-screen max-w-3xl mx-auto p-4">
      {/* Header: title + back button */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-blue-600">🤖 Talk2DDD AI 助手</h1>
        <button
          onClick={() => router.push('/dashboard')}
          className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 border rounded-lg hover:bg-gray-100"
        >
          ← 返回 Dashboard
        </button>
      </div>

      {/* Collapsible provider selector */}
      <div className="mb-4 border rounded-lg overflow-hidden">
        <button
          onClick={() => setSettingsOpen((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium text-gray-700 bg-gray-50 hover:bg-gray-100"
        >
          <span>AI 设置</span>
          <span>{settingsOpen ? '▲' : '▼'}</span>
        </button>
        {settingsOpen && (
          <div className="flex items-center gap-4 px-4 py-3 bg-white">
            <span className="text-sm font-medium text-gray-700">AI 提供商：</span>
            {(['openai', 'deepseek', 'minimax'] as Provider[]).map((p) => (
              <label key={p} className="flex items-center gap-1 cursor-pointer">
                <input
                  type="radio"
                  name="provider"
                  value={p}
                  checked={provider === p}
                  onChange={() => setProvider(p)}
                  aria-label={p}
                />
                <span className="capitalize text-sm">{p}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Chat history */}
      <div
        className="flex-1 overflow-y-auto border rounded-lg p-4 mb-4 space-y-3 bg-gray-50"
        aria-label="chat history"
      >
        {messages.length === 0 && (
          <p className="text-gray-400 text-sm text-center mt-8">
            发送消息开始对话 ✨
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[75%] rounded-lg px-4 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border text-gray-800'
              }`}
            >
              {msg.content}
            </div>
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
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
          aria-label="send message"
        >
          发送
        </button>
      </div>
    </main>
  )
}
