from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import uuid
from collections import Counter
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
        self._incremental_key_batch_size = max(
            int(os.environ.get("SYNC_INCREMENTAL_KEY_BATCH_SIZE", "10000")),
            1,
        )
        self._connect_timeout = min(
            max(int(os.environ.get("SYNC_CONNECT_TIMEOUT_SECONDS", "10")), 5),
            60,
        )

    def get_config(self) -> SyncConfig:
        local_defaults = self._get_local_mysql_defaults()
        defaults = SyncConfig(
            local_mysql_host=str(local_defaults["host"]),
            local_mysql_port=int(local_defaults["port"]),
            local_mysql_user=str(local_defaults["user"]),
            local_mysql_password=str(local_defaults["password"]),
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

        required_tools = ["mysql", "mysqldump", "gzip"]
        if not self._is_direct_mode(config):
            required_tools.extend(["ssh", "scp"])
        missing_tools = [name for name in required_tools if shutil.which(name) is None]
        checks["local_tools"] = not missing_tools
        details["local_tools"] = (
            "依赖完整" if not missing_tools else f"缺少命令: {', '.join(missing_tools)}"
        )

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

        if self._is_direct_mode(config):
            remote_password = await self._test_direct_remote_mysql(config, checks, details)
            if remote_password is not None:
                details["remote_env"] = "已使用页面填写的远程 MySQL 密码"
        else:
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

    async def _test_direct_remote_mysql(
        self,
        config: SyncConfig,
        checks: dict[str, bool],
        details: dict[str, str],
    ) -> str | None:
        if not config.remote_mysql_host.strip():
            checks["remote_mysql"] = False
            details["remote_mysql"] = "未配置远程 MySQL 主机"
            checks["remote_env"] = False
            details["remote_env"] = "直连模式必须填写远程 MySQL 密码"
            return None
        try:
            password = await self._get_remote_mysql_password(config)
        except Exception as exc:
            checks["remote_mysql"] = False
            details["remote_mysql"] = "缺少可用的远程 MySQL 凭据"
            checks["remote_env"] = False
            details["remote_env"] = str(exc)
            return None
        checks["remote_env"] = True
        try:
            await self._run_exec(
                self._build_remote_mysql_query_args(config, "SELECT 1", password),
                timeout=self._connect_timeout,
            )
            checks["remote_mysql"] = True
            details["remote_mysql"] = "远程 MySQL 直连成功"
        except Exception as exc:
            checks["remote_mysql"] = False
            details["remote_mysql"] = str(exc)
        return password

    async def list_databases(self, config: SyncConfig) -> list[DatabaseSyncInfo]:
        config = self._normalize_config(config)
        try:
            local = await self._query_local_database_info(config.sync_databases)
        except Exception:
            local = {name: self._empty_database_info(name) for name in config.sync_databases}
        remote_available = (
            config.remote_mysql_host.strip()
            if self._is_direct_mode(config)
            else config.remote_host.strip()
        )
        if remote_available:
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
            raise ValueError("同步会保留目标数据库中已存在的数据，请确认后再执行")

        config = self.get_config()
        config = self._normalize_config(config)
        if self._is_direct_mode(config):
            if not config.remote_mysql_host.strip():
                raise ValueError("请先保存远程 MySQL 配置")
        elif not config.remote_host.strip():
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
            self._update_task(
                task_id,
                message=f"正在准备同步，共 {len(request.databases)} 个数据库，表级并发数 {config.sync_parallel_workers}",
            )
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
        if self._is_direct_mode(config):
            tables = await self._list_local_tables(config, database, local_password)
            if request.sync_mode != "data_only":
                self._update_task(
                    task_id,
                    stage="dumping",
                    progress_pct=20,
                    message=f"正在准备同步数据库结构 {database}",
                )
                await self._import_remote_database_direct(
                    task_id=task_id,
                    config=config,
                    database=database,
                    input_path=None,
                    request=request,
                    remote_password=remote_password,
                    schema_only=True,
                    local_password=local_password,
                )
            if request.sync_mode != "schema_only":
                await self._sync_local_tables_to_remote_direct(
                    task_id=task_id,
                    config=config,
                    database=database,
                    tables=tables,
                    local_password=local_password,
                    remote_password=remote_password,
                )
        else:
            self._update_task(
                task_id, stage="dumping", progress_pct=20, message=f"正在导出本地数据库 {database}"
            )
            await self._dump_local_database(
                database, local_dump_path, request, config, local_password
            )
            self._update_task(
                task_id,
                stage="transferring",
                progress_pct=55,
                message=f"正在准备同步 {database} 到远程数据库",
            )
            self._update_task(
                task_id,
                stage="importing",
                progress_pct=80,
                message=f"正在导入远程数据库 {database}",
            )
            await self._scp_upload(
                config, local_dump_path, f"/tmp/backtrader_sync_{task_id}_{database}{suffix}"
            )
            await self._import_remote_database(
                config,
                database,
                f"/tmp/backtrader_sync_{task_id}_{database}{suffix}",
                request,
                remote_password,
            )
        self._update_task(
            task_id, stage="verifying", progress_pct=95, message=f"正在校验远程数据库 {database}"
        )
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
        if self._is_direct_mode(config):
            tables = await self._list_remote_tables_direct(config, database, remote_password)
            if request.sync_mode != "data_only":
                self._update_task(
                    task_id,
                    stage="dumping",
                    progress_pct=20,
                    message=f"正在准备同步数据库结构 {database}",
                )
                await self._import_local_database_direct_schema(
                    task_id=task_id,
                    config=config,
                    database=database,
                    request=request,
                    local_password=local_password,
                    remote_password=remote_password,
                )
            if request.sync_mode != "schema_only":
                await self._sync_remote_tables_to_local_direct(
                    task_id=task_id,
                    config=config,
                    database=database,
                    tables=tables,
                    local_password=local_password,
                    remote_password=remote_password,
                )
        else:
            self._update_task(
                task_id, stage="dumping", progress_pct=20, message=f"正在导出远程数据库 {database}"
            )
            await self._dump_remote_database(
                config,
                database,
                f"/tmp/backtrader_sync_{task_id}_{database}{suffix}",
                request,
                remote_password,
            )
            self._update_task(
                task_id,
                stage="transferring",
                progress_pct=55,
                message=f"正在下载 {database} 到本地",
            )
            await self._scp_download(
                config, f"/tmp/backtrader_sync_{task_id}_{database}{suffix}", local_dump_path
            )
            self._update_task(
                task_id,
                stage="importing",
                progress_pct=80,
                message=f"正在导入本地数据库 {database}",
            )
            await self._import_local_database(
                database, local_dump_path, request, config, local_password
            )
        self._update_task(
            task_id, stage="verifying", progress_pct=95, message=f"正在校验本地数据库 {database}"
        )
        await self._query_local_database_info([database])
        if not self._is_direct_mode(config):
            try:
                await self._run_ssh(
                    config,
                    f"rm -f {shlex.quote(f'/tmp/backtrader_sync_{task_id}_{database}{suffix}')}",
                    timeout=self._connect_timeout,
                )
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
        remote_cmd = self._compose_remote_dump_command(
            config.remote_container, inner, remote_output_path, request.compress
        )
        await self._run_ssh(config, remote_cmd, timeout=self._timeout_seconds)

    async def _dump_remote_database_direct(
        self,
        config: SyncConfig,
        database: str,
        output_path: Path,
        request: SyncRequest,
        remote_password: str,
    ) -> None:
        cmd = self._compose_dump_command(
            self._build_remote_mysqldump_args(config, database, request.sync_mode, remote_password),
            output_path,
            request.compress,
        )
        await self._run_bash(cmd, timeout=self._timeout_seconds)

    async def _import_local_database(
        self,
        database: str,
        input_path: Path,
        request: SyncRequest,
        config: SyncConfig,
        local_password: str,
    ) -> None:
        if request.sync_mode != "data_only":
            sql = self._build_ensure_database_sql(database)
            await self._run_exec(
                self._build_local_mysql_query_args(config, sql, local_password),
                timeout=self._timeout_seconds,
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
            recreate_sql = self._build_ensure_database_sql(database)
            recreate_inner = self._join_command(
                [
                    "sh",
                    "-lc",
                    self._build_remote_mysql_query_command(config, recreate_sql, remote_password),
                ]
            )
            steps.append(f"docker exec {shlex.quote(config.remote_container)} {recreate_inner}")
        import_inner = self._join_command(
            [
                "sh",
                "-lc",
                self._build_remote_mysql_import_command(config, database, remote_password),
            ]
        )
        cat_command = "gunzip -c" if request.compress else "cat"
        steps.append(
            f"{cat_command} {shlex.quote(remote_input_path)} | docker exec -i {shlex.quote(config.remote_container)} {import_inner}"
        )
        steps.append(f"rm -f {shlex.quote(remote_input_path)}")
        await self._run_ssh(config, "; ".join(steps), timeout=self._timeout_seconds)

    async def _import_remote_database_direct(
        self,
        task_id: str | None,
        config: SyncConfig,
        database: str,
        input_path: Path | None,
        request: SyncRequest,
        remote_password: str,
        schema_only: bool = False,
        local_password: str | None = None,
    ) -> None:
        source_summary: dict[str, Any] | None = None
        target_summary: dict[str, Any] | None = None
        if request.sync_mode != "data_only":
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="dumping",
                    progress_pct=22,
                    message=f"正在查询远程数据库 {database} 是否已存在",
                )
            exists = await self._remote_database_exists(config, database, remote_password)
            if exists:
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=24,
                        message=f"远程数据库 {database} 已存在，跳过创建",
                    )
                if schema_only:
                    if local_password is None:
                        raise RuntimeError("缺少本地 MySQL 密码，无法比对数据库结构")
                    if task_id is not None:
                        self._update_task(
                            task_id,
                            stage="dumping",
                            progress_pct=28,
                            message=f"正在读取本地数据库结构摘要 {database}",
                        )
                    source_summary = self._parse_schema_summary(
                        await self._export_local_schema_dump(config, database, local_password)
                    )
                    if task_id is not None:
                        self._update_task(
                            task_id,
                            stage="dumping",
                            progress_pct=29,
                            message=f"正在读取远程数据库结构摘要 {database}",
                        )
                    target_summary = self._parse_schema_summary(
                        await self._export_remote_schema_dump(config, database, remote_password)
                    )
                    if task_id is not None:
                        self._update_task(
                            task_id,
                            stage="dumping",
                            progress_pct=30,
                            message=f"正在比较本地与远程数据库结构差异 {database}",
                        )
            else:
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=26,
                        message=f"远程数据库 {database} 不存在，正在创建",
                    )
                sql = self._build_ensure_database_sql(database)
                await self._run_exec(
                    self._build_remote_mysql_query_args(config, sql, remote_password),
                    timeout=self._timeout_seconds,
                )
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=28,
                        message=f"远程数据库 {database} 创建完成，准备导出本地结构",
                    )
        if schema_only:
            if local_password is None:
                raise RuntimeError("缺少本地 MySQL 密码，无法同步数据库结构")
            if source_summary is not None and target_summary is not None:
                delta = self._build_schema_delta(source_summary, target_summary)
                if self._schema_delta_is_empty(delta):
                    if task_id is not None:
                        self._update_task(
                            task_id,
                            stage="importing",
                            progress_pct=42,
                            message=f"数据库结构 {database} 已一致，跳过远程导入，准备开始同步数据",
                        )
                    return
                stats = await self._apply_schema_delta_local_to_remote(
                    task_id=task_id,
                    config=config,
                    database=database,
                    local_password=local_password,
                    remote_password=remote_password,
                    source_summary=source_summary,
                    target_summary=target_summary,
                )
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="importing",
                        progress_pct=42,
                        message=(
                            f"数据库结构 {database} 已增量同步：新增表 {stats['tables']} 个，"
                            f"字段变更 {stats['columns']} 项，索引变更 {stats['indexes']} 项，视图变更 {stats['views']} 项"
                        ),
                    )
                return
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="dumping",
                    progress_pct=30,
                    message=f"正在导出本地数据库结构 {database}",
                )
            stream_cmd = self._compose_stream_command(
                self._join_command(
                    self._build_local_mysqldump_args(
                        config, database, "schema_only", local_password
                    )
                ),
                self._join_command(
                    self._build_remote_mysql_import_args(
                        config,
                        database,
                        remote_password,
                        force=True,
                    )
                ),
            )
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=38,
                    message=f"正在导入数据库结构到远程库 {database}",
                )
            await self._run_bash(stream_cmd, timeout=self._timeout_seconds)
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=42,
                    message=f"数据库结构 {database} 已同步到远程库，准备开始同步数据",
                )
            return
        if input_path is None:
            raise RuntimeError("缺少导入文件，无法同步远程数据库")
        import_cmd = self._compose_import_command(
            input_path=str(input_path),
            mysql_command=self._join_command(
                self._build_remote_mysql_import_args(config, database, remote_password)
            ),
            compressed=request.compress,
        )
        await self._run_bash(import_cmd, timeout=self._timeout_seconds)

    async def _import_local_database_direct_schema(
        self,
        task_id: str | None,
        config: SyncConfig,
        database: str,
        request: SyncRequest,
        local_password: str,
        remote_password: str,
    ) -> None:
        source_summary: dict[str, Any] | None = None
        target_summary: dict[str, Any] | None = None
        if request.sync_mode != "data_only":
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="dumping",
                    progress_pct=22,
                    message=f"正在查询本地数据库 {database} 是否已存在",
                )
            exists = await self._local_database_exists(config, database, local_password)
            if exists:
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=24,
                        message=f"本地数据库 {database} 已存在，跳过创建",
                    )
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=28,
                        message=f"正在读取远程数据库结构摘要 {database}",
                    )
                source_summary = self._parse_schema_summary(
                    await self._export_remote_schema_dump(config, database, remote_password)
                )
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=29,
                        message=f"正在读取本地数据库结构摘要 {database}",
                    )
                target_summary = self._parse_schema_summary(
                    await self._export_local_schema_dump(config, database, local_password)
                )
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=30,
                        message=f"正在比较远程与本地数据库结构差异 {database}",
                    )
            else:
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=26,
                        message=f"本地数据库 {database} 不存在，正在创建",
                    )
                sql = self._build_ensure_database_sql(database)
                await self._run_exec(
                    self._build_local_mysql_query_args(config, sql, local_password),
                    timeout=self._timeout_seconds,
                )
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="dumping",
                        progress_pct=28,
                        message=f"本地数据库 {database} 创建完成，准备导出远程结构",
                    )
        if source_summary is not None and target_summary is not None:
            delta = self._build_schema_delta(source_summary, target_summary)
            if self._schema_delta_is_empty(delta):
                if task_id is not None:
                    self._update_task(
                        task_id,
                        stage="importing",
                        progress_pct=42,
                        message=f"数据库结构 {database} 已一致，跳过本地导入，准备开始同步数据",
                    )
                return
            stats = await self._apply_schema_delta_remote_to_local(
                task_id=task_id,
                config=config,
                database=database,
                local_password=local_password,
                remote_password=remote_password,
                source_summary=source_summary,
                target_summary=target_summary,
            )
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=42,
                    message=(
                        f"数据库结构 {database} 已增量同步：新增表 {stats['tables']} 个，"
                        f"字段变更 {stats['columns']} 项，索引变更 {stats['indexes']} 项，视图变更 {stats['views']} 项"
                    ),
                )
            return
        if task_id is not None:
            self._update_task(
                task_id,
                stage="dumping",
                progress_pct=30,
                message=f"正在导出远程数据库结构 {database}",
            )
        stream_cmd = self._compose_stream_command(
            self._join_command(
                self._build_remote_mysqldump_args(config, database, "schema_only", remote_password)
            ),
            self._join_command(
                self._build_local_mysql_import_args(
                    config,
                    database,
                    local_password,
                    force=True,
                )
            ),
        )
        if task_id is not None:
            self._update_task(
                task_id,
                stage="importing",
                progress_pct=38,
                message=f"正在导入数据库结构到本地库 {database}",
            )
        await self._run_bash(stream_cmd, timeout=self._timeout_seconds)
        if task_id is not None:
            self._update_task(
                task_id,
                stage="importing",
                progress_pct=42,
                message=f"数据库结构 {database} 已同步到本地库，准备开始同步数据",
            )

    async def _sync_local_tables_to_remote_direct(
        self,
        *,
        task_id: str,
        config: SyncConfig,
        database: str,
        tables: list[str],
        local_password: str,
        remote_password: str,
    ) -> None:
        if not tables:
            self._update_task(
                task_id,
                stage="importing",
                progress_pct=85,
                message=f"数据库 {database} 没有可同步的数据表",
            )
            return
        await self._run_parallel_table_sync(
            task_id=task_id,
            config=config,
            database=database,
            tables=tables,
            worker_count=config.sync_parallel_workers,
            sync_table=self._sync_single_local_table_to_remote,
            direction_label="上传",
            local_password=local_password,
            remote_password=remote_password,
        )

    async def _sync_remote_tables_to_local_direct(
        self,
        *,
        task_id: str,
        config: SyncConfig,
        database: str,
        tables: list[str],
        local_password: str,
        remote_password: str,
    ) -> None:
        if not tables:
            self._update_task(
                task_id,
                stage="importing",
                progress_pct=85,
                message=f"数据库 {database} 没有可同步的数据表",
            )
            return
        await self._run_parallel_table_sync(
            task_id=task_id,
            config=config,
            database=database,
            tables=tables,
            worker_count=config.sync_parallel_workers,
            sync_table=self._sync_single_remote_table_to_local,
            direction_label="拉取",
            local_password=local_password,
            remote_password=remote_password,
        )

    async def _run_parallel_table_sync(
        self,
        *,
        task_id: str,
        config: SyncConfig,
        database: str,
        tables: list[str],
        worker_count: int,
        sync_table: Any,
        direction_label: str,
        local_password: str,
        remote_password: str,
    ) -> None:
        total = max(len(tables), 1)
        semaphore = asyncio.Semaphore(max(worker_count, 1))
        completed = 0
        progress_lock = asyncio.Lock()

        async def run_single(index: int, table: str) -> None:
            nonlocal completed
            progress = 45 + int(((index + 1) / total) * 45)
            async with semaphore:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=min(progress, 90),
                    message=f"正在{direction_label}数据表 {database}.{table} ({index + 1}/{total})",
                )
                await sync_table(
                    task_id=task_id,
                    index=index,
                    total=total,
                    direction_label=direction_label,
                    config=config,
                    database=database,
                    table=table,
                    local_password=local_password,
                    remote_password=remote_password,
                )
                async with progress_lock:
                    completed += 1
                    done_progress = 45 + int((completed / total) * 45)
                    self._update_task(
                        task_id,
                        stage="importing",
                        progress_pct=min(done_progress, 90),
                        message=f"已完成 {completed}/{total} 张表同步，最近完成 {database}.{table}",
                    )

        await asyncio.gather(*(run_single(index, table) for index, table in enumerate(tables)))

    def _build_table_step_progress(
        self,
        *,
        index: int,
        total: int,
        step: int,
        step_count: int,
    ) -> int:
        table_start = 45 + int((index / max(total, 1)) * 45)
        table_end = 45 + int(((index + 1) / max(total, 1)) * 45)
        span = max(table_end - table_start, 1)
        normalized_step = min(max(step, 0), max(step_count, 1))
        return min(table_start + int((normalized_step / max(step_count, 1)) * span), 90)

    def _update_table_substep_task(
        self,
        *,
        task_id: str,
        direction_label: str,
        database: str,
        table: str,
        index: int,
        total: int,
        step: int,
        step_count: int,
        detail: str,
    ) -> None:
        self._update_task(
            task_id,
            stage="importing",
            progress_pct=self._build_table_step_progress(
                index=index,
                total=total,
                step=step,
                step_count=step_count,
            ),
            message=f"正在{direction_label}数据表 {database}.{table} ({index + 1}/{total})：{detail}",
        )

    async def _sync_single_local_table_to_remote(
        self,
        *,
        task_id: str,
        index: int,
        total: int,
        direction_label: str,
        config: SyncConfig,
        database: str,
        table: str,
        local_password: str,
        remote_password: str,
    ) -> None:
        step_count = 5
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=1,
            step_count=step_count,
            detail="正在识别增量比对键",
        )
        key_columns, use_row_hash = await self._get_local_incremental_key_columns(
            config,
            database,
            table,
            local_password,
        )
        if use_row_hash:
            self._update_table_substep_task(
                task_id=task_id,
                direction_label=direction_label,
                database=database,
                table=table,
                index=index,
                total=total,
                step=1,
                step_count=step_count,
                detail=f"未找到主键/唯一键，已切换为全行哈希比对（{len(key_columns)} 列）",
            )
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=2,
            step_count=step_count,
            detail=(
                f"正在读取本地行签名集合（基于 {len(key_columns)} 列）"
                if use_row_hash
                else f"正在读取本地键集合（{len(key_columns)} 列）"
            ),
        )
        source_keys = await self._fetch_local_key_rows(
            config,
            database,
            table,
            key_columns,
            local_password,
            use_row_hash=use_row_hash,
        )
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=3,
            step_count=step_count,
            detail=(
                f"正在读取远程行签名集合（基于 {len(key_columns)} 列）"
                if use_row_hash
                else f"正在读取远程键集合（{len(key_columns)} 列）"
            ),
        )
        target_keys = await self._fetch_remote_key_rows(
            config,
            database,
            table,
            key_columns,
            remote_password,
            use_row_hash=use_row_hash,
        )
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=4,
            step_count=step_count,
            detail="正在计算缺失数据",
        )
        missing_keys = self._build_missing_rows(source_keys, target_keys)
        if not missing_keys:
            return
        batch_count = len(self._chunk_keys(missing_keys))
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=5,
            step_count=step_count,
            detail=(
                f"正在写入缺失数据（{len(missing_keys)} 条行签名，{batch_count} 批）"
                if use_row_hash
                else f"正在写入缺失数据（{len(missing_keys)} 条键，{batch_count} 批）"
            ),
        )
        await self._stream_local_missing_rows_to_remote(
            config,
            database,
            table,
            key_columns,
            missing_keys,
            local_password,
            remote_password,
            use_row_hash=use_row_hash,
        )

    async def _sync_single_remote_table_to_local(
        self,
        *,
        task_id: str,
        index: int,
        total: int,
        direction_label: str,
        config: SyncConfig,
        database: str,
        table: str,
        local_password: str,
        remote_password: str,
    ) -> None:
        step_count = 5
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=1,
            step_count=step_count,
            detail="正在识别增量比对键",
        )
        key_columns, use_row_hash = await self._get_remote_incremental_key_columns(
            config,
            database,
            table,
            remote_password,
        )
        if use_row_hash:
            self._update_table_substep_task(
                task_id=task_id,
                direction_label=direction_label,
                database=database,
                table=table,
                index=index,
                total=total,
                step=1,
                step_count=step_count,
                detail=f"未找到主键/唯一键，已切换为全行哈希比对（{len(key_columns)} 列）",
            )
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=2,
            step_count=step_count,
            detail=(
                f"正在读取远程行签名集合（基于 {len(key_columns)} 列）"
                if use_row_hash
                else f"正在读取远程键集合（{len(key_columns)} 列）"
            ),
        )
        source_keys = await self._fetch_remote_key_rows(
            config,
            database,
            table,
            key_columns,
            remote_password,
            use_row_hash=use_row_hash,
        )
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=3,
            step_count=step_count,
            detail=(
                f"正在读取本地行签名集合（基于 {len(key_columns)} 列）"
                if use_row_hash
                else f"正在读取本地键集合（{len(key_columns)} 列）"
            ),
        )
        target_keys = await self._fetch_local_key_rows(
            config,
            database,
            table,
            key_columns,
            local_password,
            use_row_hash=use_row_hash,
        )
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=4,
            step_count=step_count,
            detail="正在计算缺失数据",
        )
        missing_keys = self._build_missing_rows(source_keys, target_keys)
        if not missing_keys:
            return
        batch_count = len(self._chunk_keys(missing_keys))
        self._update_table_substep_task(
            task_id=task_id,
            direction_label=direction_label,
            database=database,
            table=table,
            index=index,
            total=total,
            step=5,
            step_count=step_count,
            detail=(
                f"正在写入缺失数据（{len(missing_keys)} 条行签名，{batch_count} 批）"
                if use_row_hash
                else f"正在写入缺失数据（{len(missing_keys)} 条键，{batch_count} 批）"
            ),
        )
        await self._stream_remote_missing_rows_to_local(
            config,
            database,
            table,
            key_columns,
            missing_keys,
            local_password,
            remote_password,
            use_row_hash=use_row_hash,
        )

    async def _list_local_tables(
        self,
        config: SyncConfig,
        database: str,
        password: str,
    ) -> list[str]:
        sql = self._build_table_names_sql(database)
        stdout = await self._run_exec(
            self._build_local_mysql_query_args(config, sql, password),
            timeout=self._connect_timeout,
        )
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    async def _list_remote_tables_direct(
        self,
        config: SyncConfig,
        database: str,
        password: str,
    ) -> list[str]:
        sql = self._build_table_names_sql(database)
        stdout = await self._run_exec(
            self._build_remote_mysql_query_args(config, sql, password),
            timeout=self._connect_timeout,
        )
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    async def _get_local_incremental_key_columns(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        password: str,
    ) -> tuple[tuple[str, ...], bool]:
        sql = self._build_index_metadata_sql(database, table)
        stdout = await self._run_exec(
            self._build_local_mysql_query_args(config, sql, password),
            timeout=self._connect_timeout,
        )
        columns = self._select_incremental_key_columns(stdout, database, table)
        if columns:
            return columns, False
        return await self._get_local_table_columns(config, database, table, password), True

    async def _get_remote_incremental_key_columns(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        password: str,
    ) -> tuple[tuple[str, ...], bool]:
        sql = self._build_index_metadata_sql(database, table)
        stdout = await self._run_exec(
            self._build_remote_mysql_query_args(config, sql, password),
            timeout=self._connect_timeout,
        )
        columns = self._select_incremental_key_columns(stdout, database, table)
        if columns:
            return columns, False
        return await self._get_remote_table_columns(config, database, table, password), True

    async def _get_local_table_columns(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        password: str,
    ) -> tuple[str, ...]:
        sql = self._build_table_columns_sql(database, table)
        stdout = await self._run_exec(
            self._build_local_mysql_query_args(config, sql, password),
            timeout=self._connect_timeout,
        )
        return self._parse_table_columns(stdout, database, table)

    async def _get_remote_table_columns(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        password: str,
    ) -> tuple[str, ...]:
        sql = self._build_table_columns_sql(database, table)
        stdout = await self._run_exec(
            self._build_remote_mysql_query_args(config, sql, password),
            timeout=self._connect_timeout,
        )
        return self._parse_table_columns(stdout, database, table)

    async def _collect_missing_keys_local_to_remote(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        key_columns: tuple[str, ...],
        local_password: str,
        remote_password: str,
    ) -> list[tuple[str | None, ...]]:
        source_keys = await self._fetch_local_key_rows(
            config, database, table, key_columns, local_password
        )
        target_keys = await self._fetch_remote_key_rows(
            config, database, table, key_columns, remote_password
        )
        return self._build_missing_rows(source_keys, target_keys)

    async def _collect_missing_keys_remote_to_local(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        key_columns: tuple[str, ...],
        local_password: str,
        remote_password: str,
    ) -> list[tuple[str | None, ...]]:
        source_keys = await self._fetch_remote_key_rows(
            config, database, table, key_columns, remote_password
        )
        target_keys = await self._fetch_local_key_rows(
            config, database, table, key_columns, local_password
        )
        return self._build_missing_rows(source_keys, target_keys)

    async def _fetch_local_key_rows(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        key_columns: tuple[str, ...],
        password: str,
        use_row_hash: bool = False,
    ) -> list[tuple[str | None, ...]]:
        sql = (
            self._build_table_row_hash_values_sql(database, table, key_columns)
            if use_row_hash
            else self._build_table_key_values_sql(database, table, key_columns)
        )
        stdout = await self._run_exec(
            self._build_local_mysql_query_args(config, sql, password),
            timeout=self._timeout_seconds,
        )
        return self._parse_key_rows(stdout, 1 if use_row_hash else len(key_columns))

    async def _fetch_remote_key_rows(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        key_columns: tuple[str, ...],
        password: str,
        use_row_hash: bool = False,
    ) -> list[tuple[str | None, ...]]:
        sql = (
            self._build_table_row_hash_values_sql(database, table, key_columns)
            if use_row_hash
            else self._build_table_key_values_sql(database, table, key_columns)
        )
        stdout = await self._run_exec(
            self._build_remote_mysql_query_args(config, sql, password),
            timeout=self._timeout_seconds,
        )
        return self._parse_key_rows(stdout, 1 if use_row_hash else len(key_columns))

    async def _stream_local_missing_rows_to_remote(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        key_columns: tuple[str, ...],
        missing_keys: list[tuple[str | None, ...]],
        local_password: str,
        remote_password: str,
        use_row_hash: bool = False,
    ) -> None:
        for batch in self._chunk_keys(missing_keys):
            where_sql = (
                self._build_missing_row_hashes_where_sql(key_columns, batch)
                if use_row_hash
                else self._build_missing_keys_where_sql(key_columns, batch)
            )
            stream_cmd = self._compose_stream_command(
                self._join_command(
                    self._build_local_incremental_table_dump_args(
                        config,
                        database,
                        table,
                        local_password,
                        where_sql,
                    )
                ),
                self._join_command(
                    self._build_remote_mysql_import_args(config, database, remote_password)
                ),
            )
            await self._run_bash(stream_cmd, timeout=self._timeout_seconds)

    async def _stream_remote_missing_rows_to_local(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        key_columns: tuple[str, ...],
        missing_keys: list[tuple[str | None, ...]],
        local_password: str,
        remote_password: str,
        use_row_hash: bool = False,
    ) -> None:
        for batch in self._chunk_keys(missing_keys):
            where_sql = (
                self._build_missing_row_hashes_where_sql(key_columns, batch)
                if use_row_hash
                else self._build_missing_keys_where_sql(key_columns, batch)
            )
            stream_cmd = self._compose_stream_command(
                self._join_command(
                    self._build_remote_incremental_table_dump_args(
                        config,
                        database,
                        table,
                        remote_password,
                        where_sql,
                    )
                ),
                self._join_command(
                    self._build_local_mysql_import_args(config, database, local_password)
                ),
            )
            await self._run_bash(stream_cmd, timeout=self._timeout_seconds)

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
        if self._is_direct_mode(config):
            stdout = await self._run_exec(
                self._build_remote_mysql_query_args(config, sql, password),
                timeout=self._connect_timeout,
            )
        else:
            remote_cmd = (
                f"docker exec {shlex.quote(config.remote_container)} sh -lc "
                f"{shlex.quote(self._build_remote_mysql_query_command(config, sql, password))}"
            )
            stdout = await self._run_ssh(config, remote_cmd, timeout=self._connect_timeout)
        return self._parse_database_info(databases, stdout)

    async def _scp_upload(self, config: SyncConfig, source: Path, target: str) -> None:
        await self._run_exec(
            self._build_scp_base_args(config)
            + [str(source), f"{config.remote_user}@{config.remote_host}:{target}"],
            timeout=self._timeout_seconds,
        )

    async def _scp_download(self, config: SyncConfig, source: str, target: Path) -> None:
        await self._run_exec(
            self._build_scp_base_args(config)
            + [f"{config.remote_user}@{config.remote_host}:{source}", str(target)],
            timeout=self._timeout_seconds,
        )

    async def _get_remote_mysql_password(self, config: SyncConfig) -> str:
        explicit_password = str(config.remote_mysql_password or "").strip()
        if explicit_password:
            return explicit_password
        if self._is_direct_mode(config):
            raise RuntimeError("直连模式必须填写远程 MySQL 密码")
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

    def _get_local_mysql_defaults(self) -> dict[str, str | int]:
        fallback_host = str(getattr(settings, "SYNC_LOCAL_MYSQL_HOST", "127.0.0.1"))
        fallback_port = int(getattr(settings, "SYNC_LOCAL_MYSQL_PORT", 3306))
        fallback_user = str(getattr(settings, "SYNC_LOCAL_MYSQL_USER", "root"))
        fallback_password = str(getattr(settings, "SYNC_LOCAL_MYSQL_PASSWORD", ""))

        for candidate in (
            os.environ.get("DATABASE_URL") or settings.DATABASE_URL,
            os.environ.get("AKSHARE_DATA_DATABASE_URL") or settings.AKSHARE_DATA_DATABASE_URL,
        ):
            if not candidate:
                continue
            parsed = urlparse(candidate)
            if parsed.scheme.startswith("mysql"):
                return {
                    "host": parsed.hostname or fallback_host,
                    "port": parsed.port or fallback_port,
                    "user": parsed.username or fallback_user,
                    "password": parsed.password or fallback_password,
                }

        return {
            "host": fallback_host,
            "port": fallback_port,
            "user": fallback_user,
            "password": fallback_password,
        }

    def _get_local_mysql_password(self, config: SyncConfig | None = None) -> str:
        value = (getattr(config, "local_mysql_password", "") if config is not None else "") or (
            os.environ.get("SYNC_LOCAL_MYSQL_PASSWORD")
            or getattr(settings, "SYNC_LOCAL_MYSQL_PASSWORD", "")
            or os.environ.get("LOCAL_MYSQL_PASSWORD")
            or str(self._get_local_mysql_defaults()["password"])
        )
        return str(value or "").strip()

    def _normalize_config(self, config: SyncConfig) -> SyncConfig:
        payload = config.model_copy(deep=True)
        local_defaults = self._get_local_mysql_defaults()
        payload.connection_mode = payload.connection_mode or "direct_mysql"
        payload.local_mysql_host = payload.local_mysql_host.strip() or str(local_defaults["host"])
        payload.local_mysql_port = int(payload.local_mysql_port or int(local_defaults["port"]))
        payload.local_mysql_user = payload.local_mysql_user.strip() or str(local_defaults["user"])
        payload.local_mysql_password = str(
            payload.local_mysql_password or local_defaults["password"]
        ).strip()
        payload.sync_parallel_workers = min(max(int(payload.sync_parallel_workers or 2), 1), 16)
        payload.remote_host = self._normalize_host(payload.remote_host)
        payload.remote_user = payload.remote_user.strip() or "root"
        payload.remote_ssh_key = payload.remote_ssh_key.strip() or "~/.ssh/id_rsa"
        payload.remote_container = payload.remote_container.strip() or "backtrader_mysql"
        payload.remote_install_dir = payload.remote_install_dir.strip() or "/opt/backtrader_web"
        payload.remote_mysql_host = self._normalize_host(
            payload.remote_mysql_host or payload.remote_host
        )
        payload.remote_mysql_port = int(payload.remote_mysql_port or 3306)
        payload.remote_mysql_user = payload.remote_mysql_user.strip() or "root"
        payload.remote_mysql_password = str(payload.remote_mysql_password or "").strip()
        payload.sync_databases = [name.strip() for name in payload.sync_databases if name.strip()]
        if not payload.sync_databases:
            payload.sync_databases = ["backtrader_web", "akshare_data"]
        return payload

    def _is_direct_mode(self, config: SyncConfig) -> bool:
        return getattr(config, "connection_mode", "direct_mysql") == "direct_mysql"

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

    def _build_table_names_sql(self, database: str) -> str:
        return (
            "SELECT TABLE_NAME "
            "FROM information_schema.TABLES "
            f"WHERE TABLE_SCHEMA = {self._quote_sql_string(database)} "
            "ORDER BY TABLE_NAME"
        )

    def _build_table_columns_sql(self, database: str, table: str) -> str:
        return (
            "SELECT COLUMN_NAME "
            "FROM information_schema.COLUMNS "
            f"WHERE TABLE_SCHEMA = {self._quote_sql_string(database)} "
            f"AND TABLE_NAME = {self._quote_sql_string(table)} "
            "ORDER BY ORDINAL_POSITION"
        )

    def _build_index_metadata_sql(self, database: str, table: str) -> str:
        return (
            "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
            "FROM information_schema.STATISTICS "
            f"WHERE TABLE_SCHEMA = {self._quote_sql_string(database)} "
            f"AND TABLE_NAME = {self._quote_sql_string(table)} "
            "AND (INDEX_NAME = 'PRIMARY' OR NON_UNIQUE = 0) "
            "ORDER BY CASE WHEN INDEX_NAME = 'PRIMARY' THEN 0 ELSE 1 END, INDEX_NAME, SEQ_IN_INDEX"
        )

    def _build_table_key_values_sql(
        self,
        database: str,
        table: str,
        key_columns: tuple[str, ...],
    ) -> str:
        key_select = ", ".join(self._quote_identifier(column) for column in key_columns)
        return f"SELECT {key_select} FROM {self._quote_identifier(database)}.{self._quote_identifier(table)}"

    def _build_row_hash_expression(self, key_columns: tuple[str, ...]) -> str:
        json_items = ", ".join(self._quote_identifier(column) for column in key_columns)
        return f"SHA2(CAST(JSON_ARRAY({json_items}) AS CHAR), 256)"

    def _build_table_row_hash_values_sql(
        self,
        database: str,
        table: str,
        key_columns: tuple[str, ...],
    ) -> str:
        row_hash = self._build_row_hash_expression(key_columns)
        return f"SELECT {row_hash} FROM {self._quote_identifier(database)}.{self._quote_identifier(table)}"

    def _select_incremental_key_columns(
        self,
        stdout: str,
        database: str,
        table: str,
    ) -> tuple[str, ...]:
        indexes: dict[str, list[tuple[int, str]]] = {}
        for line in stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            index_name, _non_unique, seq_in_index, column_name = parts
            indexes.setdefault(index_name, []).append((int(seq_in_index), column_name))
        if not indexes:
            return ()
        if "PRIMARY" in indexes:
            selected = indexes["PRIMARY"]
        else:
            first_name = next(iter(indexes))
            selected = indexes[first_name]
        return tuple(column for _, column in sorted(selected, key=lambda item: item[0]))

    def _parse_table_columns(
        self,
        stdout: str,
        database: str,
        table: str,
    ) -> tuple[str, ...]:
        columns = tuple(line.strip() for line in stdout.splitlines() if line.strip())
        if not columns:
            raise RuntimeError(f"数据表 {database}.{table} 未读取到可用列，无法执行增量同步")
        return columns

    def _build_missing_rows(
        self,
        source_rows: list[tuple[str | None, ...]],
        target_rows: list[tuple[str | None, ...]],
    ) -> list[tuple[str | None, ...]]:
        remaining = Counter(source_rows)
        remaining.subtract(target_rows)
        missing_rows: list[tuple[str | None, ...]] = []
        for row in source_rows:
            if remaining[row] > 0:
                missing_rows.append(row)
                remaining[row] -= 1
        return missing_rows

    def _parse_key_rows(
        self,
        stdout: str,
        expected_columns: int,
    ) -> list[tuple[str | None, ...]]:
        rows: list[tuple[str | None, ...]] = []
        for line in stdout.splitlines():
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != expected_columns:
                continue
            rows.append(tuple(None if value == "\\N" else value for value in parts))
        return rows

    def _chunk_keys(
        self,
        keys: list[tuple[str | None, ...]],
    ) -> list[list[tuple[str | None, ...]]]:
        return [
            keys[index : index + self._incremental_key_batch_size]
            for index in range(0, len(keys), self._incremental_key_batch_size)
        ]

    def _build_missing_keys_where_sql(
        self,
        key_columns: tuple[str, ...],
        key_rows: list[tuple[str | None, ...]],
    ) -> str:
        clauses: list[str] = []
        for row in key_rows:
            parts: list[str] = []
            for column, value in zip(key_columns, row, strict=False):
                identifier = self._quote_identifier(column)
                if value is None:
                    parts.append(f"{identifier} IS NULL")
                else:
                    parts.append(f"{identifier} = {self._quote_sql_string(value)}")
            clauses.append("(" + " AND ".join(parts) + ")")
        return " OR ".join(clauses) if clauses else "1 = 0"

    def _build_missing_row_hashes_where_sql(
        self,
        key_columns: tuple[str, ...],
        key_rows: list[tuple[str | None, ...]],
    ) -> str:
        row_hash = self._build_row_hash_expression(key_columns)
        values = [row[0] for row in key_rows if row and row[0] is not None]
        if not values:
            return "1 = 0"
        in_clause = ", ".join(self._quote_sql_string(str(value)) for value in values)
        return f"{row_hash} IN ({in_clause})"

    def _build_ensure_database_sql(self, database: str) -> str:
        identifier = self._quote_identifier(database)
        return f"CREATE DATABASE IF NOT EXISTS {identifier} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

    def _build_database_exists_sql(self, database: str) -> str:
        return (
            "SELECT SCHEMA_NAME "
            "FROM information_schema.SCHEMATA "
            f"WHERE SCHEMA_NAME = {self._quote_sql_string(database)} "
            "LIMIT 1"
        )

    def _build_schema_table_summary_sql(self, database: str) -> str:
        return (
            "SELECT JSON_ARRAY("
            "'TABLE', TABLE_NAME, COALESCE(TABLE_TYPE, ''), COALESCE(ENGINE, ''), COALESCE(TABLE_COLLATION, '')"
            ") "
            "FROM information_schema.TABLES "
            f"WHERE TABLE_SCHEMA = {self._quote_sql_string(database)} "
            "ORDER BY TABLE_NAME"
        )

    def _build_schema_column_summary_sql(self, database: str) -> str:
        return (
            "SELECT JSON_ARRAY("
            "'COLUMN', TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
            "IF(COLUMN_DEFAULT IS NULL, '__SYNC_NULL__', COLUMN_DEFAULT), COALESCE(EXTRA, ''), "
            "COALESCE(CHARACTER_SET_NAME, ''), COALESCE(COLLATION_NAME, '')"
            ") "
            "FROM information_schema.COLUMNS "
            f"WHERE TABLE_SCHEMA = {self._quote_sql_string(database)} "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION"
        )

    def _build_schema_index_summary_sql(self, database: str) -> str:
        return (
            "SELECT JSON_ARRAY("
            "'INDEX', TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, "
            "IF(SUB_PART IS NULL, -1, SUB_PART), COALESCE(COLLATION, ''), COALESCE(INDEX_TYPE, '')"
            ") "
            "FROM information_schema.STATISTICS "
            f"WHERE TABLE_SCHEMA = {self._quote_sql_string(database)} "
            "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
        )

    def _build_schema_view_summary_sql(self, database: str) -> str:
        return (
            "SELECT JSON_ARRAY("
            "'VIEW', TABLE_NAME, VIEW_DEFINITION, COALESCE(CHECK_OPTION, ''), "
            "COALESCE(IS_UPDATABLE, ''), COALESCE(SECURITY_TYPE, '')"
            ") "
            "FROM information_schema.VIEWS "
            f"WHERE TABLE_SCHEMA = {self._quote_sql_string(database)} "
            "ORDER BY TABLE_NAME"
        )

    def _build_schema_summary_sql_list(self, database: str) -> tuple[str, ...]:
        return (
            self._build_schema_table_summary_sql(database),
            self._build_schema_column_summary_sql(database),
            self._build_schema_index_summary_sql(database),
            self._build_schema_view_summary_sql(database),
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
            "-h",
            config.local_mysql_host,
            "-P",
            str(config.local_mysql_port),
            "-u",
            config.local_mysql_user,
            f"-p{password}",
        ]
        if sync_mode == "schema_only":
            args.extend(
                [
                    "--no-data",
                    "--skip-comments",
                    "--skip-dump-date",
                    "--skip-add-drop-table",
                    "--skip-add-drop-trigger",
                    "--skip-triggers",
                ]
            )
        elif sync_mode == "data_only":
            args.extend(["--no-create-info", "--replace", "--skip-triggers"])
        else:
            args.extend(["--routines", "--triggers", "--events"])
        args.append(database)
        return args

    def _build_local_table_dump_args(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        password: str,
    ) -> list[str]:
        args = self._build_local_mysqldump_args(config, database, "data_only", password)
        args.append(table)
        return args

    def _build_local_incremental_table_dump_args(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        password: str,
        where_sql: str,
    ) -> list[str]:
        return [
            "mysqldump",
            "--single-transaction",
            "--skip-lock-tables",
            "--set-gtid-purged=OFF",
            "--default-character-set=utf8mb4",
            "--no-create-info",
            "--replace",
            f"--where={where_sql}",
            "-h",
            config.local_mysql_host,
            "-P",
            str(config.local_mysql_port),
            "-u",
            config.local_mysql_user,
            f"-p{password}",
            database,
            table,
        ]

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

    async def _local_database_exists(
        self,
        config: SyncConfig,
        database: str,
        password: str,
    ) -> bool:
        stdout = await self._run_exec(
            self._build_local_mysql_query_args(
                config,
                self._build_database_exists_sql(database),
                password,
            ),
            timeout=self._connect_timeout,
        )
        return bool(stdout.strip())

    async def _export_local_schema_dump(
        self,
        config: SyncConfig,
        database: str,
        password: str,
    ) -> str:
        chunks: list[str] = []
        for sql in self._build_schema_summary_sql_list(database):
            stdout = await self._run_exec(
                self._build_local_mysql_query_args(config, sql, password),
                timeout=self._timeout_seconds,
            )
            if stdout.strip():
                chunks.append(stdout.strip())
        return "\n".join(chunks)

    async def _schemas_match_remote_to_local(
        self,
        config: SyncConfig,
        database: str,
        local_password: str,
        remote_password: str,
        task_id: str | None = None,
    ) -> bool:
        if task_id is not None:
            self._update_task(
                task_id,
                stage="dumping",
                progress_pct=28,
                message=f"正在读取远程数据库结构摘要 {database}",
            )
        remote_schema = await self._export_remote_schema_dump(config, database, remote_password)
        if task_id is not None:
            self._update_task(
                task_id,
                stage="dumping",
                progress_pct=29,
                message=f"正在读取本地数据库结构摘要 {database}",
            )
        local_schema = await self._export_local_schema_dump(config, database, local_password)
        if task_id is not None:
            self._update_task(
                task_id,
                stage="dumping",
                progress_pct=30,
                message=f"正在比较远程与本地数据库结构摘要 {database}",
            )
        return self._normalize_schema_dump(remote_schema) == self._normalize_schema_dump(
            local_schema
        )

    def _build_local_mysql_import_args(
        self,
        config: SyncConfig,
        database: str,
        password: str,
        force: bool = False,
    ) -> list[str]:
        args = [
            "mysql",
            "-h",
            config.local_mysql_host,
            "-P",
            str(config.local_mysql_port),
            "-u",
            config.local_mysql_user,
            f"-p{password}",
        ]
        if force:
            args.append("--force")
        args.append(database)
        return args

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
            "-h",
            config.remote_mysql_host,
            "-P",
            str(config.remote_mysql_port),
            "-u",
            config.remote_mysql_user,
        ]
        if sync_mode == "schema_only":
            args.extend(
                [
                    "--no-data",
                    "--skip-comments",
                    "--skip-dump-date",
                    "--skip-add-drop-table",
                    "--skip-add-drop-trigger",
                    "--skip-triggers",
                ]
            )
        elif sync_mode == "data_only":
            args.extend(["--no-create-info", "--replace", "--skip-triggers"])
        else:
            args.extend(["--routines", "--triggers", "--events"])
        args.append(database)
        return f"MYSQL_PWD={shlex.quote(password)} {self._join_command(args)}"

    def _build_remote_mysqldump_args(
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
            "-h",
            config.remote_mysql_host,
            "-P",
            str(config.remote_mysql_port),
            "-u",
            config.remote_mysql_user,
            f"-p{password}",
        ]
        if sync_mode == "schema_only":
            args.extend(
                [
                    "--no-data",
                    "--skip-comments",
                    "--skip-dump-date",
                    "--skip-add-drop-table",
                    "--skip-add-drop-trigger",
                    "--skip-triggers",
                ]
            )
        elif sync_mode == "data_only":
            args.extend(["--no-create-info", "--replace", "--skip-triggers"])
        else:
            args.extend(["--routines", "--triggers", "--events"])
        args.append(database)
        return args

    def _build_remote_table_dump_args(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        password: str,
    ) -> list[str]:
        args = self._build_remote_mysqldump_args(config, database, "data_only", password)
        args.append(table)
        return args

    def _build_remote_incremental_table_dump_args(
        self,
        config: SyncConfig,
        database: str,
        table: str,
        password: str,
        where_sql: str,
    ) -> list[str]:
        return [
            "mysqldump",
            "--single-transaction",
            "--skip-lock-tables",
            "--set-gtid-purged=OFF",
            "--default-character-set=utf8mb4",
            "--no-create-info",
            "--replace",
            f"--where={where_sql}",
            "-h",
            config.remote_mysql_host,
            "-P",
            str(config.remote_mysql_port),
            "-u",
            config.remote_mysql_user,
            f"-p{password}",
            database,
            table,
        ]

    def _build_remote_mysql_query_args(
        self,
        config: SyncConfig,
        sql: str,
        password: str,
    ) -> list[str]:
        return [
            "mysql",
            "-h",
            config.remote_mysql_host,
            "-P",
            str(config.remote_mysql_port),
            "-u",
            config.remote_mysql_user,
            f"-p{password}",
            "-N",
            "-B",
            "-e",
            sql,
        ]

    async def _remote_database_exists(
        self,
        config: SyncConfig,
        database: str,
        password: str,
    ) -> bool:
        stdout = await self._run_exec(
            self._build_remote_mysql_query_args(
                config,
                self._build_database_exists_sql(database),
                password,
            ),
            timeout=self._connect_timeout,
        )
        return bool(stdout.strip())

    async def _export_remote_schema_dump(
        self,
        config: SyncConfig,
        database: str,
        password: str,
    ) -> str:
        chunks: list[str] = []
        for sql in self._build_schema_summary_sql_list(database):
            stdout = await self._run_exec(
                self._build_remote_mysql_query_args(config, sql, password),
                timeout=self._timeout_seconds,
            )
            if stdout.strip():
                chunks.append(stdout.strip())
        return "\n".join(chunks)

    async def _schemas_match_local_to_remote(
        self,
        config: SyncConfig,
        database: str,
        local_password: str,
        remote_password: str,
        task_id: str | None = None,
    ) -> bool:
        if task_id is not None:
            self._update_task(
                task_id,
                stage="dumping",
                progress_pct=28,
                message=f"正在读取本地数据库结构摘要 {database}",
            )
        local_schema = await self._export_local_schema_dump(config, database, local_password)
        if task_id is not None:
            self._update_task(
                task_id,
                stage="dumping",
                progress_pct=29,
                message=f"正在读取远程数据库结构摘要 {database}",
            )
        remote_schema = await self._export_remote_schema_dump(config, database, remote_password)
        if task_id is not None:
            self._update_task(
                task_id,
                stage="dumping",
                progress_pct=30,
                message=f"正在比较本地与远程数据库结构摘要 {database}",
            )
        return self._normalize_schema_dump(local_schema) == self._normalize_schema_dump(
            remote_schema
        )

    def _build_remote_mysql_import_args(
        self,
        config: SyncConfig,
        database: str,
        password: str,
        force: bool = False,
    ) -> list[str]:
        args = [
            "mysql",
            "-h",
            config.remote_mysql_host,
            "-P",
            str(config.remote_mysql_port),
            "-u",
            config.remote_mysql_user,
            f"-p{password}",
        ]
        if force:
            args.append("--force")
        args.append(database)
        return args

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

    def _compose_import_command(
        self, *, input_path: str, mysql_command: str, compressed: bool
    ) -> str:
        cat_command = "gunzip -c" if compressed else "cat"
        return f"set -o pipefail; {cat_command} {shlex.quote(input_path)} | {mysql_command}"

    def _compose_stream_command(self, dump_command: str, mysql_command: str) -> str:
        return f"set -o pipefail; {dump_command} | {mysql_command}"

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
        return await self._run_exec(
            self._build_ssh_base_args(config) + [remote_command], timeout=timeout
        )

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
        return DatabaseInfo(
            name=name, size_bytes=0, size_display="0 B", table_count=0, exists=False
        )

    def _join_command(self, args: list[str]) -> str:
        return " ".join(shlex.quote(arg) for arg in args)

    def _quote_sql_string(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _quote_identifier(self, value: str) -> str:
        return "`" + value.replace("`", "``") + "`"

    def _normalize_schema_dump(self, payload: str) -> str:
        normalized = payload.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"AUTO_INCREMENT=\d+", "AUTO_INCREMENT=0", normalized)
        normalized = re.sub(r"DEFINER=`[^`]+`@`[^`]+`", "DEFINER=CURRENT_USER", normalized)
        lines = [line.strip() for line in normalized.split("\n") if line.strip()]
        return "\n".join(lines)

    def _parse_schema_summary(self, payload: str) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "tables": {},
            "columns": {},
            "indexes": {},
            "views": {},
        }
        for line in payload.splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, list) or not row:
                continue
            kind = str(row[0])
            if kind == "TABLE" and len(row) >= 5:
                table_name = str(row[1])
                summary["tables"][table_name] = {
                    "table_type": str(row[2]),
                    "engine": str(row[3]),
                    "collation": str(row[4]),
                }
                continue
            if kind == "COLUMN" and len(row) >= 10:
                table_name = str(row[1])
                ordinal = int(row[2])
                column_name = str(row[3])
                summary["columns"].setdefault(table_name, {})[column_name] = {
                    "ordinal": ordinal,
                    "signature": json.dumps(row[3:], ensure_ascii=False, separators=(",", ":")),
                }
                continue
            if kind == "INDEX" and len(row) >= 9:
                table_name = str(row[1])
                index_name = str(row[2])
                table_indexes = summary["indexes"].setdefault(table_name, {})
                entry = table_indexes.setdefault(
                    index_name,
                    {
                        "non_unique": int(row[3]),
                        "index_type": str(row[8]),
                        "parts": [],
                    },
                )
                entry["parts"].append(
                    (
                        int(row[4]),
                        str(row[5]),
                        int(row[6]),
                        str(row[7]),
                    )
                )
                continue
            if kind == "VIEW" and len(row) >= 6:
                view_name = str(row[1])
                summary["views"][view_name] = json.dumps(
                    row[2:], ensure_ascii=False, separators=(",", ":")
                )
        for table_indexes in summary["indexes"].values():
            for index_meta in table_indexes.values():
                index_meta["parts"].sort(key=lambda item: item[0])
                index_meta["signature"] = json.dumps(
                    [index_meta["non_unique"], index_meta["index_type"], index_meta["parts"]],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
        return summary

    def _build_schema_delta(
        self,
        source_summary: dict[str, Any],
        target_summary: dict[str, Any],
    ) -> dict[str, Any]:
        source_tables = {
            name: meta
            for name, meta in source_summary.get("tables", {}).items()
            if str(meta.get("table_type", "")).upper() == "BASE TABLE"
        }
        target_tables = {
            name: meta
            for name, meta in target_summary.get("tables", {}).items()
            if str(meta.get("table_type", "")).upper() == "BASE TABLE"
        }
        missing_tables = sorted(set(source_tables) - set(target_tables))
        common_tables = sorted(set(source_tables) & set(target_tables))
        table_changes: dict[str, dict[str, list[str]]] = {}
        for table in common_tables:
            source_columns = source_summary.get("columns", {}).get(table, {})
            target_columns = target_summary.get("columns", {}).get(table, {})
            source_order = [
                name
                for name, _meta in sorted(
                    source_columns.items(), key=lambda item: item[1]["ordinal"]
                )
            ]
            add_columns = [name for name in source_order if name not in target_columns]
            modify_columns = [
                name
                for name in source_order
                if name in target_columns
                and source_columns[name]["signature"] != target_columns[name]["signature"]
            ]
            source_indexes = source_summary.get("indexes", {}).get(table, {})
            target_indexes = target_summary.get("indexes", {}).get(table, {})
            add_indexes = sorted(name for name in source_indexes if name not in target_indexes)
            rebuild_indexes = sorted(
                name
                for name in source_indexes
                if name in target_indexes
                and source_indexes[name]["signature"] != target_indexes[name]["signature"]
            )
            if add_columns or modify_columns or add_indexes or rebuild_indexes:
                table_changes[table] = {
                    "add_columns": add_columns,
                    "modify_columns": modify_columns,
                    "add_indexes": add_indexes,
                    "rebuild_indexes": rebuild_indexes,
                }
        source_views = source_summary.get("views", {})
        target_views = target_summary.get("views", {})
        views_to_upsert = sorted(
            name for name, signature in source_views.items() if target_views.get(name) != signature
        )
        return {
            "missing_tables": missing_tables,
            "table_changes": table_changes,
            "views_to_upsert": views_to_upsert,
        }

    def _schema_delta_is_empty(self, delta: dict[str, Any]) -> bool:
        return (
            not delta["missing_tables"]
            and not delta["table_changes"]
            and not delta["views_to_upsert"]
        )

    def _build_local_object_schema_dump_args(
        self,
        config: SyncConfig,
        database: str,
        object_name: str,
        password: str,
    ) -> list[str]:
        args = self._build_local_mysqldump_args(config, database, "schema_only", password)
        args.append(object_name)
        return args

    def _build_remote_object_schema_dump_args(
        self,
        config: SyncConfig,
        database: str,
        object_name: str,
        password: str,
    ) -> list[str]:
        args = self._build_remote_mysqldump_args(config, database, "schema_only", password)
        args.append(object_name)
        return args

    async def _export_local_object_schema_sql(
        self,
        config: SyncConfig,
        database: str,
        object_name: str,
        password: str,
    ) -> str:
        return await self._run_exec(
            self._build_local_object_schema_dump_args(config, database, object_name, password),
            timeout=self._timeout_seconds,
        )

    async def _export_remote_object_schema_sql(
        self,
        config: SyncConfig,
        database: str,
        object_name: str,
        password: str,
    ) -> str:
        return await self._run_exec(
            self._build_remote_object_schema_dump_args(config, database, object_name, password),
            timeout=self._timeout_seconds,
        )

    def _extract_create_table_statement(self, payload: str, table: str) -> str:
        quoted_table = re.escape(self._quote_identifier(table))
        match = re.search(rf"CREATE TABLE {quoted_table} \(.*?\)[^;]*;", payload, re.S)
        if match is None:
            raise RuntimeError(f"未找到数据表 {table} 的 CREATE TABLE 语句")
        return match.group(0).strip()

    def _extract_create_table_definitions(
        self, payload: str, table: str
    ) -> dict[str, dict[str, str]]:
        quoted_table = re.escape(self._quote_identifier(table))
        match = re.search(
            rf"CREATE TABLE {quoted_table} \((?P<body>.*?)\)[^;]*;",
            payload,
            re.S,
        )
        if match is None:
            raise RuntimeError(f"未找到数据表 {table} 的字段定义")
        body = match.group("body")
        column_defs: dict[str, str] = {}
        index_defs: dict[str, str] = {}
        for raw_line in body.splitlines():
            line = raw_line.strip().rstrip(",")
            if not line:
                continue
            if line.startswith("`"):
                column_name = line.split("`", 2)[1]
                column_defs[column_name] = line
                continue
            if line.startswith("PRIMARY KEY"):
                index_defs["PRIMARY"] = line
                continue
            index_match = re.match(r"(?:UNIQUE KEY|FULLTEXT KEY|SPATIAL KEY|KEY) `([^`]+)`", line)
            if index_match is not None:
                index_defs[index_match.group(1)] = line
        return {
            "columns": column_defs,
            "indexes": index_defs,
        }

    def _build_column_position_clause(
        self,
        source_order: list[str],
        current_columns: set[str],
        column_name: str,
    ) -> str:
        column_index = source_order.index(column_name)
        for previous_name in reversed(source_order[:column_index]):
            if previous_name in current_columns:
                return f" AFTER {self._quote_identifier(previous_name)}"
        return " FIRST"

    def _build_incremental_table_alter_sql(
        self,
        database: str,
        table: str,
        table_delta: dict[str, list[str]],
        source_summary: dict[str, Any],
        target_summary: dict[str, Any],
        source_schema_sql: str,
    ) -> str | None:
        parsed = self._extract_create_table_definitions(source_schema_sql, table)
        source_columns = source_summary.get("columns", {}).get(table, {})
        target_columns = target_summary.get("columns", {}).get(table, {})
        source_order = [
            name
            for name, _meta in sorted(source_columns.items(), key=lambda item: item[1]["ordinal"])
        ]
        current_columns = set(target_columns)
        clauses: list[str] = []
        for column_name in source_order:
            if column_name in table_delta["add_columns"]:
                column_definition = parsed["columns"].get(column_name)
                if column_definition is None:
                    raise RuntimeError(f"未找到数据表 {table}.{column_name} 的字段定义")
                position_clause = self._build_column_position_clause(
                    source_order, current_columns, column_name
                )
                clauses.append(f"ADD COLUMN {column_definition}{position_clause}")
                current_columns.add(column_name)
            elif column_name in table_delta["modify_columns"]:
                column_definition = parsed["columns"].get(column_name)
                if column_definition is None:
                    raise RuntimeError(f"未找到数据表 {table}.{column_name} 的字段定义")
                clauses.append(f"MODIFY COLUMN {column_definition}")
        for index_name in table_delta["rebuild_indexes"]:
            index_definition = parsed["indexes"].get(index_name)
            if index_definition is None:
                raise RuntimeError(f"未找到数据表 {table} 索引 {index_name} 的定义")
            if index_name == "PRIMARY":
                clauses.append("DROP PRIMARY KEY")
                clauses.append(f"ADD {index_definition}")
            else:
                clauses.append(f"DROP INDEX {self._quote_identifier(index_name)}")
                clauses.append(f"ADD {index_definition}")
        for index_name in table_delta["add_indexes"]:
            index_definition = parsed["indexes"].get(index_name)
            if index_definition is None:
                raise RuntimeError(f"未找到数据表 {table} 索引 {index_name} 的定义")
            clauses.append(f"ADD {index_definition}")
        if not clauses:
            return None
        return (
            f"ALTER TABLE {self._quote_identifier(database)}.{self._quote_identifier(table)} "
            + ", ".join(clauses)
        )

    def _build_show_create_view_sql(self, database: str, view_name: str) -> str:
        return f"SHOW CREATE VIEW {self._quote_identifier(database)}.{self._quote_identifier(view_name)}"

    def _normalize_create_view_sql(self, payload: str, view_name: str) -> str:
        parts = payload.split("\t", 3)
        if len(parts) < 2:
            raise RuntimeError(f"未找到视图 {view_name} 的 CREATE VIEW 语句")
        create_sql = parts[1].replace("\\n", "\n").replace("\\t", "\t")
        create_sql = re.sub(r"\sDEFINER=`[^`]+`@`[^`]+`", "", create_sql, count=1)
        if create_sql.startswith("CREATE "):
            create_sql = create_sql.replace("CREATE ", "CREATE OR REPLACE ", 1)
        return create_sql.strip()

    async def _fetch_local_view_create_sql(
        self,
        config: SyncConfig,
        database: str,
        view_name: str,
        password: str,
    ) -> str:
        stdout = await self._run_exec(
            self._build_local_mysql_query_args(
                config,
                self._build_show_create_view_sql(database, view_name),
                password,
            ),
            timeout=self._timeout_seconds,
        )
        return self._normalize_create_view_sql(stdout, view_name)

    async def _fetch_remote_view_create_sql(
        self,
        config: SyncConfig,
        database: str,
        view_name: str,
        password: str,
    ) -> str:
        stdout = await self._run_exec(
            self._build_remote_mysql_query_args(
                config,
                self._build_show_create_view_sql(database, view_name),
                password,
            ),
            timeout=self._timeout_seconds,
        )
        return self._normalize_create_view_sql(stdout, view_name)

    def _build_database_scoped_sql(self, database: str, sql: str) -> str:
        statement = sql.strip()
        if statement.endswith(";"):
            statement = statement[:-1]
        return f"USE {self._quote_identifier(database)}; {statement};"

    async def _execute_remote_database_sql(
        self,
        config: SyncConfig,
        database: str,
        sql: str,
        password: str,
    ) -> None:
        await self._run_exec(
            self._build_remote_mysql_query_args(
                config,
                self._build_database_scoped_sql(database, sql),
                password,
            ),
            timeout=self._timeout_seconds,
        )

    async def _execute_local_database_sql(
        self,
        config: SyncConfig,
        database: str,
        sql: str,
        password: str,
    ) -> None:
        await self._run_exec(
            self._build_local_mysql_query_args(
                config,
                self._build_database_scoped_sql(database, sql),
                password,
            ),
            timeout=self._timeout_seconds,
        )

    async def _apply_schema_delta_local_to_remote(
        self,
        *,
        task_id: str | None,
        config: SyncConfig,
        database: str,
        local_password: str,
        remote_password: str,
        source_summary: dict[str, Any],
        target_summary: dict[str, Any],
    ) -> dict[str, int]:
        delta = self._build_schema_delta(source_summary, target_summary)
        stats = {"tables": 0, "columns": 0, "indexes": 0, "views": 0}
        for table in delta["missing_tables"]:
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=34,
                    message=f"正在创建远程缺失数据表 {database}.{table}",
                )
            source_schema_sql = await self._export_local_object_schema_sql(
                config, database, table, local_password
            )
            create_sql = self._extract_create_table_statement(source_schema_sql, table)
            await self._execute_remote_database_sql(config, database, create_sql, remote_password)
            stats["tables"] += 1
        for table, table_delta in delta["table_changes"].items():
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=36,
                    message=f"正在增量更新远程表结构 {database}.{table}",
                )
            source_schema_sql = await self._export_local_object_schema_sql(
                config, database, table, local_password
            )
            alter_sql = self._build_incremental_table_alter_sql(
                database,
                table,
                table_delta,
                source_summary,
                target_summary,
                source_schema_sql,
            )
            if alter_sql is None:
                continue
            await self._execute_remote_database_sql(config, database, alter_sql, remote_password)
            stats["columns"] += len(table_delta["add_columns"]) + len(table_delta["modify_columns"])
            stats["indexes"] += len(table_delta["add_indexes"]) + len(
                table_delta["rebuild_indexes"]
            )
        for view_name in delta["views_to_upsert"]:
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=38,
                    message=f"正在增量更新远程视图 {database}.{view_name}",
                )
            view_sql = await self._fetch_local_view_create_sql(
                config, database, view_name, local_password
            )
            await self._execute_remote_database_sql(config, database, view_sql, remote_password)
            stats["views"] += 1
        return stats

    async def _apply_schema_delta_remote_to_local(
        self,
        *,
        task_id: str | None,
        config: SyncConfig,
        database: str,
        local_password: str,
        remote_password: str,
        source_summary: dict[str, Any],
        target_summary: dict[str, Any],
    ) -> dict[str, int]:
        delta = self._build_schema_delta(source_summary, target_summary)
        stats = {"tables": 0, "columns": 0, "indexes": 0, "views": 0}
        for table in delta["missing_tables"]:
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=34,
                    message=f"正在创建本地缺失数据表 {database}.{table}",
                )
            source_schema_sql = await self._export_remote_object_schema_sql(
                config, database, table, remote_password
            )
            create_sql = self._extract_create_table_statement(source_schema_sql, table)
            await self._execute_local_database_sql(config, database, create_sql, local_password)
            stats["tables"] += 1
        for table, table_delta in delta["table_changes"].items():
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=36,
                    message=f"正在增量更新本地表结构 {database}.{table}",
                )
            source_schema_sql = await self._export_remote_object_schema_sql(
                config, database, table, remote_password
            )
            alter_sql = self._build_incremental_table_alter_sql(
                database,
                table,
                table_delta,
                source_summary,
                target_summary,
                source_schema_sql,
            )
            if alter_sql is None:
                continue
            await self._execute_local_database_sql(config, database, alter_sql, local_password)
            stats["columns"] += len(table_delta["add_columns"]) + len(table_delta["modify_columns"])
            stats["indexes"] += len(table_delta["add_indexes"]) + len(
                table_delta["rebuild_indexes"]
            )
        for view_name in delta["views_to_upsert"]:
            if task_id is not None:
                self._update_task(
                    task_id,
                    stage="importing",
                    progress_pct=38,
                    message=f"正在增量更新本地视图 {database}.{view_name}",
                )
            view_sql = await self._fetch_remote_view_create_sql(
                config, database, view_name, remote_password
            )
            await self._execute_local_database_sql(config, database, view_sql, local_password)
            stats["views"] += 1
        return stats

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
