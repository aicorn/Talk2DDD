/**
 * Tests for the Dashboard page (frontend/app/dashboard/page.tsx).
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DashboardPage from '../app/dashboard/page'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

jest.mock('../lib/auth', () => ({
  getAuthHeaders: jest.fn(() => ({ Authorization: 'Bearer test-token' })),
}))

global.fetch = jest.fn()

const USER_OK = { id: '1', email: 'test@example.com', username: 'testuser', is_active: true }
const SESSIONS_OK = {
  conversations: [
    {
      session_id: 'aaaaaaaa-0000-4000-8000-000000000001',
      title: '博客系统对话',
      phase: 'REQUIREMENT',
      phase_label: '需求收集',
      turn_count: 5,
      updated_at: '2026-04-12T09:00:00Z',
    },
    {
      session_id: 'bbbbbbbb-0000-4000-8000-000000000002',
      title: null,
      phase: 'ICEBREAK',
      phase_label: '破冰引入',
      turn_count: 1,
      updated_at: '2026-04-11T08:00:00Z',
    },
  ],
}

/** Mock fetch: first call returns user info, second returns sessions list */
function mockFetchUserAndSessions() {
  ;(global.fetch as jest.Mock)
    .mockResolvedValueOnce({ ok: true, json: async () => USER_OK })
    .mockResolvedValueOnce({ ok: true, json: async () => SESSIONS_OK })
}

beforeEach(() => {
  jest.clearAllMocks()
})

describe('DashboardPage', () => {
  it('renders the Talk2DDD heading', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => USER_OK,
    })
    render(<DashboardPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Talk2DDD')
  })

  it('shows loading state initially', () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => USER_OK,
    })
    render(<DashboardPage />)
    expect(screen.getByLabelText('loading')).toBeInTheDocument()
  })

  it('renders welcome message with username after loading', async () => {
    mockFetchUserAndSessions()
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText(/欢迎回来，testuser/)).toBeInTheDocument()
    })
  })

  it('renders quick action cards', async () => {
    mockFetchUserAndSessions()
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByLabelText('go to chat')).toBeInTheDocument()
      expect(screen.getByLabelText('go to projects')).toBeInTheDocument()
      expect(screen.getByLabelText('go to profile')).toBeInTheDocument()
    })
  })

  it('renders chat link pointing to /chat', async () => {
    mockFetchUserAndSessions()
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByLabelText('go to chat')).toHaveAttribute('href', '/chat')
    })
  })

  it('sends Authorization header with Bearer token from cookie', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => USER_OK,
    })
    render(<DashboardPage />)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/users/me'),
        expect.objectContaining({ headers: { Authorization: 'Bearer test-token' } }),
      )
    })
  })

  it('redirects to /login when API returns 401', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Not authenticated' }),
    })
    render(<DashboardPage />)
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/login')
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('redirects to /login when API returns 403', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: async () => ({ detail: 'Not authenticated' }),
    })
    render(<DashboardPage />)
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/login')
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows error message when non-401 API call fails', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: '服务器错误' }),
    })
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('服务器错误')
    })
  })

  it('shows logout button', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => USER_OK,
    })
    render(<DashboardPage />)
    expect(screen.getByLabelText('logout')).toBeInTheDocument()
  })

  it('redirects to /login when logout is clicked', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => USER_OK,
    })
    render(<DashboardPage />)
    fireEvent.click(screen.getByLabelText('logout'))
    expect(mockPush).toHaveBeenCalledWith('/login')
  })

  it('renders session history section after loading', async () => {
    mockFetchUserAndSessions()
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByLabelText('session history')).toBeInTheDocument()
    })
  })

  it('renders session list items with titles', async () => {
    mockFetchUserAndSessions()
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('博客系统对话')).toBeInTheDocument()
      // Second session has no title; falls back to default label
      expect(screen.getByText('AI Agent 对话')).toBeInTheDocument()
    })
  })

  it('renders a resume link for each session with correct href', async () => {
    mockFetchUserAndSessions()
    render(<DashboardPage />)
    await waitFor(() => {
      const resumeLink = screen.getByLabelText(
        'resume session aaaaaaaa-0000-4000-8000-000000000001',
      )
      expect(resumeLink).toHaveAttribute(
        'href',
        '/chat?session=aaaaaaaa-0000-4000-8000-000000000001',
      )
    })
  })

  it('removes a session from the list when delete button is clicked', async () => {
    mockFetchUserAndSessions()
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true, json: async () => ({}) })

    render(<DashboardPage />)
    await waitFor(() => expect(screen.getByText('博客系统对话')).toBeInTheDocument())

    fireEvent.click(
      screen.getByLabelText('delete session aaaaaaaa-0000-4000-8000-000000000001'),
    )

    await waitFor(() => {
      expect(screen.queryByText('博客系统对话')).not.toBeInTheDocument()
    })
  })

  it('renders AI chat link in quick actions linking to /chat', async () => {
    mockFetchUserAndSessions()
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByLabelText('go to chat')).toHaveAttribute('href', '/chat')
    })
  })
})
