"""
Helpers for the current Yien/Endata box-office API.

The old AkShare implementations used www.endata.com.cn/API/GetData.ashx.
The public site now serves the same box-office product from ys.endata.cn
through /enlib-api/api endpoints.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from functools import cached_property
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

BASE_URL = "https://ys.endata.cn"
API_BASE = f"{BASE_URL}/enlib-api/api"

MOVIE_WEEK_COLUMNS = "100,102,103,119,105,107,109,106,112,129,142,143,163,164,165"
MOVIE_MONTH_COLUMNS = "100,101,102,130,127,103,104,105,148,149"
MOVIE_YEAR_COLUMNS = "100,201,101,102,107,115,103,116,104,117,118,105,106"
CINEMA_COLUMNS = "100,101,102,121,122,103,104,108,123,109"


def normalize_date(value: str | date | datetime | None) -> str:
    if value is None:
        raise ValueError("date value is required")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return datetime.fromisoformat(text).date().isoformat()


def normalize_year(value: str | date | datetime | int | None, default_year: int) -> int:
    if value is None:
        return default_year
    if isinstance(value, int):
        return value
    if isinstance(value, (date, datetime)):
        return value.year
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return default_year


class EndataYienClient:
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/BoxOffice/Movie",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        self.session.get(f"{BASE_URL}/BoxOffice/Movie", timeout=self.timeout)

    def api(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        payload = {"r": random.random()}
        payload.update(params or {})
        response = self.session.post(
            f"{API_BASE}{endpoint}",
            data=urlencode(payload, doseq=True).encode(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if str(data.get("status")) != "1":
            raise RuntimeError(f"Endata API error {endpoint}: {data.get('des')}")
        return data.get("data")

    @cached_property
    def date_data(self) -> dict[str, Any]:
        data = self.api("/moviecommon/getCommon_DateList.do")
        if not isinstance(data, dict):
            raise RuntimeError("Endata date list returned an unexpected payload")
        return data

    @property
    def date_summary(self) -> dict[str, Any]:
        table = self.date_data.get("table0") or []
        return table[0] if table else {}

    def now_date(self) -> str:
        now = self.date_summary.get("NowDate")
        if now:
            return normalize_date(now)
        return date.today().isoformat()

    def latest_completed_day(self) -> str:
        return (datetime.fromisoformat(self.now_date()).date() - timedelta(days=1)).isoformat()

    def latest_week(self) -> dict[str, Any]:
        rows = self.date_data.get("table1") or []
        if not rows:
            raise RuntimeError("Endata date list has no weekly rows")
        return rows[0]

    def month_for_date(self, value: str | date | datetime | None = None) -> dict[str, Any]:
        target = datetime.fromisoformat(normalize_date(value or self.now_date())).date()
        rows = self.date_data.get("table2") or []
        for row in rows:
            start = datetime.fromisoformat(row["SDate"]).date()
            end = datetime.fromisoformat(row["EDate"]).date()
            if start <= target <= end:
                return row
        if rows:
            return rows[0]
        raise RuntimeError("Endata date list has no monthly rows")

    def fetch_paged(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        page_size: int,
        list_name: str = "table1",
        total_name: str = "table2",
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        first_params = dict(params, pageindex=1, pagesize=page_size)
        data = self.api(endpoint, first_params)
        if not isinstance(data, dict):
            raise RuntimeError(f"Endata API returned an unexpected payload: {endpoint}")

        rows = list(data.get(list_name) or [])
        total_rows = data.get(total_name) or []
        total = total_rows[0] if total_rows else {}
        total_pages = int(total.get("TotalPage") or 1)

        for page in range(2, total_pages + 1):
            page_data = self.api(endpoint, dict(params, pageindex=page, pagesize=page_size))
            if not isinstance(page_data, dict):
                raise RuntimeError(f"Endata API returned an unexpected page: {endpoint}#{page}")
            rows.extend(page_data.get(list_name) or [])
        return rows, data

    def fetch_movie_day(self, value: str | date | datetime | None = None) -> pd.DataFrame:
        data_date = normalize_date(value or self.latest_completed_day())
        rows, payload = self.fetch_paged(
            "/movie/getMovie_BoxOffice_Day_List.do",
            {
                "datetype": "Day",
                "date": data_date,
                "sdate": data_date,
                "edate": data_date,
                "columnslist": MOVIE_WEEK_COLUMNS,
                "order": "103",
                "ordertype": "desc",
            },
            page_size=10000,
        )
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        total = (payload.get("table0") or [{}])[0]
        df["data_date"] = data_date
        df["source_update_time"] = total.get("UpTime")
        df["fetched_at"] = datetime.now()
        return df

    def fetch_movie_realtime(self, value: str | date | datetime | None = None) -> pd.DataFrame:
        data_date = normalize_date(value or self.now_date())
        df = self.fetch_movie_day(data_date)
        if not df.empty:
            df["snapshot_date"] = data_date
        return df

    def fetch_movie_month(self, value: str | date | datetime | None = None) -> pd.DataFrame:
        month = self.month_for_date(value)
        rows, _ = self.fetch_paged(
            "/movie/getMovie_BoxOffice_Month_List.do",
            {
                "datetype": "Month",
                "date": f"{month['SDate']},{month['EDate']}",
                "sdate": month["SDate"],
                "edate": month["EDate"],
                "dateid": month["MonthID"],
                "sdateid": month["MonthID"],
                "edateid": month["MonthID"],
                "columnslist": MOVIE_MONTH_COLUMNS,
                "order": "102",
                "ordertype": "desc",
            },
            page_size=10000,
        )
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["month_id"] = month["MonthID"]
        df["period_start"] = month["SDate"]
        df["period_end"] = month["EDate"]
        df["data_date"] = month["SDate"]
        df["fetched_at"] = datetime.now()
        return df

    def fetch_movie_week(self, value: str | date | datetime | None = None) -> pd.DataFrame:
        week = self.latest_week()
        if value is not None:
            target = datetime.fromisoformat(normalize_date(value)).date()
            for row in self.date_data.get("table1") or []:
                start = datetime.fromisoformat(row["SDate"]).date()
                end = datetime.fromisoformat(row["EDate"]).date()
                if start <= target <= end:
                    week = row
                    break

        data = self.api(
            "/movie/getMovie_BoxOffice_Day_Chart.do",
            {
                "datetype": "Week",
                "date": f"{week['SDate']},{week['EDate']}",
                "sdate": week["SDate"],
                "edate": week["EDate"],
                "dateid": week["WeekID"],
                "sdateid": week["WeekID"],
                "edateid": week["WeekID"],
            },
        )
        if not isinstance(data, dict):
            raise RuntimeError("Endata weekly movie chart returned an unexpected payload")

        df = pd.DataFrame(data.get("table0") or [])
        if df.empty:
            return df
        total = (data.get("table3") or [{}])[0]
        df["week_id"] = week["WeekID"]
        df["week_start"] = week["SDate"]
        df["week_end"] = week["EDate"]
        df["data_date"] = week["SDate"]
        df["source_update_time"] = total.get("UpTime")
        df["fetched_at"] = datetime.now()
        return df

    def fetch_movie_year(self, value: str | date | datetime | int | None = None) -> pd.DataFrame:
        year = normalize_year(value, datetime.fromisoformat(self.now_date()).year)
        rows, _ = self.fetch_paged(
            "/movie/getMovie_BoxOffice_Year_List.do",
            {
                "datetype": "Year",
                "columnslist": MOVIE_YEAR_COLUMNS,
                "order": "102",
                "ordertype": "desc",
            },
            page_size=30000,
        )
        df = pd.DataFrame(rows)
        if df.empty or "Year" not in df.columns:
            return pd.DataFrame()
        df = df[df["Year"].astype("Int64") == year].copy()
        if df.empty:
            return df
        df["SourceIrank"] = df["Irank"]
        df = df.sort_values("BoxOffice", ascending=False).reset_index(drop=True)
        df["Irank"] = range(1, len(df) + 1)
        df["data_year"] = year
        df["data_date"] = f"{year}-12-31"
        df["fetched_at"] = datetime.now()
        return df

    def fetch_movie_year_first_week(
        self, value: str | date | datetime | int | None = None
    ) -> pd.DataFrame:
        df = self.fetch_movie_year(value)
        if df.empty or "WeekBoxOffice" not in df.columns:
            return pd.DataFrame()
        target_year = int(df["data_year"].dropna().iloc[0]) if "data_year" in df.columns else None
        if target_year and "ReleaseDate" in df.columns:
            release_year = pd.to_datetime(df["ReleaseDate"], errors="coerce").dt.year
            df = df[release_year == target_year].copy()
        df = df[df["WeekBoxOffice"].notna()].copy()
        if df.empty:
            return df
        df = df.sort_values("WeekBoxOffice", ascending=False).reset_index(drop=True)
        df["YearRank"] = df["Irank"]
        df["Irank"] = range(1, len(df) + 1)
        df["FirstWeekBoxOffice"] = df["WeekBoxOffice"]
        if "BoxOffice" in df.columns:
            df["FirstWeekBoxPercent"] = (
                pd.to_numeric(df["WeekBoxOffice"], errors="coerce")
                / pd.to_numeric(df["BoxOffice"], errors="coerce")
                * 100
            )
        return df

    def fetch_cinema_day(self, value: str | date | datetime | None = None) -> pd.DataFrame:
        data_date = normalize_date(value or self.latest_completed_day())
        rows, _ = self.fetch_paged(
            "/cinema/getcinemaboxoffice_day_list.do",
            {
                "datetype": "Day",
                "date": data_date,
                "sdate": data_date,
                "edate": data_date,
                "columnslist": CINEMA_COLUMNS,
                "order": "102",
                "ordertype": "desc",
            },
            page_size=20000,
        )
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["data_date"] = data_date
        df["fetched_at"] = datetime.now()
        return df

    def fetch_cinema_week(self, value: str | date | datetime | None = None) -> pd.DataFrame:
        week = self.latest_week()
        if value is not None:
            target = datetime.fromisoformat(normalize_date(value)).date()
            for row in self.date_data.get("table1") or []:
                start = datetime.fromisoformat(row["SDate"]).date()
                end = datetime.fromisoformat(row["EDate"]).date()
                if start <= target <= end:
                    week = row
                    break

        rows, _ = self.fetch_paged(
            "/cinema/getcinemaboxoffice_week_list.do",
            {
                "datetype": "Week",
                "date": f"{week['SDate']},{week['EDate']}",
                "sdate": week["SDate"],
                "edate": week["EDate"],
                "dateid": week["WeekID"],
                "sdateid": week["WeekID"],
                "edateid": week["WeekID"],
                "columnslist": CINEMA_COLUMNS,
                "order": "102",
                "ordertype": "desc",
            },
            page_size=20000,
        )
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["week_id"] = week["WeekID"]
        df["week_start"] = week["SDate"]
        df["week_end"] = week["EDate"]
        df["data_date"] = week["SDate"]
        df["fetched_at"] = datetime.now()
        return df
