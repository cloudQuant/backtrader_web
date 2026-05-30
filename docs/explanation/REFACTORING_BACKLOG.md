# Refactoring & Hardening Backlog

This file tracks items that surfaced during the iteration-163 health pass but
were intentionally **not** addressed in that pass because each is too large or
too policy-sensitive to do at the end of a session. Each entry is sized in
calendar terms for a single engineer, and includes the smallest meaningful
first slice.

> All items below are deliberate "do later, on purpose". The hygiene fixes that
> were applied in the same pass live in CHANGELOG / git history; this file is
> only the *deferred* list.
>
> **2026-05-30 — iteration-175 debt clearance (176 §).** The bulk of the
> "176 候选" list (mypy services strict §A, i18n CJK §C, a11y §D, frontend
> coverage 75 §E, OTel perf baseline §F, 500–999 line .vue split §G) plus
> P1#5, P2#8, P2#9, P2#11, P2#13 all shipped and were **deleted from this file**
> per the "don't leave green checks" rule. Their evidence lives in
> `docs/iterations/迭代176-工程债接续与基础设施收尾/DEBT_CLEARANCE.md`,
> CHANGELOG and git history. What remains below is the genuinely-open set:
> ops-only policy items, the large live-trading refactors that need staged
> branches, and the feature-track reclassification of §B.

---

## Feature-track (NOT refactoring debt) — 173B 三项

> These are **new product features**, not refactor/hardening debt. Treating
> them as debt to "clear with code" would mean shipping an un-briefed
> implementation. 176 decision: move them out of the refactor backlog and track
> them on the product backlog. Listed here only for audit trace; **out of scope
> for the iteration-175 debt clearance.**

| Item | Nature | Disposition | Owner | Target |
| --- | --- | --- | --- | --- |
| T2 (WS Gateway Migration) | feature | product backlog (needs design) | @yunjinqi | 2026-08-15 |
| T7 (News Intelligence 产品化) | feature | product backlog (**needs product brief**) | @yunjinqi | 2026-09-01 |
| T10 (Quant Tool Registry 产品化) | feature | product backlog | @yunjinqi | 2026-08-30 |

---

## P0 — Policy decisions (need product / ops sign-off)

### 3. Local `.env` files contain real third-party credentials

- **Where**: developer-local `.env` and `strategies/simulate/*/.env`
- **Symptom**: real OKX / Binance / HTX / CTP / Telegram / PyPI / ReadTheDocs
  keys live on developer machines.
- **Status**: `git log --all -- .env` returns empty — they were never committed,
  so this is **not a code fix**.
- **Action**: operational. Audit any place these `.env` files might have leaked
  (screenshots, CI artifacts, support bundles), rotate the keys that have.
  **Code-side done (176)**: the "Sharing a Repro Bundle (Scrub Secrets First)"
  checklist was added to `CONTRIBUTING.md` (scrub/redact `.env`, logs,
  screenshots; rotate on exposure). The remaining audit + key rotation is a
  developer/ops action that cannot be performed in-repo.
- **Effort**: 1–2 hours of audit + rotations (ops, outside this repo).

---

## Infrastructure policy items (need team decision, 176 §H)

These are the monitoring/CI items from §H that are **not closeable with code**;
the code-side of §H (logs↔traces correlation, OTel/Prometheus metrics) shipped
2026-05-30 — see `DEBT_CLEARANCE.md`.

- E2E full suite as a PR-blocking gate (175 only blocks on smoke) — needs team
  acceptance of longer PR times and a flake budget.
- Bundle-size threshold tightening (300KB → 250KB) — confirm current headroom
  first.
- DB migration dry-run against a real staging dataset — needs a staging
  environment + a real data snapshot.
- `monorepo-check` job advisory → blocker — needs team policy decision.

---

## P1 — Real correctness issues, large surfaces

### 4. `manual_gateway_service.py` mixes blocking I/O with async context

- **Where**: `src/backend/app/services/manual_gateway_service.py` (~2671 lines)
- **Symptom**: top-level imports include `time`, `subprocess`, `urllib.request`,
  `socket`. `time.sleep`, `subprocess.run`, `urlopen` are called from coroutines
  reachable from async API handlers (live-trading lifecycle).
- **Why deferred**: this code owns gateway lifecycle for **real** order routing
  (CTP / IBKR ClientPortal / CCXT). A bug here can break live trading. Refactors
  must be staged behind a dedicated branch with manual paper-trading verification.
- **Recommended slices** (each independently shippable):
  1. Extract pure helpers (port discovery, error parsing, env autodetection)
     into a new `manual_gateway/utils.py`. Pure functions, no behavioural change.
  2. Wrap blocking calls in `asyncio.to_thread(...)` at the *callers* in
     async handlers; keep the service synchronous internally.
  3. Split the file by gateway family: `ib_clientportal.py`, `ctp.py`,
     `ccxt.py`, `mt5.py`, with a thin facade preserving the existing API.
  4. Replace `subprocess.run(["lsof", ...])` with a documented `psutil`
     fallback chain that doesn't require a non-Python tool to be installed.
- **Effort**: M-L per slice; full split is L (1–2 weeks).

### 6. `workspace_service.py` (~2560 lines → 726 lines after slices)

**Status update (2026-05-30)**: 7 slices have landed in `app/services/workspace/`
(reconciliation, reports, lifecycle, units, optimization, runtime, run_ops).
The original module is now 726 lines. The remaining work is opportunistic
clean-up of the few static helpers still on the class; no large surface left.

**Pattern (re-use for any further extraction)**:

1. Create `app/services/workspace/<slice>.py` with module-level async
   functions. No class, no `self`. Dependencies (`_load_workspace`,
   `_resolve_unit_bar_count`, etc.) injected as callable parameters.
2. Original `WorkspaceService.<method>` becomes a 5-line facade that
   imports the slice locally (inside the method body) and delegates,
   passing the bound static helpers as the callable args.
3. Tests that hit `WorkspaceService.<method>` keep working unchanged.
4. Tests that reach into static helpers (`WorkspaceService._task_elapsed_seconds`)
   keep working too — those helpers stay on the class for now.

### 7. Vue views > 1500 lines

- **Status (2026-05-30)**: the original two offenders (`AIChatPage.vue` 2220→548,
  `TradingWorkspaceUnitsTab.vue` 1597→481) were split during §G. No `.vue` file
  is over 1500 lines anymore. This entry stays as a *standing rule*: any new
  view that grows past ~500 lines should be split per the recipe below.
- **Recommended slices**: extract per-pane child components, move data
  transformations into `src/frontend/src/composables/`, push API normalization
  into `src/frontend/src/api/*` modules. Aim for views under 500 lines.
- **Effort**: M per file.

---

## P2 — Worth doing, smaller

### 12. `mypy` is installed but ungated

- **Where**: `src/backend/pyproject.toml :: [tool.mypy]`
- **Status**: config present; strict override now covers the services subpackages
  (§A) but there is still no CI gate that fails on *new* errors repo-wide.
- **Recommended fix**: introduce a ratchet — fail CI on new errors in the
  already-clean packages (`app/utils`, `app/schemas`, `app/services/*` strict
  set), and widen the scope as packages get cleaned up.
- **Effort**: S to set up, M-L to chase down errors.

### 13. `quote_service.py` still mixes transport, cache, symbol persistence, and normalization

- **Where**: `src/backend/app/services/quote_service.py`
- **Status**: cache/persistence helpers extracted to `quote/cache.py` and
  gateway/runtime + ZMQ command transport extracted to `quote/runtime.py`
  (176 §P2#13). The remaining module still owns symbol/default-source
  normalization and response shaping.
- **Recommended slices**:
  1. Move symbol/default-source normalization into `quote/symbols.py`.
  2. Keep `QuoteService` as the thin façade/singleton boundary used by the API.
  3. Add focused unit tests per slice before touching transport behavior.
- **Effort**: M.

---

## How to use this list

- **Don't** treat this as a TODO that one PR closes. Each item is its own work.
- **Do** open a tracking issue per entry as you start it.
- **Do** delete items from this file once they ship; don't leave green checks.
- For P0 items, get product/ops alignment before writing code.
