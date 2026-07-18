# Gitleaks historical baseline

Iteration 183 replaced the planned destructive history rewrite with a
fingerprint-scoped risk baseline. This preserves commit history while ensuring
that every new finding, including one in a previously affected path, remains
visible to CI.

## Owner decision

- IBKR is used for paper trading. The repository owner accepts the historical
  exposure risk and does not require a history rewrite for its cookie file.
- `ibkr_cookies.json` produced zero findings in the gitleaks 8.30.1 full-history
  scan. It remains removed from the tracked tree and ignored; the adjacent
  example contains placeholders only.
- History rewrite and force-push are optional emergency remediation, not an
  iteration acceptance requirement.

## Audited scan

The 2026-07-18 redacted scan covered 485 commits and initially produced 114
findings across 35 files and 18 commits:

- 103 findings are test fixtures, examples, manifest hashes, false positives,
  or the intentionally public Supabase `anon` JWT.
- The remaining 11 findings came from old Binance, OKX, manual-gateway, and
  MySQL sync configuration. The owner confirmed on 2026-07-18 that all of those
  historical credentials had already been revoked. Their exact fingerprints
  are now recorded in `.gitleaksignore`.

The fingerprint format includes commit, path, rule and line. It does not create
a path-wide exception, so a new secret in the same file remains blocking.

## Closure rule

The owner revocation attestation and exact 114-fingerprint baseline are now
recorded. A gitleaks 8.30.1 redacted scan of all 485 commits exited 0 with zero
findings. The committed `blocking_ready=true` metadata makes the CI full-history
step blocking automatically; retain a passing published CI run as final evidence.

Reference: the official Gitleaks documentation describes `.gitleaksignore` as
the mechanism for suppressing a uniquely identified finding by fingerprint.
