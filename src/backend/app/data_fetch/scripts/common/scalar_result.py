from datetime import date
from typing import Any

import pandas as pd


def normalize_scalar_result(
    result: Any,
    source_symbol: str = "default",
    data_date: date | None = None,
) -> pd.DataFrame:
    if isinstance(result, pd.DataFrame):
        df = result.copy()
    elif result is None:
        return pd.DataFrame(columns=["symbol", "name", "data_date"])
    else:
        value = str(result).strip()
        if not value:
            return pd.DataFrame(columns=["symbol", "name", "data_date"])
        df = pd.DataFrame([{"symbol": source_symbol, "name": value}])

    if "symbol" not in df.columns:
        df["symbol"] = source_symbol
    if "name" not in df.columns and len(df.columns) == 1:
        df = df.rename(columns={df.columns[0]: "name"})
    if "data_date" not in df.columns:
        df["data_date"] = data_date or pd.Timestamp.now().date()
    return df[["symbol", "name", "data_date"]]
