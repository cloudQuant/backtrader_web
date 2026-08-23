# Iteration 195 governance desired state

This directory is the repository-side, auditable contract for community PR
governance. It is not proof that a GitHub Ruleset, branch protection setting,
release environment, or security disclosure channel is active.

## Sources of truth

- `risk-paths.json` is the only source used to classify changed paths. The
  highest matching level wins: `R0` documentation, default `R1`, elevated
  `R2`, and highest-risk `R3`. Labels can add review context but cannot lower a
  path-derived risk level.
- `rulesets/*.json` are normalized desired-state manifests. Current pending
  state intentionally excludes GitHub API IDs, timestamps, actor IDs, secrets,
  and guessed required-check contexts; later evidenced transitions may add only
  verified actor or integration IDs through their structured contracts.
- `.github/CODEOWNERS` names the currently verified GitHub owner
  `@cloudQuant`; it preserves the Iteration 193 ratchet entries and adds the
  governance coverage used by this iteration.

## Current gate limits

D2 has one verified owner but no second independent approval pool. The
manifests therefore record code-owner review as desired but disabled; they do
not claim it is remotely enabled. D3 permits only a desired-state draft and a
read-only verifier until Ruleset capability is tested. D4 remains blocked, so
both branch manifests deliberately use an empty `required_checks.contexts`
list with a source pointing to future real Check Run evidence. D6 also keeps
tag-authorized actors empty until release-environment capability is verified.

Each target records both its `include` and `exclude` ref arrays. The current
arrays intentionally have no exclusions; the verifier treats an unexpected
API exclusion as drift rather than silently broadening or narrowing a Rule.

The validator recognizes the future transition only when it is evidenced:
`required_checks.status: "verified"` needs non-empty, non-blank, unique Check
Run contexts plus a source; an applied Ruleset needs a readback reference;
enabled code-owner review needs D2 owner evidence; and verified tag actors need
GitHub-valid actor identity, `bypass_mode`, D3/D6 evidence, and an exact match
to the tag Ruleset's `bypass.actors` API-readback field. `Integration`,
`RepositoryRole`, `Team`, and `User` need positive integer IDs;
`OrganizationAdmin` IDs are intentionally ignored/canonicalized to `null`;
and `DeployKey` must use `null`. The only accepted modes are `always` and
`pull_request`; the latter is allowed only on branch Rulesets and never for a
DeployKey. GitHub's `exempt` mode is deliberately rejected: a standing
exemption cannot be bound to this repository's incident, reason, expiry, and
24-hour postmortem emergency-bypass contract. Every future bypass actor must
therefore have a matching structured emergency exception with incident, reason,
an ISO-8601 `issued_at` (or `starts_at`), an unexpired `expires_at` no more
than 24 hours after that start, and gate-scoped readback evidence. These are
schema capabilities, not claims that the current repository has passed those
gates.

Future applied activation, code-owner enablement, verified Check Runs, tag
actors, and emergency exceptions use evidence objects with explicit gate IDs
and a repository-local evidence path or HTTPS URL; free-form strings do not
prove a gate. Required Check Run identities retain both `context` and
`integration_id`, and `do_not_enforce_on_create` is fixed at `false`. The
normalizer fails closed when a Rulesets API readback omits `bypass_actors`: an
explicit empty array is required to prove an empty bypass pool.

`enforcement: "active"` expresses the eventual Ruleset configuration to be
read back after its gates pass. `activation.remote_state: "not_applied"`
records the current truth: this repository has not applied it externally.

## Read-only verification

Use a sanitized fixture while developing the contract:

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python \
  scripts/ci/verify_github_governance.py --fixture \
  scripts/ci/tests/fixtures/github-rulesets.json \
  --manifest-dir .github/governance/rulesets
```

After D3 grants a read-only capability check, `--live --repo
cloudQuant/backtrader_web` only invokes GitHub CLI `api` GET endpoints to list
Rulesets and retrieve their details. A difference exits non-zero and produces
both a concise human report and JSON. The verifier never creates, updates,
deletes, applies, pushes, or bypasses a Rule.

The included fixture represents the normalized shape expected after approved
external application. It is a test fixture, not external activation evidence.
