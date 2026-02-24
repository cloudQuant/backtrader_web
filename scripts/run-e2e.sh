#!/bin/bash
# E2E Test Runner Script
# Usage: ./scripts/run-e2e.sh [options]
# Options:
#   --headed           Run tests in headed mode
#   --debug            Run tests in debug mode
#   --ui               Run tests with UI mode
#   --project=<name>   Run tests for specific project (chromium/firefox/webkit)
#   --file=<path>      Run specific test file

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/src/frontend"
BACKEND_DIR="$PROJECT_ROOT/src/backend"

# Default options
HEADED=false
DEBUG=false
UI_MODE=false
PROJECT=""
TEST_FILE=""

# Parse arguments
for arg in "$@"; do
    case $arg in
        --headed)
            HEADED=true
            shift
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --ui)
            UI_MODE=true
            shift
            ;;
        --project=*)
            PROJECT="${arg#*=}"
            shift
            ;;
        --file=*)
            TEST_FILE="${arg#*=}"
            shift
            ;;
        *)
            # Unknown option
            ;;
    esac
done

echo "========================================"
echo "E2E Test Runner"
echo "========================================"
echo "Project Root: $PROJECT_ROOT"
echo "Frontend: $FRONTEND_DIR"
echo "Backend: $BACKEND_DIR"
echo "========================================"

# Function to check if backend is running
check_backend() {
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to check if frontend is running
check_frontend() {
    if curl -s http://localhost:3000 > /dev/null 2>&1 || \
       curl -s http://localhost:5173 > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to start backend
start_backend() {
    echo "Starting backend server..."
    cd "$BACKEND_DIR"
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/backend.log 2>&1 &
    BACKEND_PID=$!
    echo "Backend PID: $BACKEND_PID"

    # Wait for backend to be ready
    for i in {1..30}; do
        if check_backend; then
            echo "Backend is ready!"
            return 0
        fi
        echo "Waiting for backend... ($i/30)"
        sleep 2
    done

    echo "ERROR: Backend failed to start"
    cat /tmp/backend.log
    return 1
}

# Function to start frontend
start_frontend() {
    echo "Starting frontend server..."
    cd "$FRONTEND_DIR"

    # Check if dev server is already configured for port 3000 or 5173
    if grep -q "port: 3000" vite.config.ts 2>/dev/null || \
       grep -q "port: 5173" vite.config.ts 2>/dev/null; then
        npm run dev > /tmp/frontend.log 2>&1 &
    else
        npm run dev -- --port 3000 > /tmp/frontend.log 2>&1 &
    fi

    FRONTEND_PID=$!
    echo "Frontend PID: $FRONTEND_PID"

    # Wait for frontend to be ready
    for i in {1..30}; do
        if check_frontend; then
            echo "Frontend is ready!"
            return 0
        fi
        echo "Waiting for frontend... ($i/30)"
        sleep 2
    done

    echo "ERROR: Frontend failed to start"
    cat /tmp/frontend.log
    return 1
}

# Function to cleanup
cleanup() {
    echo ""
    echo "========================================"
    echo "Cleaning up..."

    if [ ! -z "$BACKEND_PID" ]; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
    fi

    if [ ! -z "$FRONTEND_PID" ]; then
        echo "Stopping frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null || true
    fi

    echo "Cleanup complete!"
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Check if services are already running
SERVICES_ALREADY_RUNNING=false
if check_backend && check_frontend; then
    echo "Both services are already running!"
    SERVICES_ALREADY_RUNNING=true
else
    # Start services if not running
    if ! check_backend; then
        start_backend || exit 1
    else
        echo "Backend is already running!"
    fi

    if ! check_frontend; then
        start_frontend || exit 1
    else
        echo "Frontend is already running!"
    fi
fi

# Determine base URL
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    BASE_URL="http://localhost:3000"
elif curl -s http://localhost:5173 > /dev/null 2>&1; then
    BASE_URL="http://localhost:5173"
else
    echo "ERROR: Could not determine frontend URL"
    exit 1
fi

echo "========================================"
echo "Running E2E Tests"
echo "========================================"
echo "Base URL: $BASE_URL"
echo ""

# Build Playwright command
cd "$FRONTEND_DIR"

PLAYWRIGHT_CMD="npx playwright test"

# Add project filter if specified
if [ ! -z "$PROJECT" ]; then
    PLAYWRIGHT_CMD="$PLAYWRIGHT_CMD --project=$PROJECT"
fi

# Add file filter if specified
if [ ! -z "$TEST_FILE" ]; then
    PLAYWRIGHT_CMD="$PLAYWRIGHT_CMD $TEST_FILE"
fi

# Add mode flags
if [ "$DEBUG" = true ]; then
    PLAYWRIGHT_CMD="npx playwright test --debug"
elif [ "$UI_MODE" = true ]; then
    PLAYWRIGHT_CMD="npx playwright test --ui"
elif [ "$HEADED" = true ]; then
    PLAYWRIGHT_CMD="$PLAYWRIGHT_CMD --headed"
fi

# Run tests
echo "Command: $PLAYWRIGHT_CMD"
echo "========================================"

export BASE_URL="$BASE_URL"
eval $PLAYWRIGHT_CMD

# Exit with proper code
exit $?
