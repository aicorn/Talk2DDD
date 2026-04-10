#!/usr/bin/env bash
# Talk2DDD 本地一键部署脚本（Miniconda / 无虚拟环境）
#
# 用法:
#   bash scripts/local_deploy.sh           # 自动检测 conda，优先创建独立虚拟环境
#   bash scripts/local_deploy.sh --no-venv # 使用系统 Python，不创建虚拟环境
#
# 前置条件（二选一即可）:
#   - Miniconda / Anaconda 已安装（推荐）
#   - Python 3.11+ 与 pip 已安装
# 加上:
#   - Node.js 18+ 与 npm 已安装
#   - Docker（仅用于启动 PostgreSQL 和 Redis）

set -euo pipefail

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
error()   { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }

# ── 参数解析 ──────────────────────────────────────────────────────────────────
USE_VENV=true
for arg in "$@"; do
    [[ "$arg" == "--no-venv" ]] && USE_VENV=false
done

CONDA_ENV_NAME="talk2ddd"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo -e "${BLUE}"
cat << 'EOF'
  _____     _ _    ____  ____  ____
 |_   _|_ _| | | _|___ \|  _ \|  _ \
   | |/ _` | | |/ / __) | | | | | | |
   | | (_| | |   < / __/| |_| | |_| |
   |_|\__,_|_|_|\_\_____|____/|____/

  本地一键部署脚本  v1.0
EOF
echo -e "${NC}"

cd "${ROOT_DIR}"

# ── 工具检测 ──────────────────────────────────────────────────────────────────
check_command() { command -v "$1" &>/dev/null; }

check_node() {
    check_command node || error "未找到 Node.js，请先安装 Node.js 18+: https://nodejs.org/"
    check_command npm  || error "未找到 npm，请先安装 npm"
    NODE_VER=$(node -e "process.stdout.write(process.versions.node)")
    MAJOR=${NODE_VER%%.*}
    [[ "$MAJOR" -ge 18 ]] || error "需要 Node.js 18+，当前版本: $NODE_VER"
    success "Node.js $NODE_VER"
}

# ── 启动 PostgreSQL + Redis（仅用 Docker 启动基础服务）────────────────────────
start_infra() {
    if ! check_command docker; then
        warn "未找到 Docker，跳过自动启动 PostgreSQL/Redis。"
        warn "请确保本地已运行 PostgreSQL（端口 5432）和 Redis（端口 6379）。"
        return
    fi

    # 解析 docker compose 命令
    if docker compose version &>/dev/null; then
        COMPOSE_CMD=(docker compose)
    elif check_command docker-compose; then
        COMPOSE_CMD=(docker-compose)
    else
        warn "未找到 Docker Compose，跳过自动启动基础服务。"
        return
    fi

    info "使用 Docker 启动 PostgreSQL 和 Redis..."
    "${COMPOSE_CMD[@]}" up -d db redis
    info "等待数据库就绪..."
    local attempts=0
    until "${COMPOSE_CMD[@]}" exec -T db pg_isready -U talk2ddd &>/dev/null; do
        attempts=$((attempts + 1))
        [[ $attempts -ge 20 ]] && error "PostgreSQL 未能在规定时间内就绪，请检查 Docker 日志"
        sleep 2
    done
    success "PostgreSQL 和 Redis 已就绪"
}

# ── 配置 .env ─────────────────────────────────────────────────────────────────
setup_env() {
    if [[ -f ".env" ]]; then
        warn ".env 已存在，跳过生成（如需重置请删除该文件）"
        return
    fi
    cp .env.example .env
    # 修改 DATABASE_URL 指向本地（非 Docker 网络内）
    if grep -q "DATABASE_URL" .env 2>/dev/null; then
        sed -i.bak 's|@db:|@localhost:|g' .env && rm -f .env.bak
    fi
    warn "请编辑 .env，填入您的 AI API Key（OPENAI_API_KEY / DEEPSEEK_API_KEY 等）"
    success ".env 已生成"
}

# ── Python 环境 ───────────────────────────────────────────────────────────────
setup_python_conda() {
    # 尝试初始化 conda
    local conda_sh=""
    for p in \
        "$HOME/miniconda3/etc/profile.d/conda.sh" \
        "$HOME/anaconda3/etc/profile.d/conda.sh" \
        "/opt/miniconda3/etc/profile.d/conda.sh" \
        "/opt/anaconda3/etc/profile.d/conda.sh"; do
        [[ -f "$p" ]] && conda_sh="$p" && break
    done

    if [[ -z "$conda_sh" ]] && check_command conda; then
        conda_sh="$(conda info --base)/etc/profile.d/conda.sh"
    fi

    [[ -n "$conda_sh" && -f "$conda_sh" ]] || error \
        "未找到 conda 初始化脚本。请先安装 Miniconda: https://docs.conda.io/en/latest/miniconda.html"

    # shellcheck disable=SC1090
    source "$conda_sh"

    if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
        info "激活已有 conda 环境: ${CONDA_ENV_NAME}"
    else
        info "创建 conda 环境: ${CONDA_ENV_NAME} (Python 3.11)..."
        conda create -y -n "${CONDA_ENV_NAME}" python=3.11
        success "conda 环境已创建"
    fi

    conda activate "${CONDA_ENV_NAME}"
    success "已激活 conda 环境: ${CONDA_ENV_NAME}"

    install_python_deps
}

install_python_deps() {
    info "安装 Python 依赖..."
    pip install -r backend/requirements.txt -q
    success "Python 依赖安装完成"
}

setup_python_no_venv() {
    local py=""
    for cmd in python3.11 python3 python; do
        if check_command "$cmd"; then
            local ver
            ver=$("$cmd" -c "import sys; print(sys.version_info.major*100+sys.version_info.minor)" 2>/dev/null || echo 0)
            [[ "$ver" -ge 311 ]] && py="$cmd" && break
        fi
    done
    [[ -n "$py" ]] || error "需要 Python 3.11+，请先安装: https://www.python.org/downloads/"
    PYTHON_CMD="$py"
    success "使用 Python: $($py --version)"

    install_python_deps
}

# ── 数据库迁移 ────────────────────────────────────────────────────────────────
run_migrations() {
    info "运行数据库迁移..."
    # 加载 .env 中的 DATABASE_URL（本地模式需指向 localhost）
    if [[ -f ".env" ]]; then
        set -a
        # shellcheck disable=SC1091
        source .env
        set +a
    fi
    # 如果 .env 里没有 DATABASE_URL，使用默认值
    export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://talk2ddd:password@localhost:5432/talk2ddd}"
    (cd backend && alembic upgrade head)
    success "数据库迁移完成"
}

# ── 前端依赖 ──────────────────────────────────────────────────────────────────
setup_frontend() {
    info "安装前端依赖..."
    (cd frontend && npm install --legacy-peer-deps --silent)
    success "前端依赖安装完成"
}

# ── 启动服务 ──────────────────────────────────────────────────────────────────
start_services() {
    info "启动后端服务（uvicorn，端口 8000）..."
    (
        cd backend
        if [[ -f "../.env" ]]; then
            set -a; source ../.env; set +a
        fi
        export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://talk2ddd:password@localhost:5432/talk2ddd}"
        nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 \
            > ../logs/backend.log 2>&1 &
        echo $! > ../logs/backend.pid
    )
    success "后端已在后台启动（日志: logs/backend.log，PID: $(cat logs/backend.pid)）"

    info "启动前端服务（Next.js，端口 3000）..."
    (
        cd frontend
        nohup npm run dev > ../logs/frontend.log 2>&1 &
        echo $! > ../logs/frontend.pid
    )
    success "前端已在后台启动（日志: logs/frontend.log，PID: $(cat logs/frontend.pid)）"
}

# ── 等待后端就绪 ──────────────────────────────────────────────────────────────
wait_for_backend() {
    info "等待后端 API 就绪..."
    local attempts=0
    until curl -sf http://localhost:8000/health &>/dev/null; do
        attempts=$((attempts + 1))
        [[ $attempts -ge 30 ]] && {
            warn "后端未能在规定时间内就绪，请查看日志: logs/backend.log"
            return
        }
        sleep 2
    done
    success "后端 API 已就绪"
}

# ── 打印摘要 ──────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${GREEN}🎉 Talk2DDD 本地部署完成！${NC}"
    echo ""
    echo "  访问地址："
    echo -e "    前端应用:  ${BLUE}http://localhost:3000${NC}"
    echo -e "    后端 API:  ${BLUE}http://localhost:8000${NC}"
    echo -e "    API 文档:  ${BLUE}http://localhost:8000/docs${NC}"
    echo ""
    echo "  日志文件："
    echo "    后端:  logs/backend.log"
    echo "    前端:  logs/frontend.log"
    echo ""
    echo "  停止服务："
    echo "    kill \$(cat logs/backend.pid) \$(cat logs/frontend.pid)"
    echo ""
}

# ── conda 安装检测 ────────────────────────────────────────────────────────────
has_conda() {
    check_command conda && return 0
    for dir in "$HOME/miniconda3" "$HOME/anaconda3" /opt/miniconda3 /opt/anaconda3; do
        [[ -x "$dir/bin/conda" ]] && return 0
    done
    return 1
}

# ── 主流程 ────────────────────────────────────────────────────────────────────
main() {
    check_node
    mkdir -p logs
    start_infra
    setup_env
    if $USE_VENV && has_conda; then
        setup_python_conda
    elif $USE_VENV; then
        warn "未检测到 conda，回退到系统 Python（如需 conda 环境请先安装 Miniconda）"
        setup_python_no_venv
    else
        setup_python_no_venv
    fi
    run_migrations
    setup_frontend
    start_services
    wait_for_backend
    print_summary
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
