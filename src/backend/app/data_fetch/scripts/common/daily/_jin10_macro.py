"""Helpers for Jin10 datacenter endpoints used by AkShare macro functions."""

from __future__ import annotations

import datetime as dt
import time
from typing import Iterable

import pandas as pd
import requests


JIN10_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36"
    ),
    "x-app-id": "rU6QIu7JHe2gOUeR",
    "x-csrf-token": "x-csrf-token",
    "x-version": "1.0.0",
}


def _date_before(value: object) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return (parsed.date() - dt.timedelta(days=1)).isoformat()


def fetch_jin10_list_v2(
    *,
    category: str,
    attr_id: str,
    symbol: str,
    value_columns: Iterable[str] = ("今值", "预测值", "前值"),
    timeout: int = 20,
    max_pages: int | None = None,
) -> pd.DataFrame:
    """Fetch the same list_v2 history endpoint used by AkShare Jin10 functions."""

    url = "https://datacenter-api.jin10.com/reports/list_v2"
    params = {
        "max_date": "",
        "category": category,
        "attr_id": str(attr_id),
        "_": str(int(round(time.time() * 1000))),
    }
    frames: list[pd.DataFrame] = []
    seen_max_dates: set[str] = set()
    expected_columns = ["日期", *list(value_columns)]
    page = 0

    while True:
        if max_pages is not None and page >= max_pages:
            break
        response = requests.get(url, params=params, headers=JIN10_HEADERS, timeout=timeout)
        response.raise_for_status()
        data = response.json().get("data") or {}
        values = data.get("values") or []
        if not values:
            break

        temp_df = pd.DataFrame(values)
        key_names = [item.get("name") for item in data.get("keys") or [] if item.get("name")]
        if key_names and len(key_names) == temp_df.shape[1]:
            temp_df.columns = key_names
        elif len(expected_columns) == temp_df.shape[1]:
            temp_df.columns = expected_columns
        else:
            temp_df = temp_df.iloc[:, : len(expected_columns)].copy()
            temp_df.columns = expected_columns[: temp_df.shape[1]]

        frames.append(temp_df)
        next_max_date = _date_before(temp_df.iloc[-1, 0])
        if not next_max_date or next_max_date in seen_max_dates:
            break
        seen_max_dates.add(next_max_date)
        params["max_date"] = next_max_date
        page += 1

    if not frames:
        return pd.DataFrame(columns=["商品", *expected_columns])

    result = pd.concat(frames, ignore_index=True)
    for column in expected_columns:
        if column not in result.columns:
            result[column] = pd.NA
    result = result[expected_columns].copy()
    result["商品"] = symbol
    result["日期"] = pd.to_datetime(result["日期"], errors="coerce").dt.date
    result = result.dropna(subset=["日期"])
    for column in expected_columns[1:]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result[["商品", *expected_columns]]
    result = result.drop_duplicates(subset=["商品", "日期"]).sort_values("日期")
    result.reset_index(drop=True, inplace=True)
    return result


def add_jin10_symbol_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Map AkShare/Jin10 source columns to the common storage fields."""

    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    if "日期" in result.columns:
        result["data_date"] = pd.to_datetime(result["日期"], errors="coerce").dt.date
        result = result.dropna(subset=["data_date"])
    elif "data_date" not in result.columns:
        result["data_date"] = pd.Timestamp.now().date()
    if "商品" in result.columns:
        result["symbol"] = result["商品"].astype(str)
        result["name"] = result["商品"].astype(str)
    else:
        if "symbol" not in result.columns:
            result["symbol"] = ""
        if "name" not in result.columns:
            result["name"] = ""
    return result


def fetch_jin10_opec_month(timeout: int = 20, max_dates: int | None = None) -> pd.DataFrame:
    """Fetch the same OPEC monthly report endpoints used by AkShare."""

    headers = {
        **JIN10_HEADERS,
        "accept": "*/*",
        "origin": "https://datacenter.jin10.com",
        "referer": "https://datacenter.jin10.com/reportType/dc_opec_report",
    }
    stamp = str(int(round(time.time() * 1000)))
    dates_url = "https://datacenter-api.jin10.com/reports/dates"
    response = requests.get(
        dates_url, params={"category": "opec", "_": stamp}, headers=headers, timeout=timeout
    )
    response.raise_for_status()
    dates = response.json().get("data") or []
    if max_dates is not None:
        dates = dates[:max_dates]

    wanted = [
        "阿尔及利亚",
        "安哥拉",
        "加蓬",
        "伊朗",
        "伊拉克",
        "科威特",
        "利比亚",
        "尼日利亚",
        "沙特",
        "阿联酋",
        "委内瑞拉",
        "欧佩克产量",
    ]
    rows: list[pd.Series] = []
    list_url = "https://datacenter-api.jin10.com/reports/list"
    for item in reversed(dates):
        params = {"category": "opec", "date": item, "_": str(int(round(time.time() * 1000)))}
        response = requests.get(list_url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json().get("data") or {}
        values = data.get("values") or []
        keys = [key.get("name") for key in data.get("keys") or [] if key.get("name")]
        if not values or not keys:
            continue
        temp_df = pd.DataFrame(values, columns=keys).T
        if temp_df.empty:
            continue
        temp_df.columns = temp_df.iloc[0, :]
        temp_df = temp_df.iloc[1:, :]
        temp_df = temp_df.loc[:, ~pd.Index(temp_df.columns).duplicated()].copy()
        available = [column for column in wanted if column in temp_df.columns]
        if not available:
            continue
        selected = temp_df[available].dropna(how="all")
        if selected.empty:
            continue
        row = selected.iloc[-2, :] if len(selected) >= 2 else selected.iloc[-1, :]
        row = row.reindex(wanted)
        row.name = item
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=["日期", *wanted])

    result = pd.DataFrame(rows)
    result.index.name = "日期"
    result.reset_index(inplace=True)
    for column in result.columns:
        if column != "日期":
            result[column] = pd.to_numeric(result[column], errors="coerce")
    result["日期"] = pd.to_datetime(result["日期"], errors="coerce").dt.date
    result = result.dropna(subset=["日期"]).sort_values("日期")
    result.reset_index(drop=True, inplace=True)
    return result
