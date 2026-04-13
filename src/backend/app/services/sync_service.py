from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import get_settings
from app.schemas.sync import (
    DatabaseInfo,
    DatabaseSyncInfo,
    SyncConfig,
    SyncConnectionStatus,
    SyncHistoryEntry,
    SyncRequest,
    SyncTaskCreateResponse,
    SyncTaskStatus,
)
from app.utils.backend_data_paths import get_backend_data_path

settings = get_settings()


class SyncService:
    def __init__(self) -> None:
        self._config_file = get_backend_data_path("sync_config.json")
        self._history_file = get_backend_data_path("sync_history.json")
        self._tmp_dir = get_backend_data_path("sync_tmp")
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._timeout_seconds = max(int(os.environ.get("SYNC_TIMEOUT_SECONDS", "7200")), 60)
        self._connect_timeout = min(
            max(int(os.environ.get("SYNC_CONNECT_TIMEOUT_SECONDS", "10")), 5),
            60,
        )

    def get_config(self) -> SyncConfig:
        defaults = SyncConfig(
            local_mysql_host=getattr(settings, "SYNC_LOCAL_MYSQL_HOST", "127.0.0.1"),
            local_mysql_port=int(getattr(settings, "SYNC_LOCAL_MYSQL_PORT", 3306)),
            local_mysql_user=getattr(settings, "SYNC_LOCAL_MYSQL_USER", "root"),
            local_mysql_password=self._get_local_mysql_password(None),
        )
        if self._config_file.is_file():
            try:
                payload = json.loads(self._config_file.read_text("utf-8"))
                return SyncConfig(**{**defaults.model_dump(), **payload})
            except (json.JSONDecodeError, OSError, ValueError):
                return defaults
        return defaults

    def save_config(self, config: SyncConfig) -> SyncConfig:
        config = self._normalize_config(config)
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        self._config_file.write_text(
            json.dumps(config.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return config

    async def test_connection(self, config: SyncConfig) -> SyncConnectionStatus:
        config = self._normalize_config(config)
        checks: dict[str, bool] = {}
        details: dict[str, str] = {}

        missing_tools = [
            name for name in ("mysql", "mysqldump", "gzip", "ssh", "scp")
            if shutil.which(name) is None
        ]
        checks["local_tools"] = not missing_tools
        details["local_tools"] = "依赖完整" if not missing_tools else f"缺少命令: {', '.join(missing_tools)}"

        local_password = self._get_local_mysql_password(config)
        if local_password:
            try:
                await self._run_exec(
                    self._build_local_mysql_query_args(
                        config,
                        "SELECT 1",
                        local_password,
                    ),
                    timeout=self._connect_timeout,
                )
                checks["local_mysql"] = True
                details["local_mysql"] = "本地 MySQL 可访问"
            except Exception as exc:
                checks["local_mysql"] = False
                details["local_mysql"] = str(exc)
        else:
            checks["local_mysql"] = False
            details["local_mysql"] = "未配置本地 MySQL 密码"

        if not config.remote_host.strip():
            checks["ssh"] = False
            checks["docker"] = False
            checks["remote_env"] = False
            details["ssh"] = "未配置远程服务器地址"
            details["docker"] = "未配置远程服务器地址"
            details["remote_env"] = "未配置远程服务器地址"
            return SyncConnectionStatus(
                success=all(checks.values()),
                checks=checks,
                details=details,
            )

        try:
            await self._run_ssh(config, "echo connected", timeout=self._connect_timeout)
            checks["ssh"] = True
            details["ssh"] = "SSH 连接成功"
        except Exception as exc:
            checks["ssh"] = False
            details["ssh"] = str(exc)
            checks["docker"] = False
            checks["remote_env"] = False
            details["docker"] = "SSH 未连通，无法检查容器"
            details["remote_env"] = "SSH 未连通，无法读取 .env"
            return SyncConnectionStatus(
                success=all(checks.values()),
                checks=checks,
                details=details,
            )

        try:
            container_state = await self._run_ssh(
                config,
                f"docker inspect -f '{{{{.State.Running}}}}' {shlex.quote(config.remote_container)}",
                timeout=self._connect_timeout,
            )
            checks["docker"] = container_state.strip() == "true"
            details["docker"] = (
                f"容器 {config.remote_container} 正在运行"
                if checks["docker"]
                else f"容器 {config.remote_container} 未运行"
            )
        except Exception as exc:
            checks["docker"] = False
            details["docker"] = str(exc)

        try:
            await self._get_remote_mysql_password(config)
            checks["remote_env"] = True
            details["remote_env"] = (
                "已使用页面填写的远程 MySQL 密码"
                if str(config.remote_mysql_password or "").strip()
                else "已读取远程 MYSQL_ROOT_PASSWORD"
            )
        except Exception as exc:
            checks["remote_env"] = False
            details["remote_env"] = str(exc)

        return SyncConnectionStatus(
            success=all(checks.values()),
            checks=checks,
            details=details,
        )

    async def list_databases(self, config: SyncConfig) -> list[DatabaseSyncInfo]:
        config = self._normalize_config(config)
        try:
            local = await self._query_local_database_info(config.sync_databases)
        except Exception:
            local = {name: self._empty_database_info(name) for name in config.sync_databases}
        if config.remote_host.strip():
            try:
                remote = await self._query_remote_database_info(config, config.sync_databases)
            except Exception:
                remote = {name: self._empty_database_info(name) for name in config.sync_databases}
        else:
            remote = {name: self._empty_database_info(name) for name in config.sync_databases}
        return [
            DatabaseSyncInfo(
                name=name,
                local=local.get(name, self._empty_database_info(name)),
                remote=remote.get(name, self._empty_database_info(name)),
            )
            for name in config.sync_databases
        ]

    async def start_upload(self, request: SyncRequest) -> SyncTaskCreateResponse:
        return await self._start_task("upload", request)

    async def start_download(self, request: SyncRequest) -> SyncTaskCreateResponse:
        return await self._start_task("download", request)

    async def get_task_status(self, task_id: str) -> SyncTaskStatus | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return SyncTaskStatus(**task)

    async def get_history(self, limit: int = 50) -> list[SyncHistoryEntry]:
        items = self._load_history()
        return [SyncHistoryEntry(**item) for item in items[:limit]]

    async def _start_task(self, direction: str, request: SyncRequest) -> SyncTaskCreateResponse:
        if not request.confirm:
            raise ValueError("同步会覆盖目标数据库，请先确认后再执行")

        config = self.get_config()
        config = self._normalize_config(config)
        if not config.remote_host.strip():
            raise ValueError("请先保存远程同步配置")

        allowed = set(config.sync_databases)
        invalid = [name for name in request.databases if name not in allowed]
        if invalid:
            raise ValueError(f"不支持的数据库: {', '.join(invalid)}")

        task_id = uuid.uuid4().hex
        now = self._now_iso()
        payload = SyncTaskStatus(
            task_id=task_id,
            status="pending",
            direction=direction,
            databases=request.databases,
            current_database=request.databases[0] if request.databases else None,
            completed_databases=[],
            stage="queued",
            progress_pct=0,
            message="任务已创建，等待执行",
            started_at=now,
            finished_at=None,
            duration_seconds=None,
            error=None,
            sync_mode=request.sync_mode,
        )
        self._tasks[task_id] = payload.model_dump()
        asyncio.get_running_loop().create_task(self._run_task(task_id, config, request))
        return SyncTaskCreateResponse(
            task_id=task_id,
            status="pending",
            message="同步任务已启动",
        )

    async def _run_task(self, task_id: str, config: SyncConfig, request: SyncRequest) -> None:
        started_monotonic = asyncio.get_running_loop().time()
        task_tmp_dir = self._tmp_dir / task_id
        task_tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._update_task(
                task_id,
                status="running",
                stage="validating",
                progress_pct=5,
                message="正在校验同步环境",
            )
            local_password = self._get_local_mysql_password(config)
            if not local_password:
                raise RuntimeError("未配置本地 MySQL 密码")
            remote_password = await self._get_remote_mysql_password(config)
            total = max(len(request.databases), 1)
            for index, database in enumerate(request.databases):
                self._update_task(
                    task_id,
                    current_database=database,
                    message=f"正在同步 {database} ({index + 1}/{total})",
                )
                if self._tasks[task_id]["direction"] == "upload":
                    await self._upload_database(
                        task_id=task_id,
                        config=config,
                        request=request,
                        database=database,
                        local_password=local_password,
                        remote_password=remote_password,
                        task_tmp_dir=task_tmp_dir,
                    )
                else:
                    await self._download_database(
                        task_id=task_id,
                        config=config,
                        request=request,
                        database=database,
                        local_password=local_password,
                        remote_password=remote_password,
                        task_tmp_dir=task_tmp_dir,
                    )
                completed = list(self._tasks[task_id].get("completed_databases", []))
                if database not in completed:
                    completed.append(database)
                overall_pct = int(((index + 1) / total) * 100)
                self._update_task(
                    task_id,
                    completed_databases=completed,
                    progress_pct=min(overall_pct, 99),
                    message=f"{database} 同步完成",
                )

            duration = round(asyncio.get_running_loop().time() - started_monotonic, 2)
            self._update_task(
                task_id,
                status="completed",
                stage="done",
                progress_pct=100,
                message="同步完成",
                finished_at=self._now_iso(),
                duration_seconds=duration,
                error=None,
            )
            await self._append_history(self._tasks[task_id])
        except Exception as exc:
            duration = round(asyncio.get_running_loop().time() - started_monotonic, 2)
            self._update_task(
                task_id,
                status="failed",
                stage="failed",
                progress_pct=min(int(self._tasks[task_id].get("progress_pct", 0)), 100),
                message=f"同步失败: {exc}",
                finished_at=self._now_iso(),
                duration_seconds=duration,
                error=str(exc),
            )
            await self._append_history(self._tasks[task_id])
        finally:
            shutil.rmtree(task_tmp_dir, ignore_errors=True)

    async def _upload_database(
        self,
        *,
        task_id: str,
        config: SyncConfig,
        request: SyncRequest,
        database: str,
        local_password: str,
        remote_password: str,
        task_tmp_dir: Path,
    ) -> None:
        suffix = ".sql.gz" if request.compress else ".sql"
        local_dump_path = task_tmp_dir / f"{database}{suffix}"
        remote_dump_path = f"/tmp/backtrader_sync_{task_id}_{database}{suffix}"
        self._update_task(task_id, stage="dumping", progress_pct=20, message=f"正在导出本地数据库 {database}")
        await self._dump_local_database(database, local_dump_path, request, config, local_password)
        self._update_task(task_id, stage="transferring", progress_pct=55, message=f"正在上传 {database} 到远程服务器")
        await self._scp_upload(config, local_dump_path, remote_dump_path)
        self._update_task(task_id, stage="importing", progress_pct=80, message=f"正在导入远程数据库 {database}")
        await self._import_remote_database(config, database, remote_dump_path, request, remote_password)
        self._update_task(task_id, stage="verifying", progress_pct=95, message=f"正在校验远程数据库 {database}")
        await self._query_remote_database_info(config, [database])

    async def _download_database(
        self,
        *,
        task_id: str,
        config: SyncConfig,
        request: SyncRequest,
        database: str,
        local_password: str,
        remote_password: str,
        task_tmp_dir: Path,
    ) -> None:
        suffix = ".sql.gz" if request.compress else ".sql"
        local_dump_path = task_tmp_dir / f"{database}{suffix}"
        remote_dump_path = f"/tmp/backtrader_sync_{task_id}_{database}{suffix}"
        self._update_task(task_id, stage="dumping", progress_pct=20, message=f"正在导出远程数据库 {database}")
        await self._dump_remote_database(config, database, remote_dump_path, request, remote_password)
        self._update_task(task_id, stage="transferring", progress_pct=55, message=f"正在下载 {database} 到本地")
        await self._scp_download(config, remote_dump_path, local_dump_path)
        self._update_task(task_id, stage="importing", progress_pct=80, message=f"正在导入本地数据库 {database}")
        await self._import_local_database(database, local_dump_path, request, config, local_password)
        self._update_task(task_id, stage="verifying", progress_pct=95, message=f"正在校验本地数据库 {database}")
        await self._query_local_database_info([database])
        try:
            await self._run_ssh(config, f"rm -f {shlex.quote(remote_dump_path)}", timeout=self._connect_timeout)
        except Exception:
            pass

    async def _dump_local_database(
        self,
        database: str,
        output_path: Path,
        request: SyncRequest,
        config: SyncConfig,
        local_password: str,
    ) -> None:
        cmd = self._compose_dump_command(
            self._build_local_mysqldump_args(config, database, request.sync_mode, local_password),
            output_path,
            request.compress,
        )
        await self._run_bash(cmd, timeout=self._timeout_seconds)

    async def _dump_remote_database(
        self,
        config: SyncConfig,
        database: str,
        remote_output_path: str,
        request: SyncRequest,
        remote_password: str,
    ) -> None:
        inner = self._build_remote_mysqldump_command(
            config,
            database,
            request.sync_mode,
            remote_password,
        )
        remote_cmd = self._compose_remote_dump_command(config.remote_container, inner, remote_output_path, request.compress)
        await self._run_ssh(config, remote_cmd, timeout=self._timeout_seconds)

    async def _import_local_database(
        self,
        database: str,
        input_path: Path,
        request: SyncRequest,
        config: SyncConfig,
        local_password: str,
    ) -> None:
        if request.sync_mode != "data_only":
            sql = self._build_recreate_database_sql(database)
            await self._run_exec(
                self._build_local_mysql_query_args(config, sql, local_password),
                timeout=self._connect_timeout,
            )
        import_cmd = self._compose_import_command(
            input_path=str(input_path),
            mysql_command=self._join_command(
                self._build_local_mysql_import_args(config, database, local_password)
            ),
            compressed=request.compress,
        )
        await self._run_bash(import_cmd, timeout=self._timeout_seconds)

    async def _import_remote_database(
        self,
        config: SyncConfig,
        database: str,
        remote_input_path: str,
        request: SyncRequest,
        remote_password: str,
    ) -> None:
        steps: list[str] = ["set -euo pipefail"]
        if request.sync_mode != "data_only":
            recreate_sql = self._build_recreate_database_sql(database)
            recreate_inner = self._join_command([
                "sh",
                "-lc",
                self._build_remote_mysql_query_command(config, recreate_sql, remote_password),
            ])
            steps.append(f"docker exec {shlex.quote(config.remote_container)} {recreate_inner}")
        import_inner = self._join_command([
            "sh",
            "-lc",
            self._build_remote_mysql_import_command(config, database, remote_password),
        ])
        cat_command = "gunzip -c" if request.compress else "cat"
        steps.append(
            f"{cat_command} {shlex.quote(remote_input_path)} | docker exec -i {shlex.quote(config.remote_container)} {import_inner}"
        )
        steps.append(f"rm -f {shlex.quote(remote_input_path)}")
        await self._run_ssh(config, "; ".join(steps), timeout=self._timeout_seconds)

    async def _query_local_database_info(self, databases: list[str]) -> dict[str, DatabaseInfo]:
        config = self.get_config()
        password = self._get_local_mysql_password(config)
        if not password:
            raise RuntimeError("未配置本地 MySQL 密码")
        sql = self._build_database_info_sql(databases)
        stdout = await self._run_exec(
            self._build_local_mysql_query_args(config, sql, password),
            timeout=self._connect_timeout,
        )
        return self._parse_database_info(databases, stdout)

    async def _query_remote_database_info(
        self,
        config: SyncConfig,
        databases: list[str],
    ) -> dict[str, DatabaseInfo]:
        password = await self._get_remote_mysql_password(config)
        sql = self._build_database_info_sql(databases)
        remote_cmd = (
            f"docker exec {shlex.quote(config.remote_container)} sh -lc "
            f"{shlex.quote(self._build_remote_mysql_query_command(config, sql, password))}"
        )
        stdout = await self._run_ssh(config, remote_cmd, timeout=self._connect_timeout)
        return self._parse_database_info(databases, stdout)

    async def _scp_upload(self, config: SyncConfig, source: Path, target: str) -> None:
        await self._run_exec(
            self._build_scp_base_args(config) + [str(source), f"{config.remote_user}@{config.remote_host}:{target}"],
            timeout=self._timeout_seconds,
        )

    async def _scp_download(self, config: SyncConfig, source: str, target: Path) -> None:
        await self._run_exec(
            self._build_scp_base_args(config) + [f"{config.remote_user}@{config.remote_host}:{source}", str(target)],
            timeout=self._timeout_seconds,
        )

    async def _get_remote_mysql_password(self, config: SyncConfig) -> str:
        explicit_password = str(config.remote_mysql_password or "").strip()
        if explicit_password:
            return explicit_password
        env_path = f"{config.remote_install_dir.rstrip('/')}/src/backend/.env"
        command = (
            f"if [ ! -f {shlex.quote(env_path)} ]; then "
            f"echo '.env not found: {env_path}' 1>&2; exit 1; "
            "fi; "
            f"sed -n 's/^MYSQL_ROOT_PASSWORD=//p' {shlex.quote(env_path)} | head -n 1"
        )
        stdout = await self._run_ssh(config, command, timeout=self._connect_timeout)
        password = stdout.strip().strip('"').strip("'")
        if not password:
            raise RuntimeError("远程 .env 中未找到 MYSQL_ROOT_PASSWORD")
        return password

    def _get_local_mysql_password(self, config: SyncConfig | None = None) -> str:
        value = (
            getattr(config, "local_mysql_password", "") if config is not None else ""
        ) or (
            os.environ.get("SYNC_LOCAL_MYSQL_PASSWORD")
            or getattr(settings, "SYNC_LOCAL_MYSQL_PASSWORD", "")
            or os.environ.get("LOCAL_MYSQL_PASSWORD")
        )
        return str(value or "").strip()

    def _normalize_config(self, config: SyncConfig) -> SyncConfig:
        payload = config.model_copy(deep=True)
        payload.local_mysql_host = payload.local_mysql_host.strip() or "127.0.0.1"
        payload.local_mysql_port = int(payload.local_mysql_port or 3306)
        payload.local_mysql_user = payload.local_mysql_user.strip() or "root"
        payload.local_mysql_password = str(payload.local_mysql_password or "").strip()
        payload.remote_host = self._normalize_host(payload.remote_host)
        payload.remote_user = payload.remote_user.strip() or "root"
        payload.remote_ssh_key = payload.remote_ssh_key.strip() or "~/.ssh/id_rsa"
        payload.remote_container = payload.remote_container.strip() or "backtrader_mysql"
        payload.remote_install_dir = payload.remote_install_dir.strip() or "/opt/backtrader_web"
        payload.remote_mysql_host = payload.remote_mysql_host.strip() or "127.0.0.1"
        payload.remote_mysql_port = int(payload.remote_mysql_port or 3306)
        payload.remote_mysql_user = payload.remote_mysql_user.strip() or "root"
        payload.remote_mysql_password = str(payload.remote_mysql_password or "").strip()
        payload.sync_databases = [name.strip() for name in payload.sync_databases if name.strip()]
        if not payload.sync_databases:
            payload.sync_databases = ["backtrader_web", "akshare_data"]
        return payload

    def _update_task(self, task_id: str, **changes: Any) -> None:
        current = self._tasks[task_id]
        current.update(changes)
        self._tasks[task_id] = current

    async def _append_history(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            items = self._load_history()
            items.insert(0, payload)
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            self._history_file.write_text(
                json.dumps(items[:200], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _load_history(self) -> list[dict[str, Any]]:
        if not self._history_file.is_file():
            return []
        try:
            payload = json.loads(self._history_file.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _build_database_info_sql(self, databases: list[str]) -> str:
        in_clause = ", ".join(self._quote_sql_string(name) for name in databases)
        return (
            "SELECT TABLE_SCHEMA, "
            "COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) AS size_bytes, "
            "COUNT(*) AS table_count "
            "FROM information_schema.TABLES "
            f"WHERE TABLE_SCHEMA IN ({in_clause}) "
            "GROUP BY TABLE_SCHEMA"
        )

    def _build_recreate_database_sql(self, database: str) -> str:
        identifier = self._quote_identifier(database)
        return (
            f"DROP DATABASE IF EXISTS {identifier}; "
            f"CREATE DATABASE {identifier} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )

    def _build_local_mysqldump_args(
        self,
        config: SyncConfig,
        database: str,
        sync_mode: str,
        password: str,
    ) -> list[str]:
        args = [
            "mysqldump",
            "--single-transaction",
            "--skip-lock-tables",
            "--set-gtid-purged=OFF",
            "--default-character-set=utf8mb4",
            "--routines",
            "--triggers",
            "--events",
            "-h",
            config.local_mysql_host,
            "-P",
            str(config.local_mysql_port),
            "-u",
            config.local_mysql_user,
            f"-p{password}",
        ]
        if sync_mode == "schema_only":
            args.append("--no-data")
        elif sync_mode == "data_only":
            args.extend(["--no-create-info", "--replace"])
        args.append(database)
        return args

    def _build_local_mysql_query_args(
        self,
        config: SyncConfig,
        sql: str,
        password: str,
    ) -> list[str]:
        return [
            "mysql",
            "-h",
            config.local_mysql_host,
            "-P",
            str(config.local_mysql_port),
            "-u",
            config.local_mysql_user,
            f"-p{password}",
            "-N",
            "-B",
            "-e",
            sql,
        ]

    def _build_local_mysql_import_args(
        self,
        config: SyncConfig,
        database: str,
        password: str,
    ) -> list[str]:
        return [
            "mysql",
            "-h",
            config.local_mysql_host,
            "-P",
            str(config.local_mysql_port),
            "-u",
            config.local_mysql_user,
            f"-p{password}",
            database,
        ]

    def _build_remote_mysqldump_command(
        self,
        config: SyncConfig,
        database: str,
        sync_mode: str,
        password: str,
    ) -> str:
        args = [
            "mysqldump",
            "--single-transaction",
            "--skip-lock-tables",
            "--set-gtid-purged=OFF",
            "--default-character-set=utf8mb4",
            "--routines",
            "--triggers",
            "--events",
            "-h",
            config.remote_mysql_host,
            "-P",
            str(config.remote_mysql_port),
            "-u",
            config.remote_mysql_user,
        ]
        if sync_mode == "schema_only":
            args.append("--no-data")
        elif sync_mode == "data_only":
            args.extend(["--no-create-info", "--replace"])
        args.append(database)
        return f"MYSQL_PWD={shlex.quote(password)} {self._join_command(args)}"

    def _build_remote_mysql_query_command(
        self,
        config: SyncConfig,
        sql: str,
        password: str,
    ) -> str:
        args = [
            "mysql",
            "-h",
            config.remote_mysql_host,
            "-P",
            str(config.remote_mysql_port),
            "-u",
            config.remote_mysql_user,
            "-N",
            "-B",
            "-e",
            sql,
        ]
        return f"MYSQL_PWD={shlex.quote(password)} {self._join_command(args)}"

    def _build_remote_mysql_import_command(
        self,
        config: SyncConfig,
        database: str,
        password: str,
    ) -> str:
        args = [
            "mysql",
            "-h",
            config.remote_mysql_host,
            "-P",
            str(config.remote_mysql_port),
            "-u",
            config.remote_mysql_user,
            database,
        ]
        return f"MYSQL_PWD={shlex.quote(password)} {self._join_command(args)}"

    def _compose_dump_command(self, dump_args: list[str], output_path: Path, compress: bool) -> str:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if compress:
            return f"set -o pipefail; {self._join_command(dump_args)} | gzip -c > {shlex.quote(str(output_path))}"
        return f"set -o pipefail; {self._join_command(dump_args)} > {shlex.quote(str(output_path))}"

    def _compose_remote_dump_command(
        self,
        container: str,
        inner_dump_command: str,
        output_path: str,
        compress: bool,
    ) -> str:
        pipe_target = "gzip -c" if compress else "cat"
        return (
            "set -o pipefail; "
            f"docker exec {shlex.quote(container)} sh -lc {shlex.quote(inner_dump_command)} "
            f"| {pipe_target} > {shlex.quote(output_path)}"
        )

    def _compose_import_command(self, *, input_path: str, mysql_command: str, compressed: bool) -> str:
        cat_command = "gunzip -c" if compressed else "cat"
        return f"set -o pipefail; {cat_command} {shlex.quote(input_path)} | {mysql_command}"

    def _build_ssh_base_args(self, config: SyncConfig) -> list[str]:
        key_path = str(Path(config.remote_ssh_key).expanduser())
        return [
            "ssh",
            "-i",
            key_path,
            "-o",
            f"ConnectTimeout={self._connect_timeout}",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{config.remote_user}@{config.remote_host}",
        ]

    def _build_scp_base_args(self, config: SyncConfig) -> list[str]:
        key_path = str(Path(config.remote_ssh_key).expanduser())
        return [
            "scp",
            "-i",
            key_path,
            "-o",
            f"ConnectTimeout={self._connect_timeout}",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]

    async def _run_ssh(self, config: SyncConfig, command: str, timeout: int) -> str:
        remote_command = self._join_command(["bash", "-lc", command])
        return await self._run_exec(self._build_ssh_base_args(config) + [remote_command], timeout=timeout)

    async def _run_bash(self, command: str, timeout: int) -> str:
        return await self._run_exec(["bash", "-lc", command], timeout=timeout)

    async def _run_exec(self, args: list[str], timeout: int) -> str:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"命令执行超时（>{timeout}s）: {self._join_command(args)}") from exc
        if proc.returncode != 0:
            error = (stderr or stdout).decode("utf-8", errors="ignore").strip()
            raise RuntimeError(error or f"命令执行失败: {self._join_command(args)}")
        return stdout.decode("utf-8", errors="ignore").strip()

    def _parse_database_info(self, names: list[str], stdout: str) -> dict[str, DatabaseInfo]:
        result = {name: self._empty_database_info(name) for name in names}
        for line in stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            try:
                size_bytes = int(float(parts[1] or 0))
            except ValueError:
                size_bytes = 0
            try:
                table_count = int(float(parts[2] or 0))
            except ValueError:
                table_count = 0
            result[name] = DatabaseInfo(
                name=name,
                size_bytes=size_bytes,
                size_display=self._format_bytes(size_bytes),
                table_count=table_count,
                exists=True,
            )
        return result

    def _empty_database_info(self, name: str) -> DatabaseInfo:
        return DatabaseInfo(name=name, size_bytes=0, size_display="0 B", table_count=0, exists=False)

    def _join_command(self, args: list[str]) -> str:
        return " ".join(shlex.quote(arg) for arg in args)

    def _quote_sql_string(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _quote_identifier(self, value: str) -> str:
        return "`" + value.replace("`", "``") + "`"

    def _normalize_host(self, value: str) -> str:
        host = str(value or "").strip()
        if not host:
            return ""
        if host.startswith("http://") or host.startswith("https://"):
            parsed = urlparse(host)
            return parsed.hostname or host
        return host

    def _format_bytes(self, value: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(max(value, 0))
        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{int(value)} B"

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


@lru_cache
def get_sync_service() -> SyncService:
    return SyncService()
