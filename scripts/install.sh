#!/usr/bin/env bash
# Talk2DDD 一键安装脚本
# 用法: curl -fsSL https://raw.githubusercontent.com/aicorn/Talk2DDD/main/scripts/install.sh | bash
#   或: bash scripts/install.sh

set -euo pipefail

REPO_URL="https://github.com/aicorn/Talk2DDD.git"
INSTALL_DIR="${TALK2DDD_DIR:-$HOME/talk2ddd}"

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
error()   { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }

# ── 横幅 ──────────────────────────────────────────────────────────────────────
echo -e "${BLUE}"
cat << 'EOF'
  _____     _ _    ____  ____  ____
 |_   _|_ _| | | _|___ \|  _ \|  _ \
   | |/ _` | | |/ / __) | | | | | | |
   | | (_| | |   < / __/| |_| | |_| |
   |_|\__,_|_|_|\_\_____|____/|____/

  一键安装脚本  v1.0
EOF
echo -e "${NC}"

# ── 检测操作系统 ──────────────────────────────────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        OS="${ID:-linux}"
    else
        OS="linux"
    fi
    info "检测到操作系统: $OS"
}

# ── 检查必要工具 ──────────────────────────────────────────────────────────────
check_command() {
    command -v "$1" &>/dev/null
}

# ── 安装 Docker ───────────────────────────────────────────────────────────────
install_docker() {
    if check_command docker; then
        success "Docker 已安装: $(docker --version)"
        return
    fi

    info "正在安装 Docker..."
    case "$OS" in
        ubuntu|debian)
            sudo apt-get update -qq
            sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release
            curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
                | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
                | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            sudo apt-get update -qq
            sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
            sudo usermod -aG docker "$USER" || true
            ;;
        centos|rhel|fedora)
            sudo yum install -y -q yum-utils
            sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            sudo yum install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
            sudo systemctl enable --now docker
            sudo usermod -aG docker "$USER" || true
            ;;
        macos)
            if check_command brew; then
                brew install --cask docker
            else
                error "请先安装 Homebrew (https://brew.sh) 或手动安装 Docker Desktop"
            fi
            ;;
        *)
            error "不支持的操作系统 '$OS'，请手动安装 Docker: https://docs.docker.com/engine/install/"
            ;;
    esac
    success "Docker 安装完成"
}

# ── 解析 Docker Compose 命令（存入全局数组 COMPOSE_CMD）────────────────────────
set_compose_cmd() {
    if docker compose version &>/dev/null; then
        COMPOSE_CMD=(docker compose)
    elif check_command docker-compose; then
        COMPOSE_CMD=(docker-compose)
    else
        error "未找到 Docker Compose，请安装后重试"
    fi
}

# ── 克隆或更新仓库 ────────────────────────────────────────────────────────────
setup_repo() {
    # 如果脚本本身就在仓库目录里执行，直接使用当前目录
    if [[ -f "$(pwd)/docker-compose.yml" && -f "$(pwd)/.env.example" ]]; then
        INSTALL_DIR="$(pwd)"
        info "在现有仓库目录中运行: $INSTALL_DIR"
        return
    fi

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        info "更新已有仓库: $INSTALL_DIR"
        git -C "$INSTALL_DIR" pull --ff-only
    else
        info "克隆仓库到 $INSTALL_DIR ..."
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
    success "仓库准备完成"
}

# ── 生成随机密码 ──────────────────────────────────────────────────────────────
random_secret() {
    # 优先使用 openssl，其次 /dev/urandom
    if check_command openssl; then
        openssl rand -hex 32
    else
        tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 64
    fi
}

# ── 配置环境变量 ──────────────────────────────────────────────────────────────
setup_env() {
    if [[ -f ".env" ]]; then
        warn ".env 已存在，跳过自动生成（如需重置请删除该文件）"
        return
    fi

    info "生成 .env 配置文件..."
    cp .env.example .env

    # 自动填入随机密码，避免使用默认值
    DB_PASS=$(random_secret)
    SECRET=$(random_secret)

    sed -i.bak \
        -e "s|your-secure-database-password|${DB_PASS}|g" \
        -e "s|your-secret-key-change-in-production-minimum-32-chars|${SECRET}|g" \
        .env
    rm -f .env.bak

    # 更新 docker-compose 中 DATABASE_URL 引用的密码占位符（如有）
    # docker-compose.yml 使用 ${DB_PASSWORD:-password}，已覆盖

    warn "请编辑 .env 文件，填入您的 AI API Key（OPENAI_API_KEY / DEEPSEEK_API_KEY 等）"
    success ".env 配置文件已生成"
}

# ── 启动服务 ──────────────────────────────────────────────────────────────────
start_services() {
    set_compose_cmd
    info "启动所有服务（${COMPOSE_CMD[*]} up）..."
    "${COMPOSE_CMD[@]}" up -d --build
    success "服务已启动"
}

# ── 等待后端就绪 ──────────────────────────────────────────────────────────────
wait_for_backend() {
    set_compose_cmd
    info "等待后端服务就绪..."
    local attempts=0
    local max_attempts=30
    until "${COMPOSE_CMD[@]}" exec -T backend curl -sf http://localhost:8000/health &>/dev/null; do
        attempts=$((attempts + 1))
        if [[ $attempts -ge $max_attempts ]]; then
            warn "后端在 ${max_attempts} 次尝试内未就绪，请检查日志: ${COMPOSE_CMD[*]} logs backend"
            return
        fi
        sleep 3
    done
    success "后端服务已就绪"
}

# ── 数据库迁移 ────────────────────────────────────────────────────────────────
run_migrations() {
    set_compose_cmd
    info "运行数据库迁移..."
    "${COMPOSE_CMD[@]}" exec -T backend alembic upgrade head
    success "数据库迁移完成"
}

# ── 打印访问信息 ──────────────────────────────────────────────────────────────
print_summary() {
    set_compose_cmd
    echo ""
    echo -e "${GREEN}🎉 Talk2DDD 安装完成！${NC}"
    echo ""
    echo "  访问地址："
    echo -e "    前端应用:  ${BLUE}http://localhost:3000${NC}"
    echo -e "    后端 API:  ${BLUE}http://localhost:8000${NC}"
    echo -e "    API 文档:  ${BLUE}http://localhost:8000/docs${NC}"
    echo -e "    健康检查:  ${BLUE}http://localhost:8000/health${NC}"
    echo ""
    echo "  常用命令："
    echo "    查看日志:  ${COMPOSE_CMD[*]} logs -f"
    echo "    停止服务:  ${COMPOSE_CMD[*]} down"
    echo "    重启服务:  ${COMPOSE_CMD[*]} restart"
    echo ""
}

# ── 主流程 ────────────────────────────────────────────────────────────────────
main() {
    detect_os
    install_docker
    setup_repo
    setup_env
    start_services
    wait_for_backend
    run_migrations
    print_summary
}

# 仅在直接执行时运行 main（非 source 引入）
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
