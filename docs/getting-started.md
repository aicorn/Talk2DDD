# Talk2DDD 快速启动指南

## 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- Git

## 快速启动（5 分钟）

### 1. 克隆仓库

```bash
git clone https://github.com/aicorn/Talk2DDD.git
cd Talk2DDD
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 编辑 .env，添加必要配置
# 必须配置 OPENAI_API_KEY
nano .env
```

最重要的配置：
```bash
OPENAI_API_KEY=sk-your-openai-api-key-here
SECRET_KEY=your-secure-secret-key-minimum-32-chars
DB_PASSWORD=your-secure-database-password
```

### 3. 启动所有服务

```bash
docker-compose up -d
```

### 4. 初始化数据库

```bash
docker-compose exec backend alembic upgrade head
```

### 5. 验证服务

```bash
# 检查所有服务状态
docker-compose ps

# 检查后端健康
curl http://localhost:8000/health

# 访问前端
open http://localhost:3000
```

## 服务地址

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:3000 |
| 后端 API | http://localhost:8000 |
| API 文档（Swagger） | http://localhost:8000/docs |
| API 文档（ReDoc） | http://localhost:8000/redoc |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

## 常用命令

```bash
# 查看日志
docker-compose logs -f

# 重启特定服务
docker-compose restart backend

# 停止所有服务
docker-compose down

# 停止并删除数据卷（危险！会丢失数据）
docker-compose down -v
```

## 本地开发

### 后端开发

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端开发

```bash
cd frontend
npm install
npm run dev
```
