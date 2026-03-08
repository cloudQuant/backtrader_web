# Story 117.2: Backtest Task Persistence Implementation Summary

## Overview
Backtest task state has been extracted from pure in-memory bookkeeping into a
database-persistent task model managed by `BacktestExecutionManager`.

As of迭代119, execution ownership is also explicitly split:

1. `BacktestExecutionManager` only manages persisted task state and results
2. `BacktestExecutionRunner` only manages process-local asyncio tasks and subprocess handles

This improves the boundary between state and execution, but it is not yet a full
multi-worker or restart-resumable execution system.

## Changes Made

### 1. Created `BacktestExecutionManager` (src/backend/app/services/backtest_manager.py)
- New service class for database-backed task state management
- Key features:
  - Database as single source of truth for task state
  - Task metadata survives service restart
  - User task limits enforced via database queries (MAX_GLOBAL_TASKS=10, MAX_USER_TASKS=3)
  - Supports task creation, status updates, result storage, deletion, and listing

- Methods:
  - `create_task(user_id, request)` - Create task with limit checking
  - `get_task(task_id, user_id)` - Get task with authorization
  - `update_task_status(task_id, status, error_message, log_dir)` - Update status
  - `create_result(task_id, metrics, ...)` - Store backtest results
  - `get_result(task_id)` - Retrieve backtest results
  - `delete_task_and_result(task_id, user_id)` - Delete task and result
  - `list_user_tasks(user_id, limit, offset, ...)` - List tasks with pagination
  - `get_user_task_count(user_id)` - Get active task count
  - `can_user_start_task(user_id)` - Check if user can start new task
  - `get_global_task_count()` - Get total active task count

### 2. Updated `BacktestService` (src/backend/app/services/backtest_service.py)
- `BacktestService` now coordinates two explicit collaborators:
  - `BacktestExecutionManager` for persisted task state
  - `BacktestExecutionRunner` for process-local execution handles

- Integrated `BacktestExecutionManager`:
  - Added `self.task_manager = BacktestExecutionManager()` to __init__

- Integrated `BacktestExecutionRunner`:
  - Added `self.task_runner = BacktestExecutionRunner()` to __init__

- Updated methods to use task_manager:
  - `run_backtest()` - Uses `task_manager.create_task()` for task creation and limit checking
  - `_execute_backtest()` - Uses `task_manager.update_task_status()` for status updates
  - `_execute_backtest()` success path - Uses `task_manager.create_result()` for result storage
  - `_execute_backtest()` exception handlers - Use `task_manager.update_task_status()` for FAILED/CANCELLED states
  - `cancel_task()` - Uses `task_runner` for process-local cancellation and `task_manager` for persisted status updates
  - `delete_result()` - Uses `task_manager.delete_task_and_result()` for deletion

### 3. Added `BacktestExecutionRunner` (src/backend/app/services/backtest_runner.py)
- New process-local execution helper
- Responsibilities:
  - schedule local asyncio tasks
  - track subprocess handles for the current process
  - perform best-effort local cancellation
  - release execution handles after task completion

## Benefits

1. **Persistence**: Task metadata and results are database-backed instead of pure in-memory state
2. **Cleaner architecture**: Clear separation between task state management and execution logic
3. **Honest execution model**: The code no longer implies that database persistence alone equals worker decoupling
4. **Safer cancellation boundary**: Only process-local execution is cancellable in the current design

## Backward Compatibility

- API contracts remain unchanged
- WebSocket notification format remains the same
- Backtest execution logic (strategy running, log parsing, etc.) unchanged
- Only the internal state management mechanism changed

## Testing Considerations

### Existing Tests to Update
The following test files may need updates to accommodate the new architecture:

1. `src/backend/tests/test_backtest_service.py`
   - Tests for `run_backtest()` now use database-backed task creation
   - Tests for `cancel_task()` need to account for new cancellation flow
   - Tests for concurrency limits need to verify database-based enforcement

2. `src/backend/tests/test_backtest_api.py`
   - API behavior should remain unchanged, but integration tests should verify
   - Ensure task state persists correctly across requests

3. `tests/e2e/test_backtest.py` and `tests/e2e/test_backtest_result.py`
   - E2E tests should verify task metadata survives service restarts
   - Test cancellation and cleanup scenarios

### New Tests Needed
1. Test `BacktestExecutionManager` methods:
   - Task creation with limit enforcement
   - Status updates
   - Result storage and retrieval
   - Task deletion with file cleanup
   - Pagination and sorting in list_user_tasks

2. Test persistence across service restarts:
   - Create task, restart service, verify task metadata still exists in the database
   - Confirm RUNNING tasks do not resume automatically after restart in the current design

3. Test multi-worker scenarios (if applicable):
   - Multiple workers accessing the same persisted task state
   - Verify only the worker that owns the local execution handle can cancel a running subprocess

## Files Modified

1. **Created**: `src/backend/app/services/backtest_manager.py` (257 lines)
   - New BacktestExecutionManager class

2. **Modified**: `src/backend/app/services/backtest_service.py`
   - Explicitly separates persisted task state from process-local execution
   - Uses `task_runner` for local scheduling and cancellation

3. **Created**: `src/backend/app/services/backtest_runner.py`
   - New BacktestExecutionRunner class

## Migration Path

No schema migration is required for this boundary split:
- Existing tasks in the database continue to work
- New tasks automatically use the persistent task manager
- Process-local execution handles are intentionally not shared across workers

## Next Steps

1. Update existing tests to verify new behavior
2. Add tests for BacktestExecutionManager
3. Verify E2E tests still pass
4. Monitor task persistence in production
5. Add task recovery or stale-task reconciliation for RUNNING tasks after restart
6. Introduce a real worker queue before claiming multi-worker execution support
