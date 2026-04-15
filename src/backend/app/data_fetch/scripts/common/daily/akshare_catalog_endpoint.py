from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql
from app.utils.akshare_catalog_utils import make_akcat_table_name, normalize_mysql_column_names

logger = logging.getLogger(__name__)


def _to_dataframe(obj: Any) -> pd.DataFrame:
    if obj is None:
        return pd.DataFrame()
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, dict):
        return pd.DataFrame([obj])
    if isinstance(obj, (list, tuple)):
        try:
            return pd.DataFrame(list(obj))
        except Exception:
            return pd.DataFrame([{"value": json.dumps(obj, ensure_ascii=False)}])
    return pd.DataFrame([{"value": str(obj)}])


def run_endpoint(
    *,
    endpoint_name: str,
    target_table: str | None = None,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    call_timeout: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Generic runner for akshare_catalog endpoints.

    Params are designed to be passed via `data_jobs.params` / `data_job_executions.params`.
    """
    provider = AkshareToMySql(DB_CONFIG, logger=logger)

    args = list(args or [])
    kwargs = dict(kwargs or {})
    if call_timeout is not None:
        kwargs["_call_timeout"] = int(call_timeout)

    table = target_table or make_akcat_table_name(endpoint_name)

    raw = provider.fetch_ak_data(endpoint_name, *args, **kwargs)
    df = _to_dataframe(raw)
    if df.empty:
        return {"success": True, "table": table, "rows": 0, "note": "empty"}

    # Normalize columns to something MySQL can reliably handle.
    df = df.copy()
    df.columns = normalize_mysql_column_names(list(df.columns))

    fetched_at = datetime.utcnow()
    try:
        h = pd.util.hash_pandas_object(df, index=False).astype("uint64")
        r_ids = [f"{endpoint_name}_{int(x):016x}" for x in h.values.tolist()]
    except Exception:
        # Fallback: keep uniqueness best-effort even if hashing fails.
        r_ids = [f"{endpoint_name}_{i}" for i in range(len(df))]

    df_to_write = df.copy()
    df_to_write.insert(0, "FETCHED_AT", fetched_at)
    df_to_write.insert(0, "R_ID", r_ids)

    if dry_run:
        return {
            "success": True,
            "table": table,
            "rows": int(len(df_to_write)),
            "dry_run": True,
        }

    provider.create_table_from_dataframe_if_not_exists(
        table_name=table, df=df, primary_key="R_ID", add_fetched_at=True
    )
    ok = provider.save_data(df_to_write, table, on_duplicate_update=True, unique_keys=["R_ID"])
    return {"success": bool(ok), "table": table, "rows": int(len(df_to_write))}


def run(
    endpoint_name: str,
    target_table: str | None = None,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    call_timeout: int | None = None,
    dry_run: bool = False,
) -> bool:
    """
    ScriptService default entrypoint.
    Return bool for legacy compatibility.
    """
    result = run_endpoint(
        endpoint_name=endpoint_name,
        target_table=target_table,
        args=args,
        kwargs=kwargs,
        call_timeout=call_timeout,
        dry_run=dry_run,
    )
    return bool(result.get("success"))
