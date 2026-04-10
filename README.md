# 🎯 Talk2DDD - AI 智能文档助手

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)

## 项目简介

Talk2DDD 是一个基于 AI 的智能文档助手系统，专门为领域驱动设计（DDD）文档创建而设计。通过自然语言对话，帮助开发团队轻松创建高质量的技术文档。

## 核心特性

- 🤖 **AI 驱动对话** - 通过 GPT-4 智能引导需求梳理
- 📄 **文档自动生成** - 自动生成 DDD 文档和领域模型
- 🔐 **安全认证** - JWT 令牌认证系统
- 📊 **版本管理** - 完整的文档版本历史
- 🌐 **多语言支持** - 中文优先，支持多语言界面

## 技术架构

- **后端**：Python 3.11 + FastAPI + PostgreSQL + Redis
- **前端**：Next.js 14 + TypeScript + Tailwind CSS
- **AI**：OpenAI GPT-4
- **部署**：Docker + Docker Compose

## 一键部署

> **前置条件**：已安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/) 并正在运行。

### 方式一：一键脚本（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/aicorn/Talk2DDD.git
cd Talk2DDD

# 2. 运行一键启动脚本（自动配置环境、启动服务、初始化数据库）
bash scripts/setup.sh
```

脚本会自动完成以下操作：
1. 检查 Docker 环境
2. 复制并提示配置 `.env`（需填入 AI API Key）
3. 启动全部 Docker 服务
4. 初始化数据库

启动完成后访问：
- 🌐 **前端**：http://localhost:3000
- ⚙️ **后端 API**：http://localhost:8000
- 📖 **API 文档**：http://localhost:8000/docs

### 方式二：手动步骤

```bash
# 1. 克隆仓库
git clone https://github.com/aicorn/Talk2DDD.git
cd Talk2DDD

# 2. 配置环境变量（支持 OpenAI / DeepSeek / MiniMax）
cp .env.example .env
# 编辑 .env，设置 AI_PROVIDER 及对应的 API Key

# 3. 启动所有服务
docker-compose up -d

# 4. 初始化数据库
docker-compose exec backend alembic upgrade head
```

### AI 提供商配置

在 `.env` 中通过 `AI_PROVIDER` 选择模型提供商：

| 提供商 | `AI_PROVIDER` 值 | 所需 Key |
|--------|-----------------|---------|
| OpenAI | `openai` | `OPENAI_API_KEY` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` |
| MiniMax | `minimax` | `MINIMAX_API_KEY` |

### 常见问题排查

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs backend
docker-compose logs frontend

# 重启服务
docker-compose restart
```

详细说明请参阅 [快速启动指南](QUICKSTART.md)

## 项目文档

- [业务需求文档](docs/business-requirements.md)
- [通用语言术语表](docs/ubiquitous-language.md)
- [领域模型设计](docs/domain-model-corrected.md)
- [用例说明](docs/use-cases.md)
- [技术选型](docs/tech-stack.md)
- [技术架构详解](docs/tech-architecture-nextjs-fastapi.md)

## API 文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
