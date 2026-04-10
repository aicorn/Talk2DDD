#!/bin/bash

set -e

echo "🚀 Talk2DDD 一键启动脚本"
echo "=========================="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker Desktop"
    exit 1
fi

# 检测 docker compose 命令（优先使用新版插件形式）
if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "❌ Docker Compose 未安装，请安装 Docker Compose 插件或独立版本"
    echo "   参考: https://docs.docker.com/compose/install/"
    exit 1
fi

# Setup environment
if [ ! -f ".env" ]; then
    echo "📋 复制环境变量配置..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件，添加必要配置（特别是 OPENAI_API_KEY）"
    echo "   按回车继续，或 Ctrl+C 退出去配置..."
    read
fi

if [ ! -f "backend/.env" ]; then
    cp backend/.env.example backend/.env
fi

if [ ! -f "frontend/.env" ]; then
    cp frontend/.env.example frontend/.env.local
fi

# Start services
echo "🐳 启动 Docker 服务..."
$COMPOSE_CMD up -d

# Wait for services
echo "⏳ 等待服务启动..."
sleep 10

# Initialize database
echo "🗄️  初始化数据库..."
$COMPOSE_CMD exec -T backend alembic upgrade head

# Verify
echo ""
echo "✅ 验证服务状态..."
$COMPOSE_CMD ps

echo ""
echo "🎉 启动完成！"
echo ""
echo "访问地址："
echo "  前端:      http://localhost:3000"
echo "  后端 API:  http://localhost:8000"
echo "  API 文档:  http://localhost:8000/docs"
echo "  健康检查:  http://localhost:8000/health"
