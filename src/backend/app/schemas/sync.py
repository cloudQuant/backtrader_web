from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SyncDirection = Literal["upload", "download"]
SyncMode = Literal["full", "schema_only", "data_only"]
SyncStage = Literal[
    "queued",
    "validating",
    "dumping",
    "transferring",
    "importing",
    "verifying",
    "done",
    "failed",
]
SyncTaskState = Literal["pending", "running", "completed", "failed"]


class SyncConfig(BaseModel):
    local_mysql_host: str = "127.0.0.1"
    local_mysql_port: int = 3306
    local_mysql_user: str = "root"
    local_mysql_password: str = ""
    remote_host: str = ""
    remote_user: str = "root"
    remote_ssh_key: str = "~/.ssh/id_rsa"
    remote_container: str = "backtrader_mysql"
    remote_install_dir: str = "/opt/backtrader_web"
    remote_mysql_host: str = "127.0.0.1"
    remote_mysql_port: int = 3306
    remote_mysql_user: str = "root"
    remote_mysql_password: str = ""
    sync_databases: list[str] = Field(
        default_factory=lambda: ["backtrader_web", "akshare_data"]
    )


class SyncRequest(BaseModel):
    databases: list[str] = Field(min_length=1)
    compress: bool = True
    confirm: bool = False
    sync_mode: SyncMode = "full"


class DatabaseInfo(BaseModel):
    name: str
    size_bytes: int = 0
    size_display: str = "0 B"
    table_count: int = 0
    exists: bool = False


class DatabaseSyncInfo(BaseModel):
    name: str
    local: DatabaseInfo
    remote: DatabaseInfo


class SyncTaskStatus(BaseModel):
    task_id: str
    status: SyncTaskState
    direction: SyncDirection
    databases: list[str]
    current_database: str | None = None
    completed_databases: list[str] = Field(default_factory=list)
    stage: SyncStage = "queued"
    progress_pct: int = 0
    message: str = ""
    started_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    error: str | None = None
    sync_mode: SyncMode = "full"


class SyncTaskCreateResponse(BaseModel):
    task_id: str
    status: SyncTaskState
    message: str


class SyncConnectionStatus(BaseModel):
    success: bool
    checks: dict[str, bool]
    details: dict[str, str] = Field(default_factory=dict)


class SyncHistoryEntry(SyncTaskStatus):
    pass
