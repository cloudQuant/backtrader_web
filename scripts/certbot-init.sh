#!/bin/bash
###############################################################################
# Obtain Let's Encrypt SSL Certificate for aifortrader.cn
#
# Usage:
#   ./scripts/certbot-init.sh
#
# This script:
#   1. Creates required directories for certbot
#   2. Stops nginx to allow certbot to bind port 80
#   3. Obtains the certificate
#   4. Restarts nginx
###############################################################################

set -e

DOMAIN="aifortrader.cn"
EMAIL="${CERTBOT_EMAIL:-admin@aifortrader.cn}"
CERT_DIR="./runtime/certbot"
CONF_DIR="${CERT_DIR}/conf"
WWW_DIR="${CERT_DIR}/www"

echo "=== Let's Encrypt Certificate Initialization for ${DOMAIN} ==="

mkdir -p "${CONF_DIR}/live/${DOMAIN}"
mkdir -p "${WWW_DIR}/.well-known/acme-challenge"

if [ -f "${CONF_DIR}/live/${DOMAIN}/fullchain.pem" ]; then
    echo "Certificate already exists at ${CONF_DIR}/live/${DOMAIN}/"
    echo "Skipping certificate generation."
    exit 0
fi

echo "Stopping nginx to allow certbot to bind port 80..."
docker compose -f docker-compose.prod.yml stop frontend

echo "Obtaining certificate from Let's Encrypt..."
docker run --rm \
    -v "$(pwd)/${CONF_DIR}:/etc/letsencrypt" \
    -v "$(pwd)/${WWW_DIR}:/var/www/certbot" \
    --entrypoint certbot \
    certbot/certbot:latest \
    certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --domain "${DOMAIN}" \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    --keep-until-expiring \
    || true

echo "Restarting nginx..."
docker compose -f docker-compose.prod.yml start frontend

if [ -f "${CONF_DIR}/live/${DOMAIN}/fullchain.pem" ]; then
    echo "=== Certificate obtained successfully! ==="
else
    echo "=== Warning: Certificate may not have been obtained ==="
    echo "Please check the output above for errors."
fi
