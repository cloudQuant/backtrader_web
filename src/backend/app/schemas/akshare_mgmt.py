"""
Schemas for akshare data management APIs.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PaginatedQuery(BaseModel):
    """Common pagination query params."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class PaginatedResult(BaseModel):
    """Common paginated response."""

    items: list[Any]
    total: int
    page: int
    page_size: int


class ScriptStatsResponse(BaseModel):
    """Summary statistics for data scripts."""

    total_scripts: int
    active_scripts: int
    custom_scripts: int
    categories: list[str]


class DataScriptBase(BaseModel):
    """Base schema for akshare scripts."""

    script_name: str
    category: str
    sub_category: str | None = None
    frequency: str | None = None
    description: str | None = None
    source: str = "akshare"
    target_table: str | None = None
    module_path: str | None = None
    function_name: str | None = None
    dependencies: dict[str, Any] | None = None
    estimated_duration: int = 60
    timeout: int = 300
    is_active: bool = True


class DataScriptCreate(DataScriptBase):
    """Create schema for custom scripts."""

    script_id: str


class DataScriptUpdate(BaseModel):
    """Update schema for scripts."""

    script_name: str | None = None
    category: str | None = None
    sub_category: str | None = None
    frequency: str | None = None
    description: str | None = None
    source: str | None = None
    target_table: str | None = None
    module_path: str | None = None
    function_name: str | None = None
    dependencies: dict[str, Any] | None = None
    estimated_duration: int | None = None
    timeout: int | None = None
    is_active: bool | None = None


class DataScriptResponse(DataScriptBase):
    """Read schema for scripts."""

    id: int
    script_id: str
    is_custom: bool
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScriptRunRequest(BaseModel):
    """Manual run request for a script."""

    parameters: dict[str, Any] = Field(default_factory=dict)


class ExecutionTriggerResponse(BaseModel):
    """Execution trigger response."""

    execution_id: str
    status: str
    task_id: int | None = None


class ScheduledTaskBase(BaseModel):
    """Base schema for scheduled tasks."""

    name: str
    description: str | None = None
    script_id: str
    schedule_type: str
    schedule_expression: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    retry_on_failure: bool = True
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout: int = Field(default=0, ge=0)


class ScheduledTaskCreate(ScheduledTaskBase):
    """Create schema for tasks."""


class ScheduledTaskUpdate(BaseModel):
    """Update schema for tasks."""

    name: str | None = None
    description: str | None = None
    schedule_type: str | None = None
    schedule_expression: str | None = None
    parameters: dict[str, Any] | None = None
    is_active: bool | None = None
    retry_on_failure: bool | None = None
    max_retries: int | None = Field(default=None, ge=0, le=10)
    timeout: int | None = Field(default=None, ge=0)


class ScheduledTaskResponse(ScheduledTaskBase):
    """Read schema for tasks."""

    id: int
    user_id: str
    last_execution_at: datetime | None = None
    next_execution_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleTemplateResponse(BaseModel):
    """Response schema for task schedule templates."""

    value: str
    label: str
    description: str
    cron_expression: str


class TaskExecutionResponse(BaseModel):
    """Read schema for execution records."""

    id: int
    execution_id: str
    task_id: int | None = None
    script_id: str
    params: dict[str, Any] | None = None
    status: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration: float | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    error_trace: str | None = None
    rows_before: int | None = None
    rows_after: int | None = None
    retry_count: int
    triggered_by: str
    operator_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionStatsResponse(BaseModel):
    """Statistics for executions."""

    total_count: int
    success_count: int
    failed_count: int
    running_count: int
    success_rate: float
    avg_duration: float


class DataTableResponse(BaseModel):
    """Read schema for stored data tables."""

    id: int
    table_name: str
    table_comment: str | None = None
    category: str | None = None
    script_id: str | None = None
    row_count: int
    last_update_time: datetime | None = None
    last_update_status: str | None = None
    data_start_date: date | None = None
    data_end_date: date | None = None
    symbol_raw: str | None = None
    symbol_normalized: str | None = None
    market: str | None = None
    asset_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DataTableSchemaColumn(BaseModel):
    """Schema description for a warehouse table column."""

    name: str
    type: str
    nullable: bool
    default: Any | None = None


class DataTableSchemaResponse(BaseModel):
    """Schema info for a warehouse table."""

    table_name: str
    columns: list[DataTableSchemaColumn]
    row_count: int
    last_update_time: datetime | None = None


class DataTableRowsResponse(BaseModel):
    """Preview rows for a warehouse table."""

    table_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    total: int


class InterfaceCategoryResponse(BaseModel):
    """Read schema for interface categories."""

    id: int
    name: str
    description: str | None = None
    icon: str | None = None
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class InterfaceParameterResponse(BaseModel):
    """Read schema for interface parameters."""

    id: int
    name: str
    display_name: str
    param_type: str
    description: str | None = None
    default_value: str | None = None
    required: bool
    options: list[str] | None = None
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class DataInterfaceBase(BaseModel):
    """Base schema for interfaces."""

    name: str
    display_name: str
    description: str | None = None
    category_id: int
    module_path: str | None = None
    function_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    extra_config: dict[str, Any] = Field(default_factory=dict)
    return_type: str = "DataFrame"
    example: str | None = None
    is_active: bool = True


class DataInterfaceCreate(DataInterfaceBase):
    """Create schema for interfaces."""


class DataInterfaceUpdate(BaseModel):
    """Update schema for interfaces."""

    display_name: str | None = None
    description: str | None = None
    category_id: int | None = None
    module_path: str | None = None
    function_name: str | None = None
    parameters: dict[str, Any] | None = None
    extra_config: dict[str, Any] | None = None
    return_type: str | None = None
    example: str | None = None
    is_active: bool | None = None


class DataInterfaceResponse(DataInterfaceBase):
    """Read schema for interfaces."""

    id: int
    created_at: datetime
    updated_at: datetime
    params: list[InterfaceParameterResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
