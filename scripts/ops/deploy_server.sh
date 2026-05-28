#!/usr/bin/env bash
###############################################################################
# Backtrader Web - 一键服务器部署脚本
#
# 适用于全新的 Ubuntu 22.04 / 24.04 LTS 服务器
# 用法:
#   1. 将此脚本上传到服务器 (或 git clone 后执行)
#   2. 编辑脚本顶部的配置变量
#   3. chmod +x deploy_server.sh && sudo ./deploy_server.sh
#
# 脚本会完成以下工作:
#   - 安装系统依赖 (Python 3.11, Node.js 20, MySQL 8, Nginx)
#   - 创建项目用户和目录
#   - 克隆项目代码
#   - 创建 MySQL 数据库和用户
#   - 生成 .env 配置 (随机安全密钥)
#   - 安装 Python / Node 依赖
#   - 构建前端
#   - 配置 Nginx 反向代理
#   - 配置 systemd 服务 (后端自动重启)
#   - 初始化数据库表和管理员账户
#   - 启动服务
###############################################################################
set -euo pipefail

# ========================= 用户配置区 (部署前请修改) =========================

# 项目 Git 仓库地址
GIT_REPO="${GIT_REPO:-https://github.com/cloudQuant/backtrader_web.git}"
GIT_BRANCH="${GIT_BRANCH:-dev}"

# 安装目录
INSTALL_DIR="${INSTALL_DIR:-/opt/backtrader_web}"

# 运行项目的系统用户
APP_USER="${APP_USER:-backtrader}"

# MySQL 配置
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"  # 留空则自动生成
MYSQL_APP_USER="${MYSQL_APP_USER:-backtrader}"
MYSQL_APP_PASSWORD="${MYSQL_APP_PASSWORD:-}"    # 留空则自动生成
MYSQL_DB_MAIN="${MYSQL_DB_MAIN:-backtrader_web}"
MYSQL_DB_DATA="${MYSQL_DB_DATA:-akshare_data}"

# 后端配置
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_WORKERS="${BACKEND_WORKERS:-4}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"           # 留空则自动生成
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@localhost}"

# Nginx 域名 (使用 IP 则填 _ 或服务器 IP)
SERVER_DOMAIN="${SERVER_DOMAIN:-_}"

# Python 版本
PYTHON_VERSION="3.11"

# ========================= 以下无需修改 ======================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}========== $* ==========${NC}"; }

# 生成随机密码 (32 字符)
gen_password() {
    python3 -c "import secrets; print(secrets.token_urlsafe(32))"
}

# 检查 root 权限
if [[ $EUID -ne 0 ]]; then
    log_error "请使用 root 权限运行: sudo $0"
    exit 1
fi

# 自动生成缺失的密码
if [[ -z "$MYSQL_ROOT_PASSWORD" ]]; then
    MYSQL_ROOT_PASSWORD=$(gen_password)
    log_warn "自动生成 MySQL root 密码: $MYSQL_ROOT_PASSWORD"
fi
if [[ -z "$MYSQL_APP_PASSWORD" ]]; then
    MYSQL_APP_PASSWORD=$(gen_password)
    log_warn "自动生成 MySQL 应用密码: $MYSQL_APP_PASSWORD"
fi
if [[ -z "$ADMIN_PASSWORD" ]]; then
    ADMIN_PASSWORD=$(gen_password | head -c 16)
    log_warn "自动生成管理员密码: $ADMIN_PASSWORD"
fi

SECRET_KEY=$(gen_password)
JWT_SECRET_KEY=$(gen_password)

# 保存所有密码到文件
CREDENTIALS_FILE="/root/.backtrader_web_credentials"

###############################################################################
# 1. 系统依赖
###############################################################################
log_step "1/10 安装系统依赖"

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq \
    software-properties-common curl wget git build-essential \
    libffi-dev libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev libncurses5-dev libgdbm-dev libnss3-dev \
    libxml2-dev libxslt1-dev nginx

# Python
if ! command -v "python${PYTHON_VERSION}" &>/dev/null; then
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y -qq "python${PYTHON_VERSION}" "python${PYTHON_VERSION}-venv" "python${PYTHON_VERSION}-dev"
fi

# pip
"python${PYTHON_VERSION}" -m ensurepip --upgrade 2>/dev/null || true
"python${PYTHON_VERSION}" -m pip install --upgrade pip setuptools wheel

# Node.js 20 LTS
if ! command -v node &>/dev/null || [[ "$(node -v | cut -d. -f1 | tr -d v)" -lt 18 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
fi

log_info "Python: $("python${PYTHON_VERSION}" --version)"
log_info "Node.js: $(node --version)"
log_info "npm: $(npm --version)"

###############################################################################
# 2. MySQL
###############################################################################
log_step "2/10 安装并配置 MySQL"

if ! command -v mysql &>/dev/null; then
    # 预设 root 密码避免交互
    debconf-set-selections <<< "mysql-server mysql-server/root_password password ${MYSQL_ROOT_PASSWORD}"
    debconf-set-selections <<< "mysql-server mysql-server/root_password_again password ${MYSQL_ROOT_PASSWORD}"
    apt-get install -y -qq mysql-server mysql-client
fi

systemctl enable mysql
systemctl start mysql

# 设置 root 密码 (如果 MySQL 使用 auth_socket)
mysql -u root <<-EOSQL 2>/dev/null || true
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '${MYSQL_ROOT_PASSWORD}';
FLUSH PRIVILEGES;
EOSQL

# 创建数据库和应用用户
mysql -u root -p"${MYSQL_ROOT_PASSWORD}" <<-EOSQL
CREATE DATABASE IF NOT EXISTS \`${MYSQL_DB_MAIN}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS \`${MYSQL_DB_DATA}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS '${MYSQL_APP_USER}'@'localhost' IDENTIFIED BY '${MYSQL_APP_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${MYSQL_DB_MAIN}\`.* TO '${MYSQL_APP_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${MYSQL_DB_DATA}\`.* TO '${MYSQL_APP_USER}'@'localhost';
FLUSH PRIVILEGES;
EOSQL

log_info "MySQL 数据库 ${MYSQL_DB_MAIN} 和 ${MYSQL_DB_DATA} 已创建"

###############################################################################
# 3. 创建项目用户
###############################################################################
log_step "3/10 创建项目用户"

if ! id "$APP_USER" &>/dev/null; then
    useradd --system --create-home --shell /bin/bash "$APP_USER"
    log_info "用户 ${APP_USER} 已创建"
else
    log_info "用户 ${APP_USER} 已存在"
fi

###############################################################################
# 4. 克隆项目
###############################################################################
log_step "4/10 克隆项目代码"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    log_info "项目已存在，执行 git pull"
    su - "$APP_USER" -c "cd ${INSTALL_DIR} && git fetch origin && git checkout ${GIT_BRANCH} && git pull origin ${GIT_BRANCH}"
else
    rm -rf "${INSTALL_DIR}"
    git clone --branch "${GIT_BRANCH}" --single-branch "${GIT_REPO}" "${INSTALL_DIR}"
    chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}"
    log_info "项目已克隆到 ${INSTALL_DIR}"
fi

###############################################################################
# 5. 生成 .env
###############################################################################
log_step "5/10 生成后端 .env 配置"

ENV_FILE="${INSTALL_DIR}/src/backend/.env"

cat > "${ENV_FILE}" <<EOF
# ===== 自动生成于 $(date '+%Y-%m-%d %H:%M:%S') =====
APP_NAME=backtrader_web
DEBUG=false
SECRET_KEY=${SECRET_KEY}

# 数据库
DATABASE_TYPE=mysql
DATABASE_URL=mysql+asyncmy://${MYSQL_APP_USER}:${MYSQL_APP_PASSWORD}@127.0.0.1:3306/${MYSQL_DB_MAIN}
AKSHARE_DATA_DATABASE_URL=mysql+asyncmy://${MYSQL_APP_USER}:${MYSQL_APP_PASSWORD}@127.0.0.1:3306/${MYSQL_DB_DATA}

# JWT
JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# 服务
HOST=127.0.0.1
PORT=${BACKEND_PORT}
CORS_ORIGINS=http://localhost,http://127.0.0.1,http://${SERVER_DOMAIN}

# 管理员
ADMIN_USERNAME=${ADMIN_USERNAME}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ADMIN_EMAIL=${ADMIN_EMAIL}

# 数据库自动初始化
DB_AUTO_CREATE_SCHEMA=true
DB_AUTO_CREATE_DEFAULT_ADMIN=true

# Akshare
AKSHARE_SCHEDULER_TIMEZONE=Asia/Shanghai
AKSHARE_SCRIPT_ROOT=app/data_fetch/scripts
AKSHARE_INTERFACE_BOOTSTRAP_MODE=manual
EOF

chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
chmod 600 "${ENV_FILE}"
log_info ".env 已生成 (权限 600)"

###############################################################################
# 6. 安装后端依赖
###############################################################################
log_step "6/10 安装后端 Python 依赖"

VENV_DIR="${INSTALL_DIR}/venv"

su - "$APP_USER" -c "
    cd ${INSTALL_DIR}/src/backend
    python${PYTHON_VERSION} -m venv ${VENV_DIR}
    source ${VENV_DIR}/bin/activate
    pip install --upgrade pip setuptools wheel -q
    pip install -e '.[backtrader]' -q
    pip install asyncmy -q
"
log_info "Python 虚拟环境: ${VENV_DIR}"

###############################################################################
# 7. 构建前端
###############################################################################
log_step "7/10 构建前端"

su - "$APP_USER" -c "
    cd ${INSTALL_DIR}/src/frontend
    npm ci --silent 2>/dev/null || npm install --silent
    npm run build
"

FRONTEND_DIST="${INSTALL_DIR}/src/frontend/dist"
if [[ -d "$FRONTEND_DIST" ]]; then
    log_info "前端构建完成: ${FRONTEND_DIST}"
else
    log_error "前端构建失败，dist 目录不存在"
    exit 1
fi

###############################################################################
# 8. 配置 systemd 服务
###############################################################################
log_step "8/10 配置 systemd 后端服务"

cat > /etc/systemd/system/backtrader-web.service <<EOF
[Unit]
Description=Backtrader Web API
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=exec
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${INSTALL_DIR}/src/backend
Environment=PATH=${VENV_DIR}/bin:/usr/bin:/bin
ExecStart=${VENV_DIR}/bin/uvicorn app.main:app \\
    --host 127.0.0.1 \\
    --port ${BACKEND_PORT} \\
    --workers ${BACKEND_WORKERS} \\
    --access-log \\
    --log-level info
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# 安全加固
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable backtrader-web
log_info "systemd 服务 backtrader-web 已注册"

###############################################################################
# 9. 配置 Nginx
###############################################################################
log_step "9/10 配置 Nginx 反向代理"

cat > /etc/nginx/sites-available/backtrader-web <<EOF
server {
    listen 80;
    server_name ${SERVER_DOMAIN};

    # 前端静态文件
    root ${FRONTEND_DIST};
    index index.html;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;

    # 静态资源缓存
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 后端 API
    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        client_max_body_size 50M;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400s;
    }

    # API 文档
    location ~ ^/(docs|redoc|openapi.json) {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
    }

    # Vue Router history 模式 - 所有未匹配路由回退到 index.html
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/backtrader-web /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl enable nginx
systemctl restart nginx
log_info "Nginx 已配置并重启"

###############################################################################
# 10. 启动服务
###############################################################################
log_step "10/10 启动服务"

systemctl start backtrader-web

# 等待后端就绪
log_info "等待后端启动..."
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
        log_info "后端已就绪"
        break
    fi
    sleep 1
done

# 验证
HEALTH=$(curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" 2>/dev/null || echo '{"status":"failed"}')
DB_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json;print(json.load(sys.stdin).get('database','unknown'))" 2>/dev/null || echo "unknown")

###############################################################################
# 保存凭据
###############################################################################
cat > "${CREDENTIALS_FILE}" <<EOF
# Backtrader Web 部署凭据 - 请妥善保管！
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')

MySQL root 密码:     ${MYSQL_ROOT_PASSWORD}
MySQL 应用用户:      ${MYSQL_APP_USER}
MySQL 应用密码:      ${MYSQL_APP_PASSWORD}
管理员用户名:        ${ADMIN_USERNAME}
管理员密码:          ${ADMIN_PASSWORD}
JWT 密钥:            ${JWT_SECRET_KEY}

安装目录:            ${INSTALL_DIR}
后端端口:            ${BACKEND_PORT}
EOF
chmod 600 "${CREDENTIALS_FILE}"

###############################################################################
# 完成
###############################################################################
echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "  访问地址:     ${BLUE}http://${SERVER_DOMAIN}${NC}"
echo -e "  API 文档:     ${BLUE}http://${SERVER_DOMAIN}/docs${NC}"
echo -e "  数据库状态:   ${DB_STATUS}"
echo ""
echo -e "  管理员账号:   ${ADMIN_USERNAME}"
echo -e "  管理员密码:   ${ADMIN_PASSWORD}"
echo ""
echo -e "  ${YELLOW}所有凭据已保存到: ${CREDENTIALS_FILE}${NC}"
echo ""
echo -e "  常用命令:"
echo -e "    查看后端状态:  systemctl status backtrader-web"
echo -e "    查看后端日志:  journalctl -u backtrader-web -f"
echo -e "    重启后端:      systemctl restart backtrader-web"
echo -e "    重启 Nginx:    systemctl restart nginx"
echo ""
echo -e "  更新部署:"
echo -e "    cd ${INSTALL_DIR} && git pull"
echo -e "    cd src/frontend && npm run build"
echo -e "    systemctl restart backtrader-web"
echo ""
