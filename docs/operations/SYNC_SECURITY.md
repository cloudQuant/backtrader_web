# Sync Security Notes

> Scope: MySQL sync command construction in `app.services.sync.transport`.

## Credential Handling

- MySQL passwords must not be passed as `-p<password>` argv.
- Local `mysql` / `mysqldump` executions use a temporary `--defaults-extra-file`.
- Temporary defaults files are created with `0600` permissions and removed after command execution.
- Local shell pipelines run through `bash -s` with the script sent on stdin, so sensitive command text is not placed in the `bash -lc` process argv.
- Remote SSH commands run `bash -s` with the script sent on stdin.
- Remote Docker shell commands use `docker exec -i <container> sh -s` and receive the inner script through stdin.
- Remote Docker imports write a temporary defaults file inside the container and use `mysql --defaults-extra-file=<path>`. The remote file is cleaned up by a best-effort trap.

## Identifier And Filter Guardrails

- Sync database, table, object, column, index, and view names are restricted to MySQL-safe identifiers matching `[A-Za-z0-9_][A-Za-z0-9_$]{0,63}`.
- `mysqldump --where` only accepts `InternalWhereSql`, which is produced by internal sync diff builders.
- Request payloads cannot provide raw `where_sql`.

## Troubleshooting

- If sync fails with `非法 MySQL ...`, rename the database object or add a reviewed migration path before syncing.
- If a MySQL command fails, user-visible errors should show redacted command previews only.
- If a temporary defaults file is left behind after an interrupted local run, remove files matching `/tmp/bt-sync-mysql-*.cnf`.
- If a remote Docker import is interrupted, remove `/tmp/backtrader_sync_mysql_*.cnf` inside the MySQL container.

## Verification

Recommended checks after sync transport changes:

```bash
cd src/backend
ruff check app/services/sync/schema_diff.py app/services/sync/transport.py app/services/sync_service.py tests/test_sync_schema_diff.py tests/test_sync_transport_security.py
pytest tests/test_sync_transport_security.py tests/test_sync_schema_diff.py tests/test_sync_progress.py -q
```
