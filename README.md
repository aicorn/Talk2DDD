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

项目提供两种部署方式，请根据你的环境选择：

| 方式 | 适用场景 | 前置条件 |
|------|---------|---------|
| [Docker 部署（推荐）](#docker-部署推荐) | 生产环境 / 任何平台快速拉起 | Docker Desktop |
| [本地部署（Miniconda / 无虚拟环境）](#本地部署miniconda--无虚拟环境) | 无 Docker / 本地开发调试 | Python 3.11+ · Node.js 18+ |

---

## Docker 部署（推荐）

> **前置条件**：已安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/) 并正在运行。

### 方式一：一键脚本

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

启动完成后访问：
- 🌐 **前端**：http://localhost:3000
- ⚙️ **后端 API**：http://localhost:8000
- 📖 **API 文档**：http://localhost:8000/docs

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

---

## 本地部署（Miniconda / 无虚拟环境）

适合在**没有 Docker** 或希望直接在宿主机运行的场景。
PostgreSQL 和 Redis 仍通过 Docker 拉起（仅启动这两个容器）；Python 后端和 Next.js 前端则直接在本机运行。

### 前置条件

| 工具 | 版本要求 | 安装参考 |
|------|---------|---------|
| Python | 3.11+ | [Miniconda（推荐）](https://docs.conda.io/en/latest/miniconda.html) 或 [python.org](https://www.python.org/downloads/) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| Docker | 任意版本 | [docker.com](https://www.docker.com/products/docker-desktop/)（仅用于 PostgreSQL/Redis，可用本地安装替代） |
| Git | 任意版本 | [git-scm.com](https://git-scm.com/) |

### 方式一：一键脚本（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/aicorn/Talk2DDD.git
cd Talk2DDD

# 2a. 使用 Miniconda 环境（脚本自动创建 talk2ddd conda 环境）
bash scripts/local_deploy.sh

# 2b. 使用系统 Python（不创建虚拟环境）
bash scripts/local_deploy.sh --no-venv
```

脚本自动完成：
1. 检测并启动 PostgreSQL、Redis（通过 Docker）
2. 创建/激活 `talk2ddd` conda 环境（或使用系统 Python）
3. 安装 Python 依赖（`pip install -r backend/requirements.txt`）
4. 生成 `.env` 配置文件
5. 运行数据库迁移（Alembic）
6. 安装前端依赖（`npm install`）
7. 在后台启动后端（uvicorn）和前端（Next.js）
8. 打印访问地址和常用命令

> **提示**：脚本运行后请编辑 `.env`，填入您的 AI API Key，然后重启后端服务。

### 方式二：手动步骤

#### 步骤 1 — 启动 PostgreSQL 和 Redis

```bash
# 仅启动数据库和缓存容器（无需完整 Docker 栈）
docker-compose up -d db redis
```

如果本机已安装 PostgreSQL 和 Redis，可跳过此步骤，直接在 `.env` 中填写对应的连接信息。

#### 步骤 2 — 配置环境变量

```bash
cp .env.example .env
# 编辑 .env：
#   - 填入 AI API Key（OPENAI_API_KEY / DEEPSEEK_API_KEY 等）
#   - 本地运行时 DATABASE_URL 中的主机名改为 localhost（默认已指向 localhost）
```

#### 步骤 3 — 搭建 Python 环境并安装后端依赖

**使用 Miniconda（推荐）：**

```bash
conda create -n talk2ddd python=3.11 -y
conda activate talk2ddd
pip install -r backend/requirements.txt
```

**使用系统 Python（无虚拟环境）：**

```bash
pip install -r backend/requirements.txt
```

#### 步骤 4 — 运行数据库迁移

```bash
cd backend
alembic upgrade head
cd ..
```

#### 步骤 5 — 安装前端依赖

```bash
cd frontend
npm install --legacy-peer-deps
cd ..
```

#### 步骤 6 — 启动服务

```bash
# 终端 1：启动后端
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：启动前端
cd frontend
npm run dev
```

启动完成后访问：
- 🌐 **前端**：http://localhost:3000
- ⚙️ **后端 API**：http://localhost:8000
- 📖 **API 文档**：http://localhost:8000/docs

### 停止本地服务

```bash
# 如果通过一键脚本启动（后台进程）
kill $(cat logs/backend.pid) $(cat logs/frontend.pid)

# 停止 PostgreSQL / Redis 容器
docker-compose stop db redis
```

### 常见问题

| 问题 | 解决方案 |
|------|---------|
| `conda: command not found` | 安装 Miniconda 或使用 `--no-venv` 参数 |
| `alembic: command not found` | 确认已激活 conda 环境或 pip 安装成功 |
| 数据库连接失败 | 检查 `.env` 中 `DATABASE_URL` 主机名是否为 `localhost` |
| 端口 3000/8000 被占用 | 修改启动命令中的端口号，并更新 `.env` 中的 `NEXT_PUBLIC_API_URL` |

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
