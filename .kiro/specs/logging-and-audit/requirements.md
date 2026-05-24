# Requirements Document

## Introduction

本功能为 backtrader_web 量化交易平台增强日志系统并添加用户操作审计功能。主要包含三部分：

1. **日志分级与按日轮转**：根据环境（开发/测试/生产）自动调整日志输出级别，测试环境输出所有级别日志，生产环境仅输出 WARNING 及以上级别；日志文件按日期自动分割，避免单文件过大。
2. **后端日志增强**：通过装饰器机制自动记录模块和函数的调用时间、入参摘要、返回结果摘要以及异常信息，提升系统可观测性和问题排查效率。
3. **前端用户操作审计**：在前端捕获用户的页面交互行为（点击、导航等），通过 API 写入后端数据库，实现用户操作留痕和行为追溯。

## Glossary

- **Call_Logger**：后端函数调用日志装饰器，负责记录函数的调用时间、执行耗时、返回结果和异常信息
- **Log_Level_Policy**：日志级别策略，根据运行环境自动决定输出哪些级别的日志
- **Daily_Rotation**：日志按日轮转机制，每天生成新的日志文件，旧文件自动压缩归档
- **Audit_Tracker**：前端用户操作追踪模块，负责捕获用户交互事件并上报到后端
- **Audit_Service**：后端审计服务，负责接收前端上报的操作事件并持久化到数据库
- **Audit_Record**：审计记录数据库模型，存储用户操作的详细信息
- **Operation_Event**：用户操作事件数据结构，包含时间戳、用户标识、操作类型、操作目标等字段
- **Log_Decorator**：Python 装饰器，应用于服务层和 API 层函数，自动注入日志记录逻辑
- **Audit_API**：后端审计相关的 REST API 端点，提供事件上报和审计日志查询功能

## Requirements

### Requirement 1: 日志分级输出与环境适配

**User Story:** 作为系统管理员，我希望日志系统能根据运行环境自动调整输出级别，测试时输出所有日志便于调试，生产环境只输出警告和错误以减少噪音和磁盘占用。

#### Acceptance Criteria

1. THE logging system SHALL support five standard log levels in ascending severity order: DEBUG, INFO, WARNING, ERROR, CRITICAL
2. WHEN the application runs in development/test mode (DEBUG=true), THE logging system SHALL output all log levels (DEBUG and above) to both console and log files
3. WHEN the application runs in production mode (DEBUG=false), THE logging system SHALL output only WARNING level and above to the console, and INFO level and above to log files
4. THE logging system SHALL support a configurable LOG_LEVEL environment variable that overrides the environment-based default; WHEN LOG_LEVEL is set, THE logging system SHALL use the specified level regardless of DEBUG flag
5. THE Call_Logger decorator SHALL respect the global log level policy: WHEN the global minimum level is WARNING, THE Call_Logger SHALL suppress DEBUG and INFO level call logs while still recording ERROR level exception logs
6. THE logging system SHALL apply the log level filter consistently across all output sinks (console, application log file, error log file, audit log file)

### Requirement 2: 日志按日轮转与归档

**User Story:** 作为系统管理员，我希望日志文件按日期自动分割，避免单个日志文件过大导致难以查看和占用过多磁盘空间。

#### Acceptance Criteria

1. THE logging system SHALL create a new log file at midnight (00:00 server local time) each day, with the date included in the filename (format: `app_YYYY-MM-DD.log`)
2. THE logging system SHALL maintain separate daily files for different log categories: application logs (`app_YYYY-MM-DD.log`), error logs (`errors_YYYY-MM-DD.log`), audit logs (`audit_YYYY-MM-DD.log`)
3. THE logging system SHALL compress rotated log files older than 1 day using zip format to reduce disk usage
4. THE logging system SHALL support a configurable retention period per log category: application logs (default: 30 days), error logs (default: 90 days), audit logs (default: 365 days)
5. WHEN a log file exceeds the retention period, THE logging system SHALL automatically delete the expired compressed file during the next rotation cycle
6. THE logging system SHALL ensure that log rotation does not cause any log entries to be lost during the transition between files
7. THE logging system SHALL support a configurable LOG_DIR environment variable to specify the log output directory (default: `./logs`)

### Requirement 3: 函数调用日志装饰器

**User Story:** 作为后端开发者，我希望通过装饰器自动记录函数的调用时间、执行耗时和返回结果，以便快速定位性能瓶颈和排查问题。

#### Acceptance Criteria

1. WHEN a decorated function is invoked, THE Call_Logger SHALL record the function name, module name, and invocation timestamp in ISO 8601 format to the INFO log level
2. WHEN a decorated function returns successfully, THE Call_Logger SHALL record the execution duration in milliseconds and the return value's string representation truncated to 200 characters at the INFO log level
3. WHEN a decorated function raises an exception, THE Call_Logger SHALL record the exception type, exception message, and full traceback to the ERROR log level, and then re-raise the original exception unchanged
4. THE Call_Logger SHALL support both synchronous and asynchronous functions without requiring separate decorators
5. WHILE the Call_Logger is active, THE Call_Logger SHALL propagate the current request_id context from the logging middleware to maintain request traceability; IF no request_id is present in the current context, THEN THE Call_Logger SHALL log without a request_id field and not raise an error
6. THE Call_Logger SHALL replace the values of sensitive parameters whose names contain any of the substrings "password", "token", "secret", or "api_key" (case-insensitive match) with the literal string "***" in logged input arguments

### Requirement 4: 日志装饰器配置与性能

**User Story:** 作为系统管理员，我希望能够配置日志装饰器的行为和日志级别，以便在不同环境中平衡可观测性和性能。

#### Acceptance Criteria

1. THE Call_Logger SHALL accept an optional log_level parameter that accepts Python standard logging levels (DEBUG, INFO, WARNING, ERROR, CRITICAL) to control the output log level (default: INFO for success, ERROR for exceptions)
2. THE Call_Logger SHALL accept an optional log_result parameter (boolean) to control whether return values are included in the log output (default: True); WHEN log_result is False, THE Call_Logger SHALL log the function call completion without including the return value
3. THE Call_Logger SHALL accept an optional log_args parameter (boolean) to control whether input arguments are included in the log output (default: True); WHEN log_args is False, THE Call_Logger SHALL log the function call without including argument values
4. WHEN execution duration exceeds the configurable slow_threshold parameter (default: 1000ms, minimum: 0ms), THE Call_Logger SHALL emit an additional WARNING level log entry indicating a slow function call, supplementing the normal success or error log entry
5. THE Call_Logger SHALL add less than 1ms of overhead to the decorated function execution time, measured as the difference between decorated and undecorated execution averaged over 1000 consecutive invocations on a single-threaded workload
6. IF an invalid log_level value is provided to Call_Logger, THEN THE Call_Logger SHALL raise a ValueError at decoration time with an error message indicating the accepted log level values

### Requirement 5: 前端用户操作事件捕获

**User Story:** 作为产品经理，我希望记录用户在页面上的关键操作行为，以便分析用户使用习惯和追溯操作历史。

#### Acceptance Criteria

1. WHEN a user clicks a button, link, input, select, or element with a role attribute (button, link, tab, menuitem), THE Audit_Tracker SHALL capture the event type, element identifier (the element's id attribute, or nearest ancestor id combined with tag name and index if no id exists), page path, and timestamp in ISO 8601 UTC format
2. WHEN a user navigates to a new page, THE Audit_Tracker SHALL capture the navigation event with source path and target path
3. THE Audit_Tracker SHALL batch collected events and send them to the Audit_API at intervals not exceeding 10 seconds or when the batch reaches 50 events, whichever occurs first
4. IF the Audit_API is unreachable, THEN THE Audit_Tracker SHALL store events in browser localStorage up to a maximum of 500 events, discard the oldest events when the limit is exceeded, and retry sending stored events on each subsequent batch interval when connectivity is restored
5. THE Audit_Tracker SHALL include the current user ID and session ID in each Operation_Event
6. THE Audit_Tracker SHALL exclude events from elements marked with the data-no-audit attribute and from all descendant elements of a data-no-audit marked ancestor

### Requirement 6: 审计事件持久化

**User Story:** 作为系统管理员，我希望用户操作事件能够可靠地写入数据库，以便进行合规审计和问题追溯。

#### Acceptance Criteria

1. WHEN the Audit_Service receives a batch of Operation_Events, THE Audit_Service SHALL validate each event against the following rules and persist valid events to the Audit_Record table: each event must contain non-empty user_id, event_type, client_timestamp, and page_path fields; client_timestamp must be a valid ISO 8601 datetime not more than 24 hours in the past or future relative to server_timestamp; event_data must be valid JSON not exceeding 10 KB in size
2. THE Audit_Record SHALL store the following fields: id, user_id, session_id, event_type, event_target, page_path, event_data (JSON, maximum 10 KB), client_timestamp, server_timestamp, client_ip
3. IF an Operation_Event fails validation, THEN THE Audit_Service SHALL log the validation error including the event_type and user_id of the failed event, and skip the invalid event without affecting the persistence of other valid events in the batch
4. THE Audit_Service SHALL process a batch of up to 50 events within 500ms under normal database connectivity
5. IF the database write fails, THEN THE Audit_Service SHALL retry the write operation up to 3 times with exponential backoff starting at 100ms (doubling each retry, maximum delay 400ms), and IF all retries are exhausted, THEN THE Audit_Service SHALL log the failure including the batch size and first event's user_id, and return an error response indicating persistence failure to the caller

### Requirement 7: 审计日志查询 API

**User Story:** 作为系统管理员，我希望能够按用户、时间范围和操作类型查询审计日志，以便进行安全审计和用户行为分析。

#### Acceptance Criteria

1. WHEN a query request is received with user_id filter, THE Audit_API SHALL return only the Audit_Records belonging to the specified user
2. WHEN a query request is received with start_time and end_time filters in ISO 8601 format, THE Audit_API SHALL return only the Audit_Records whose server_timestamp falls within the specified inclusive time range
3. WHEN a query request is received with event_type filter, THE Audit_API SHALL return only the Audit_Records matching the specified event type
4. WHEN a query request includes multiple filters simultaneously, THE Audit_API SHALL apply all filters as AND conditions and return only the Audit_Records satisfying all specified criteria
5. THE Audit_API SHALL support pagination with page (minimum: 1) and page_size (minimum: 1, default: 20, maximum: 100) parameters, and SHALL include total_count, current_page, and total_pages in the response metadata
6. THE Audit_API SHALL require admin role permission to access audit log query endpoints
7. IF a non-admin user requests the audit log query endpoint, THEN THE Audit_API SHALL reject the request with an authorization error indication without returning any Audit_Records
8. IF a query request contains invalid filter values (malformed time format, non-existent event_type, or page_size exceeding 100), THEN THE Audit_API SHALL reject the request with an error message indicating the invalid parameter
9. THE Audit_API SHALL return results sorted by server_timestamp in descending order

### Requirement 8: 审计数据生命周期管理

**User Story:** 作为系统管理员，我希望审计数据有合理的保留策略，以便控制数据库存储增长同时满足合规要求。

#### Acceptance Criteria

1. THE Audit_Service SHALL support a configurable retention period for audit records (default: 90 days, minimum: 7 days, maximum: 365 days)
2. THE Audit_Service SHALL execute a cleanup cycle on a configurable schedule (default: daily at 02:00 server local time)
3. WHEN a cleanup cycle runs, THE Audit_Service SHALL identify records whose server_timestamp is older than the configured retention period and delete them in batches of 1000 to avoid long-running transactions
4. THE Audit_Service SHALL log the number of deleted records and the execution duration after each cleanup cycle completes
5. IF a cleanup cycle encounters a database error, THEN THE Audit_Service SHALL log the error and retry the cleanup in the next scheduled cycle without crashing the application
