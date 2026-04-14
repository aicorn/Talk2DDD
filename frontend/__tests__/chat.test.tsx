/**
 * Tests for the AI Chat page (frontend/app/chat/page.tsx).
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChatPage from '../app/chat/page'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

// Provide a valid auth token by default; individual tests override as needed.
const mockGetAuthHeaders = jest.fn<Record<string, string>, []>(() => ({ Authorization: 'Bearer test-token' }))
jest.mock('../lib/auth', () => ({
  getAuthHeaders: () => mockGetAuthHeaders(),
}))

// Silence fetch-not-defined warnings in jsdom
global.fetch = jest.fn()

// Deterministic session ID in tests
const MOCK_SESSION_ID = '00000000-0000-4000-8000-000000000001'
const MOCK_TASK_ID = 'test-task-00000000-0000-4000-8000-000000000001'
Object.defineProperty(globalThis, 'crypto', {
  value: { randomUUID: () => MOCK_SESSION_ID },
  writable: true,
})

/** Minimal agent response matching AgentChatResponse shape */
function agentReply(reply: string, overrides: Record<string, unknown> = {}) {
  return {
    reply,
    session_id: MOCK_SESSION_ID,
    phase: 'ICEBREAK',
    phase_label: '破冰引入',
    progress: 0.0,
    suggestions: [],
    extracted_concepts: [],
    requirement_changes: [],
    stale_documents: [],
    pending_documents: [],
    phase_document: null,
    ...overrides,
  }
}

/**
 * Set up the two fetch mocks needed for a successful async chat round-trip:
 *  1. POST /chat/async  → { task_id, status: "pending" }
 *  2. GET  /tasks/{id}  → { task_id, status: "completed", result: agentReply(...) }
 */
function mockAsyncChat(reply: string, replyOverrides: Record<string, unknown> = {}) {
  ;(global.fetch as jest.Mock)
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ task_id: MOCK_TASK_ID, status: 'pending' }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        task_id: MOCK_TASK_ID,
        status: 'completed',
        result: agentReply(reply, replyOverrides),
        error: null,
      }),
    })
}

beforeEach(() => {
  jest.clearAllMocks()
  // Default: authenticated
  mockGetAuthHeaders.mockReturnValue({ Authorization: 'Bearer test-token' })
})

describe('ChatPage', () => {
  it('redirects to /login when no auth token is present', () => {
    mockGetAuthHeaders.mockReturnValue({})
    render(<ChatPage />)
    expect(mockPush).toHaveBeenCalledWith('/login')
  })

  it('renders the heading', () => {
    render(<ChatPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Talk2DDD AI 助手')
  })

  it('renders the message input textarea', () => {
    render(<ChatPage />)
    expect(screen.getByRole('textbox', { name: 'message input' })).toBeInTheDocument()
  })

  it('renders the send button', () => {
    render(<ChatPage />)
    expect(screen.getByRole('button', { name: 'send message' })).toBeInTheDocument()
  })

  it('send button is disabled when input is empty', () => {
    render(<ChatPage />)
    expect(screen.getByRole('button', { name: 'send message' })).toBeDisabled()
  })

  it('send button is enabled when input has text', () => {
    render(<ChatPage />)
    const input = screen.getByRole('textbox', { name: 'message input' })
    fireEvent.change(input, { target: { value: 'Hello' } })
    expect(screen.getByRole('button', { name: 'send message' })).not.toBeDisabled()
  })

  it('sends a message and displays the reply', async () => {
    mockAsyncChat('Hi there!')

    render(<ChatPage />)
    const input = screen.getByRole('textbox', { name: 'message input' })
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() => {
      expect(screen.getByText('Hello')).toBeInTheDocument()
      expect(screen.getByText('Hi there!')).toBeInTheDocument()
    })
  })

  it('shows an error message when the API call fails', async () => {
    // The initial POST /chat/async fails — no poll mock needed.
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'AI provider error: connection refused' }),
    })

    render(<ChatPage />)
    const input = screen.getByRole('textbox', { name: 'message input' })
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('AI provider error: connection refused')
    })
  })

  it('shows an error message when the task fails during polling', async () => {
    ;(global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ task_id: MOCK_TASK_ID, status: 'pending' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          task_id: MOCK_TASK_ID,
          status: 'failed',
          result: null,
          error: 'AI 服务当前繁忙，请稍等几秒后点击「重试」。',
        }),
      })

    render(<ChatPage />)
    fireEvent.change(screen.getByRole('textbox', { name: 'message input' }), {
      target: { value: 'Hello' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('AI 服务当前繁忙')
    })
  })

  it('calls the async chat endpoint with session_id and message', async () => {
    mockAsyncChat('Agent reply')

    render(<ChatPage />)
    const input = screen.getByRole('textbox', { name: 'message input' })
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() => {
      const fetchCall = (global.fetch as jest.Mock).mock.calls[0]
      expect(fetchCall[0]).toContain('/api/v1/agent/chat/async')
      const body = JSON.parse(fetchCall[1].body)
      expect(body.session_id).toBe(MOCK_SESSION_ID)
      expect(body.message).toBe('Hello')
    })
  })

  it('polls the tasks endpoint after submitting the chat request', async () => {
    mockAsyncChat('Agent reply')

    render(<ChatPage />)
    fireEvent.change(screen.getByRole('textbox', { name: 'message input' }), {
      target: { value: 'Hello' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls
      expect(calls.length).toBeGreaterThanOrEqual(2)
      expect(calls[1][0]).toContain(`/api/v1/agent/tasks/${MOCK_TASK_ID}`)
    })
  })

  it('calls fetch with the provider from localStorage', async () => {
    window.localStorage.setItem('ai_provider', 'deepseek')
    mockAsyncChat('deepseek reply', { phase: 'ICEBREAK' })

    render(<ChatPage />)
    const input = screen.getByRole('textbox', { name: 'message input' })
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() => {
      const fetchCall = (global.fetch as jest.Mock).mock.calls[0]
      const body = JSON.parse(fetchCall[1].body)
      expect(body.provider).toBe('deepseek')
    })

    window.localStorage.removeItem('ai_provider')
  })

  it('renders the phase navigation bar', () => {
    render(<ChatPage />)
    expect(screen.getByLabelText('phase navigation')).toBeInTheDocument()
    expect(screen.getByText('P1 破冰引入')).toBeInTheDocument()
  })

  it('shows phase document panel after receiving a phase_document in the response', async () => {
    mockAsyncChat('Hello!', {
      phase_document: {
        phase: 'ICEBREAK',
        title: '项目简介',
        content: '# 项目简介\n\n待填写',
        rendered_at: new Date().toISOString(),
        turn_count: 1,
      },
    })

    render(<ChatPage />)
    fireEvent.change(screen.getByRole('textbox', { name: 'message input' }), {
      target: { value: '你好' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() => {
      expect(screen.getByLabelText('phase document panel')).toBeInTheDocument()
      // Title appears in h2; getAllByText handles duplicates (also appears in content)
      const matches = screen.getAllByText(/项目简介/)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('toggle phase document button shows/hides the panel', async () => {
    mockAsyncChat('Hello!', {
      phase_document: {
        phase: 'ICEBREAK',
        title: '项目简介',
        content: '# 项目简介\n\n内容',
        rendered_at: new Date().toISOString(),
        turn_count: 1,
      },
    })

    render(<ChatPage />)
    fireEvent.change(screen.getByRole('textbox', { name: 'message input' }), {
      target: { value: '你好' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() =>
      expect(screen.getByLabelText('phase document panel')).toBeInTheDocument()
    )

    // Click the toggle button to hide the panel
    fireEvent.click(screen.getByLabelText('toggle phase document'))
    expect(screen.queryByLabelText('phase document panel')).not.toBeInTheDocument()
  })

  it('switches phase using the async polling approach', async () => {
    const phaseReply = agentReply('欢迎进入需求收集阶段！', {
      phase: 'REQUIREMENT',
      phase_label: '需求收集',
      progress: 0.2,
    })

    ;(global.fetch as jest.Mock)
      // pre-fetch phase document call
      .mockResolvedValueOnce({ ok: false })
      // POST /switch-phase/async → task_id
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ task_id: MOCK_TASK_ID, status: 'pending' }),
      })
      // GET /tasks/{id} → completed
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          task_id: MOCK_TASK_ID,
          status: 'completed',
          result: phaseReply,
          error: null,
        }),
      })

    render(<ChatPage />)

    const nextBtn = screen.getByRole('button', { name: '下一阶段' })
    fireEvent.click(nextBtn)

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls
      const switchCall = calls.find((c: string[]) => c[0]?.includes('/switch-phase/async'))
      expect(switchCall).toBeDefined()
    })

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls
      const pollCall = calls.find((c: string[]) => c[0]?.includes(`/tasks/${MOCK_TASK_ID}`))
      expect(pollCall).toBeDefined()
    })
  })
})

