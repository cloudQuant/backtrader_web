#!/bin/bash
###############################################################################
# Renew Let's Encrypt SSL Certificate for aifortrader.cn
#
# Usage:
#   ./scripts/certbot-renew.sh
#
# This script is also called automatically every 2 months by the certbot
# container via its entrypoint.
###############################################################################

set -e

DOMAIN="aifortrader.cn"
CERT_DIR="./runtime/certbot"
CONF_DIR="${CERT_DIR}/conf"

echo "=== Renewing Let's Encrypt Certificate for ${DOMAIN} ==="

docker run --rm \
    -v "$(pwd)/${CONF_DIR}:/etc/letsencrypt" \
    -v "$(pwd)/${CERT_DIR}/www:/var/www/certbot" \
    --entrypoint certbot \
    certbot/certbot:latest \
    renew \
    --webroot \
    --webroot-path /var/www/certbot \
    --post-hook "docker exec backtrader_frontend nginx -s reload"

echo "=== Certificate renewal complete ==="
