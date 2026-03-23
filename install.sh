#!/usr/bin/env bash
# ==============================================================================
# Talk2DDD 一键安装脚本 / One-Click Install Script
# ==============================================================================
# 用法 / Usage:
#   ./install.sh                     # 交互式安装 / Interactive install
#   ./install.sh --non-interactive   # 非交互式，使用环境变量 / Non-interactive
#
# 支持的环境变量 / Supported env vars (for non-interactive mode):
#   OPENAI_API_KEY   - OpenAI API 密钥
#   DEEPSEEK_API_KEY - DeepSeek API 密钥
#   MINIMAX_API_KEY  - MiniMax API 密钥
#   AI_PROVIDER      - AI 提供商: openai | deepseek | minimax (默认: openai)
#   DB_PASSWORD      - 数据库密码 (默认: 自动生成)
#   SECRET_KEY       - JWT 密钥   (默认: 自动生成)
# ==============================================================================

set -euo pipefail

# ── 颜色定义 / Color definitions ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── 脚本目录 / Script directory ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 解析参数 / Parse arguments ────────────────────────────────────────────────
NON_INTERACTIVE=false
SKIP_PULL=false
for arg in "$@"; do
    case "$arg" in
        --non-interactive|-y) NON_INTERACTIVE=true ;;
        --skip-pull)          SKIP_PULL=true ;;
        --help|-h)
            echo "Usage: $0 [--non-interactive|-y] [--skip-pull] [--help|-h]"
            echo ""
            echo "Environment variables for non-interactive mode:"
            echo "  AI_PROVIDER      openai | deepseek | minimax  (default: openai)"
            echo "  OPENAI_API_KEY   OpenAI API key"
            echo "  DEEPSEEK_API_KEY DeepSeek API key"
            echo "  MINIMAX_API_KEY  MiniMax API key"
            echo "  DB_PASSWORD      Database password  (auto-generated if empty)"
            echo "  SECRET_KEY       JWT secret key     (auto-generated if empty)"
            exit 0
            ;;
    esac
done

# ── 辅助函数 / Helper functions ───────────────────────────────────────────────
log_info()    { echo -e "${BLUE}ℹ${NC}  $*"; }
log_success() { echo -e "${GREEN}✅${NC} $*"; }
log_warn()    { echo -e "${YELLOW}⚠️${NC}  $*"; }
log_error()   { echo -e "${RED}❌${NC} $*" >&2; }
log_step()    { echo -e "\n${BOLD}${CYAN}━━ $* ━━${NC}"; }

# 跨平台 sed -i / Cross-platform in-place sed
sedi() {
    if sed --version 2>/dev/null | grep -q GNU; then
        sed -i "$@"
    else
        sed -i '' "$@"
    fi
}

# 生成随机字符串 / Generate a random string (length)
generate_secret() {
    local length="${1:-64}"
    # Try multiple sources in order of preference
    if command -v openssl &>/dev/null; then
        openssl rand -hex "$((length / 2))"
    elif [ -r /dev/urandom ]; then
        LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()_+' < /dev/urandom | head -c "$length"
        echo
    else
        # Fallback using date + PID
        echo "$(date +%s%N)$$" | sha256sum 2>/dev/null | cut -c1-"$length" || \
        printf '%s' "$(date +%s%N)$$" | md5sum | cut -c1-"$length"
    fi
}

# 检查命令是否存在 / Check if command exists
require_cmd() {
    local cmd="$1"
    local install_hint="${2:-}"
    if ! command -v "$cmd" &>/dev/null; then
        log_error "必需命令未找到: '$cmd'"
        [ -n "$install_hint" ] && log_error "安装提示: $install_hint"
        return 1
    fi
}

# 等待容器健康 / Wait for container health
wait_healthy() {
    local service="$1"
    local max_wait="${2:-120}"
    local interval=5
    local elapsed=0

    log_info "等待 $service 服务就绪..."
    while [ "$elapsed" -lt "$max_wait" ]; do
        local status
        status=$(docker compose ps --format json "$service" 2>/dev/null \
                 | grep -o '"Health":"[^"]*"' | cut -d'"' -f4 || true)
        # Also accept containers without healthcheck (just running)
        local running
        running=$(docker compose ps --format json "$service" 2>/dev/null \
                  | grep -o '"State":"[^"]*"' | cut -d'"' -f4 || true)

        if [ "$status" = "healthy" ] || { [ "$status" = "" ] && [ "$running" = "running" ]; }; then
            log_success "$service 已就绪"
            return 0
        fi

        printf "."
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    echo ""
    log_error "$service 在 ${max_wait}s 内未能就绪"
    docker compose logs --tail=30 "$service" >&2
    return 1
}

# ── 欢迎横幅 / Welcome banner ─────────────────────────────────────────────────
echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║        Talk2DDD 一键安装脚本 v1.0.0              ║"
echo "║   AI-Powered DDD Documentation Assistant         ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

cd "$SCRIPT_DIR"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
log_step "第 1 步: 检查前置条件"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MISSING_DEPS=0

require_cmd "docker"  "https://docs.docker.com/get-docker/" || MISSING_DEPS=$((MISSING_DEPS + 1))
require_cmd "git"     "https://git-scm.com/downloads"       || MISSING_DEPS=$((MISSING_DEPS + 1))
require_cmd "curl"    "apt-get install curl  / brew install curl" || MISSING_DEPS=$((MISSING_DEPS + 1))

# docker compose (v2) or docker-compose (v1)
if docker compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    log_error "Docker Compose 未找到。请安装 Docker Desktop 或独立的 docker-compose。"
    log_error "参考: https://docs.docker.com/compose/install/"
    MISSING_DEPS=$((MISSING_DEPS + 1))
fi

if [ "$MISSING_DEPS" -gt 0 ]; then
    log_error "请先安装以上缺失的依赖后重新运行此脚本。"
    exit 1
fi

# Check Docker daemon is running
if ! docker info &>/dev/null; then
    log_error "Docker 守护进程未运行。请启动 Docker Desktop 或 Docker 服务后重试。"
    exit 1
fi

log_success "前置条件检查通过 (Docker, Git, curl)"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
log_step "第 2 步: 配置环境变量"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Auto-generate secrets if not supplied
: "${DB_PASSWORD:=$(generate_secret 32)}"
: "${SECRET_KEY:=$(generate_secret 64)}"
: "${AI_PROVIDER:=openai}"

# ── 选择 AI 提供商 / Select AI provider ──────────────────────────────────────
if [ "$NON_INTERACTIVE" = false ]; then
    echo ""
    echo -e "${BOLD}请选择 AI 提供商 / Choose AI provider:${NC}"
    echo "  1) OpenAI   (GPT-4, 需要 OPENAI_API_KEY)"
    echo "  2) DeepSeek (需要 DEEPSEEK_API_KEY)"
    echo "  3) MiniMax  (需要 MINIMAX_API_KEY)"
    printf "选择 [1/2/3，默认=1]: "
    read -r provider_choice
    case "$provider_choice" in
        2) AI_PROVIDER="deepseek" ;;
        3) AI_PROVIDER="minimax"  ;;
        *) AI_PROVIDER="openai"   ;;
    esac
fi

# ── 读取 API Key / Read API Key ───────────────────────────────────────────────
API_KEY_VAR=""
case "$AI_PROVIDER" in
    openai)   API_KEY_VAR="OPENAI_API_KEY"   ;;
    deepseek) API_KEY_VAR="DEEPSEEK_API_KEY" ;;
    minimax)  API_KEY_VAR="MINIMAX_API_KEY"  ;;
esac

# Evaluate the variable named by $API_KEY_VAR
api_key_value="${!API_KEY_VAR:-}"

if [ -z "$api_key_value" ] && [ "$NON_INTERACTIVE" = false ]; then
    echo ""
    printf "请输入 ${BOLD}${API_KEY_VAR}${NC} (可稍后在 .env 中填写，直接回车跳过): "
    read -r api_key_value
fi

if [ -z "$api_key_value" ]; then
    log_warn "未设置 ${API_KEY_VAR}，AI 功能将在配置后才可用。"
    log_warn "安装完成后请编辑 .env 文件并重启服务: ${DOCKER_COMPOSE} restart backend"
fi

# ── 写入根 .env / Write root .env ─────────────────────────────────────────────
if [ ! -f ".env" ]; then
    log_info "创建 .env 文件..."
    cp .env.example .env
fi

# Update values in .env (using a portable sed approach)
update_env() {
    local key="$1"
    local value="$2"
    local file="$3"
    # Escape special chars for sed replacement
    local escaped_value
    escaped_value=$(printf '%s\n' "$value" | sed 's/[\/&]/\\&/g')
    if grep -q "^${key}=" "$file"; then
        sedi "s|^${key}=.*|${key}=${escaped_value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

update_env "DB_PASSWORD"   "$DB_PASSWORD"  ".env"
update_env "SECRET_KEY"    "$SECRET_KEY"   ".env"
update_env "AI_PROVIDER"   "$AI_PROVIDER"  ".env"

if [ -n "$api_key_value" ]; then
    update_env "$API_KEY_VAR" "$api_key_value" ".env"
fi

# ── 后端 .env / Backend .env ──────────────────────────────────────────────────
if [ ! -f "backend/.env" ]; then
    log_info "创建 backend/.env 文件..."
    cp backend/.env.example backend/.env
fi
update_env "SECRET_KEY"    "$SECRET_KEY"   "backend/.env"
update_env "AI_PROVIDER"   "$AI_PROVIDER"  "backend/.env"
if [ -n "$api_key_value" ]; then
    update_env "$API_KEY_VAR" "$api_key_value" "backend/.env"
fi

# ── 前端 .env / Frontend .env ─────────────────────────────────────────────────
if [ ! -f "frontend/.env.local" ]; then
    log_info "创建 frontend/.env.local 文件..."
    cp frontend/.env.example frontend/.env.local
fi

log_success "环境变量配置完成"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
log_step "第 3 步: 构建并启动 Docker 服务"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if [ "$SKIP_PULL" = false ]; then
    log_info "拉取基础镜像..."
    $DOCKER_COMPOSE pull --ignore-pull-failures || true
fi

log_info "构建并启动所有服务..."
$DOCKER_COMPOSE up -d --build

# ── 等待数据库就绪 / Wait for database ───────────────────────────────────────
wait_healthy "db" 60

# ── 等待 Redis 就绪 / Wait for Redis ─────────────────────────────────────────
wait_healthy "redis" 30

# ── 等待后端就绪 / Wait for backend ──────────────────────────────────────────
wait_healthy "backend" 120

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
log_step "第 4 步: 初始化数据库"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

log_info "运行数据库迁移 (alembic upgrade head)..."
$DOCKER_COMPOSE exec -T backend alembic upgrade head
log_success "数据库初始化完成"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
log_step "第 5 步: 验证安装"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

log_info "检查健康端点..."
HEALTH_OK=false
for i in $(seq 1 6); do
    if curl -sf http://localhost:8000/health -o /dev/null; then
        HEALTH_OK=true
        break
    fi
    sleep 5
done

if [ "$HEALTH_OK" = true ]; then
    log_success "后端 API 健康检查通过"
else
    log_warn "后端 API 健康检查未通过，请检查日志: ${DOCKER_COMPOSE} logs backend"
fi

echo ""
log_info "服务状态:"
$DOCKER_COMPOSE ps

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║           🎉 安装完成！Installation Done!        ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}访问地址 / Access URLs:${NC}"
echo -e "  ${CYAN}前端界面   / Frontend:${NC}  http://localhost:3000"
echo -e "  ${CYAN}后端 API   / Backend:${NC}   http://localhost:8000"
echo -e "  ${CYAN}API 文档   / API Docs:${NC}  http://localhost:8000/docs"
echo -e "  ${CYAN}健康检查   / Health:${NC}    http://localhost:8000/health"
echo ""
if [ -z "$api_key_value" ]; then
    echo -e "  ${YELLOW}⚠️  提示: 请编辑 .env 文件设置 ${API_KEY_VAR}，然后运行:${NC}"
    echo -e "     ${DOCKER_COMPOSE} restart backend"
    echo ""
fi
echo -e "  ${BOLD}常用命令 / Common commands:${NC}"
echo -e "  查看日志:   ${DOCKER_COMPOSE} logs -f"
echo -e "  停止服务:   ${DOCKER_COMPOSE} down"
echo -e "  重启服务:   ${DOCKER_COMPOSE} restart"
echo -e "  完全卸载:   ${DOCKER_COMPOSE} down -v  ${YELLOW}(删除数据库数据!)${NC}"
echo ""
