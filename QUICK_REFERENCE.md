# 🎯 快速参考指南

## 📋 5 分钟快速启动

```bash
# 1️⃣ 克隆仓库
git clone https://github.com/aicorn/Talk2DDD.git
cd Talk2DDD

# 2️⃣ 设置环境变量
cp .env.example .env
cp backend/.env.example backend/.env
# 编辑 .env 添加你的 OPENAI_API_KEY

# 3️⃣ 启动所有服务
docker-compose up -d

# 4️⃣ 初始化数据库
docker-compose exec backend alembic upgrade head

# 5️⃣ 验证服务
docker-compose ps