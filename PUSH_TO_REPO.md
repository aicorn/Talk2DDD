# 推送到仓库指南

## 方法一：使用 Docker（推荐）

```bash
# 确保 Docker 已运行
docker-compose up -d

# 验证服务
docker-compose ps
```

## 方法二：本地开发环境

### 后端
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 设置环境变量
cp .env.example .env
# 编辑 .env

# 启动开发服务器
uvicorn app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

## 数据库初始化

```bash
# 使用 Docker
docker-compose exec backend alembic upgrade head

# 或本地
cd backend
alembic upgrade head
```

## 验证服务

- 前端：http://localhost:3000
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
