-- Add performance indexes for high-frequency queries
-- Generated: 2025-03-07

-- Create indexes for better query performance

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_user_id ON backtest_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_status ON backtest_tasks(status);
CREATE INDEX IF NOT EXISTS idx_backtest_results_task_id ON backtest_results(task_id);
CREATE INDEX IF NOT EXISTS idx_strategies_user_id ON strategies(user_id);
CREATE INDEX IF NOT EXISTS idx_strategies_type ON strategies(type);

-- Add composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_user_status ON backtest_tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_created_desc ON backtest_tasks(created_at DESC);

-- Analyze query patterns before adding more indexes
-- Run: EXPLAIN QUERY ANALYZE on slow queries to identify missing indexes
