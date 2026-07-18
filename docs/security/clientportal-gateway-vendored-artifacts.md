# IBKR Client Portal Gateway vendored artifacts

The following files are upstream Client Portal Gateway demo artifacts, not
application runtime credentials. They remain allowlisted by
`scripts/ci/check_sensitive_tracked_files.py` so the tracked-sensitive check
has an explicit, reviewable rationale.

| Path | Purpose | SHA-256 |
| --- | --- | --- |
| `src/clientportal.gw/root/demo.zip` | Upstream gateway demo archive | `5a67a018c6f1cf05e7aa8f076e8116a3f87477b0976443f32a8e2cc436720329` |
| `src/clientportal.gw/root/vertx.jks` | Upstream gateway demo keystore referenced by `conf*.yaml` | `be825cd00e9c6e40bf836b1a5b4c68f78bf3b8b60aa139811423b7657cb02849` |

IBKR session cookies are deliberately different: the working path
`src/bt_api_py/configs/ibkr_cookies.json` is ignored and must be supplied on a
developer machine or runtime volume. The tracked
`ibkr_cookies.example.json` contains placeholders only.
