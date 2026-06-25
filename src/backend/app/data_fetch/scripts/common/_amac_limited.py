"""Bounded AMAC public-disclosure fetch helpers."""

from __future__ import annotations

import pandas as pd
import requests
from akshare.fund.fund_amac import _post_json, headers


AMAC_BASE_URL = "https://gs.amac.org.cn/amac-infodisc/api"


def _fetch_content(endpoint: str, *, page_size: int, max_pages: int) -> pd.DataFrame:
    session = requests.Session()
    frames = []
    for page in range(max(1, int(max_pages))):
        params = {
            "rand": "0.7665138514630696",
            "page": str(page),
            "size": str(page_size),
        }
        data_json = _post_json(
            f"{AMAC_BASE_URL}/{endpoint}",
            params=params,
            json={},
            verify=False,
            headers=headers,
            session=session,
            timeout=8,
            max_retries=1,
            retry_delay=0.2,
        )
        data = data_json.get("content") or []
        if not data:
            break
        frames.append(pd.DataFrame(data))
        total_pages = int(data_json.get("totalPages") or page + 1)
        if page + 1 >= total_pages:
            break
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _ms_date(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    parsed_ms = pd.to_datetime(values, unit="ms", errors="coerce")
    parsed_text = pd.to_datetime(series, errors="coerce")
    return parsed_ms.fillna(parsed_text).dt.date


def _standardize(
    df: pd.DataFrame,
    *,
    symbol_col: str,
    name_col: str,
    date_col: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["symbol"] = df[symbol_col].astype(str).str.strip()
    df["name"] = df[name_col].astype(str).str.strip()
    df["data_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    return df


def amac_fund_abs(max_pages: int = 1) -> pd.DataFrame:
    raw = _fetch_content("fund/abs", page_size=100, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "编号": range(1, len(raw) + 1),
            "备案编号": raw["productCode"],
            "专项计划全称": raw["productName"],
            "管理人": raw["orgName"],
            "托管人": raw["trustee"],
            "成立日期": _ms_date(raw["fundFoundDate"]),
            "预期到期时间": _ms_date(raw["fundDueDate"]),
            "备案通过时间": _ms_date(raw["registeredDate"]),
        }
    )
    return _standardize(
        df,
        symbol_col="备案编号",
        name_col="专项计划全称",
        date_col="备案通过时间",
    )


def amac_fund_account_info(max_pages: int = 1) -> pd.DataFrame:
    raw = _fetch_content("fund/account", page_size=20, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "成立日期": _ms_date(raw["registerDate"]),
            "产品编码": raw["registerCode"],
            "产品名称": raw["name"],
            "管理人名称": raw["manager"],
        }
    )
    return _standardize(df, symbol_col="产品编码", name_col="产品名称", date_col="成立日期")


def amac_fund_sub_info(max_pages: int = 1) -> pd.DataFrame:
    raw = _fetch_content("pof/subfund", page_size=20, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "产品编码": raw["productCode"],
            "产品名称": raw["productName"],
            "私募基金管理人名称": raw["mgrName"],
            "托管人名称": raw["trustee"],
            "成立日期": _ms_date(raw["foundDate"]),
            "备案日期": _ms_date(raw["registeredDate"]),
        }
    )
    return _standardize(df, symbol_col="产品编码", name_col="产品名称", date_col="备案日期")


def amac_futures_info(max_pages: int = 1) -> pd.DataFrame:
    raw = _fetch_content("pof/futures", page_size=20, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "产品名称": raw["mpiName"],
            "产品编码": raw["mpiProductCode"],
            "管理人名称": raw["aoiName"],
            "托管人名称": raw["mpiTrustee"],
            "成立日期": _ms_date(raw["mpiCreateDate"]),
            "投资类型": raw["tzlx"],
            "是否分级": raw["sfjgh"],
            "备案日期": _ms_date(raw["registeredDate"]),
            "到期日": _ms_date(raw["dueDate"]),
            "运作状态": raw["fundStatus"],
        }
    )
    return _standardize(df, symbol_col="产品编码", name_col="产品名称", date_col="备案日期")


def amac_manager_cancelled_info(max_pages: int = 1) -> pd.DataFrame:
    raw = _fetch_content("cancelled/manager", page_size=20, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "管理人名称": raw["orgName"],
            "统一社会信用代码": raw["orgCode"],
            "登记时间": _ms_date(raw["orgSignDate"]),
            "注销时间": _ms_date(raw["cancelDate"]),
            "注销类型": raw["status"],
        }
    )
    return _standardize(
        df,
        symbol_col="统一社会信用代码",
        name_col="管理人名称",
        date_col="注销时间",
    )


def amac_member_sub_info(max_pages: int = 1) -> pd.DataFrame:
    raw = _fetch_content("pof/pofMember", page_size=20, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "机构（会员）名称": raw["managerName"],
            "会员代表": raw["memberBehalf"],
            "会员类型": raw["memberType"],
            "会员编号": raw["memberCode"],
            "入会时间": _ms_date(raw["memberDate"]),
            "公司类型": raw["primaryInvestType"],
        }
    )
    return _standardize(
        df,
        symbol_col="会员编号",
        name_col="机构（会员）名称",
        date_col="入会时间",
    )


def amac_securities_info(max_pages: int = 1) -> pd.DataFrame:
    raw = _fetch_content("pof/securities", page_size=20, max_pages=max_pages)
    if raw.empty:
        return raw
    df = pd.DataFrame(
        {
            "产品名称": raw["cpmc"],
            "产品编码": raw["cpbm"],
            "管理人名称": raw["gljg"],
            "成立日期": _ms_date(raw["slrq"]),
            "到期时间": _ms_date(raw["dqr"]),
            "投资类型": raw["tzlx"],
            "是否分级": raw["sffj"],
            "托管人名称": raw["tgjg"],
            "备案日期": _ms_date(raw["barq"]),
            "运作状态": raw["yzzt"],
        }
    )
    return _standardize(df, symbol_col="产品编码", name_col="产品名称", date_col="备案日期")
