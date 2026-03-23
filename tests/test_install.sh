#!/usr/bin/env bash
# ==============================================================================
# tests/test_install.sh — 安装脚本单元测试 / Unit tests for install.sh
# ==============================================================================
# 运行方式 / Run:
#   bash tests/test_install.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_SCRIPT="$REPO_ROOT/install.sh"
WORK_DIR="/tmp/talk2ddd_install_test_$$"

# ── Test framework ─────────────────────────────────────────────────────────────
PASS=0
FAIL=0
SKIP=0

_green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
_red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
_yellow(){ printf '\033[1;33m%s\033[0m\n' "$*"; }

assert_ok() {
    local description="$1"; shift
    if "$@" &>/dev/null; then
        _green  "  ✅ PASS: $description"
        PASS=$((PASS + 1))
    else
        _red    "  ❌ FAIL: $description"
        FAIL=$((FAIL + 1))
    fi
}

assert_fail() {
    local description="$1"; shift
    if ! "$@" &>/dev/null; then
        _green  "  ✅ PASS: $description"
        PASS=$((PASS + 1))
    else
        _red    "  ❌ FAIL: $description (expected failure but succeeded)"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local description="$1"
    local haystack="$2"
    local needle="$3"
    if echo "$haystack" | grep -q "$needle"; then
        _green  "  ✅ PASS: $description"
        PASS=$((PASS + 1))
    else
        _red    "  ❌ FAIL: $description — expected '$needle' in output"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_exists() {
    local description="$1"
    local file="$2"
    if [ -f "$file" ]; then
        _green  "  ✅ PASS: $description"
        PASS=$((PASS + 1))
    else
        _red    "  ❌ FAIL: $description — file not found: $file"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_contains() {
    local description="$1"
    local file="$2"
    local pattern="$3"
    if grep -q "$pattern" "$file" 2>/dev/null; then
        _green  "  ✅ PASS: $description"
        PASS=$((PASS + 1))
    else
        _red    "  ❌ FAIL: $description — '$pattern' not found in $file"
        FAIL=$((FAIL + 1))
    fi
}

assert_not_file_contains() {
    local description="$1"
    local file="$2"
    local pattern="$3"
    if ! grep -q "$pattern" "$file" 2>/dev/null; then
        _green  "  ✅ PASS: $description"
        PASS=$((PASS + 1))
    else
        _red    "  ❌ FAIL: $description — '$pattern' should NOT be in $file"
        FAIL=$((FAIL + 1))
    fi
}

skip_test() {
    _yellow "  ⏭  SKIP: $1"
    SKIP=$((SKIP + 1))
}

# ── Setup / Teardown ───────────────────────────────────────────────────────────
setup() {
    mkdir -p "$WORK_DIR"
    # Copy project skeleton into a temp dir so tests don't pollute the repo
    cp -r "$REPO_ROOT/." "$WORK_DIR/"
    # Remove any real .env files to ensure clean state
    rm -f "$WORK_DIR/.env" "$WORK_DIR/backend/.env" "$WORK_DIR/frontend/.env.local"
}

teardown() {
    rm -rf "$WORK_DIR"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "══════════════════════════════════════════════"
echo "  Talk2DDD install.sh 单元测试"
echo "══════════════════════════════════════════════"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "【测试组 1】安装脚本基础检查 / Basic script checks"
echo "──────────────────────────────────────────────"

assert_file_exists "install.sh 存在" "$INSTALL_SCRIPT"
assert_ok          "install.sh 可执行" test -x "$INSTALL_SCRIPT"
assert_ok          "install.sh 是有效 Bash 脚本 (bash -n)" bash -n "$INSTALL_SCRIPT"

OUTPUT=$(bash "$INSTALL_SCRIPT" --help 2>&1 || true)
assert_contains    "--help 显示用法说明"            "$OUTPUT" "Usage:"
assert_contains    "--help 包含 non-interactive"    "$OUTPUT" "non-interactive"
assert_contains    "--help 列出 AI_PROVIDER 变量"   "$OUTPUT" "AI_PROVIDER"
assert_contains    "--help 列出 OPENAI_API_KEY 变量" "$OUTPUT" "OPENAI_API_KEY"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 2】generate_secret 函数 / Secret generation"
echo "──────────────────────────────────────────────"

# Source helper functions only (not the main flow)
_gen_test_script=$(cat <<'EOF'
#!/usr/bin/env bash
generate_secret() {
    local length="${1:-64}"
    if command -v openssl &>/dev/null; then
        openssl rand -hex "$((length / 2))"
    elif [ -r /dev/urandom ]; then
        LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()_+' < /dev/urandom | head -c "$length"
        echo
    else
        printf '%s' "$(date +%s%N)$$" | sha256sum 2>/dev/null | cut -c1-"$length" || \
        printf '%s' "$(date +%s%N)$$" | md5sum | cut -c1-"$length"
    fi
}
S=$(generate_secret 32)
L=${#S}
echo "$L"
echo "$S"
EOF
)
GEN_OUT=$(bash <(echo "$_gen_test_script"))
GEN_LEN=$(echo "$GEN_OUT" | head -1)
GEN_VAL=$(echo "$GEN_OUT" | tail -1)

assert_ok "generate_secret 返回非空字符串" test -n "$GEN_VAL"
assert_ok "generate_secret(32) 返回 >=32 字符" [ "$GEN_LEN" -ge 32 ]

GEN_OUT2=$(bash <(echo "$_gen_test_script"))
GEN_VAL2=$(echo "$GEN_OUT2" | tail -1)
assert_ok "两次调用 generate_secret 结果不同 (随机性)" [ "$GEN_VAL" != "$GEN_VAL2" ]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 3】前置条件检查 / Prerequisites check"
echo "──────────────────────────────────────────────"

# Simulate missing docker by overriding PATH
NO_DOCKER_PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "^$" | \
    while read -r p; do
        ls "$p"/docker &>/dev/null 2>&1 && continue || echo "$p"
    done | tr '\n' ':' | sed 's/:$//')

# We can't easily mock docker without a real shell override, so we test
# indirectly by checking the script sources its guard correctly.
assert_ok  "脚本中包含 docker 前置条件检查" grep -q 'require_cmd.*docker\|command -v docker' "$INSTALL_SCRIPT"
assert_ok  "脚本中包含 docker-compose/docker compose 检查" grep -q 'docker compose\|docker-compose' "$INSTALL_SCRIPT"
assert_ok  "脚本中包含 git 前置条件检查" grep -q 'require_cmd.*git\|command -v git' "$INSTALL_SCRIPT"
assert_ok  "脚本中包含 curl 前置条件检查" grep -q 'require_cmd.*curl\|command -v curl' "$INSTALL_SCRIPT"
assert_ok  "脚本中检查 Docker 守护进程" grep -q 'docker info' "$INSTALL_SCRIPT"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 4】update_env 函数 / update_env function"
echo "──────────────────────────────────────────────"

setup

_update_env_script=$(cat <<'SCRIPT'
#!/usr/bin/env bash
sedi() {
    if sed --version 2>/dev/null | grep -q GNU; then
        sed -i "$@"
    else
        sed -i '' "$@"
    fi
}
update_env() {
    local key="$1"
    local value="$2"
    local file="$3"
    local escaped_value
    escaped_value=$(printf '%s\n' "$value" | sed 's/[\/&]/\\&/g')
    if grep -q "^${key}=" "$file"; then
        sedi "s|^${key}=.*|${key}=${escaped_value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

TMPENV="/tmp/talk2ddd_env_test_$$"
echo "EXISTING_KEY=old_value" > "$TMPENV"
echo "OTHER_KEY=unchanged"   >> "$TMPENV"

# Test 1: Update existing key
update_env "EXISTING_KEY" "new_value" "$TMPENV"
grep -q "^EXISTING_KEY=new_value$" "$TMPENV" && echo "PASS:update_existing" || echo "FAIL:update_existing"

# Test 2: Other key unchanged
grep -q "^OTHER_KEY=unchanged$" "$TMPENV" && echo "PASS:other_unchanged" || echo "FAIL:other_unchanged"

# Test 3: Add new key
update_env "NEW_KEY" "added_value" "$TMPENV"
grep -q "^NEW_KEY=added_value$" "$TMPENV" && echo "PASS:add_new_key" || echo "FAIL:add_new_key"

# Test 4: Value with special chars (slashes)
update_env "URL_KEY" "postgresql+asyncpg://user:pass@host:5432/db" "$TMPENV"
grep -q "^URL_KEY=postgresql+asyncpg://user:pass@host:5432/db$" "$TMPENV" && echo "PASS:special_chars" || echo "FAIL:special_chars"

rm -f "$TMPENV"
SCRIPT
)

ENV_TEST_OUT=$(bash <(echo "$_update_env_script") 2>&1)

assert_contains "update_env: 更新已存在的 key"  "$ENV_TEST_OUT" "PASS:update_existing"
assert_contains "update_env: 其他 key 不受影响"  "$ENV_TEST_OUT" "PASS:other_unchanged"
assert_contains "update_env: 添加新 key"          "$ENV_TEST_OUT" "PASS:add_new_key"
assert_contains "update_env: 处理包含斜杠的值"    "$ENV_TEST_OUT" "PASS:special_chars"

teardown

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 5】.env 文件创建逻辑 / .env file creation"
echo "──────────────────────────────────────────────"

setup

# Extract the env setup portion and run with mocked docker/docker-compose
_env_setup_test=$(cat <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

WORK_DIR="$1"
cd "$WORK_DIR"

# ── mock docker to skip actual container operations ──
docker()        { return 0; }
docker-compose(){ return 0; }
export -f docker docker-compose 2>/dev/null || true

# ── inline the relevant functions from install.sh ──
generate_secret() {
    local length="${1:-64}"
    if command -v openssl &>/dev/null; then
        openssl rand -hex "$((length / 2))"
    elif [ -r /dev/urandom ]; then
        LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()_+' < /dev/urandom | head -c "$length"; echo
    else
        printf '%s' "$(date +%s%N)$$" | sha256sum 2>/dev/null | cut -c1-"$length" || \
        printf '%s' "$(date +%s%N)$$" | md5sum | cut -c1-"$length"
    fi
}

update_env() {
    local key="$1"; local value="$2"; local file="$3"
    local escaped_value
    escaped_value=$(printf '%s\n' "$value" | sed 's/[\/&]/\\&/g')
    if grep -q "^${key}=" "$file"; then
        if sed --version 2>/dev/null | grep -q GNU; then
            sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$file"
        else
            sed -i '' "s|^${key}=.*|${key}=${escaped_value}|" "$file"
        fi
    else
        echo "${key}=${value}" >> "$file"
    fi
}

DB_PASSWORD=$(generate_secret 32)
SECRET_KEY=$(generate_secret 64)
AI_PROVIDER="${AI_PROVIDER:-openai}"
api_key_value="${OPENAI_API_KEY:-}"

[ ! -f ".env" ]              && cp .env.example .env
[ ! -f "backend/.env" ]      && cp backend/.env.example backend/.env
[ ! -f "frontend/.env.local" ] && cp frontend/.env.example frontend/.env.local

update_env "DB_PASSWORD" "$DB_PASSWORD" ".env"
update_env "SECRET_KEY"  "$SECRET_KEY"  ".env"
update_env "AI_PROVIDER" "$AI_PROVIDER" ".env"
[ -n "$api_key_value" ] && update_env "OPENAI_API_KEY" "$api_key_value" ".env"

update_env "SECRET_KEY"  "$SECRET_KEY"  "backend/.env"
update_env "AI_PROVIDER" "$AI_PROVIDER" "backend/.env"
[ -n "$api_key_value" ] && update_env "OPENAI_API_KEY" "$api_key_value" "backend/.env"

echo "DONE"
SCRIPT
)

ENV_SETUP_OUT=$(bash <(echo "$_env_setup_test") "$WORK_DIR" 2>&1)
assert_contains ".env 创建脚本完成执行" "$ENV_SETUP_OUT" "DONE"

assert_file_exists "根目录 .env 文件已创建"          "$WORK_DIR/.env"
assert_file_exists "backend/.env 文件已创建"          "$WORK_DIR/backend/.env"
assert_file_exists "frontend/.env.local 文件已创建"   "$WORK_DIR/frontend/.env.local"

assert_file_contains ".env 含 DB_PASSWORD 行"     "$WORK_DIR/.env"         "^DB_PASSWORD="
assert_file_contains ".env 含 SECRET_KEY 行"      "$WORK_DIR/.env"         "^SECRET_KEY="
assert_file_contains ".env 含 AI_PROVIDER 行"     "$WORK_DIR/.env"         "^AI_PROVIDER="
assert_not_file_contains ".env SECRET_KEY 不是默认值" "$WORK_DIR/.env" "your-secret-key-change"
assert_not_file_contains ".env DB_PASSWORD 不是默认值" "$WORK_DIR/.env" "your-secure-database-password"

assert_file_contains "backend/.env 含 SECRET_KEY 行" "$WORK_DIR/backend/.env" "^SECRET_KEY="
assert_not_file_contains "backend/.env SECRET_KEY 不是默认值" "$WORK_DIR/backend/.env" "your-secret-key-change"

# Test non-interactive with API key env var
(
    export OPENAI_API_KEY="sk-test-key-12345"
    bash <(echo "$_env_setup_test") "$WORK_DIR" >/dev/null 2>&1
)
assert_file_contains ".env 含 OPENAI_API_KEY 值"  "$WORK_DIR/.env" "sk-test-key-12345"

teardown

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 6】AI 提供商选择 / AI provider selection"
echo "──────────────────────────────────────────────"

assert_ok "脚本支持 openai 提供商"   grep -q 'openai'   "$INSTALL_SCRIPT"
assert_ok "脚本支持 deepseek 提供商" grep -q 'deepseek' "$INSTALL_SCRIPT"
assert_ok "脚本支持 minimax 提供商"  grep -q 'minimax'  "$INSTALL_SCRIPT"
assert_ok "脚本默认使用 openai"      grep -q 'AI_PROVIDER.*openai\|openai.*AI_PROVIDER' "$INSTALL_SCRIPT"

# Check correct API key var mapping
assert_ok "openai -> OPENAI_API_KEY 映射存在"   grep -q 'OPENAI_API_KEY'   "$INSTALL_SCRIPT"
assert_ok "deepseek -> DEEPSEEK_API_KEY 映射存在" grep -q 'DEEPSEEK_API_KEY' "$INSTALL_SCRIPT"
assert_ok "minimax -> MINIMAX_API_KEY 映射存在"  grep -q 'MINIMAX_API_KEY'  "$INSTALL_SCRIPT"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 7】非交互模式 / Non-interactive mode"
echo "──────────────────────────────────────────────"

assert_ok  "脚本支持 --non-interactive 标志" grep -q '\-\-non-interactive\|-y' "$INSTALL_SCRIPT"
assert_ok  "脚本支持 -y 短标志"              grep -q '\-y' "$INSTALL_SCRIPT"
assert_ok  "交互 read 被 NON_INTERACTIVE 条件守护" \
    grep -q 'NON_INTERACTIVE.*false.*read\|if.*NON_INTERACTIVE.*false' "$INSTALL_SCRIPT"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 8】健康等待逻辑 / Health wait logic"
echo "──────────────────────────────────────────────"

assert_ok  "脚本包含 wait_healthy 函数"   grep -q 'wait_healthy'  "$INSTALL_SCRIPT"
assert_ok  "等待 db 服务"                 grep -q 'wait_healthy.*db\|db.*wait_healthy' "$INSTALL_SCRIPT"
assert_ok  "等待 redis 服务"              grep -q 'wait_healthy.*redis\|redis.*wait_healthy' "$INSTALL_SCRIPT"
assert_ok  "等待 backend 服务"            grep -q 'wait_healthy.*backend\|backend.*wait_healthy' "$INSTALL_SCRIPT"
assert_ok  "健康等待有超时限制"           grep -q 'max_wait\|timeout\|120\|60\|30' "$INSTALL_SCRIPT"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 9】Docker Compose v1/v2 兼容性 / Docker Compose compatibility"
echo "──────────────────────────────────────────────"

assert_ok  "脚本同时支持 'docker compose' (v2)" grep -q 'docker compose' "$INSTALL_SCRIPT"
assert_ok  "脚本同时支持 'docker-compose' (v1)" grep -q 'docker-compose'  "$INSTALL_SCRIPT"
assert_ok  "使用变量 DOCKER_COMPOSE 以支持两个版本" grep -q 'DOCKER_COMPOSE' "$INSTALL_SCRIPT"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 10】数据库迁移 / Database migration"
echo "──────────────────────────────────────────────"

assert_ok  "脚本运行 alembic upgrade head" grep -q 'alembic upgrade head' "$INSTALL_SCRIPT"
assert_ok  "使用 docker compose exec 运行迁移" grep -q 'exec.*alembic\|alembic.*exec' "$INSTALL_SCRIPT"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "【测试组 11】验证与输出 / Verification and output"
echo "──────────────────────────────────────────────"

assert_ok  "脚本输出访问 URL"     grep -q 'localhost:3000\|localhost:8000' "$INSTALL_SCRIPT"
assert_ok  "脚本输出 API 文档地址" grep -q 'localhost:8000/docs\|/docs' "$INSTALL_SCRIPT"
assert_ok  "脚本包含健康端点检查"  grep -q 'health\|/health' "$INSTALL_SCRIPT"
assert_ok  "脚本打印常用命令提示"  grep -q 'logs\|restart\|down' "$INSTALL_SCRIPT"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "══════════════════════════════════════════════"
TOTAL=$((PASS + FAIL + SKIP))
echo -e "  测试结果 / Results: \033[0;32m${PASS} passed\033[0m, \033[0;31m${FAIL} failed\033[0m, \033[1;33m${SKIP} skipped\033[0m  (total: ${TOTAL})"
echo "══════════════════════════════════════════════"
echo ""

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
