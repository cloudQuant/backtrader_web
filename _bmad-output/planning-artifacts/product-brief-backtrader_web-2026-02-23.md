---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - "迭代114-项目完成度分析.md"
  - "迭代101-技术设计文档.md"
  - "迭代101-用户故事与验收标准.md"
  - "API.md"
  - "AGILE_DEVELOPMENT.md"
date: 2026-02-23
author: cloud
---

# Product Brief: backtrader_web

<!-- Content will be appended sequentially through collaborative workflow steps -->

---

## Executive Summary

**backtrader_web** is an open-source quantitative trading research and investment management platform built on the Backtrader engine, dedicated to solving the core pain points of quantitative traders throughout the entire workflow of strategy research, backtesting validation, paper trading, and live trading management.

Through an intuitive web visualization interface, strategy-parameter separation design, real-time monitoring, and in-depth performance analysis, we enable quantitative traders to focus on strategies themselves rather than tool usage. Our goal is to become the **best open-source investment research management tool**, enabling individual traders and small-to-medium institutions to have professional-grade quantitative trading capabilities.

---

## Core Vision

### Problem Statement

Quantitative traders face three core problems in strategy research and live trading management:

1. **Unintuitive Tools**: Excellent engines like Backtrader use command-line interfaces with steep learning curves and unintuitive result analysis
2. **Chaotic Strategy Management**: Strategy code and parameter configuration are mixed, requiring code modifications for parameter adjustments, difficult version management, and cumbersome A/B testing
3. **Blind Spots in Live Trading Management**: Lack of real-time monitoring during live trading prevents timely issue detection; lack of post-trade performance attribution analysis prevents systematic strategy optimization

### Problem Impact

These problems lead to:
- Researchers spending 60% of their time on tool operations rather than strategy optimization
- Excellent strategies cannot be fully validated due to cumbersome parameter tuning
- Live trading risk exposures cannot be discovered in time, potentially causing significant losses
- Unclear sources of profit and loss, leading to aimless strategy iteration

### Why Existing Solutions Fall Short

| Solution | Why It Falls Short |
|----------|-------------------|
| **Backtrader Native** | Pure code/CLI operations, no visual interface, no strategy management, no monitoring |
| **SaaS Platforms (JoinQuant/MiQuant)** | Strategy code uploaded to cloud (security risk), high subscription fees, cannot self-host, limited features |
| **Self-Built Systems** | High development cost, fragmented functionality, difficult to achieve professional grade |

### Proposed Solution

**backtrader_web** provides:

- 🖥️ **Intuitive Web Interface**: All operations through visual interface, backtest results at a glance
- 📦 **Strategy-Parameter Separation**: YAML configuration files manage parameters, code and configuration decoupled, supporting batch parameter optimization
- 📊 **Professional Visualization**: K-line charts, equity curves, drawdown analysis, monthly heatmaps, and 10+ other chart types
- 🔴 **Real-time Monitoring & Alerts**: WebSocket real-time push, supports custom alert rules
- 📈 **Deep Performance Attribution**: Trade-level analysis, understand the source of each trade's P&L
- 🔄 **Full Process Integration**: One set of strategy code, seamless migration from backtest to paper trading to live trading

### Key Differentiators

| Feature | Our Advantage |
|---------|---------------|
| **Open Source & Self-Hosted** | Complete control, strategy code security, no privacy leakage risk |
| **Backtrader Native** | 100% compatible with Backtrader ecosystem, no need to rewrite strategies |
| **Research-Investment Integration** | The only open-source platform connecting the full process of research→backtest→paper→live |
| **Professional-Grade Analysis** | Institutional-level features like performance attribution, risk analysis, parameter optimization |
| **100% Test Coverage** | Guaranteed code quality, enterprise-level reliability |

---

## Target Users

### Primary Users

#### 1. Independent Quantitative Trader (Individual)

**Background:**
- **Name**: Li Ming
- **Role**: Full-time individual quantitative trader
- **Experience**: 3 years in quant trading, familiar with Python and Backtrader
- **Context**: Works from home, responsible for the entire workflow from strategy research to live trading

**Pain Points:**
- Running backtests via command line with unintuitive results, requiring custom analysis scripts
- Parameter adjustments require code modifications, high trial and error cost
- No real-time visibility during live trading, creating uncertainty
- Only knows total P&L, unclear which trade or parameter caused the outcome

**Success Vision:**
- "Write strategy in morning, see visualized backtest results by noon"
- "Batch parameter optimization in afternoon, select best configuration by evening"
- "Check live status on mobile anytime, receive immediate alerts for issues"

---

#### 2. Quantitative Researcher (Professional/Team)

**Background:**
- **Name**: Wang Fang
- **Role**: Quantitative hedge fund researcher
- **Experience**: Master in Statistics, 5 years in quantitative research
- **Context**: Team collaboration, needs to report strategy performance to fund managers

**Pain Points:**
- Command line approach too slow for running hundreds of parameter combinations
- Chaotic strategy version management, unclear which version corresponds to which result
- Need to generate professional reports for leadership, but existing tools have crude output
- Difficult to share and manage team members' strategy code

**Success Vision:**
- "One-click batch parameter optimization, results sorted in table at a glance"
- "Strategy version control, can trace back to historical versions anytime"
- "One-click export professional PDF reports with beautiful charts"

---

#### 3. Quantitative Developer (Technical Integration)

**Background:**
- **Name**: Zhang Wei
- **Role**: Technical lead at quant firm
- **Experience**: 8 years development, needs to integrate backtesting platform into company system
- **Context**: Company has existing data sources and risk systems, needs integration

**Pain Points:**
- Commercial SaaS platforms cannot be self-hosted, data security concerns
- Needs API interfaces to automate backtesting calls
- Needs custom strategy templates and indicators
- Closed-source platforms cannot be secondary developed

**Success Vision:**
- "Complete RESTful API, can integrate into our trading system"
- "Open source self-hosted, complete control over strategy code"
- "Can customize analyzers and charts"

---

#### 4. Team Manager (Risk Control/Decision Making)

**Background:**
- **Name**: Mr. Chen
- **Role**: Quantitative hedge fund fund manager
- **Experience**: Responsible for team strategy approval and risk control
- **Context**: Doesn't write code, needs to understand team members' strategy performance

**Pain Points:**
- Can't read team members' code but needs to evaluate strategy quality
- No real-time monitoring of live trading risks
- Needs to compare performance across different strategies and members
- Needs permission management to prevent accidental operations

**Success Vision:**
- "Visual dashboard lets me see which strategies are making money at a glance"
- "Receive immediate alert notifications when live trading anomalies occur"
- "Can see each member's strategy contribution"

### Investment-Research Integration Trend

**Core Insight:** The boundary between research and trading is blurring. Modern quantitative traders need:

- **Unified Data**: Backtest and live trading data analyzed together
- **Fast Feedback**: Research→validation→trading cycle compressed to daily/hourly level
- **Same Person/Team**: One person or team handles both research and trading

### User Journey (Li Ming - Independent Trader)

```
Discovery Phase
   │
   ├─ Sees backtrader_web on GitHub/tech forums
   ├─ Learns about visualized backtesting + real-time monitoring
   └─ Decides to try
   │
Onboarding Phase
   │
   ├─ One-click Docker deployment, up and running in 5 minutes
   ├─ Built-in strategy templates, first backtest successful
   ├─ Sees beautiful K-line charts + equity curves, impressed ✨
   └─ "Aha moment": Backtesting can be this intuitive!
   │
Core Usage
   │
   ├─ Adjust logic in strategy code editor
   ├─ Batch parameter tuning via YAML config
   ├─ Parameter optimization results sorted, select best
   ├─ Validate in paper trading account for 2 weeks
   └─ One-click switch to live trading after confirmation
   │
Long-term Value
   │
   ├─ Check live monitoring dashboard daily
   ├─ Performance attribution analysis guides strategy iteration
   ├─ Strategy library accumulates 20+ reusable strategies
   └─ Becomes core platform for daily investment research work
```

---

## Success Metrics

### User Success Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **First Backtest Time** | Time from installation to completing first backtest | ≤ 5 minutes |
| **Strategy Validation Efficiency** | Time from idea to completing parameter optimization | ≤ 1 day |
| **Live Trading Monitoring Coverage** | Percentage of live trading with active monitoring | 100% |
| **Aha Moment Rate** | User positive reaction when first seeing visualized analysis | > 80% |
| **Daily Active Usage** | Frequency of core feature usage | Weekly usage by active researchers |
| **Strategy Library Growth** | Number of reusable strategies accumulated per user | 10+ strategies within 3 months |

### Business Objectives

#### 3-Month Objectives (Community Building)

| Goal | Metric | Target |
|------|--------|--------|
| **Community Adoption** | GitHub Stars | 500+ |
| **Contributor Growth** | Active contributors | 10+ |
| **Deployment Reach** | Deployment instances | 50+ |
| **User Feedback** | Issue resolution rate | > 90% |

#### 6-Month Objectives (User Adoption)

| Goal | Metric | Target |
|------|--------|--------|
| **User Base** | Deployment instances | 100+ |
| **Active Users** | Weekly active users | 50+ |
| **Feature Completeness** | Core features implemented | 100% |
| **Documentation** | Documentation completeness | User onboarding guide complete |

#### 12-Month Objectives (Ecosystem Maturity)

| Goal | Metric | Target |
|------|--------|--------|
| **Market Position** | Become the preferred platform in Backtrader ecosystem | #1 choice for Backtrader Web UI |
| **Community Scale** | GitHub Stars | 2000+ |
| **Contributor Network** | Active contributors | 30+ |
| **Enterprise Readiness** | Enterprise deployment cases | 5+ teams/companies |
| **Plugin Ecosystem** | Community-contributed strategies/analyzers | 20+ |

### Key Performance Indicators

#### Leading Indicators (Predict Success)

| KPI | Measurement Method | Frequency |
|-----|-------------------|-----------|
| **New User Onboarding Rate** | Percentage of new users completing first backtest within 24 hours | Weekly |
| **Feature Adoption Rate** | Percentage of users using core features (backtest, optimization, monitoring) | Weekly |
| **Community Engagement** | GitHub issues, PRs, discussions per week | Weekly |
| **Documentation Usage** | Page views on documentation, time spent on onboarding guide | Monthly |

#### Lagging Indicators (Measure Outcomes)

| KPI | Measurement Method | Frequency |
|-----|-------------------|-----------|
| **User Retention** | Percentage of users still active after 1/3/6 months | Quarterly |
| **Deployment Growth** | Net new deployment instances per month | Monthly |
| **Contributor Retention** | Percentage of contributors who remain active after 3 months | Quarterly |
| **Community Sentiment** | User satisfaction score from surveys/feedback | Quarterly |

#### Quality Indicators (Maintain Standards)

| KPI | Measurement Method | Target |
|-----|-------------------|--------|
| **Test Coverage** | Code coverage percentage | Maintain ≥ 100% |
| **Test Pass Rate** | Percentage of tests passing | 100% |
| **Issue Response Time** | Median time to respond to GitHub issues | < 24 hours |
| **Bug Fix Time** | Median time to close bug reports | < 72 hours |
| **Documentation Currency** | Documentation accuracy vs. actual features | > 95% |

### Strategic Alignment

| Vision | Success Metric | Connection |
|--------|----------------|------------|
| **Intuitive Web Interface** | First Backtest Time ≤ 5min | Validates ease of use |
| **Strategy-Parameter Separation** | Strategy Validation Efficiency ≤ 1day | Validates productivity gain |
| **Real-time Monitoring** | Live Trading Monitoring 100% | Validates risk management value |
| **Best Open-source Tool** | GitHub Stars, Community Growth | Validates market positioning |
| **Professional-Grade Analysis** | User Retention, Enterprise Deployments | Validates institutional readiness |

---

## MVP Scope

### Core Features

#### 1. Investment-Research Integration Core (Completed)

| Feature | Status | Description |
|---------|--------|-------------|
| **Strategy Management** | ✅ Complete | CRUD + Version Control + YAML parameter configuration |
| **Backtesting Service** | ✅ Complete | Core backtesting engine with async task management |
| **Visualization** | ✅ Complete | K-line charts, equity curves, drawdown analysis, 10+ chart types |
| **Parameter Optimization** | ✅ Complete | Grid search, Bayesian optimization |
| **Paper Trading** | ✅ Complete | Simulation trading environment for validation |
| **Live Trading** | ✅ Complete | Production trading execution |
| **Real-time Monitoring** | ✅ Complete | WebSocket real-time status updates |
| **Alert System** | ✅ Complete | Customizable alert rules and notifications |
| **User Management** | ✅ Complete | Authentication, RBAC permission control |

#### 2. fincore Integration (Key Addition)

**Rationale:** Replace manual metric calculations with fincore package for professional-grade, standardized financial metrics.

| Current Implementation | fincore Replacement |
|-----------------------|---------------------|
| Manual `sharpe_ratio()` calculation | `fincore.sharpe_ratio()` |
| Manual `max_drawdown()` calculation | `fincore.max_drawdown()` |
| Manual return calculations | `fincore.returns()` |
| Manual attribution analysis | `fincore.attribution()` |
| Custom performance metrics | `fincore` standard metrics |

**Integration Approach:**
- Integrate fincore into `backtest_analyzers.py`
- Replace all manual metric calculations with fincore APIs
- Maintain compatibility with existing Backtrader analyzers
- Ensure consistency across all performance metrics

**Benefits:**
- **Reliability:** Industry-standard calculations, reduced bugs
- **Consistency:** Standardized metrics across the platform
- **Maintainability:** Less custom code to maintain
- **Professional:** Same metrics used by institutional quant firms

#### 3. Deployment & Documentation

| Component | Approach |
|-----------|----------|
| **Installation** | pip install from PyPI |
| **Local Deployment** | Development setup guide |
| **Server Deployment** | systemd/supervisor configuration guide |
| **Docker** | Optional (documentation appendix only) |
| **User Documentation** | Complete deployment and usage guide |

### Out of Scope for MVP

| Feature | Reason | Timeline |
|---------|--------|----------|
| **Docker as Required Deployment** | Focus on traditional deployment first | Future version |
| **Multi-language Strategy Support** | Python + Backtrader ecosystem focus | Future version |
| **Community Strategy Marketplace** | Not core to investment-research workflow | Future version |
| **Mobile Native App** | Web interface sufficient for MVP | Future version |
| **ML-based Optimization** | Current optimization (grid/Bayesian) sufficient | Future version |

### MVP Success Criteria

| Criteria | Metric |
|----------|--------|
| **Deployment Ease** | pip install + local setup within 10 minutes |
| **First Backtest** | New user completes first backtest within 10 minutes |
| **fincore Integration** | All performance metrics calculated via fincore |
| **Documentation** | Complete deployment and usage documentation |
| **Zero Critical Bugs** | All core features functional without critical issues |

### Future Vision

#### Phase 2: Enhanced Analytics (6-12 months)

- Advanced performance attribution analysis
- Portfolio-level risk metrics
- Multi-strategy comparison tools
- Custom chart builder

#### Phase 3: Ecosystem Expansion (12-18 months)

- Community strategy sharing marketplace
- Plugin system for custom analyzers
- Multi-broker integration beyond current support
- RESTful API enhancement for third-party integration

#### Phase 4: Enterprise Features (18+ months)

- Multi-tenant architecture for firms
- Advanced compliance and audit logging
- Team collaboration features
- Professional support and SLA options
