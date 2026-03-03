# Talk2DDD 技术架构：Next.js + FastAPI

## 系统架构概览

```
┌─────────────────────────────────────────────────────────┐
│                     用户浏览器                            │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/HTTPS
┌──────────────────────▼──────────────────────────────────┐
│              Next.js Frontend (Port 3000)                │
│  ┌───────────┐  ┌────────────┐  ┌───────────────────┐  │
│  │  App Dir  │  │ Middleware │  │    API Routes     │  │
│  └───────────┘  └────────────┘  └───────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP REST API
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Backend (Port 8000)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Routers  │  │   CRUD   │  │      Services        │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │  Models  │  │ Schemas  │  │   Core (Security)    │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
└──────┬───────────────────────────────────────────┬──────┘
       │                                           │
┌──────▼──────┐                          ┌─────────▼──────┐
│ PostgreSQL  │                          │     Redis      │
│  (Port 5432)│                          │  (Port 6379)   │
└─────────────┘                          └────────────────┘
       │
┌──────▼──────┐
│  OpenAI API │
└─────────────┘
```

## 后端架构详解

### 目录结构
```
backend/
├── app/
│   ├── main.py          # FastAPI 应用入口
│   ├── config.py        # 配置管理（pydantic-settings）
│   ├── database/
│   │   ├── base.py      # SQLAlchemy Base
│   │   └── session.py   # 数据库会话
│   ├── models/          # ORM 模型（SQLAlchemy）
│   ├── schemas/         # Pydantic 数据验证
│   ├── crud/            # 数据库操作层
│   ├── core/            # 核心功能（安全、异常）
│   ├── routers/         # API 路由
│   └── services/        # 业务逻辑服务
└── tests/
```

### 请求处理流程
```
HTTP 请求
    → Router（路由匹配、权限检查）
    → Dependency Injection（依赖注入）
    → CRUD（数据库操作）
    → Response（Pydantic 序列化）
```

## 前端架构详解

### 目录结构
```
frontend/
├── app/
│   ├── layout.tsx       # 根布局
│   ├── page.tsx         # 首页
│   ├── globals.css      # 全局样式
│   └── (routes)/        # 路由页面
├── components/          # 可复用组件
├── lib/                 # 工具函数
├── hooks/               # 自定义 Hooks
└── middleware.ts        # 路由中间件
```

## API 设计

### RESTful 端点
- `GET /health` - 健康检查
- `POST /api/v1/users/register` - 用户注册
- `POST /api/v1/users/login` - 用户登录
- `GET /api/v1/users/me` - 获取当前用户
- `PUT /api/v1/users/me` - 更新用户信息

### 认证流程
1. 用户登录获取 JWT Token
2. 后续请求在 Header 中携带 `Authorization: Bearer <token>`
3. 中间件验证 Token 有效性
4. 注入当前用户到请求上下文
