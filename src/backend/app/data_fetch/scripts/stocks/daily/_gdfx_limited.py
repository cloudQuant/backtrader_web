"""Bounded Eastmoney shareholder-analysis fetch helpers."""

from __future__ import annotations

import pandas as pd
import requests

EASTMONEY_DATA_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def report_date(date: str) -> str:
    return "-".join([date[:4], date[4:6], date[6:]])


def fetch_report_pages(params: dict[str, str], max_pages: int = 1) -> pd.DataFrame:
    frames = []
    page_count = max(1, int(max_pages))
    for page in range(1, page_count + 1):
        page_params = dict(params)
        page_params["pageNumber"] = str(page)
        response = requests.get(EASTMONEY_DATA_URL, params=page_params, timeout=30)
        data_json = response.json()
        result = data_json.get("result") or {}
        data = result.get("data") or []
        if not data:
            break
        frames.append(pd.DataFrame(data))
        if page >= int(result.get("pages") or page):
            break
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _series(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series([pd.NA] * len(df), index=df.index)


def _numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _date(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce").dt.date
    return df


def free_holding_analyse(date: str, max_pages: int = 1) -> pd.DataFrame:
    params = {
        "sortColumns": "UPDATE_DATE,SECURITY_CODE,HOLDER_RANK",
        "sortTypes": "-1,1,1",
        "pageSize": "500",
        "pageNumber": "1",
        "reportName": "RPT_CUSTOM_F10_EH_FREEHOLDERS_JOIN_FREEHOLDER_SHAREANALYSIS",
        "columns": "ALL;D10_ADJCHRATE,D30_ADJCHRATE,D60_ADJCHRATE",
        "source": "WEB",
        "client": "WEB",
        "filter": f"(END_DATE='{report_date(date)}')",
    }
    raw = fetch_report_pages(params, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "序号": range(1, len(raw) + 1),
            "股东名称": _series(raw, "HOLDER_NAME"),
            "股东类型": _series(raw, "HOLDER_TYPE"),
            "股票代码": _series(raw, "SECURITY_CODE"),
            "股票简称": _series(raw, "SECURITY_NAME_ABBR"),
            "报告期": _series(raw, "END_DATE"),
            "期末持股-数量": _series(raw, "HOLD_NUM"),
            "期末持股-数量变化": _series(raw, "XZCHANGE"),
            "期末持股-数量变化比例": _series(raw, "HOLD_RATIO_CHANGE"),
            "期末持股-持股变动": _series(raw, "HOLDNUM_CHANGE_NAME"),
            "期末持股-流通市值": _series(raw, "HOLDER_MARKET_CAP"),
            "公告日": _series(raw, "UPDATE_DATE"),
            "公告日后涨跌幅-10个交易日": _series(raw, "D10_ADJCHRATE"),
            "公告日后涨跌幅-30个交易日": _series(raw, "D30_ADJCHRATE"),
            "公告日后涨跌幅-60个交易日": _series(raw, "D60_ADJCHRATE"),
        }
    )
    df["symbol"] = df["股票代码"].astype(str).str.strip().str.zfill(6)
    df["name"] = df["股票简称"].astype(str).str.strip()
    df["data_date"] = pd.to_datetime(df["报告期"], errors="coerce").dt.date
    _date(df, ["报告期", "公告日"])
    _numeric(
        df,
        [
            "期末持股-数量",
            "期末持股-数量变化",
            "期末持股-数量变化比例",
            "期末持股-流通市值",
            "公告日后涨跌幅-10个交易日",
            "公告日后涨跌幅-30个交易日",
            "公告日后涨跌幅-60个交易日",
        ],
    )
    return df


def free_holding_change(date: str, max_pages: int = 1) -> pd.DataFrame:
    params = {
        "sortColumns": "HOLDER_NUM,HOLDER_NEW",
        "sortTypes": "-1,-1",
        "pageSize": "500",
        "pageNumber": "1",
        "reportName": "RPT_FREEHOLDERS_BASIC_INFO",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "filter": f"(END_DATE='{report_date(date)}')",
    }
    raw = fetch_report_pages(params, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "序号": range(1, len(raw) + 1),
            "股东名称": _series(raw, "HOLDER_NAME"),
            "股东类型": _series(raw, "HOLDER_TYPE"),
            "报告期": _series(raw, "END_DATE"),
            "期末持股只数统计-总持有": _series(raw, "HOLDER_NUM"),
            "期末持股只数统计-新进": _series(raw, "HOLDADD_NUM"),
            "期末持股只数统计-增加": _series(raw, "HOLDUP_NUM"),
            "期末持股只数统计-减少": _series(raw, "HOLDDOWN_NUM"),
            "期末持股只数统计-不变": _series(raw, "HOLDUNCHANGED_NUM"),
            "流通市值统计": _series(raw, "HOLDER_MARKET_CAP"),
            "持有个股": _series(raw, "SEAB_JOIN"),
        }
    )
    df["symbol"] = df["股东名称"].astype(str).str.strip()
    df["name"] = df["股东类型"].astype(str).str.strip()
    df["data_date"] = pd.to_datetime(df["报告期"], errors="coerce").dt.date
    _date(df, ["报告期"])
    _numeric(
        df,
        [
            "期末持股只数统计-总持有",
            "期末持股只数统计-新进",
            "期末持股只数统计-增加",
            "期末持股只数统计-减少",
            "期末持股只数统计-不变",
            "流通市值统计",
        ],
    )
    return df


def _holding_statistics(
    date: str,
    *,
    report_name: str,
    max_pages: int = 1,
) -> pd.DataFrame:
    params = {
        "sortColumns": "STATISTICS_TIMES,COOPERATION_HOLDER_MARK",
        "sortTypes": "-1,-1",
        "pageSize": "500",
        "pageNumber": "1",
        "reportName": report_name,
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "filter": f"""(HOLDNUM_CHANGE_TYPE="001")(END_DATE='{report_date(date)}')""",
    }
    raw = fetch_report_pages(params, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "序号": range(1, len(raw) + 1),
            "股东名称": _series(raw, "HOLDER_NAME"),
            "股东类型": _series(raw, "HOLDER_TYPE"),
            "报告期": _series(raw, "END_DATE"),
            "统计次数": _series(raw, "STATISTICS_TIMES"),
            "公告日后涨幅统计-10个交易日-平均涨幅": _series(raw, "AVG_CHANGE_10TD"),
            "公告日后涨幅统计-10个交易日-最大涨幅": _series(raw, "MAX_CHANGE_10TD"),
            "公告日后涨幅统计-10个交易日-最小涨幅": _series(raw, "MIN_CHANGE_10TD"),
            "公告日后涨幅统计-30个交易日-平均涨幅": _series(raw, "AVG_CHANGE_30TD"),
            "公告日后涨幅统计-30个交易日-最大涨幅": _series(raw, "MAX_CHANGE_30TD"),
            "公告日后涨幅统计-30个交易日-最小涨幅": _series(raw, "MIN_CHANGE_30TD"),
            "公告日后涨幅统计-60个交易日-平均涨幅": _series(raw, "AVG_CHANGE_60TD"),
            "公告日后涨幅统计-60个交易日-最大涨幅": _series(raw, "MAX_CHANGE_60TD"),
            "公告日后涨幅统计-60个交易日-最小涨幅": _series(raw, "MIN_CHANGE_60TD"),
            "持有个股": _series(raw, "SEAB_JOIN"),
        }
    )
    df["symbol"] = df["股东名称"].astype(str).str.strip()
    df["name"] = df["股东类型"].astype(str).str.strip()
    df["data_date"] = pd.to_datetime(df["报告期"], errors="coerce").dt.date
    _date(df, ["报告期"])
    _numeric(
        df,
        [
            "统计次数",
            "公告日后涨幅统计-10个交易日-平均涨幅",
            "公告日后涨幅统计-10个交易日-最大涨幅",
            "公告日后涨幅统计-10个交易日-最小涨幅",
            "公告日后涨幅统计-30个交易日-平均涨幅",
            "公告日后涨幅统计-30个交易日-最大涨幅",
            "公告日后涨幅统计-30个交易日-最小涨幅",
            "公告日后涨幅统计-60个交易日-平均涨幅",
            "公告日后涨幅统计-60个交易日-最大涨幅",
            "公告日后涨幅统计-60个交易日-最小涨幅",
        ],
    )
    return df


def free_holding_statistics(date: str, max_pages: int = 1) -> pd.DataFrame:
    return _holding_statistics(
        date,
        report_name="RPT_COOPFREEHOLDERS_ANALYSIS",
        max_pages=max_pages,
    )


def holding_statistics(date: str, max_pages: int = 1) -> pd.DataFrame:
    return _holding_statistics(
        date,
        report_name="RPT_COOPHOLDERS_ANALYSIS",
        max_pages=max_pages,
    )


def free_holding_teamwork(symbol: str = "社保", max_pages: int = 1) -> pd.DataFrame:
    params = {
        "sortColumns": "COOPERAT_NUM,HOLDER_NEW,COOPERAT_HOLDER_NEW",
        "sortTypes": "-1,-1,-1",
        "pageSize": "500",
        "pageNumber": "1",
        "reportName": "RPT_COOPFREEHOLDER",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
    }
    if symbol != "全部":
        params["filter"] = f'(HOLDER_TYPE="{symbol}")'
    raw = fetch_report_pages(params, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "序号": range(1, len(raw) + 1),
            "股东名称": _series(raw, "HOLDER_NAME"),
            "股东类型": _series(raw, "HOLDER_TYPE"),
            "协同股东名称": _series(raw, "COOPERAT_HOLDER_NAME"),
            "协同股东类型": _series(raw, "COOPERAT_HOLDER_TYPE"),
            "协同次数": _series(raw, "COOPERAT_NUM"),
            "个股详情": _series(raw, "COOPERAT_SECURITYDATE"),
        }
    )
    df["symbol"] = df["股东名称"].astype(str).str.strip()
    df["name"] = df["协同股东名称"].astype(str).str.strip()
    df["data_date"] = pd.Timestamp.now().date()
    _numeric(df, ["协同次数"])
    return df
