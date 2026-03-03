#!/bin/bash

set -e

echo "🔧 Talk2DDD 仓库初始化脚本"
echo "==========================="

# Initialize git if needed
if [ ! -d ".git" ]; then
    echo "📁 初始化 Git 仓库..."
    git init
    git branch -M main
fi

# Create .gitignore if not exists
if [ ! -f ".gitignore" ]; then
    echo "📝 创建 .gitignore..."
    cat > .gitignore << 'EOF'
# Dependencies
node_modules/
__pycache__/
*.py[cod]

# Environment variables
.env
.env.local
.env.production

# Build artifacts
.next/
dist/
build/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
EOF
fi

# Setup environment files
echo "📋 设置环境变量文件..."
[ ! -f ".env" ] && cp .env.example .env && echo "   创建 .env"
[ ! -f "backend/.env" ] && cp backend/.env.example backend/.env && echo "   创建 backend/.env"
[ ! -f "frontend/.env.local" ] && cp frontend/.env.example frontend/.env.local && echo "   创建 frontend/.env.local"

# Make scripts executable
chmod +x scripts/*.sh

echo ""
echo "✅ 仓库初始化完成！"
echo ""
echo "下一步："
echo "  1. 编辑 .env 添加 OPENAI_API_KEY"
echo "  2. 运行 ./scripts/setup.sh 启动服务"
