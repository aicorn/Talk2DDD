/**
 * Tests for the Dashboard page (frontend/app/dashboard/page.tsx).
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DashboardPage from '../app/dashboard/page'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
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

  it('shows error message when API call fails', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      json: async () => ({}),
    })
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('无法获取用户信息')
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
