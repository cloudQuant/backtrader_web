#!/usr/bin/env bash
###############################################################################
# Backtrader Web - Docker 一键部署脚本
#
# 适用于全新的 Ubuntu 22.04 / 24.04 LTS 服务器
# 服务器可以是完全空白的 (连 Docker 都没有)
#
# 用法:
#   方式一: 先上传此脚本到服务器
#     scp docker_deploy.sh root@your-server:~/
#     ssh root@your-server
#     chmod +x docker_deploy.sh && ./docker_deploy.sh
#
#   方式二: 直接远程执行 (如果脚本已在网络可达位置)
#     curl -fsSL <url>/docker_deploy.sh | bash
#
# 脚本会完成以下工作:
#   1. 安装 Docker Engine 和 Docker Compose 插件
#   2. 克隆项目代码
#   3. 自动生成安全的 .env 配置 (随机密钥/密码)
#   4. 使用 docker compose 构建并启动所有服务
#   5. 等待服务就绪并验证
#   6. 保存凭据并输出访问信息
#
# 部署的服务:
#   - MySQL 8 (数据库)
#   - Redis 7 (缓存)
#   - FastAPI Backend (API 服务)
#   - Nginx + Vue 3 Frontend (Web 界面)
#
# 部署后管理:
#   查看状态:  cd /opt/backtrader_web && docker compose -f docker-compose.prod.yml ps
#   查看日志:  cd /opt/backtrader_web && docker compose -f docker-compose.prod.yml logs -f
#   重启应用:  cd /opt/backtrader_web && docker compose -f docker-compose.prod.yml restart backend frontend
#   停止应用:  cd /opt/backtrader_web && docker compose -f docker-compose.prod.yml stop backend frontend
#   停止服务:  cd /opt/backtrader_web && docker compose -f docker-compose.prod.yml down
#   更新部署:  cd /opt/backtrader_web && git pull && docker compose -f docker-compose.prod.yml build backend frontend && docker compose -f docker-compose.prod.yml up -d backend frontend
###############################################################################
set -euo pipefail

# ========================= 用户配置区 =========================

# 项目 Git 仓库地址
GIT_REPO="${GIT_REPO:-https://github.com/cloudQuant/backtrader_web.git}"
GIT_BRANCH="${GIT_BRANCH:-dev}"

# 安装目录
INSTALL_DIR="${INSTALL_DIR:-/opt/backtrader_web}"
ENV_FILE_RELATIVE_PATH="${ENV_FILE_RELATIVE_PATH:-src/backend/.env}"

# 对外 HTTP 端口 (80 = 标准 HTTP)
HTTP_PORT="${HTTP_PORT:-80}"

# 管理员账户
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"    # 留空则自动生成
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@localhost}"

# 数据库配置
DB_HOST="${DB_HOST:-mysql}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-backtrader}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_NAME="${DB_NAME:-backtrader_web}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
MYSQL_DATA_DIR="${MYSQL_DATA_DIR:-./runtime/mysql}"
REDIS_DATA_DIR="${REDIS_DATA_DIR:-./runtime/redis}"
BACKEND_LOGS_DIR="${BACKEND_LOGS_DIR:-./runtime/backend/logs}"
BACKEND_APP_DATA_DIR="${BACKEND_APP_DATA_DIR:-./runtime/backend/data}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
NO_CACHE_BUILD="${NO_CACHE_BUILD:-false}"

# 域名 (用于 CORS, 默认自动检测服务器 IP)
SERVER_DOMAIN="${SERVER_DOMAIN:-}"

# ========================= 以下无需修改 =========================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}========== $* ==========${NC}"; }

# 生成随机密码/密钥
gen_secret() {
    # 使用 openssl (通常预装), 回退到 /dev/urandom
    openssl rand -base64 48 2>/dev/null | tr -d '/+=' | head -c 48 \
        || head -c 48 /dev/urandom | base64 | tr -d '/+=' | head -c 48
}

gen_password() {
    openssl rand -base64 24 2>/dev/null | tr -d '/+=' | head -c 16 \
        || head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 16
}

read_env_value() {
    local file="$1"
    local key="$2"
    [[ -f "$file" ]] || return 0
    awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$file"
}

is_default_secret() {
    local value="$1"
    [[ -z "$value" || "$value" == "your-secret-key-change-in-production" || "$value" == "your-jwt-secret-change-in-production" ]]
}

is_default_admin_password() {
    local value="$1"
    [[ -z "$value" || "$value" == "admin123" || "$value" == "password" || "$value" == "12345678" ]]
}

# 检查 root 权限
if [[ $EUID -ne 0 ]]; then
    log_error "请使用 root 权限运行: sudo $0"
    exit 1
fi

# 检测操作系统
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    log_info "操作系统: ${PRETTY_NAME:-$ID $VERSION_ID}"
else
    log_warn "无法检测操作系统, 继续尝试..."
fi

# 自动检测服务器 IP
if [[ -z "$SERVER_DOMAIN" ]]; then
    SERVER_DOMAIN=$(curl -s --max-time 5 ifconfig.me 2>/dev/null \
        || ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1 \
        || hostname -I | awk '{print $1}' \
        || echo "localhost")
    log_info "自动检测服务器地址: ${SERVER_DOMAIN}"
fi

# 自动生成缺失的密码
EXISTING_SECRET_KEY=$(read_env_value "${INSTALL_DIR}/${ENV_FILE_RELATIVE_PATH}" "SECRET_KEY")
EXISTING_JWT_SECRET_KEY=$(read_env_value "${INSTALL_DIR}/${ENV_FILE_RELATIVE_PATH}" "JWT_SECRET_KEY")
EXISTING_ADMIN_PASSWORD=$(read_env_value "${INSTALL_DIR}/${ENV_FILE_RELATIVE_PATH}" "ADMIN_PASSWORD")
EXISTING_DB_PASSWORD=$(read_env_value "${INSTALL_DIR}/${ENV_FILE_RELATIVE_PATH}" "DB_PASSWORD")
EXISTING_MYSQL_ROOT_PASSWORD=$(read_env_value "${INSTALL_DIR}/${ENV_FILE_RELATIVE_PATH}" "MYSQL_ROOT_PASSWORD")

if [[ -z "${DB_PASSWORD}" ]]; then
    DB_PASSWORD="${EXISTING_DB_PASSWORD}"
fi
if [[ -z "${MYSQL_ROOT_PASSWORD}" ]]; then
    MYSQL_ROOT_PASSWORD="${EXISTING_MYSQL_ROOT_PASSWORD}"
fi
if [[ -z "${ADMIN_PASSWORD}" ]]; then
    ADMIN_PASSWORD="${EXISTING_ADMIN_PASSWORD}"
fi
if is_default_secret "${SECRET_KEY:-}"; then
    if ! is_default_secret "${EXISTING_SECRET_KEY}"; then
        SECRET_KEY="${EXISTING_SECRET_KEY}"
    else
        SECRET_KEY=$(gen_secret)
    fi
fi
if is_default_secret "${JWT_SECRET_KEY:-}"; then
    if ! is_default_secret "${EXISTING_JWT_SECRET_KEY}"; then
        JWT_SECRET_KEY="${EXISTING_JWT_SECRET_KEY}"
    else
        JWT_SECRET_KEY=$(gen_secret)
    fi
fi
if [[ -z "${DB_PASSWORD}" ]]; then
    DB_PASSWORD=$(gen_password)
    log_warn "自动生成 MySQL 应用密码"
fi
if [[ -z "${MYSQL_ROOT_PASSWORD}" ]]; then
    MYSQL_ROOT_PASSWORD=$(gen_password)
    log_warn "自动生成 MySQL Root 密码"
fi
if is_default_admin_password "${ADMIN_PASSWORD}"; then
    ADMIN_PASSWORD=$(gen_password)
    log_warn "自动生成管理员密码"
fi

###############################################################################
# 1. 安装 Docker
###############################################################################
log_step "1/5 安装 Docker"

if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version)
    log_info "Docker 已安装: ${DOCKER_VERSION}"
else
    log_info "正在安装 Docker..."

    # 安装依赖
    apt-get update -qq
    apt-get install -y -qq \
        ca-certificates \
        curl \
        gnupg \
        lsb-release

    # 添加 Docker 官方 GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    # 添加 Docker 仓库
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "${VERSION_CODENAME:-$UBUNTU_CODENAME}") stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null

    # 安装 Docker Engine + Compose 插件
    apt-get update -qq
    apt-get install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    # 启动 Docker
    systemctl enable docker
    systemctl start docker

    log_info "Docker 安装完成: $(docker --version)"
fi

# 验证 docker compose
if ! docker compose version &>/dev/null; then
    log_error "Docker Compose 插件未安装"
    exit 1
fi
log_info "Docker Compose: $(docker compose version --short)"

###############################################################################
# 2. 克隆项目
###############################################################################
log_step "2/5 获取项目代码"

# 安装 git (如果没有)
if ! command -v git &>/dev/null; then
    apt-get install -y -qq git
fi

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    log_info "项目已存在, 执行 git pull"
    cd "${INSTALL_DIR}"
    git fetch origin
    git checkout "${GIT_BRANCH}" 2>/dev/null || git checkout -b "${GIT_BRANCH}" "origin/${GIT_BRANCH}"
    git pull origin "${GIT_BRANCH}"
else
    log_info "克隆项目到 ${INSTALL_DIR}"
    rm -rf "${INSTALL_DIR}"
    git clone --branch "${GIT_BRANCH}" --single-branch "${GIT_REPO}" "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"
log_info "项目版本: $(git log --oneline -1)"

mkdir -p \
    "${INSTALL_DIR}/runtime/mysql" \
    "${INSTALL_DIR}/runtime/redis" \
    "${INSTALL_DIR}/runtime/backend/logs" \
    "${INSTALL_DIR}/runtime/backend/data" \
    "${INSTALL_DIR}/workspace_units"

###############################################################################
# 3. 生成配置
###############################################################################
log_step "3/5 生成配置文件"

ENV_FILE="${INSTALL_DIR}/${ENV_FILE_RELATIVE_PATH}"
mkdir -p "$(dirname "${ENV_FILE}")"

cat > "${ENV_FILE}" <<EOF
# ===== Backtrader Web Docker 配置 =====
# 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')
# 此文件由 docker compose --env-file ${ENV_FILE_RELATIVE_PATH} 读取

# MySQL
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=${DB_NAME}
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
MYSQL_DATA_DIR=${MYSQL_DATA_DIR}
REDIS_DATA_DIR=${REDIS_DATA_DIR}
BACKEND_LOGS_DIR=${BACKEND_LOGS_DIR}
BACKEND_APP_DATA_DIR=${BACKEND_APP_DATA_DIR}

# 安全密钥
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}

# 管理员账户
ADMIN_USERNAME=${ADMIN_USERNAME}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ADMIN_EMAIL=${ADMIN_EMAIL}

# CORS (逗号分隔)
CORS_ORIGINS=http://localhost,http://127.0.0.1,http://${SERVER_DOMAIN}

# 对外端口
HTTP_PORT=${HTTP_PORT}
DB_AUTO_CREATE_SCHEMA=true
DB_AUTO_CREATE_DEFAULT_ADMIN=true
EOF

chmod 600 "${ENV_FILE}"
log_info ".env 配置已生成"

###############################################################################
# 4. 构建并启动
###############################################################################
log_step "4/5 构建并启动 Docker 服务"

cd "${INSTALL_DIR}"

log_info "启动基础服务 (MySQL/Redis)..."
docker compose --env-file "${ENV_FILE_RELATIVE_PATH}" -f "${COMPOSE_FILE}" up -d mysql redis

log_info "构建应用镜像..."
if [[ "${NO_CACHE_BUILD}" == "true" ]]; then
    docker compose --env-file "${ENV_FILE_RELATIVE_PATH}" -f "${COMPOSE_FILE}" build --no-cache backend frontend
else
    docker compose --env-file "${ENV_FILE_RELATIVE_PATH}" -f "${COMPOSE_FILE}" build backend frontend
fi

log_info "启动应用服务..."
docker compose --env-file "${ENV_FILE_RELATIVE_PATH}" -f "${COMPOSE_FILE}" up -d --remove-orphans backend frontend

log_info "服务已启动"

###############################################################################
# 5. 等待服务就绪
###############################################################################
log_step "5/5 验证服务状态"

log_info "等待后端启动..."
MAX_WAIT=120
for i in $(seq 1 $MAX_WAIT); do
    if curl -sf "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
        log_info "服务已就绪! (等待 ${i} 秒)"
        break
    fi
    if [[ $i -eq $MAX_WAIT ]]; then
        log_warn "等待超时, 服务可能仍在启动中"
        log_warn "请手动检查: docker compose -f ${COMPOSE_FILE} logs -f"
    fi
    sleep 1
done

# 显示容器状态
echo ""
docker compose --env-file "${ENV_FILE_RELATIVE_PATH}" -f "${COMPOSE_FILE}" ps

###############################################################################
# 保存凭据
###############################################################################
CREDENTIALS_FILE="/root/.backtrader_web_credentials"
cat > "${CREDENTIALS_FILE}" <<EOF
# Backtrader Web Docker 部署凭据 - 请妥善保管!
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')

MySQL 主机:          ${DB_HOST}
MySQL 端口:          ${DB_PORT}
MySQL 用户:          ${DB_USER}
MySQL 密码:          ${DB_PASSWORD}
MySQL 数据库:        ${DB_NAME}
MySQL Root 密码:     ${MYSQL_ROOT_PASSWORD}

管理员用户名:        ${ADMIN_USERNAME}
管理员密码:          ${ADMIN_PASSWORD}
管理员邮箱:          ${ADMIN_EMAIL}
EOF
chmod 600 "${CREDENTIALS_FILE}"

###############################################################################
# 完成
###############################################################################
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Backtrader Web Docker 部署完成!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "  访问地址:     ${BLUE}http://${SERVER_DOMAIN}${NC}"
echo -e "  API 文档:     ${BLUE}http://${SERVER_DOMAIN}/docs${NC}"
echo ""
echo -e "  管理员账号:   ${ADMIN_USERNAME}"
echo -e "  管理员密码:   ${ADMIN_PASSWORD}"
echo ""
echo -e "  ${YELLOW}所有凭据已保存到: ${CREDENTIALS_FILE}${NC}"
echo ""
echo -e "  常用命令:"
echo -e "    cd ${INSTALL_DIR}"
echo -e "    查看状态:      docker compose --env-file ${ENV_FILE_RELATIVE_PATH} -f ${COMPOSE_FILE} ps"
echo -e "    查看日志:      docker compose --env-file ${ENV_FILE_RELATIVE_PATH} -f ${COMPOSE_FILE} logs -f"
echo -e "    查看后端日志:  docker compose --env-file ${ENV_FILE_RELATIVE_PATH} -f ${COMPOSE_FILE} logs -f backend"
echo -e "    重启服务:      docker compose --env-file ${ENV_FILE_RELATIVE_PATH} -f ${COMPOSE_FILE} restart backend frontend"
echo -e "    停止应用:      docker compose --env-file ${ENV_FILE_RELATIVE_PATH} -f ${COMPOSE_FILE} stop backend frontend"
echo -e "    停止全部:      docker compose --env-file ${ENV_FILE_RELATIVE_PATH} -f ${COMPOSE_FILE} down"
echo ""
echo -e "  更新部署:"
echo -e "    cd ${INSTALL_DIR}"
echo -e "    git pull origin ${GIT_BRANCH}"
echo -e "    docker compose --env-file ${ENV_FILE_RELATIVE_PATH} -f ${COMPOSE_FILE} build backend frontend && docker compose --env-file ${ENV_FILE_RELATIVE_PATH} -f ${COMPOSE_FILE} up -d backend frontend"
echo ""
