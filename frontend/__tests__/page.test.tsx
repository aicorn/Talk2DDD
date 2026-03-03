/**
 * Tests for the Home page (frontend/app/page.tsx).
 *
 * We test that every key element the user expects to see is rendered:
 * - The main heading "Talk2DDD"
 * - The subtitle "AI 智能文档助手"
 * - The introductory paragraph
 * - The call-to-action "开始使用" link
 * - The API documentation link
 * - The three feature cards (对话驱动, 智能生成, 版本管理)
 */

import { render, screen } from '@testing-library/react'
import Home from '../app/page'

describe('Home page', () => {
  it('renders the Talk2DDD heading', () => {
    render(<Home />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Talk2DDD')
  })

  it('renders the AI subtitle', () => {
    render(<Home />)
    expect(screen.getByText('AI 智能文档助手')).toBeInTheDocument()
  })

  it('renders the introductory description', () => {
    render(<Home />)
    expect(
      screen.getByText(/通过对话方式，轻松创建和管理领域驱动设计/)
    ).toBeInTheDocument()
  })

  it('renders the "开始使用" call-to-action link pointing to /login', () => {
    render(<Home />)
    const link = screen.getByRole('link', { name: '开始使用' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/login')
  })

  it('renders the API documentation link', () => {
    render(<Home />)
    const link = screen.getByRole('link', { name: 'API 文档' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'http://localhost:8000/docs')
  })

  it('renders the "对话驱动" feature card', () => {
    render(<Home />)
    expect(screen.getByText(/对话驱动/)).toBeInTheDocument()
    expect(
      screen.getByText(/通过自然语言对话，AI 帮助您梳理业务需求和领域知识/)
    ).toBeInTheDocument()
  })

  it('renders the "智能生成" feature card', () => {
    render(<Home />)
    expect(screen.getByText(/智能生成/)).toBeInTheDocument()
    expect(
      screen.getByText(/自动生成 DDD 领域模型、用例文档和技术架构设计/)
    ).toBeInTheDocument()
  })

  it('renders the "版本管理" feature card', () => {
    render(<Home />)
    expect(screen.getByText(/版本管理/)).toBeInTheDocument()
    expect(
      screen.getByText(/完整的文档版本历史，支持多人协作和变更追踪/)
    ).toBeInTheDocument()
  })

  it('renders exactly two action links', () => {
    render(<Home />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(2)
  })
})
