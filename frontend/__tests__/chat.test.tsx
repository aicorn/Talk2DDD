/**
 * Tests for the AI Chat page (frontend/app/chat/page.tsx).
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChatPage from '../app/chat/page'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

// Silence fetch-not-defined warnings in jsdom
global.fetch = jest.fn()

beforeEach(() => {
  jest.clearAllMocks()
})

describe('ChatPage', () => {
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
      json: async () => ({ reply: 'Hi there!', provider: 'openai', model: 'gpt-4' }),
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

  it('calls fetch with the provider from localStorage', async () => {
    window.localStorage.setItem('ai_provider', 'deepseek')
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ reply: 'deepseek reply', provider: 'deepseek', model: 'deepseek-chat' }),
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
})

