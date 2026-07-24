---
title: AI for Investor
description: An AI-assisted research, validation, and trading-support platform for quantitative teams
---

# AI for Investor

AI for Investor connects natural-language research, knowledge retrieval, strategy development, backtest validation, trading workspaces, and portfolio-risk views into an auditable quantitative research workflow. It accelerates research; it does not replace data validation, risk controls, or human trading decisions.

[Get started](./getting-started/index.md){ .md-button }

## From a question to a verifiable result

1. Use **AI Chat** and a knowledge base to retrieve research rules, post-mortems, and data definitions.
2. Create, review, or generate a Backtrader strategy draft in **Strategies**, then add it to a research workspace.
3. In **Data → Market Data**, choose an instrument and check coverage and quality. The page reads the local MySQL market-data warehouse first; AkShare is contacted only after an explicit query.
4. Run a backtest in a **research workspace**, inspect metrics and robustness checks, and retain its configuration and result snapshot.
5. Move human-reviewed work to a **trading workspace**, then monitor accounts, positions, trades, cumulative P&L, drawdown, and allocation on the portfolio page.

## Core capabilities

| Domain | Current capability |
| --- | --- |
| AI and knowledge | Knowledge bases, document indexing, cited answers, strategy ideation/review, and AI research |
| Data trust | AkShare warehouse, MySQL-first reads, coverage matrix, quality warnings, explicit online refresh, and caching |
| Research and backtests | Backtrader runs, normalized metrics, reports, strategy versions, research workspaces, and robustness checks |
| Trading and risk | Simulation/trading workspaces, gateway state, portfolio aggregation, position valuation, P&L, and drawdown views |
| Engineering | FastAPI, Vue 3, SQLAlchemy, MySQL/PostgreSQL/SQLite, pytest, Vitest, and Playwright |

## Operating boundaries

- Review AI output, RAG evidence, and backtest metrics before acting. Historical results are not future returns.
- Market data, strategy code, and account data can be sensitive. Keep secrets in environment variables or a secrets manager; never commit them.
- Live gateways are high-risk. Validate in research/simulation first, then follow your organization’s approval and risk controls.

## Documentation map

- [Getting started](./getting-started/index.md): install, run, and complete a first research loop.
- [Features](./features/index.md): knowledge, market data, strategies, backtests, workspaces, and optimization.
- [Development](./development/index.md): architecture, API, and data boundaries.
- [Deployment](./deployment/index.md): Docker and production checklist.
- [Reference](./reference/index.md): configuration and common commands.

## Technology

| Layer | Technology |
| --- | --- |
| Frontend | Vue 3, TypeScript, Vite, Element Plus, ECharts, Pinia |
| Backend | FastAPI, Pydantic, SQLAlchemy 2, Uvicorn |
| Research engine | Backtrader; fincore adapters where available, with compatible metric calculation otherwise |
| Data and AI | AkShare, MySQL market-data warehouse, OpenAI-compatible generation, optional ChromaDB / sentence-transformers semantic retrieval |

For repository entry points, internal engineering docs, and the archive policy, see `docs/INDEX.md`.
