# Legacy Helper Scripts

These are one-off helper / verification scripts that were previously sitting at
the backend root or repo root. They are kept here for historical reference and
because some are still mentioned in archived iteration docs, but **none are
required by the application or by CI**.

## Inventory

| File | Purpose | Status |
|------|---------|--------|
| `check_imports.py` | Prints whether a hardcoded list of `app.*` modules is importable. | Diagnostic. Use `pytest --collect-only` instead. |
| `simple_check.py` | Prints whether a few backend files exist on disk. | Diagnostic. Trivial. |
| `quick_test.py` | Lightweight smoke run for the backend. | Superseded by `pytest tests/`. |
| `manual_verify.py` | Same flavour as `check_imports.py` (originally named `manual_verify.sh` despite a python shebang; renamed to `.py`). | Diagnostic. |
| `fix_auth_tests.py` | One-shot codemod that rewrote `403 → 401` assertions in auth tests. | Already applied. Kept as audit trail. |
| `test_acceptance_124.py` | HTTP-driven manual acceptance script for iteration 124 (workspace APIs). Hits a running `localhost:8000`. | Manual smoke. Referenced in archived iteration docs. |
| `test_strategy_load.py` | Hand-written strategy-loading smoke run that imports backend modules and runs Backtrader. Originally sat at repo root and was referenced in `docs/TESTING.md`. | Manual smoke. |

## Guidance for new diagnostic scripts

Prefer adding real `pytest` tests under `src/backend/tests/` (use `@pytest.mark.integration`
or `@pytest.mark.e2e` for tests that need a running service). Only drop a new file
into this folder if it's a deliberately throwaway one-shot.
