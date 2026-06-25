from __future__ import annotations

from typing import Any

import pandas as pd


def flatten_dict_result(
    result: Any,
    *,
    key_column: str = "symbol",
    data_date: str | None = None,
) -> pd.DataFrame:
    """Flatten AkShare dict-of-DataFrame results into one DataFrame."""
    if isinstance(result, pd.DataFrame):
        df = result.copy()
    elif isinstance(result, dict):
        frames = []
        for key, value in result.items():
            if not isinstance(value, pd.DataFrame) or value.empty:
                continue
            frame = value.copy()
            if key_column in frame.columns:
                frame.insert(0, "result_key", str(key))
            else:
                frame.insert(0, key_column, str(key))
            frames.append(frame)
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        df = pd.DataFrame()

    if df.empty:
        return df

    if "data_date" not in df.columns:
        parsed = pd.to_datetime(data_date, format="%Y%m%d", errors="coerce")
        df["data_date"] = parsed.date() if not pd.isna(parsed) else pd.Timestamp.now().date()
    return df
