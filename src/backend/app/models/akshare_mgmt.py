"""
Akshare data management ORM models.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class ScriptFrequency(str, enum.Enum):
    """Script execution frequency."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ONCE = "once"
    MANUAL = "manual"


class TaskStatus(str, enum.Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ScheduleType(str, enum.Enum):
    """Task schedule type."""

    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"
    INTERVAL = "interval"


class TriggeredBy(str, enum.Enum):
    """Execution trigger type."""

    SCHEDULER = "scheduler"
    MANUAL = "manual"
    API = "api"


class ParameterType(str, enum.Enum):
    """Interface parameter type."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    LIST = "list"
    OPTION = "option"


class DataScript(Base):
    """Metadata for akshare-backed data scripts."""

    __tablename__ = "ak_data_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    script_id = Column(String(100), unique=True, nullable=False, index=True)
    script_name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    sub_category = Column(String(50), nullable=True, index=True)
    frequency = Column(Enum(ScriptFrequency), nullable=True, default=ScriptFrequency.DAILY)
    description = Column(Text, nullable=True)
    source = Column(String(50), default="akshare", nullable=False)
    target_table = Column(String(100), nullable=True, index=True)
    module_path = Column(String(255), nullable=True)
    function_name = Column(String(100), nullable=True)
    dependencies = Column(JSON, nullable=True)
    estimated_duration = Column(Integer, default=60, nullable=False)
    timeout = Column(Integer, default=300, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_custom = Column(Boolean, default=False, nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tasks = relationship("ScheduledTask", back_populates="script")


class DataTable(Base):
    """Metadata describing tables stored in the akshare data warehouse."""

    __tablename__ = "ak_data_tables"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    table_name = Column(String(100), unique=True, nullable=False, index=True)
    table_comment = Column(String(200), nullable=True)
    category = Column(String(50), nullable=True, index=True)
    script_id = Column(String(100), nullable=True, index=True)
    row_count = Column(BigInteger, default=0, nullable=False)
    last_update_time = Column(DateTime, nullable=True, index=True)
    last_update_status = Column(String(20), nullable=True)
    data_start_date = Column(Date, nullable=True)
    data_end_date = Column(Date, nullable=True)
    symbol_raw = Column(String(100), nullable=True, index=True)
    symbol_normalized = Column(String(100), nullable=True, index=True)
    market = Column(String(50), nullable=True, index=True)
    asset_type = Column(String(50), nullable=True, index=True)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class InterfaceCategory(Base):
    """Category used to group akshare interfaces."""

    __tablename__ = "ak_interface_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    icon = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)

    interfaces = relationship("DataInterface", back_populates="category")


class DataInterface(Base):
    """Browsable akshare interface definition."""

    __tablename__ = "ak_data_interfaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(Integer, ForeignKey("ak_interface_categories.id"), nullable=False)
    module_path = Column(String(255), nullable=True)
    function_name = Column(String(100), nullable=True)
    parameters = Column(JSON, default=dict, nullable=False)
    extra_config = Column(JSON, default=dict, nullable=False)
    return_type = Column(String(50), default="DataFrame", nullable=False)
    example = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    category = relationship("InterfaceCategory", back_populates="interfaces")
    params = relationship(
        "InterfaceParameter",
        back_populates="interface",
        cascade="all, delete-orphan",
    )


class InterfaceParameter(Base):
    """Parameter definition for a data interface."""

    __tablename__ = "ak_interface_parameters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    interface_id = Column(Integer, ForeignKey("ak_data_interfaces.id"), nullable=False)
    name = Column(String(50), nullable=False)
    display_name = Column(String(100), nullable=False)
    param_type = Column(Enum(ParameterType), default=ParameterType.STRING, nullable=False)
    description = Column(Text, nullable=True)
    default_value = Column(Text, nullable=True)
    required = Column(Boolean, default=False, nullable=False)
    options = Column(JSON, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)

    interface = relationship("DataInterface", back_populates="params")


class ScheduledTask(Base):
    """Scheduled task metadata for akshare scripts."""

    __tablename__ = "ak_scheduled_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    script_id = Column(String(100), ForeignKey("ak_data_scripts.script_id"), nullable=False)
    schedule_type = Column(Enum(ScheduleType), default=ScheduleType.DAILY, nullable=False)
    schedule_expression = Column(String(100), nullable=False)
    parameters = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    retry_on_failure = Column(Boolean, default=True, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    timeout = Column(Integer, default=0, nullable=False)
    last_execution_at = Column(DateTime, nullable=True)
    next_execution_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    script = relationship("DataScript", back_populates="tasks")
    executions = relationship(
        "TaskExecution",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class TaskExecution(Base):
    """Execution record for a scheduled or manual akshare task run."""

    __tablename__ = "ak_task_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(String(100), unique=True, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("ak_scheduled_tasks.id"), nullable=True, index=True)
    script_id = Column(String(100), nullable=False, index=True)
    params = Column(JSON, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False, index=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    error_trace = Column(Text, nullable=True)
    rows_before = Column(Integer, nullable=True)
    rows_after = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    triggered_by = Column(Enum(TriggeredBy), default=TriggeredBy.SCHEDULER, nullable=False)
    operator_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    task = relationship("ScheduledTask", back_populates="executions")


__all__ = [
    "DataInterface",
    "DataScript",
    "DataTable",
    "InterfaceCategory",
    "InterfaceParameter",
    "ParameterType",
    "ScheduleType",
    "ScheduledTask",
    "ScriptFrequency",
    "TaskExecution",
    "TaskStatus",
    "TriggeredBy",
]
