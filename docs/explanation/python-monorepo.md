# Python Monorepo (uv workspace)

> Iteration 175 §9.6 — selection rationale and operating notes for the
> backend + bt_api_py monorepo wiring.

## Selection rationale

| Tool | Pros | Cons | Decision |
|---|---|---|---|
| **uv workspace (selected)** | First-class `[tool.uv.workspace]` declaration; resolves member packages into a single venv with one lock file; backed by Astral, same vendor as the project's existing `uv` adoption. | Lock-file format (`uv.lock`) is uv-specific. | ✅ chosen for 175. |
| hatch workspace | Mature isolation per env; explicit env tables. | Heavier ergonomics; second tool on top of the existing pip/uv toolchain we want to keep small. | not chosen. |
| pdm workspace | PEP 517 native; supports multi-package mono-repos via `[tool.pdm]`. | Adds yet another lock format alongside our SSOT pip lock. | not chosen. |

> 175 also explicitly rejected polyrepo splits and pnpm-style JS monorepo
> tooling: the project already enforces a clean Python/JS split at the
> top-level (`src/backend` vs `src/frontend`), so a single Python-side
> workspace is sufficient.

## Vendored package handling

`src/clientportal.gw/` is a vendored third-party tarball. It is **not** a
workspace member — it is built and shipped separately as part of the live
trading gateway. The 174 §A6 boundary discussion documented this; 175
inherits that decision unchanged. The workspace `[tool.uv.workspace]
members = ["src/backend", "src/bt_api_py"]` list is intentionally the
complete set.

If a future iteration adds a third Python member (e.g. a CLI shipped from
the repo), the steps are:

1. Add the new directory to `[tool.uv.workspace] members`.
2. Ensure that directory has its own `pyproject.toml`.
3. Re-run `uv sync --workspace` to regenerate `uv.lock`.
4. Run `python scripts/dev/check_workspace_lock_conflict.py` to verify the
   new dependencies do not contradict `config/requirements-dev.lock`.

## Boundary consistency with 174 §A6

174 §A6 already declared:

- `src/backend` and `src/bt_api_py` are independent Python packages.
- `src/backend` is **consumer-only** of `bt_api_py` brokers; no business
  logic crosses the boundary other than via the public broker contract.
- `src/clientportal.gw/` is vendored (third-party), explicitly **not** part
  of the project's source tree under management.

175 §9 preserves all three of those rules. The workspace tooling does not
relax them; it only provides a single command (`make check-all`) that
exercises both packages with one venv resolution.

## Daily usage

| What you want | Command |
|---|---|
| Install both packages into a shared venv | `uv sync --workspace` |
| Run lint + typecheck + tests across all members | `make check-all` |
| Verify uv.lock and config/requirements-dev.lock agree | `make workspace-lock-check` |
| Edit only the backend (legacy flow) | `pip install -e ".[dev]"` inside `src/backend/` — still supported. |

The legacy single-package flow remains the documented default in
`CONTRIBUTING.md` "Dependency Management". The workspace flow is offered
as an opt-in convenience and is the path the 175 `monorepo-check` advisory
CI job exercises.

## CI integration

- `monorepo-check` job in `.github/workflows/ci.yml` runs `make check-all`
  with `continue-on-error: true`. It surfaces failures as a ⚠️ entry in
  `ci-summary` but does not block PR merge in 175.
- Promotion plan: 176 considers flipping `monorepo-check` to a hard gate
  once it has stayed green on `master` for one week.
