# Iteration 175 §9.2 — convenience wrapper around scripts/dev/check_all.sh
# so contributors can run a single command to lint / typecheck / test the
# entire workspace.

.PHONY: check-all
check-all:
	@bash scripts/dev/check_all.sh

.PHONY: workspace-lock-check
workspace-lock-check:
	@python3 scripts/dev/check_workspace_lock_conflict.py

.PHONY: i18n-check
i18n-check:
	@python3 scripts/dev/check_i18n_coverage.py --check-parity

.PHONY: i18n-strict
i18n-strict:
	@python3 scripts/dev/check_i18n_coverage.py --strict

.PHONY: i18n-cjk
i18n-cjk:
	@python3 scripts/dev/check_i18n_coverage.py --strict --cjk-only

# Iteration 177 §E — repo-wide mypy error ratchet. Fails if `mypy app`
# reports more errors than the frozen baseline; `make mypy-ratchet-update`
# lowers the baseline after you've reduced the count.
.PHONY: mypy-ratchet
mypy-ratchet:
	@python3 scripts/ci/mypy_ratchet.py

.PHONY: mypy-ratchet-update
mypy-ratchet-update:
	@python3 scripts/ci/mypy_ratchet.py --update

.PHONY: bundle-budget
bundle-budget:
	@bash scripts/ci/check_bundle_size.sh src/frontend/dist
