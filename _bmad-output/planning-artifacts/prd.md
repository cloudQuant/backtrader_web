---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish']
inputDocuments:
  - "product-brief-backtrader_web-2026-02-23.md"
  - "迭代114-项目完成度分析.md"
  - "迭代101-技术设计文档.md"
  - "迭代101-用户故事与验收标准.md"
  - "API.md"
  - "AGILE_DEVELOPMENT.md"
documentCounts:
  briefCount: 1
  researchCount: 0
  brainstormingCount: 0
  projectDocsCount: 5
workflowType: 'prd'
classification:
  projectType: 'Web Application + API Service'
  domain: 'Fintech / Quantitative Trading'
  complexity: 'High'
  projectContext: 'brownfield'
---

# Product Requirements Document - backtrader_web

**Author:** cloud
**Date:** 2026-02-23

<!-- Content will be appended sequentially through collaborative workflow steps -->

---

## Executive Summary

**backtrader_web** is an open-source investment-research integration platform based on the Backtrader engine, providing full-process support from strategy research to live trading management for quantitative traders. The platform solves core pain points in strategy validation, risk management, and trading execution through intuitive web visualization, strategy-parameter separation design, real-time monitoring, and professional performance analysis powered by fincore.

**Target Users:** Independent quantitative traders, quantitative researchers, quantitative developers, team managers

**Core Problem:** Excellent engines like Backtrader use command-line interfaces with steep learning curves; strategy code and parameter configuration are mixed; live trading lacks real-time monitoring and post-trade performance attribution analysis

**Solution:** Provide complete backtest→paper→live trading workflow, using fincore for standardized financial metric calculations, achieving investment-research integration management

### What Makes This Special

**Unique Differentiators:**

1. **Only Open-Source Platform Connecting Full Process** — Seamless research→backtest→paper→live workflow
2. **100% Backtrader Ecosystem Compatible** — No need to rewrite strategy code
3. **Open Source & Self-Hosted** — Complete control over strategy code, no privacy leakage risk
4. **Professional-Grade Metric Calculation** — Integrated fincore for institutional-level standardized metrics

**Core Insight:** Investment-research integration is the trend — the boundary between research and trading is blurring. Modern quantitative traders need a unified platform for rapid strategy iteration, real-time risk monitoring, and deep performance attribution.

**One-Sentence Value Proposition:** Enable quantitative traders to complete the full process from strategy research to live trading management on one platform, with complete control over their strategies and data.

## Project Classification

| Classification | Value |
|---------------|-------|
| **Project Type** | Web Application + API Service |
| **Domain** | Fintech / Quantitative Trading |
| **Complexity** | High |
| **Project Context** | Brownfield (existing features + fincore integration) |

---

## Success Criteria

### User Success

| Success Scenario | Metric | Target |
|------------------|--------|--------|
| **Quick Onboarding** | Installation to first backtest completion | ≤ 10 minutes |
| **Strategy Validation** | Idea to parameter optimization completion | ≤ 1 day |
| **Visual Insight** | User reaction to first visualization view | Positive feedback rate > 80% |
| **Live Trading Confidence** | Monitoring coverage during live trading | 100% real-time monitoring |
| **Metric Credibility** | Accuracy of fincore-calculated metrics | Consistent with industry standards |

### Business Success

| Phase | Timeline | Targets |
|-------|----------|---------|
| **Community Building** | 3 months | Stars 500+, Contributors 10+, Deployments 50+ |
| **User Adoption** | 6 months | Deployments 100+, Weekly Active 50+, Issue resolution >90% |
| **Ecosystem Maturity** | 12 months | Stars 2000+, Contributors 30+, Enterprise deployments 5+ |

### Technical Success

| Metric | Target |
|--------|--------|
| Test Coverage | Maintain ≥ 100% |
| Test Pass Rate | 100% |
| fincore Integration | All metrics calculated via fincore |
| API Response Time | < 500ms (P95) |
| WebSocket Latency | < 1s real-time push |

### Measurable Outcomes

**3-Month Outcomes:**
- 500+ GitHub Stars, 10+ active contributors
- 50+ deployment instances worldwide
- Zero critical bugs in core workflows

**6-Month Outcomes:**
- 100+ deployment instances, 50+ weekly active users
- >90% issue resolution rate
- Complete fincore integration with all metrics standardized

**12-Month Outcomes:**
- Recognized as #1 choice for Backtrader Web UI
- 2000+ GitHub Stars, 30+ active contributors
- 5+ enterprise/team deployments

---

## Product Scope

### MVP - Minimum Viable Product

**Core Features (Completed + fincore Integration):**

| Feature | Status | Description |
|---------|--------|-------------|
| **Strategy Management** | ✅ Complete | CRUD + Version Control + YAML parameter configuration |
| **Backtesting Service** | ✅ Complete | Async tasks, history, cancellation |
| **Visualization** | ✅ Complete | 10+ chart types (K-line, equity, drawdown, heatmap, etc.) |
| **Parameter Optimization** | ✅ Complete | Grid search, Bayesian optimization |
| **Paper Trading** | ✅ Complete | Simulation trading environment |
| **Live Trading** | ✅ Complete | Production trading execution |
| **Real-time Monitoring** | ✅ Complete | WebSocket real-time updates |
| **Alert System** | ✅ Complete | Customizable alert rules |
| **User Management** | ✅ Complete | Authentication, RBAC |
| **fincore Integration** | 🔄 In Progress | Replace all manual metric calculations |
| **Deployment Docs** | 🔄 In Progress | pip install + server deployment guide |

### Growth Features (Post-MVP)

- Community strategy marketplace
- Plugin system for custom analyzers
- Multi-broker expansion beyond current support
- RESTful API enhancement for third-party integration
- Mobile-responsive web interface

### Vision (Future)

- Multi-language strategy support (beyond Python)
- ML-driven parameter optimization
- Enterprise features: multi-tenancy, compliance audit logging, team collaboration
- Professional support and SLA options

---

## User Journeys

### Journey 1: Independent Quantitative Trader - Li Ming (Core Success Path)

**Background:**
Li Ming is a 3-year experienced independent quantitative trader trading full-time from home. He's familiar with Python and Backtrader but tired of command-line operations and manual result analysis. He needs to quickly validate strategy ideas and run them safely in production.

**Opening Scene (First Contact):**
Li Ming discovers backtrader_web while searching for Backtrader visualization tools on GitHub. He's attracted by the "open-source investment-research integration" description and decides to try.

**Rising Action (Exploration Process):**
1. Visits documentation, sees pip install guide
2. Completes local deployment in 10 minutes
3. Runs first backtest using built-in strategy template
4. Sees beautiful K-line charts and equity curves, impressed ✨
5. Adjusts YAML parameters, runs batch optimization
6. Validates in paper trading account for 2 weeks
7. Switches to live trading after confirmation

**Climax (Critical Moment):**
First week of live trading, Li Ming receives an alert notification on his phone — strategy triggered abnormal risk control condition. He logs in immediately, identifies the issue, and adjusts in time to avoid potential loss. He realizes: this platform gives him complete control over risk.

**Resolution (New Reality):**
3 months later, Li Ming's strategy library has accumulated 20+ reusable strategies. He checks his monitoring dashboard every morning to understand each strategy's performance. Professional metrics calculated by fincore enable him to do performance attribution and continuously optimize strategies. He says: "This is the tool I've been looking for."

**Requirements Revealed:**
- Quick deployment and onboarding
- Built-in strategy templates
- YAML parameter configuration
- Mobile-friendly monitoring interface
- Real-time alert system

---

### Journey 2: Quantitative Researcher - Wang Fang (Batch Optimization Path)

**Background:**
Wang Fang is a researcher at a quantitative hedge fund, needing to report strategy performance to fund managers. She needs to run hundreds of parameter batches and generate professional reports, but command-line approach is too slow.

**Opening Scene (First Contact):**
Wang Fang's colleague recommended backtrader_web, saying it can batch optimize parameters and export professional reports.

**Rising Action (Exploration Process):**
1. Installs platform and imports existing strategy code
2. Uses parameter optimization feature, runs 100+ parameter combinations in one click
3. Results sorted in table, clearly showing optimal parameters
4. Exports professional PDF report with 10+ chart types
5. Reports to fund manager, gets approval

**Climax (Critical Moment):**
Fund manager asks: "How does this strategy perform in different market conditions?" Wang Fang uses backtest comparison feature to quickly show performance across different time periods, answering all questions.

**Resolution (New Reality):**
Wang Fang's team strategy management is now systematic, version control lets everyone track strategy iterations. She says: "Now I can focus on research itself, not tool operations."

**Requirements Revealed:**
- Batch parameter optimization
- Result sorting and filtering
- Professional report export (PDF/Excel)
- Strategy version management
- Backtest result comparison

---

### Journey 3: Quantitative Developer - Zhang Wei (Technical Integration Path)

**Background:**
Zhang Wei is technical lead at a quant firm, needs to integrate backtesting platform into company systems, but concerned about data security.

**Opening Scene (First Contact):**
Zhang Wei evaluated several commercial platforms, but none met security requirements. He discovered backtrader_web — open source, self-hosted, fully meeting requirements.

**Rising Action (Exploration Process):**
1. Deploys platform on company servers
2. Uses RESTful API to integrate with existing systems
3. Customizes strategy templates and metrics
4. Configures integration with company data sources

**Climax (Critical Moment):**
Company requires custom risk metrics. Zhang Wei uses plugin system to extend analyzers, easily implementing the requirement. He says: "Open-source flexibility is key."

**Resolution (New Reality):**
Company's investment-research system is fully connected, from data acquisition to strategy execution seamlessly. Zhang Wei says: "We have our own quantitative platform, no need to depend on external vendors."

**Requirements Revealed:**
- Complete RESTful API
- Custom analyzer extensions
- Data source integration capability
- Server deployment documentation

---

### Journey 4: Team Manager - Mr. Chen (Monitoring Risk Control Path)

**Background:**
Mr. Chen is a fund manager, doesn't write code, but needs to understand team strategy performance and risk status.

**Opening Scene (First Contact):**
Mr. Chen feels the team's tools are too scattered, lacking overall visibility. CTO recommended backtrader_web.

**Rising Action (Exploration Process):**
1. Logs into platform to see visualization dashboard
2. At a glance sees which strategies are making money
3. Checks live trading monitoring status
4. Receives abnormal alert notifications

**Climax (Critical Moment):**
A strategy shows abnormal drawdown, Mr. Chen receives alert immediately. He contacts researcher right away, stops loss in time. He says: "This system lets me sleep peacefully."

**Resolution (New Reality):**
Mr. Chen checks team strategy performance daily, understands each member's contribution. He says: "Now I have complete project control."

**Requirements Revealed:**
- Visualization monitoring dashboard
- Multi-user permission management
- Real-time alert notifications
- Strategy comparison functionality

---

### Journey Requirements Summary

| Capability Area | Related Journeys | Priority |
|-----------------|------------------|----------|
| Quick Deployment & Onboarding | Journey 1 | P0 |
| YAML Parameter Configuration | Journey 1, 2 | P0 |
| Real-time Monitoring & Alerts | Journey 1, 4 | P0 |
| Batch Parameter Optimization | Journey 2 | P0 |
| Professional Report Export | Journey 2 | P1 |
| RESTful API | Journey 3 | P1 |
| Custom Extensions | Journey 3 | P1 |
| Permission Management | Journey 4 | P0 |

---

## Domain-Specific Requirements

### Compliance & Regulatory

| Requirement | Description |
|-------------|-------------|
| **Data Security** | User strategy code must be encrypted at rest; self-hosted deployment ensures no third-party access |
| **Audit Logging** | All user actions, backtest runs, and trading operations must be logged with timestamps |
| **Risk Management** | Configurable risk controls: position limits, drawdown limits, daily loss limits |
| **Permission Control** | RBAC ensuring users can only access their own data unless explicitly granted team access |

### Technical Constraints

| Constraint | Requirement |
|------------|-------------|
| **Real-time Processing** | WebSocket latency < 1s for live trading updates |
| **System Availability** | Platform must remain stable during market hours (99.5% uptime during trading hours) |
| **Data Accuracy** | All financial metrics calculated via fincore to ensure industry-standard accuracy |
| **Backward Compatibility** | Must remain 100% compatible with Backtrader ecosystem |

### Integration Requirements

| Integration | Description |
|-------------|-------------|
| **Market Data** | Support multiple data sources; extensible data feed architecture |
| **Broker APIs** | Support for multiple broker execution APIs |
| **Strategy Format** | Standard Python strategy format compatible with Backtrader conventions |

### Risk Mitigations

| Risk | Mitigation |
|------|------------|
| **Live Trading Loss** | Pre-live validation: paper trading → small size → full deployment |
| **System Failure** | Health monitoring, automatic alerts, graceful degradation |
| **Data Corruption** | Database integrity checks, backup strategies |
| **Unauthorized Access** | JWT authentication, bcrypt password hashing, RBAC enforcement |

---

## Innovation & Novel Patterns

### Detected Innovation Areas

| Innovation Area | Description | Validation Approach |
|-----------------|-------------|---------------------|
| **Full-Process Integration** | First open-source platform connecting research→backtest→paper→live | User feedback on workflow continuity |
| **Research-Trading Integration** | Challenges traditional separation of research and execution | Measure time from strategy idea to live deployment |
| **Standardized Metrics via fincore** | Uses institutional-grade financial metric library | Compare results with industry standards |
| **Self-Hosted Security Model** | Strategy code never leaves user's infrastructure | Enterprise adoption rate |

### Market Context & Competitive Landscape

| Competitor Type | Examples | Our Differentiation |
|-----------------|----------|---------------------|
| **Backtrader Native** | Command-line, no UI | Visual interface, monitoring, collaboration |
| **Commercial SaaS** | JoinQuant, MiQuant | Self-hosted, no code upload, privacy |
| **Other Open-Source** | Fragmented tools | Full-process integration, not point solutions |

**Market Gap:** No existing open-source platform provides end-to-end investment-research integration with professional-grade metrics.

### Validation Approach

| Innovation | Validation Method | Success Metric |
|------------|-------------------|----------------|
| Full-Process Integration | User completes workflow without context switching | < 5 min from idea to backtest |
| fincore Integration | Metric accuracy compared to manual calculation | 100% consistency with industry standards |
| Self-Hosted Model | Enterprise adoption rate | 5+ enterprise deployments in 12 months |

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| fincore integration complexity | Maintain manual calculation as fallback during transition |
| Market education (open-source vs SaaS) | Emphasize data security and compliance benefits |
| Technical support burden | Community-driven support model, documentation priority |

---

## [Web Application + API Service] Specific Requirements

### Project-Type Overview

backtrader_web is a full-stack quantitative trading platform consisting of:
- **Backend**: FastAPI RESTful API with WebSocket support
- **Frontend**: Vue3 SPA (Single Page Application)
- **Real-time**: WebSocket for live trading and backtest updates
- **Data**: JSON API with CSV/Excel/PDF export capabilities

### Technical Architecture Considerations

| Layer | Technology | Purpose |
|-------|------------|---------|
| **API** | FastAPI | High-performance async API with auto-generated OpenAPI docs |
| **Auth** | JWT + bcrypt | Token-based authentication with secure password hashing |
| **Database** | SQLAlchemy ORM | Database abstraction with relationship management |
| **Validation** | Pydantic | Request/response schema validation with range checks |
| **Real-time** | WebSocket | Live trading and backtest progress updates |
| **Export** | ReportLab, openpyxl | PDF/Excel report generation |

### API Endpoint Specifications

#### Authentication Endpoints

| Endpoint | Method | Request | Response | Description |
|----------|--------|---------|----------|-------------|
| `/api/v1/auth/register` | POST | UserCreate | UserResponse | User registration |
| `/api/v1/auth/login` | POST | UserLogin | Token | JWT token generation |
| `/api/v1/auth/me` | GET | - | UserResponse | Get current user |
| `/api/v1/auth/change-password` | POST | ChangePassword | - | Change password |

#### Strategy Endpoints

| Endpoint | Method | Request | Response | Description |
|----------|--------|---------|----------|-------------|
| `/api/v1/strategy/templates` | GET | - | List[StrategyTemplate] | Get built-in templates |
| `/api/v1/strategy/templates/{id}` | GET | - | StrategyTemplate | Get template details |
| `/api/v1/strategy/templates/{id}/config` | GET | - | Dict | Get template config |
| `/api/v1/strategies` | POST | StrategyCreate | StrategyResponse | Create strategy |
| `/api/v1/strategies` | GET | - | StrategyListResponse | List user strategies |
| `/api/v1/strategies/{id}` | GET | - | StrategyResponse | Get strategy details |
| `/api/v1/strategies/{id}` | PUT | StrategyUpdate | StrategyResponse | Update strategy |
| `/api/v1/strategies/{id}` | DELETE | - | - | Delete strategy |

#### Enhanced Backtest Endpoints

| Endpoint | Method | Request | Response | Description |
|----------|--------|---------|----------|-------------|
| `/api/v1/backtests/run` | POST | BacktestRequest | BacktestResponse | Submit backtest task |
| `/api/v1/backtests/{task_id}` | GET | - | BacktestResult | Get backtest result |
| `/api/v1/backtests/{task_id}/status` | GET | - | TaskStatus | Get task status |
| `/api/v1/backtests` | GET | - | BacktestListResponse | Get backtest history |
| `/api/v1/backtests/{task_id}/report/html` | GET | - | HTML | HTML report |
| `/api/v1/backtests/{task_id}/report/pdf` | GET | - | PDF | PDF report |
| `/api/v1/backtests/{task_id}/report/excel` | GET | - | Excel | Excel report |
| `/api/v1/backtests/ws/backtest/{task_id}` | WS | - | - | WebSocket for progress |

#### Optimization Endpoints

| Endpoint | Method | Request | Response | Description |
|----------|--------|---------|----------|-------------|
| `/api/v1/optimization/run` | POST | OptimizationRequest | - | Submit optimization |
| `/api/v1/optimization/results/{task_id}` | GET | - | OptimizationResult | Get results |

#### Paper Trading Endpoints

| Endpoint | Method | Request | Response | Description |
|----------|--------|---------|----------|-------------|
| `/api/v1/paper-trading/accounts` | POST | AccountCreate | AccountResponse | Create account |
| `/api/v1/paper-trading/accounts` | GET | - | List[AccountResponse] | List accounts |
| `/api/v1/paper-trading/accounts/{id}/orders` | POST | OrderCreate | OrderResponse | Place order |
| `/api/v1/paper-trading/orders` | GET | - | List[OrderResponse] | List orders |
| `/api/v1/paper-trading/positions` | GET | - | List[PositionResponse] | List positions |
| `/api/v1/paper-trading/trades` | GET | - | List[TradeResponse] | List trades |
| `/api/v1/paper-trading/ws/account/{id}` | WS | - | - | Account updates |

#### Analytics Endpoints

| Endpoint | Method | Response | Description |
|----------|--------|----------|-------------|
| `/api/v1/analytics/performance/{task_id}` | GET | PerformanceMetrics | Performance metrics |
| `/api/v1/analytics/equity/{task_id}` | GET | List[EquityPoint] | Equity curve |
| `/api/v1/analytics/drawdown/{task_id}` | GET | List[DrawdownPoint] | Drawdown curve |
| `/api/v1/analytics/trades/{task_id}` | GET | List[TradeRecord] | Trade records |
| `/api/v1/analytics/monthly/{task_id}` | GET | MonthlyReturnsResponse | Monthly returns |

### Database Model Specifications

#### users

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Unique user ID |
| username | String(50) | UNIQUE, NOT NULL, INDEX | Login username |
| email | String(100) | UNIQUE, NOT NULL, INDEX | Email address |
| hashed_password | String(128) | NOT NULL | Bcrypt hashed password |
| is_active | Boolean | DEFAULT TRUE | Account status |
| created_at | DateTime | DEFAULT utcnow | Creation time |
| updated_at | DateTime | DEFAULT utcnow, ON UPDATE | Update time |

**Relationships:** One-to-Many with strategies, backtest_tasks, paper_trading_accounts, alerts

#### strategies

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Strategy ID |
| user_id | String(36) | FK(users.id), NOT NULL, INDEX | Owner ID |
| name | String(100) | NOT NULL | Strategy name |
| description | Text | NULLABLE | Strategy description |
| code | Text | NOT NULL | Strategy Python code |
| params | JSON | DEFAULT {} | Parameter definitions |
| category | String(50) | DEFAULT "custom", INDEX | Strategy category |
| created_at | DateTime | DEFAULT utcnow | Creation time |
| updated_at | DateTime | DEFAULT utcnow, ON UPDATE | Update time |

**Relationships:** Many-to-One with users, One-to-Many with strategy_versions

#### backtest_tasks

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Task ID |
| user_id | String(36) | FK(users.id), NOT NULL, INDEX | Owner ID |
| strategy_id | String(36) | INDEX | Strategy ID |
| strategy_version_id | String(36) | FK(strategy_versions.id), INDEX | Strategy version |
| symbol | String(20) | INDEX | Trading symbol |
| status | String(20) | DEFAULT "pending" | Task status |
| request_data | JSON | NULLABLE | Request parameters |
| error_message | Text | NULLABLE | Error details |
| log_dir | Text | NULLABLE | Log directory path |
| created_at | DateTime | DEFAULT utcnow | Creation time |
| updated_at | DateTime | DEFAULT utcnow, ON UPDATE | Update time |

**Relationships:** Many-to-One with users, One-to-One with backtest_results

#### backtest_results

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Result ID |
| task_id | String(36) | FK(backtest_tasks.id), UNIQUE, INDEX | Task ID |
| total_return | Float | DEFAULT 0 | Total return % |
| annual_return | Float | DEFAULT 0 | Annual return % |
| sharpe_ratio | Float | DEFAULT 0 | **fincore calculated** |
| max_drawdown | Float | DEFAULT 0 | **fincore calculated** |
| win_rate | Float | DEFAULT 0 | Win rate % |
| total_trades | Integer | DEFAULT 0 | Total trades |
| profitable_trades | Integer | DEFAULT 0 | Winning trades |
| losing_trades | Integer | DEFAULT 0 | Losing trades |
| equity_curve | JSON | DEFAULT [] | Equity points |
| equity_dates | JSON | DEFAULT [] | Equity dates |
| drawdown_curve | JSON | DEFAULT [] | Drawdown points |
| trades | JSON | DEFAULT [] | Trade records |
| created_at | DateTime | DEFAULT utcnow | Creation time |

**fincore Integration:** All financial metrics (sharpe_ratio, max_drawdown, etc.) will be calculated via fincore library.

#### paper_trading_accounts

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Account ID |
| user_id | String(36) | FK(users.id), NOT NULL, INDEX | Owner ID |
| name | String(100) | NOT NULL | Account name |
| initial_cash | Float | DEFAULT 100000, NOT NULL | Initial capital |
| current_cash | Float | DEFAULT 100000, NOT NULL | Current cash |
| total_equity | Float | DEFAULT 100000, NOT NULL | Total equity |
| profit_loss | Float | DEFAULT 0, NOT NULL | P&L amount |
| profit_loss_pct | Float | DEFAULT 0, NOT NULL | P&L % |
| commission_rate | Float | DEFAULT 0.001, NOT NULL | Commission rate |
| slippage_rate | Float | DEFAULT 0.001, NOT NULL | Slippage rate |
| is_active | Boolean | DEFAULT TRUE, NOT NULL | Active status |
| created_at | DateTime | DEFAULT utcnow | Creation time |
| updated_at | DateTime | DEFAULT utcnow, ON UPDATE | Update time |

#### paper_trading_positions

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Position ID |
| account_id | String(36) | FK(accounts.id), NOT NULL, INDEX | Account ID |
| symbol | String(20) | NOT NULL, INDEX | Trading symbol |
| size | Integer | DEFAULT 0, NOT NULL | Position size |
| avg_price | Float | DEFAULT 0, NOT NULL | Average cost |
| market_value | Float | DEFAULT 0, NOT NULL | Market value |
| unrealized_pnl | Float | DEFAULT 0, NOT NULL | Unrealized P&L |
| unrealized_pnl_pct | Float | DEFAULT 0, NOT NULL | Unrealized P&L % |
| entry_price | Float | DEFAULT 0, NOT NULL | Entry price |
| entry_time | DateTime | NULLABLE | Entry time |
| updated_at | DateTime | DEFAULT utcnow, ON UPDATE | Update time |

#### paper_trading_orders

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Order ID |
| account_id | String(36) | FK(accounts.id), NOT NULL, INDEX | Account ID |
| symbol | String(20) | NOT NULL, INDEX | Trading symbol |
| order_type | String(20) | NOT NULL | MARKET/LIMIT/STOP/STOP_LIMIT |
| side | String(10) | NOT NULL | BUY/SELL |
| size | Integer | NOT NULL | Order size |
| price | Float | NULLABLE | Limit price |
| stop_price | Float | NULLABLE | Stop price |
| limit_price | Float | NULLABLE | Take profit price |
| filled_size | Integer | DEFAULT 0, NOT NULL | Filled size |
| avg_fill_price | Float | DEFAULT 0, NOT NULL | Avg fill price |
| status | String(20) | DEFAULT "pending", NOT NULL, INDEX | Order status |
| rejected_reason | String(255) | NULLABLE | Rejection reason |
| commission | Float | DEFAULT 0, NOT NULL | Commission |
| slippage | Float | DEFAULT 0, NOT NULL | Slippage |
| created_at | DateTime | DEFAULT utcnow | Creation time |
| updated_at | DateTime | DEFAULT utcnow, ON UPDATE | Update time |
| filled_at | DateTime | NULLABLE | Fill time |

#### paper_trades

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Trade ID |
| account_id | String(36) | FK(accounts.id), NOT NULL, INDEX | Account ID |
| order_id | String(36) | FK(orders.id), INDEX | Order ID |
| symbol | String(20) | NOT NULL, INDEX | Trading symbol |
| side | String(10) | NOT NULL | BUY/SELL |
| size | Integer | NOT NULL | Trade size |
| price | Float | NOT NULL | Trade price |
| commission | Float | DEFAULT 0, NOT NULL | Commission |
| slippage | Float | DEFAULT 0, NOT NULL | Slippage |
| pnl | Float | DEFAULT 0, NOT NULL | Profit/loss |
| pnl_pct | Float | DEFAULT 0, NOT NULL | P&L % |
| created_at | DateTime | DEFAULT utcnow | Trade time |

#### alerts

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Alert ID |
| user_id | String(36) | FK(users.id), NOT NULL, INDEX | Owner ID |
| alert_type | String(20) | NOT NULL, INDEX | Account/Position/Order/Strategy/System/Performance/Risk |
| severity | String(20) | DEFAULT "info", NOT NULL | Info/Warning/Error/Critical |
| status | String(20) | DEFAULT "active", NOT NULL, INDEX | Active/Resolved/Acknowledged/Ignored |
| title | String(200) | NOT NULL | Alert title |
| message | Text | NOT NULL | Alert message |
| details | JSON | NULLABLE | Additional details |
| rule_id | String(36) | FK(alert_rules.id), INDEX | Triggering rule |
| strategy_id | String(36) | FK(strategies.id), INDEX | Related strategy |
| account_id | String(36) | FK(accounts.id), INDEX | Related account |
| trigger_type | String(50) | NOT NULL | Threshold/Rate/Manual |
| trigger_value | Float | NULLABLE | Trigger value |
| threshold_value | Float | NULLABLE | Threshold value |
| is_read | Boolean | DEFAULT FALSE, NOT NULL | Read status |
| is_notification_sent | Boolean | DEFAULT FALSE, NOT NULL | Notification sent |
| resolved_at | DateTime | NULLABLE | Resolution time |
| created_at | DateTime | DEFAULT utcnow | Creation time |
| updated_at | DateTime | DEFAULT utcnow, ON UPDATE | Update time |

#### alert_rules

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String(36) | PK, UUID | Rule ID |
| user_id | String(36) | FK(users.id), NOT NULL, INDEX | Owner ID |
| alert_type | String(20) | NOT NULL | Alert type |
| severity | String(20) | DEFAULT "warning", NOT NULL | Default severity |
| name | String(200) | NOT NULL | Rule name |
| description | Text | NULLABLE | Rule description |
| trigger_type | String(50) | NOT NULL | Threshold/Rate/Cross |
| trigger_config | JSON | NOT NULL | Trigger configuration |
| notification_enabled | Boolean | DEFAULT TRUE, NOT NULL | Notifications enabled |
| notification_channels | JSON | DEFAULT [], NOT NULL | Email/SMS/Push/Webhook |
| is_active | Boolean | DEFAULT TRUE, NOT NULL | Rule active |
| triggered_count | Integer | DEFAULT 0, NOT NULL | Trigger count |
| last_triggered_at | DateTime | NULLABLE | Last trigger time |
| created_at | DateTime | DEFAULT utcnow | Creation time |
| updated_at | DateTime | DEFAULT utcnow, ON UPDATE | Update time |

### Implementation Considerations

**fincore Integration Plan:**

1. **Replace Manual Calculations:** Update `backtest_analyzers.py` to use fincore for all metrics
2. **Maintain Compatibility:** Ensure output format remains consistent with existing API schemas
3. **Validation:** Compare fincore output with manual calculations during transition
4. **Performance:** Cache fincore results where appropriate

**API Versioning:**
- Current: `/api/v1/`
- Future: `/api/v2/` for breaking changes
- Backward compatibility maintained during transition

**WebSocket Channels:**
- `/ws/backtest/{task_id}` - Backtest progress updates
- `/ws/account/{account_id}` - Paper trading account updates
- `/ws/live-trading/{instance_id}` - Live trading updates

---

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Problem-Solving MVP - fincore integration to standardize financial metrics
**Resource Requirements:** 1-2 developers, Python + fincore expertise

### MVP Feature Set (Phase 1)

**Core User Journeys Supported:**
- Journey 1: Independent Trader (Core Success Path)
- Journey 2: Researcher (Batch Optimization Path)

**Must-Have Capabilities:**

| Feature | Status | Priority |
|---------|--------|----------|
| Strategy Management | ✅ Complete | P0 |
| Backtesting | ✅ Complete | P0 |
| Visualization | ✅ Complete | P0 |
| Parameter Optimization | ✅ Complete | P0 |
| Paper Trading | ✅ Complete | P0 |
| Live Trading | ✅ Complete | P0 |
| Real-time Monitoring | ✅ Complete | P0 |
| Alert System | ✅ Complete | P0 |
| **fincore Integration** | 🔄 **In Progress** | **P0** |
| Deployment Documentation | 🔄 In Progress | P0 |

### Post-MVP Features

**Phase 2 (Post-MVP - 3-6 months):**
- Community strategy marketplace
- Plugin system for custom analyzers
- Multi-broker expansion
- Enhanced report customization

**Phase 3 (Expansion - 6-12 months):**
- Multi-language strategy support
- ML-driven parameter optimization
- Enterprise features: multi-tenancy, compliance audit
- Professional support offerings

### Risk Mitigation Strategy

**Technical Risks:**

| Risk | Mitigation |
|------|------------|
| fincore integration complexity | Maintain manual calculation as fallback; gradual migration |
| Breaking existing functionality | Comprehensive test suite (100% coverage); regression testing |
| Performance degradation | Benchmark fincore vs. manual; optimize bottlenecks |

**Market Risks:**

| Risk | Mitigation |
|------|------------|
| User adoption of new metrics | Document benefits; provide comparison tools |
| Community contribution rate | Clear contribution guidelines; welcome issues/PRs |

**Resource Risks:**

| Risk | Mitigation |
|------|------------|
| Limited development capacity | Prioritize fincore integration; defer nice-to-have features |
| Documentation maintenance | Auto-generate API docs; community contribution |

---

## Functional Requirements

### User Management & Authentication

- FR1: Users can register a new account with username, email, and password
- FR2: Users can log in with username and password to receive an authentication token
- FR3: Users can change their password
- FR4: Users can view their own profile information
- FR5: Admin users can manage user permissions and access control

### Strategy Management

- FR6: Users can create custom trading strategies with Python code
- FR7: Users can view built-in strategy templates with pre-defined parameters
- FR8: Users can update strategy code and parameter definitions
- FR9: Users can delete their own strategies
- FR10: Users can categorize strategies by type (trend, mean-reversion, etc.)
- FR11: Users can manage multiple versions of a strategy
- FR12: Users can configure strategy parameters separately from code (YAML)

### Backtesting

- FR13: Users can submit backtest tasks with selected strategy, symbol, date range, and parameters
- FR14: Users can view backtest task status and progress in real-time
- FR15: Users can view detailed backtest results including performance metrics
- FR16: Users can view equity curve and drawdown charts for backtest results
- FR17: Users can view individual trade records from backtest results
- FR18: Users can export backtest results as HTML, PDF, or Excel reports
- FR19: Users can access backtest history and compare multiple runs

### Parameter Optimization

- FR20: Users can run grid search optimization across parameter combinations
- FR21: Users can run Bayesian optimization for intelligent parameter search
- FR22: Users can view optimization results sorted by performance metrics
- FR23: Users can select optimization objective (Sharpe ratio, max drawdown, total return)
- FR24: **System calculates all performance metrics using fincore library**

### Paper Trading

- FR25: Users can create paper trading accounts with initial capital and commission settings
- FR26: Users can view account status including cash, positions, and P&L
- FR27: Users can place buy/sell orders in paper trading accounts
- FR28: Users can view open positions and unrealized P&L
- FR29: Users can view order status and execution details
- FR30: Users can view trade history for paper trading accounts
- FR31: Users can receive real-time account updates via WebSocket

### Live Trading

- FR32: Users can deploy strategies to live trading environments
- FR33: Users can monitor live trading instances in real-time
- FR34: Users can start and stop live trading instances
- FR35: Users can configure risk management rules for live trading
- FR36: Users can receive real-time trading updates via WebSocket

### Analytics & Reporting

- FR37: Users can view standardized performance metrics calculated via fincore
- FR38: Users can view monthly return breakdowns
- FR39: Users can compare performance across multiple backtests
- FR40: Users can view trade-by-trade performance attribution

### Monitoring & Alerts

- FR41: Users can create custom alert rules based on account, position, or strategy conditions
- FR42: Users can configure alert severity levels (info, warning, error, critical)
- FR43: Users can receive alert notifications in real-time
- FR44: Users can acknowledge and resolve alerts
- FR45: Users can configure multiple notification channels for alerts

### Data Management

- FR46: System stores all user data with encryption at rest
- FR47: System logs all user actions with timestamps for audit purposes
- FR48: System maintains data isolation between users unless explicitly shared

---

## Non-Functional Requirements

### Performance

| NFR | Standard | Rationale |
|-----|----------|-----------|
| **API Response Time** | < 500ms (P95) for standard API calls | Smooth user experience |
| **WebSocket Latency** | < 1s for real-time updates | Real-time trading monitoring needs |
| **Backtest Completion** | < 5 minutes for standard 1-year backtest | Researcher iteration efficiency |
| **Report Generation** | < 30s for PDF/Excel export | Batch analysis efficiency |

### Security

| NFR | Standard | Rationale |
|-----|----------|-----------|
| **Data Encryption** | All sensitive data encrypted at rest (AES-256) | Protect strategy code |
| **Transmission Security** | TLS 1.3 for all API communications | Prevent man-in-the-middle attacks |
| **Password Security** | bcrypt hashing with minimum 8 rounds | Protect user accounts |
| **Authentication** | JWT tokens with configurable expiration (max 24h) | Session management |
| **Authorization** | Role-Based Access Control (RBAC) | Data isolation |
| **Audit Logging** | All user actions logged with timestamps | Compliance requirements |

### Reliability

| NFR | Standard | Rationale |
|-----|----------|-----------|
| **System Availability** | 99.5% uptime during market hours | Trading hours stability |
| **Data Persistence** | ACID compliance for financial transactions | Data consistency |
| **Error Recovery** | Graceful degradation on component failure | Fault tolerance |
| **Backup Strategy** | Daily automated backups with 30-day retention | Data recovery |

### Data Accuracy

| NFR | Standard | Rationale |
|-----|----------|-----------|
| **Financial Metrics** | All metrics calculated via fincore library | Standardized accuracy |
| **Metric Validation** | Consistency checks against industry standards | Result credibility |
| **Data Precision** | Minimum 6 decimal places for financial calculations | Precision requirements |

### Integration

| NFR | Standard | Rationale |
|-----|----------|-----------|
| **API Compatibility** | 100% Backtrader ecosystem compatibility | Seamless migration |
| **Data Feed Support** | Extensible architecture for multiple data sources | Flexibility |
| **Broker API** | Support for multiple broker execution APIs | Extensibility |
| **WebSocket Stability** | Automatic reconnection with < 5s recovery | Real-time data continuity |

### Maintainability

| NFR | Standard | Rationale |
|-----|----------|-----------|
| **Test Coverage** | Maintain ≥ 100% code coverage | Code quality |
| **API Documentation** | Auto-generated OpenAPI docs always current | Developer experience |
| **Code Quality** | Google-style docstrings for all modules | Maintainability |
