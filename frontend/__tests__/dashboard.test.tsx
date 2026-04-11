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

beforeEach(() => {
  jest.clearAllMocks()
})

describe('DashboardPage', () => {
  it('renders the Talk2DDD heading', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: '1', email: 'test@example.com', username: 'testuser', is_active: true }),
    })
    render(<DashboardPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Talk2DDD')
  })

  it('shows loading state initially', () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: '1', email: 'test@example.com', username: 'testuser', is_active: true }),
    })
    render(<DashboardPage />)
    expect(screen.getByLabelText('loading')).toBeInTheDocument()
  })

  it('renders welcome message with username after loading', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: '1', email: 'test@example.com', username: 'testuser', is_active: true }),
    })
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText(/欢迎回来，testuser/)).toBeInTheDocument()
    })
  })

  it('renders quick action cards', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: '1', email: 'test@example.com', username: 'testuser', is_active: true }),
    })
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByLabelText('go to chat')).toBeInTheDocument()
      expect(screen.getByLabelText('go to projects')).toBeInTheDocument()
      expect(screen.getByLabelText('go to profile')).toBeInTheDocument()
    })
  })

  it('renders chat link pointing to /chat', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: '1', email: 'test@example.com', username: 'testuser', is_active: true }),
    })
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByLabelText('go to chat')).toHaveAttribute('href', '/chat')
    })
  })

  it('sends Authorization header with Bearer token from cookie', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: '1', email: 'test@example.com', username: 'testuser', is_active: true }),
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
      json: async () => ({ id: '1', email: 'test@example.com', username: 'testuser', is_active: true }),
    })
    render(<DashboardPage />)
    expect(screen.getByLabelText('logout')).toBeInTheDocument()
  })

  it('redirects to /login when logout is clicked', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: '1', email: 'test@example.com', username: 'testuser', is_active: true }),
    })
    render(<DashboardPage />)
    fireEvent.click(screen.getByLabelText('logout'))
    expect(mockPush).toHaveBeenCalledWith('/login')
  })
})
