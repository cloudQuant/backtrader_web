# Historical credential rotation inventory

This inventory is intentionally value-free. It was derived from historical
runtime JSON by reading field names and counting unique values without printing
the values or their hashes.

The repository owner confirmed on 2026-07-18 that the non-IBKR credentials may
be live. They must therefore be treated as active until provider-side evidence
proves otherwise. Git history does not need to be rewritten, but every active
credential must be revoked or rotated before its historical gitleaks finding is
accepted by fingerprint.

Current-tree containment is already in place: runtime credential paths are
ignored, the local `manual_gateways.json` mode was tightened from `0664` to
`0600`, and manual-gateway, MySQL sync, and AI-provider configuration writers
now use an atomic owner-only writer that does not follow destination symlinks.

## Rotation scope

- [x] Binance: one API key + secret pair (`testnet=false`). Revoke the old key,
  issue a least-privilege replacement, and keep the new value runtime-only.
- [x] OKX: one API key + secret + passphrase set (`testnet=false`). Revoke the
  old API key and replace the complete set.
- [x] CTP: one user/password/auth-code/app-id set. Change the trading password
  and invalidate/reissue the authentication tuple where the broker supports it.
- [x] MT5: one login/password set. Change the trading password through the
  broker or terminal and verify the old password no longer authenticates.
- [x] Local MySQL: one user/password set. Change the password and update only
  ignored runtime configuration.
- [x] Remote MySQL: one user/password set. Change the password, review whether
  remote administrative login is necessary, and prefer a least-privilege user.
- [x] IBKR Client Portal: one paper-trading login/session set. The owner accepts
  its historical exposure; it is not part of the required rotation scope.

## Evidence required for closure

On 2026-07-18 the repository owner confirmed that all historical credentials
listed above had already been revoked. This owner attestation is the evidence
used to accept their 11 historical gitleaks findings. No old or new credential
value is recorded in this repository. New credentials belong only in the
deployment secret store, local environment, or ignored runtime volume.

After all items are complete:

1. [x] Add only the 11 already-audited historical gitleaks fingerprints to
   `.gitleaksignore`.
2. [x] Update `scripts/ci/gitleaks_history_baseline.json` from 103/11/not-ready
   to 114/0/ready.
3. [x] Run a redacted full-history scan and require zero unresolved findings.
4. [ ] Publish the changes and retain a passing blocking CI run. The committed
   `blocking_ready=true` metadata now enables blocking automatically;
   `SECRET_SCAN_HISTORY_BLOCKING=true` is an optional emergency override.
