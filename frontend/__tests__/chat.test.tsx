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
const mockGetAuthHeaders = jest.fn(() => ({ Authorization: 'Bearer test-token' }))
jest.mock('../lib/auth', () => ({
  getAuthHeaders: () => mockGetAuthHeaders(),
}))

// Silence fetch-not-defined warnings in jsdom
global.fetch = jest.fn()

// Deterministic session ID in tests
const MOCK_SESSION_ID = '00000000-0000-4000-8000-000000000001'
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
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => agentReply('Hi there!'),
    })

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

  it('calls the agent chat endpoint with session_id and message', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => agentReply('Agent reply'),
    })

    render(<ChatPage />)
    const input = screen.getByRole('textbox', { name: 'message input' })
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'send message' }))

    await waitFor(() => {
      const fetchCall = (global.fetch as jest.Mock).mock.calls[0]
      expect(fetchCall[0]).toContain('/api/v1/agent/chat')
      const body = JSON.parse(fetchCall[1].body)
      expect(body.session_id).toBe(MOCK_SESSION_ID)
      expect(body.message).toBe('Hello')
    })
  })

  it('calls fetch with the provider from localStorage', async () => {
    window.localStorage.setItem('ai_provider', 'deepseek')
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => agentReply('deepseek reply', { phase: 'ICEBREAK' }),
    })

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
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () =>
        agentReply('Hello!', {
          phase_document: {
            phase: 'ICEBREAK',
            title: '项目简介',
            content: '# 项目简介\n\n待填写',
            rendered_at: new Date().toISOString(),
            turn_count: 1,
          },
        }),
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
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () =>
        agentReply('Hello!', {
          phase_document: {
            phase: 'ICEBREAK',
            title: '项目简介',
            content: '# 项目简介\n\n内容',
            rendered_at: new Date().toISOString(),
            turn_count: 1,
          },
        }),
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
})

