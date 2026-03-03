# ⚡ 5 分钟快速启动

## 前置条件

- Docker Desktop 已安装并运行
- Git 已安装
- OpenAI API Key（可从 https://platform.openai.com 获取）

## 步骤

### 第一步：获取代码

```bash
git clone https://github.com/aicorn/Talk2DDD.git
cd Talk2DDD
```

### 第二步：配置 API Key

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 OpenAI API Key：
```
OPENAI_API_KEY=sk-your-actual-openai-api-key
```

### 第三步：启动

```bash
docker-compose up -d
```

等待约 1-2 分钟，直到所有服务启动完成。

### 第四步：初始化数据库

```bash
docker-compose exec backend alembic upgrade head
```

### 第五步：验证

```bash
curl http://localhost:8000/health
# 应该返回: {"status":"healthy",...}
```

打开浏览器访问 http://localhost:3000 🎉

## 遇到问题？

```bash
# 查看服务状态
docker-compose ps

# 查看后端日志
docker-compose logs backend

# 查看前端日志
docker-compose logs frontend

# 重启服务
docker-compose restart
```
