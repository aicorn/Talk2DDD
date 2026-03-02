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

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/aicorn/Talk2DDD.git
cd Talk2DDD

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，添加 OPENAI_API_KEY

# 3. 启动服务
docker-compose up -d

# 4. 初始化数据库
docker-compose exec backend alembic upgrade head
```

详细说明请参阅 [快速启动指南](docs/getting-started.md)

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
