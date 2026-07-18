"""Fallback currency data derived from AkShare-backed local tables."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import mysql.connector
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG

CURRENCY_NAME_TO_CODE: dict[str, str] = {
    "美元": "USD",
    "欧元": "EUR",
    "日元": "JPY",
    "港元": "HKD",
    "英镑": "GBP",
    "澳元": "AUD",
    "新西兰元": "NZD",
    "新加坡元": "SGD",
    "瑞士法郎": "CHF",
    "加元": "CAD",
    "澳门元": "MOP",
    "林吉特": "MYR",
    "卢布": "RUB",
    "兰特": "ZAR",
    "韩元": "KRW",
    "迪拉姆": "AED",
    "里亚尔": "SAR",
    "福林": "HUF",
    "兹罗提": "PLN",
    "丹麦克朗": "DKK",
    "瑞典克朗": "SEK",
    "挪威克朗": "NOK",
    "里拉": "TRY",
    "比索": "MXN",
    "泰铢": "THB",
}

CODE_TO_NAME = {code: name for name, code in CURRENCY_NAME_TO_CODE.items()}

# SAFE keeps some currencies as CNY per 100 foreign units and others as
# foreign units per 100 CNY. Normalize both into CNY per 1 foreign unit.
SAFE_DIRECT_CODES = {
    "USD",
    "EUR",
    "JPY",
    "HKD",
    "GBP",
    "AUD",
    "NZD",
    "SGD",
    "CHF",
    "CAD",
}


def _connect() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**DB_CONFIG)


def _read_sql(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    conn = _connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return pd.DataFrame(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()


def _normalize_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _today() -> date:
    return datetime.now().date()


def _parse_symbol_list(symbols: str | None) -> list[str]:
    if not symbols:
        return []
    return [
        item.strip().upper() for item in str(symbols).replace(";", ",").split(",") if item.strip()
    ]


def _currency_filters(symbols: str | None, base: str | None = None) -> list[str]:
    requested = _parse_symbol_list(symbols)
    if requested:
        return requested
    excluded = {str(base or "").upper()} if base else set()
    return [code for code in CURRENCY_NAME_TO_CODE.values() if code not in excluded]


def _boc_safe_columns() -> list[str]:
    try:
        desc = _read_sql("DESCRIBE `CURRENCY_BOC_SAFE`")
    except Exception:
        return []
    fields = set(desc["Field"].astype(str).tolist())
    return [name for name in CURRENCY_NAME_TO_CODE if name in fields]


def _boc_safe_rows(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    latest_only: bool = False,
) -> pd.DataFrame:
    columns = _boc_safe_columns()
    if not columns:
        return pd.DataFrame()

    quoted_columns = ", ".join(f"`{name}`" for name in columns)
    where: list[str] = []
    params: list[Any] = []
    if start_date:
        where.append("`日期` >= %s")
        params.append(start_date)
    if end_date:
        where.append("`日期` <= %s")
        params.append(end_date)

    where_sql = f" WHERE {' AND '.join(where)}" if where else ""
    limit_sql = " LIMIT 1" if latest_only else ""
    sql = (
        f"SELECT `日期`, {quoted_columns} FROM `CURRENCY_BOC_SAFE`"
        f"{where_sql} ORDER BY `日期` DESC{limit_sql}"
    )
    try:
        df = _read_sql(sql, tuple(params))
    except Exception:
        return pd.DataFrame()
    if "日期" in df.columns:
        df = df.drop_duplicates(subset=["日期"], keep="first")
    return df


def _boc_rates_for_row(row: pd.Series) -> dict[str, float]:
    rates = {"CNY": 1.0}
    for name, code in CURRENCY_NAME_TO_CODE.items():
        value = pd.to_numeric(row.get(name), errors="coerce")
        if pd.isna(value) or float(value) == 0:
            continue
        raw = float(value)
        rates[code] = raw / 100 if code in SAFE_DIRECT_CODES else 100 / raw
    return rates


def _latest_boc_rates() -> tuple[str | None, dict[str, float]]:
    rows = _boc_safe_rows(latest_only=True)
    if rows.empty:
        return None, {}
    row = rows.iloc[0]
    data_date = _normalize_date(row.get("日期"))
    return data_date, _boc_rates_for_row(row)


def _latest_spot_rates() -> tuple[str | None, dict[str, float]]:
    try:
        df = _read_sql(
            "SELECT `代码`, `名称`, `最新价`, `data_date` "
            "FROM `FOREX_SPOT_EM` ORDER BY `data_date` DESC, `R_ID` DESC"
        )
    except Exception:
        return None, {}
    if df.empty:
        return None, {}

    data_date = _normalize_date(df.iloc[0].get("data_date"))
    rates = {"CNY": 1.0, "CNH": 1.0}
    for _, row in df.iterrows():
        code = str(row.get("代码") or "").upper()
        price = pd.to_numeric(row.get("最新价"), errors="coerce")
        if not code or pd.isna(price) or float(price) == 0:
            continue
        value = float(price)
        if code.startswith(("CNY", "CNH")) and len(code) >= 6:
            target = code[3:6]
            rates[target] = 1 / value
        elif code.endswith("CNYC") and len(code) >= 7:
            source = code[:-4]
            rates.setdefault(source, value)
        elif code.endswith("CNH") and len(code) == 6:
            source = code[:3]
            rates.setdefault(source, value)
    return data_date, rates


def _latest_rates() -> tuple[str | None, dict[str, float]]:
    data_date, rates = _latest_spot_rates()
    if len(rates) > 2:
        return data_date, rates
    return _latest_boc_rates()


def _rate_records(
    *,
    base: str,
    symbols: str | None,
    data_date: str,
    cny_per_unit: dict[str, float],
) -> pd.DataFrame:
    base_code = str(base or "USD").upper()
    base_rate = cny_per_unit.get(base_code)
    if base_rate is None:
        return pd.DataFrame()

    records = []
    for code in _currency_filters(symbols, base_code):
        quote_rate = cny_per_unit.get(code)
        if quote_rate is None or quote_rate == 0:
            continue
        records.append(
            {
                "symbol": code,
                "name": CODE_TO_NAME.get(code, code),
                "currency": code,
                "date": data_date,
                "base": base_code,
                "rates": base_rate / quote_rate,
                "data_date": data_date,
                "source": "akshare_data_fallback",
            }
        )
    return pd.DataFrame(records)


def build_currency_currencies_fallback(c_type: str = "fiat", **_: Any) -> pd.DataFrame:
    data_date, rates = _latest_rates()
    if not rates:
        return pd.DataFrame()
    records = [
        {
            "symbol": "CNY",
            "name": "人民币",
            "currency": "CNY",
            "type": c_type,
            "data_date": data_date or _today(),
            "source": "akshare_data_fallback",
        }
    ]
    records.extend(
        {
            "symbol": code,
            "name": CODE_TO_NAME.get(code, code),
            "currency": code,
            "type": c_type,
            "data_date": data_date or _today(),
            "source": "akshare_data_fallback",
        }
        for code in sorted(code for code in rates if code not in {"CNY", "CNH"})
    )
    return pd.DataFrame(records)


def build_currency_latest_fallback(
    base: str = "USD",
    symbols: str = "",
    **_: Any,
) -> pd.DataFrame:
    data_date, rates = _latest_rates()
    if not data_date or not rates:
        return pd.DataFrame()
    return _rate_records(base=base, symbols=symbols, data_date=data_date, cny_per_unit=rates)


def build_currency_history_fallback(
    base: str = "USD",
    date: str = "",
    symbols: str = "",
    **_: Any,
) -> pd.DataFrame:
    target_date = _normalize_date(date) or _today().isoformat()
    rows = _boc_safe_rows(end_date=target_date, latest_only=True)
    if rows.empty:
        return pd.DataFrame()
    row = rows.iloc[0]
    data_date = _normalize_date(row.get("日期"))
    if not data_date:
        return pd.DataFrame()
    return _rate_records(
        base=base,
        symbols=symbols,
        data_date=data_date,
        cny_per_unit=_boc_rates_for_row(row),
    )


def build_currency_time_series_fallback(
    base: str = "USD",
    start_date: str = "",
    end_date: str = "",
    symbols: str = "",
    **_: Any,
) -> pd.DataFrame:
    start = _normalize_date(start_date)
    end = _normalize_date(end_date) or _today().isoformat()
    rows = _boc_safe_rows(start_date=start, end_date=end)
    if rows.empty:
        return pd.DataFrame()

    frames = []
    for _, row in rows.iterrows():
        data_date = _normalize_date(row.get("日期"))
        if not data_date:
            continue
        frame = _rate_records(
            base=base,
            symbols=symbols,
            data_date=data_date,
            cny_per_unit=_boc_rates_for_row(row),
        )
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_currency_convert_fallback(
    base: str = "USD",
    to: str = "CNY",
    amount: str | int | float = "10000",
    **_: Any,
) -> pd.DataFrame:
    data_date, rates = _latest_rates()
    base_code = str(base or "USD").upper()
    quote_code = str(to or "CNY").upper()
    base_rate = rates.get(base_code)
    quote_rate = rates.get(quote_code)
    value = pd.to_numeric(amount, errors="coerce")
    if not data_date or base_rate is None or quote_rate is None or pd.isna(value):
        return pd.DataFrame()

    rate = base_rate / quote_rate
    converted = float(value) * rate
    return pd.DataFrame(
        [
            {
                "symbol": f"{base_code}_{quote_code}",
                "name": f"{base_code} to {quote_code}",
                "base": base_code,
                "to": quote_code,
                "amount": float(value),
                "rate": rate,
                "result": converted,
                "item": "result",
                "value": converted,
                "date": data_date,
                "data_date": data_date,
                "source": "akshare_data_fallback",
            }
        ]
    )


def build_currency_pair_map_fallback(symbol: str = "", **_: Any) -> pd.DataFrame:
    try:
        df = _read_sql(
            "SELECT `代码`, `名称`, `最新价`, `data_date` "
            "FROM `FOREX_SPOT_EM` ORDER BY `data_date` DESC, `R_ID` DESC"
        )
    except Exception:
        df = pd.DataFrame()
    if df.empty:
        return build_currency_currencies_fallback()

    keyword = str(symbol or "").strip()
    if keyword:
        df = df[df["名称"].astype(str).str.contains(keyword, na=False)]
    if df.empty:
        return build_currency_currencies_fallback()

    result = df.rename(columns={"代码": "symbol", "名称": "name", "最新价": "latest"})
    result["code"] = result["symbol"]
    result["data_date"] = pd.to_datetime(result["data_date"], errors="coerce").dt.date
    result["source"] = "akshare_data_fallback"
    return result[["symbol", "name", "code", "latest", "data_date", "source"]]
