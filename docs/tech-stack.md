# Talk2DDD 技术选型

## 后端技术栈

| 技术 | 版本 | 选择理由 |
|------|------|---------|
| Python | 3.11+ | 生态成熟，AI/ML 支持最佳 |
| FastAPI | 0.104+ | 高性能，原生异步，自动文档 |
| SQLAlchemy | 2.0+ | 成熟 ORM，支持异步 |
| Alembic | 1.12+ | SQLAlchemy 配套迁移工具 |
| PostgreSQL | 16 | 生产级关系数据库 |
| Redis | 7 | 缓存和会话存储 |
| python-jose | 3.3+ | JWT 实现 |
| passlib | 1.7+ | 密码哈希 |
| OpenAI SDK | 1.3+ | GPT 模型接入 |

## 前端技术栈

| 技术 | 版本 | 选择理由 |
|------|------|---------|
| Next.js | 14 | React 全栈框架，SSR/SSG 支持 |
| TypeScript | 5+ | 类型安全，提高代码质量 |
| Tailwind CSS | 3.3+ | 实用优先 CSS 框架 |
| React Query | 5 | 服务端状态管理 |
| Zustand | 4 | 轻量客户端状态管理 |
| React Hook Form | 7 | 高性能表单处理 |
| Zod | 3 | 运行时类型验证 |

## 基础设施

| 技术 | 选择理由 |
|------|---------|
| Docker | 容器化，环境一致性 |
| Docker Compose | 本地开发多服务编排 |

## 架构模式

- **DDD（领域驱动设计）**：领域模型设计
- **分层架构**：Router → CRUD → Model → Database
- **CQRS（可扩展性）**：未来优化方向
- **事件驱动**：领域事件处理
