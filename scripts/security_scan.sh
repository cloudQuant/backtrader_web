#!/bin/bash
# Security audit script for dependency vulnerability scanning
# Run from project root: ./scripts/security_scan.sh

set -e

echo "=========================================="
echo "Security Audit - Dependency Vulnerability Scan"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track if any issues found
ISSUES_FOUND=0

# ==========================================
# Python Dependencies Audit
# ==========================================
echo ""
echo "--- Python Dependencies Audit (pip-audit) ---"

cd src/backend

# Check if pip-audit is installed
if ! command -v pip-audit &> /dev/null; then
    echo -e "${YELLOW}pip-audit not found, installing...${NC}"
    pip install pip-audit -q
fi

# Run pip-audit
echo "Scanning Python dependencies..."
if pip-audit --desc 2>&1; then
    echo -e "${GREEN}✓ No Python dependency vulnerabilities found${NC}"
else
    echo -e "${RED}✗ Python dependency vulnerabilities detected!${NC}"
    ISSUES_FOUND=1
fi

cd ../..

# ==========================================
# Node.js Dependencies Audit
# ==========================================
echo ""
echo "--- Node.js Dependencies Audit (npm audit) ---"

cd src/frontend

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}node_modules not found, running npm install...${NC}"
    npm install
fi

# Run npm audit
echo "Scanning Node.js dependencies..."
if npm audit 2>&1; then
    echo -e "${GREEN}✓ No Node.js dependency vulnerabilities found${NC}"
else
    # npm audit returns non-zero if vulnerabilities found
    echo -e "${YELLOW}⚠ Node.js dependency vulnerabilities detected${NC}"
    echo "Run 'npm audit fix' to attempt automatic fixes"
    ISSUES_FOUND=1
fi

cd ../..

# ==========================================
# Summary
# ==========================================
echo ""
echo "=========================================="
echo "Security Audit Summary"
echo "=========================================="

if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✓ All dependencies passed security audit${NC}"
    exit 0
else
    echo -e "${RED}✗ Security issues found. Please review and fix.${NC}"
    exit 1
fi
