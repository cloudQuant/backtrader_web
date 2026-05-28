# Refactoring & Hardening Backlog

This file tracks items that surfaced during the iteration-163 health pass but
were intentionally **not** addressed in that pass because each is too large or
too policy-sensitive to do at the end of a session. Each entry is sized in
calendar terms for a single engineer, and includes the smallest meaningful
first slice.

> All items below are deliberate "do later, on purpose". The hygiene fixes that
> were applied in the same pass live in CHANGELOG / git history; this file is
> only the *deferred* list.

---

## P0 — Policy decisions (need product / ops sign-off)

### 3. Local `.env` files contain real third-party credentials

- **Where**: developer-local `.env` and `strategies/simulate/*/.env`
- **Symptom**: real OKX / Binance / HTX / CTP / Telegram / PyPI / ReadTheDocs
  keys live on developer machines.
- **Status**: `git log --all -- .env` returns empty — they were never committed,
  so this is **not a code fix**.
- **Action**: operational. Audit any place these `.env` files might have leaked
  (screenshots, CI artifacts, support bundles), rotate the keys that have, and
  add a checklist item to the "share a repro bundle" section of
  `CONTRIBUTING.md`.
- **Effort**: 1–2 hours of audit + rotations.

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

### 5. `sync_service.py` is the largest file in the repo

- **Where**: `src/backend/app/services/sync_service.py` (~3091 lines)
- **Symptom**: single module owns Akshare → MySQL replication, schema diffing,
  task scheduling, error backoff, progress reporting, and the SSH/Docker
  fallback path. Hard to reason about, hard to test in isolation.
- **Recommended slices**:
  1. Extract progress / status reporting into `sync/progress.py`.
  2. Extract the `direct_mysql` and `ssh_docker` transport adapters behind a
     small `SyncTransport` protocol — the rest of the code shouldn't know which
     is in use.
  3. Move schema-diff logic into `sync/schema_diff.py`.
  4. Add per-slice unit tests as each piece moves out.
- **Effort**: L (1+ week).

### 6. `workspace_service.py` (~2560 lines → ~2296 after first 2 slices)

**Status update (2026-05-19)**: Slices 1 and 7 of the 7-step plan below have
landed. Original module shrank by 264 lines (10%). The pattern is proven; the
remaining slices follow the same recipe.

**Completed slices** (in `app/services/workspace/`):

- ✅ **Slice 7 — reconciliation** (`workspace/reconciliation.py`, ~140 lines).
  Pulled out of the orchestration layer; called once at FastAPI startup. The
  ``WorkspaceService.reconcile_*`` methods are now 5-line facades that
  delegate to standalone async functions. ``_resolve_unit_bar_count`` is
  injected as a callable to avoid a back-import on the workspace service.
- ✅ **Slice 6 — reports** (`workspace/reports.py`, ~320 lines). Same recipe:
  pure async functions, `_load_workspace` injected as a callable, original
  ``WorkspaceService.{get,delete}_workspace_report`` methods now thin facades.
  No back-imports.

**Pattern (re-use for remaining slices)**:

1. Create ``app/services/workspace/<slice>.py`` with module-level async
   functions. No class, no ``self``. Dependencies (``_load_workspace``,
   ``_resolve_unit_bar_count``, etc.) injected as callable parameters.
2. Original ``WorkspaceService.<method>`` becomes a 5-line facade that
   imports the slice locally (inside the method body) and delegates,
   passing the bound static helpers as the callable args.
3. Tests that hit ``WorkspaceService.<method>`` keep working unchanged.
4. Tests that reach into static helpers (``WorkspaceService._task_elapsed_seconds``)
   keep working too — those helpers stay on the class for now.

### 7. Vue views > 1500 lines

- **Where**:
  - `src/frontend/src/views/AIChatPage.vue` (~2220 lines)
  - `src/frontend/src/views/TradingWorkspaceUnitsTab.vue` (~1597 lines)
- **Recommended slices**: extract per-pane child components, move data
  transformations into `src/frontend/src/composables/`, push API normalization
  into `src/frontend/src/api/*` modules. Aim for views under 500 lines.
- **Effort**: M per file.

---

## P2 — Worth doing, smaller

### 8. Re-enable `B904` ruff rule (raise from)

- **Where**: `src/backend/pyproject.toml`, `[tool.ruff.lint] ignore = ["B904"]`
- **Symptom**: error context is silently dropped at every `raise X` inside an
  `except` block. Hurts production debuggability.
- **First slice**: run `ruff check --select B904 .`, group fixes by service,
  fix one service at a time, then drop `B904` from the ignore list.
- **Effort**: M (mostly mechanical, but a couple hundred call sites likely).

### 9. CI runs only smoke integration tests

- **Where**: `.github/workflows/ci.yml :: integration-test`
- **Symptom**: only tests marked `@pytest.mark.integration` run; the
  `paper_trading` and `live_trading` flows have no integration coverage.
- **Recommended fix**: add a manual workflow_dispatch matrix that exercises a
  paper-trading round-trip against the postgres service container.
- **Effort**: S–M.

### 11. `feature_flags` cache is computed at first request, then never refreshed

- **Where**: `src/backend/app/main.py`, `_get_feature_flags`
- **Status**: a `_reset_feature_flags_cache()` helper was added during the
  iteration-163 pass for tests. Production still computes once at startup.
- **Recommended fix**: call the reset helper in the FastAPI `lifespan`
  shutdown handler and document that feature flags are computed once after
  router registration.
- **Effort**: XS.

### 12. `mypy` is installed but ungated

- **Where**: `src/backend/pyproject.toml :: [tool.mypy]`
- **Status**: config present, no CI gate.
- **Recommended fix**: introduce a ratchet — start with `mypy app/utils
  app/schemas` only, fail CI on new errors in those packages, and widen the
  scope as packages get cleaned up.
- **Effort**: S to set up, M-L to chase down errors.

### 13. `quote_service.py` still mixes transport, cache, symbol persistence, and normalization

- **Where**: `src/backend/app/services/quote_service.py` (~1260 lines after cache slice)
- **Status**: cache/persistence helpers were extracted to `app/services/quote/cache.py`,
  and `quote_service.py` shrank by 89 lines. The remaining module still owns
  gateway discovery, ZMQ subscription lifecycle, snapshot hydration, symbol
  normalization, and response shaping.
- **Recommended slices**:
  1. Move gateway/runtime discovery and receiver lifecycle into `quote/runtime.py`.
  2. Move symbol/default-source normalization into `quote/symbols.py`.
  3. Keep `QuoteService` as the thin façade/singleton boundary used by the API.
  4. Add focused unit tests per slice before touching transport behavior.
- **Effort**: M.

---

## How to use this list

- **Don't** treat this as a TODO that one PR closes. Each item is its own work.
- **Do** open a tracking issue per entry as you start it.
- **Do** delete items from this file once they ship; don't leave green checks.
- For P0 items, get product/ops alignment before writing code.
**Remaining slices (in recommended order)**:

- **Slice 1 — pure helpers** → `workspace/_helpers.py`. Static methods like
  ``_db_task_elapsed_seconds``, ``_runtime_optimization_elapsed_seconds``,
  ``_parse_runtime_datetime``, ``_build_runtime_optimization_progress``,
  ``_build_db_optimization_progress``, ``_resolve_optimization_progress``,
  ``_optimization_progress_response_to_opt_info``,
  ``_requested_bar_count``, ``_collect_runtime_files``,
  ``_runtime_file_kind``, ``_resolve_runtime_file``,
  ``_open_path_in_file_manager``, ``_unit_to_dict``, ``_compute_rename``.
  No state, no I/O. Tests in
  ``src/backend/tests/test_workspace_service.py`` reach for some of these
  directly via ``WorkspaceService._task_elapsed_seconds`` etc., so keep
  thin ``@staticmethod`` shims on the class delegating to the helper module
  until the tests are updated.
- **Slice 2 — workspace CRUD** (`create_workspace`, `get_workspace`,
  `list_workspaces`, `update_workspace`, `delete_workspace`) →
  `workspace/lifecycle.py`. ~110 lines. Watch for tight coupling to
  module-level ``_normalize_workspace_*`` and ``_workspace_to_response`` —
  they need to move too or be re-exported.
- **Slice 3 — unit CRUD + helpers** (`create_unit`, `batch_create_units`,
  `list_units`, `get_unit`, `get_unit_runtime_info`, `read_unit_runtime_file`,
  `open_unit_runtime_dir`, `update_unit`, `delete_unit`, `bulk_delete_units`,
  `reorder_units`, `rename_group`, `rename_unit`) → `workspace/units.py`.
  ~350 lines. Depends on slice 1 helpers.
- **Slice 5 — optimization** (`submit_unit_optimization`,
  `get_unit_optimization_*`, `cancel_unit_optimization`, `apply_best_params`,
  `get_unit_optimization_result_artifact_metadata`,
  `get_unit_optimization_result_payload`,
  `_resolve_optimization_artifact_log_dir`,
  `_build_optimization_artifact_metadata`,
  `_build_optimization_trial_payload`) → `workspace/optimization.py`. ~500 lines.
- **Slice 4 — run / stop / status** (`run_units`, `stop_units`,
  `get_units_status`, `_background_poll_units`, `_poll_single_unit`,
  `_poll_task_completion`) → `workspace/runtime.py`. ~430 lines including
  helpers. Hardest slice; touches ``asyncio.create_task`` orchestration.

**Effort**: M per slice; remaining 5 slices are ~M-L total (1 week).
