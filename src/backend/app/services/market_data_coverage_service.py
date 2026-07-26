"""Market data coverage and quality inspection service."""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text

from app.db.akshare_data_database import _get_akshare_data_engine
from app.db.database import async_session_maker
from app.models.market_data_trust import (
    MarketDataCoverageModel,
    MarketDataQualityReportModel,
)
from app.schemas.market_data_trust import (
    MarketDataCoverageMatrixResponse,
    MarketDataCoverageResponse,
    MarketDataQualityReportResponse,
)
from app.services.asset_spec_service import infer_asset_type

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DATA_ROOT = _REPO_ROOT / "data" / "datas"
_DATE_KEYS = ("datetime", "date", "trade_date", "TRADE_DATE", "Date", "DATE")
_OPEN_KEYS = ("open", "OPEN", "OPEN_PRICE")
_HIGH_KEYS = ("high", "HIGH", "HIGH_PRICE")
_LOW_KEYS = ("low", "LOW", "LOW_PRICE")
_CLOSE_KEYS = ("close", "CLOSE", "CLOSE_PRICE", "price")
_VOLUME_KEYS = ("volume", "VOLUME", "VOL")
# The local quality checker deliberately keeps a small, versioned calendar
# baseline instead of calling a network calendar provider during a backtest
# precheck.  Weekends are handled separately; this set covers the statutory
# closures exercised by the deterministic RB0 fixtures and can be extended as
# local fixtures are added.
_CN_FUTURES_CLOSURE_DATES = {
    date(2024, 1, 1),
    date(2024, 2, 9),
    date(2024, 2, 12),
    date(2024, 2, 13),
    date(2024, 2, 14),
    date(2024, 2, 15),
    date(2024, 2, 16),
    date(2024, 4, 4),
    date(2024, 4, 5),
    date(2024, 5, 1),
    date(2024, 5, 2),
    date(2024, 5, 3),
    date(2024, 6, 10),
    date(2024, 9, 16),
    date(2024, 9, 17),
    date(2024, 10, 1),
    date(2024, 10, 2),
    date(2024, 10, 3),
    date(2024, 10, 4),
    date(2024, 10, 7),
}


@dataclass(frozen=True)
class WarehouseCoverageProfile:
    """A stable, user-facing market data source in the AkShare warehouse."""

    asset_type: str
    table_name: str
    symbol_expression: str
    date_column: str
    timeframe: str = "1d"


_WAREHOUSE_COVERAGE_PROFILES = (
    WarehouseCoverageProfile(
        "stock",
        "STOCK_ZH_A_HIST",
        "COALESCE(NULLIF(symbol, ''), `股票代码`)",
        "data_date",
    ),
    WarehouseCoverageProfile("futures", "FUTURES_DAILY_MARKET", "SYMBOL", "TRADE_DATE"),
    WarehouseCoverageProfile("bond", "BOND_ZH_HS_COV_MIN", "symbol", "data_date"),
    WarehouseCoverageProfile("fund", "FUND_ETF_HIST_SINA", "symbol", "data_date"),
    WarehouseCoverageProfile(
        "option",
        "OPTION_CURRENT_EM",
        "COALESCE(NULLIF(symbol, ''), `代码`)",
        "data_date",
    ),
    WarehouseCoverageProfile("fx", "CURRENCY_HISTORY", "symbol", "data_date"),
    WarehouseCoverageProfile("crypto", "CRYPTO_BITCOIN_CME", "'BTC_CME'", "data_date"),
)

_WAREHOUSE_FRESHNESS_DAYS = {
    "stock": 5,
    "futures": 5,
    "bond": 5,
    "fund": 5,
    "option": 5,
    "fx": 5,
    "crypto": 2,
}


@dataclass(frozen=True)
class LocalCsvProfile:
    path: Path
    asset_type: str
    symbol: str
    timeframe: str
    provider: str = "local_csv"


class MarketDataCoverageService:
    """Build coverage matrices and quality reports from available market data."""

    async def list_coverage(
        self,
        *,
        asset_type: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        provider: str | None = None,
        limit: int = 200,
        refresh_if_empty: bool = True,
    ) -> MarketDataCoverageMatrixResponse:
        items = await self._query_coverage(
            asset_type=asset_type,
            symbol=symbol,
            timeframe=timeframe,
            provider=provider,
            limit=limit,
        )
        refreshed = False
        if not items and refresh_if_empty:
            if provider == "akshare_data":
                # Listing remains available when the optional warehouse is absent.
                if _get_akshare_data_engine() is None:
                    return MarketDataCoverageMatrixResponse(total=0, items=[], refreshed=False)
                await self.refresh_warehouse_coverage(
                    asset_type=asset_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=max(limit, 1),
                )
            else:
                await self.refresh_local_csv_coverage(
                    asset_type=asset_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=max(limit, 1),
                )
            items = await self._query_coverage(
                asset_type=asset_type,
                symbol=symbol,
                timeframe=timeframe,
                provider=provider,
                limit=limit,
            )
            refreshed = True
        return MarketDataCoverageMatrixResponse(
            total=len(items),
            items=[MarketDataCoverageResponse.model_validate(item) for item in items],
            refreshed=refreshed,
        )

    async def get_best_coverage(
        self,
        *,
        asset_type: str,
        symbol: str,
        timeframe: str = "1d",
        provider: str | None = None,
    ) -> MarketDataCoverageResponse | None:
        matrix = await self.list_coverage(
            asset_type=asset_type,
            symbol=symbol,
            timeframe=timeframe,
            provider=provider,
            limit=20,
            refresh_if_empty=True,
        )
        if not matrix.items:
            return None
        return sorted(
            matrix.items,
            key=lambda item: (item.quality_status == "pass", item.row_count, item.end_date or ""),
            reverse=True,
        )[0]

    async def list_quality_reports(
        self,
        *,
        asset_type: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        provider: str | None = None,
        limit: int = 100,
    ) -> list[MarketDataQualityReportResponse]:
        async with async_session_maker() as session:
            query = select(MarketDataQualityReportModel)
            if asset_type:
                query = query.where(MarketDataQualityReportModel.asset_type == asset_type)
            if symbol:
                query = query.where(MarketDataQualityReportModel.symbol == symbol)
            if timeframe:
                query = query.where(MarketDataQualityReportModel.timeframe == timeframe)
            if provider:
                query = query.where(MarketDataQualityReportModel.provider == provider)
            result = await session.execute(
                query.order_by(MarketDataQualityReportModel.created_at.desc()).limit(limit)
            )
            models = list(result.scalars().all())
        return [MarketDataQualityReportResponse.model_validate(item) for item in models]

    async def refresh_local_csv_coverage(
        self,
        *,
        asset_type: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 500,
    ) -> MarketDataCoverageMatrixResponse:
        profiles = self._discover_local_csv_profiles(
            asset_type=asset_type,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        responses: list[MarketDataCoverageResponse] = []
        for profile in profiles:
            coverage, reports = self._inspect_csv(profile)
            if coverage is None:
                continue
            model = await self._upsert_coverage(coverage)
            await self._replace_quality_reports(
                asset_type=profile.asset_type,
                symbol=profile.symbol,
                timeframe=profile.timeframe,
                provider=profile.provider,
                reports=reports,
            )
            responses.append(MarketDataCoverageResponse.model_validate(model))
        return MarketDataCoverageMatrixResponse(
            total=len(responses),
            items=responses,
            refreshed=True,
        )

    async def refresh_warehouse_coverage(
        self,
        *,
        asset_type: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 500,
    ) -> MarketDataCoverageMatrixResponse:
        """Persist coverage summaries for the live AkShare warehouse sources."""
        if timeframe and timeframe != "1d":
            return MarketDataCoverageMatrixResponse(total=0, items=[], refreshed=True)

        engine = _get_akshare_data_engine()
        if engine is None:
            raise RuntimeError("AKSHARE_DATA_DATABASE_URL is not configured")

        profiles = [
            profile
            for profile in _WAREHOUSE_COVERAGE_PROFILES
            if asset_type is None or profile.asset_type == asset_type
        ]
        responses: list[MarketDataCoverageResponse] = []
        per_profile_limit = max(1, min(limit, 1000))
        for profile in profiles:
            rows = await self._warehouse_coverage_rows(
                engine=engine,
                profile=profile,
                symbol=symbol,
                limit=per_profile_limit,
            )
            for row in rows:
                end_date = _iso_date_text(row.get("end_date"))
                quality_status = _warehouse_quality_status(profile.asset_type, end_date)
                values = {
                    "asset_type": profile.asset_type,
                    "symbol": str(row["symbol"]),
                    "timeframe": profile.timeframe,
                    "provider": "akshare_data",
                    "start_date": _iso_date_text(row.get("start_date")),
                    "end_date": end_date,
                    "row_count": int(row.get("row_count") or 0),
                    "missing_count": 0,
                    "missing_ratio": 0.0,
                    "latest_bar_time": end_date,
                    "quality_status": quality_status,
                    "source_path": f"akshare_data.{profile.table_name}",
                }
                model = await self._upsert_coverage(values)
                reports = _warehouse_freshness_reports(
                    asset_type=profile.asset_type,
                    symbol=values["symbol"],
                    timeframe=profile.timeframe,
                    latest_date=end_date,
                    quality_status=quality_status,
                )
                await self._replace_quality_reports(
                    asset_type=profile.asset_type,
                    symbol=values["symbol"],
                    timeframe=profile.timeframe,
                    provider="akshare_data",
                    reports=reports,
                )
                responses.append(MarketDataCoverageResponse.model_validate(model))
        return MarketDataCoverageMatrixResponse(
            total=len(responses),
            items=responses,
            refreshed=True,
        )

    @staticmethod
    async def _warehouse_coverage_rows(
        *,
        engine: Any,
        profile: WarehouseCoverageProfile,
        symbol: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        symbol_expression = profile.symbol_expression
        query = f"""
            SELECT
                {symbol_expression} AS symbol,
                MIN({profile.date_column}) AS start_date,
                MAX({profile.date_column}) AS end_date,
                COUNT(*) AS row_count
            FROM {profile.table_name}
            WHERE {symbol_expression} IS NOT NULL
              AND {symbol_expression} <> ''
              AND (:symbol IS NULL OR UPPER({symbol_expression}) = UPPER(:symbol))
            GROUP BY {symbol_expression}
            ORDER BY end_date DESC, row_count DESC, symbol ASC
            LIMIT :limit
        """
        async with engine.connect() as connection:
            result = await connection.execute(
                text(query),
                {"symbol": symbol.strip() if symbol else None, "limit": limit},
            )
            return [dict(row) for row in result.mappings().all()]

    async def _query_coverage(
        self,
        *,
        asset_type: str | None,
        symbol: str | None,
        timeframe: str | None,
        provider: str | None,
        limit: int,
    ) -> list[MarketDataCoverageModel]:
        async with async_session_maker() as session:
            query = select(MarketDataCoverageModel)
            if asset_type:
                query = query.where(MarketDataCoverageModel.asset_type == asset_type)
            if symbol:
                query = query.where(MarketDataCoverageModel.symbol == symbol)
            if timeframe:
                query = query.where(MarketDataCoverageModel.timeframe == timeframe)
            if provider:
                query = query.where(MarketDataCoverageModel.provider == provider)
            result = await session.execute(
                query.order_by(
                    MarketDataCoverageModel.asset_type.asc(),
                    MarketDataCoverageModel.symbol.asc(),
                    MarketDataCoverageModel.timeframe.asc(),
                ).limit(max(1, min(limit, 1000)))
            )
            return list(result.scalars().all())

    def _discover_local_csv_profiles(
        self,
        *,
        asset_type: str | None,
        symbol: str | None,
        timeframe: str | None,
        limit: int,
    ) -> list[LocalCsvProfile]:
        if not _DATA_ROOT.is_dir():
            return []
        requested_symbol = _normalize_symbol_filter(symbol)
        profiles: list[LocalCsvProfile] = []
        for path in sorted(_DATA_ROOT.rglob("*.csv")):
            profile = self._profile_from_path(path)
            if profile is None:
                continue
            if asset_type and profile.asset_type != asset_type:
                continue
            if timeframe and profile.timeframe != timeframe:
                continue
            if requested_symbol and requested_symbol not in _symbol_match_keys(profile.symbol):
                continue
            profiles.append(profile)
            if len(profiles) >= max(1, limit):
                break
        return profiles

    def _profile_from_path(self, path: Path) -> LocalCsvProfile | None:
        stem = path.stem
        timeframe = self._timeframe_from_path(path, stem)
        symbol = self._symbol_from_stem(stem)
        if not symbol:
            return None
        asset_type = self._asset_type_from_path(path, symbol)
        return LocalCsvProfile(
            path=path,
            asset_type=asset_type,
            symbol=symbol,
            timeframe=timeframe,
        )

    @staticmethod
    def _timeframe_from_path(path: Path, stem: str) -> str:
        text = "/".join(part.upper() for part in path.parts)
        if "/H1/" in text or stem.upper().endswith("_H1"):
            return "1h"
        if "/M1/" in text or stem.upper().endswith("_M1"):
            return "1m"
        if "/D1/" in text or stem.upper().endswith("_D1"):
            return "1d"
        return "1d"

    @staticmethod
    def _symbol_from_stem(stem: str) -> str:
        value = re.sub(r"_(D1|H1|M1|W1)$", "", stem, flags=re.IGNORECASE)
        if value.lower().startswith("sh") and len(value) == 8 and value[2:].isdigit():
            return f"{value[2:]}.SH"
        if value.lower().startswith("sz") and len(value) == 8 and value[2:].isdigit():
            return f"{value[2:]}.SZ"
        return value.upper()

    @staticmethod
    def _asset_type_from_path(path: Path, symbol: str) -> str:
        parts = {part.lower() for part in path.parts}
        if "future" in parts or "futures" in parts or "期货" in parts:
            return "futures"
        if "bond" in path.name.lower() or "bond" in parts:
            return "bond"
        if "fund" in parts or "funds" in parts:
            return "fund"
        if "option" in parts or "options" in parts:
            return "option"
        if "forex" in parts or "fx" in parts:
            return "fx"
        if "crypto" in parts or "cryptos" in parts:
            return "crypto"
        return infer_asset_type(symbol)

    def _inspect_csv(
        self,
        profile: LocalCsvProfile,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        dates: list[date] = []
        duplicate_count = 0
        null_count = 0
        abnormal_price_count = 0
        abnormal_volume_count = 0
        samples: dict[str, Any] = {}
        seen_dates: set[date] = set()
        row_count = 0
        futures_rows: list[dict[str, Any]] = []

        try:
            with profile.path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for raw_row in reader:
                    row_count += 1
                    if profile.asset_type == "futures":
                        futures_rows.append(raw_row)
                    parsed_date = _parse_row_date(raw_row)
                    if parsed_date is not None:
                        dates.append(parsed_date)
                        if parsed_date in seen_dates:
                            duplicate_count += 1
                            samples.setdefault("duplicate_date", _sample_row(raw_row))
                        seen_dates.add(parsed_date)
                    if _row_has_null_ohlc(raw_row):
                        null_count += 1
                        samples.setdefault("null_ohlc", _sample_row(raw_row))
                    if _row_has_abnormal_price(raw_row):
                        abnormal_price_count += 1
                        samples.setdefault("abnormal_price", _sample_row(raw_row))
                    if _row_has_abnormal_volume(raw_row):
                        abnormal_volume_count += 1
                        samples.setdefault("abnormal_volume", _sample_row(raw_row))
        except UnicodeDecodeError:
            with profile.path.open("r", encoding="gbk", newline="") as handle:
                return self._inspect_csv_with_reader(profile, csv.DictReader(handle))
        except OSError:
            return None, []

        if row_count <= 0:
            return None, []

        start_date = min(dates).isoformat() if dates else None
        end_date = max(dates).isoformat() if dates else None
        expected_rows = _expected_rows(dates, profile.timeframe)
        missing_count = max(expected_rows - len(set(dates)), 0) if expected_rows else 0
        missing_ratio = round(missing_count / expected_rows, 6) if expected_rows else 0.0
        reports = self._quality_reports_from_counts(
            profile,
            {
                "duplicate_date": duplicate_count,
                "null_ohlc": null_count,
                "abnormal_price": abnormal_price_count,
                "abnormal_volume": abnormal_volume_count,
            },
            samples,
        )
        reports.extend(_futures_quality_reports(profile, futures_rows))
        if missing_count:
            reports.append(
                _report_payload(
                    profile,
                    issue_type="missing_bars",
                    severity="warning" if missing_ratio <= 0.2 else "error",
                    issue_count=missing_count,
                    sample_payload={
                        "expected_rows": expected_rows,
                        "observed_dates": len(set(dates)),
                    },
                )
            )
        quality_status = _quality_status(missing_ratio, reports)
        return (
            {
                "asset_type": profile.asset_type,
                "symbol": profile.symbol,
                "timeframe": profile.timeframe,
                "provider": profile.provider,
                "start_date": start_date,
                "end_date": end_date,
                "row_count": row_count,
                "missing_count": missing_count,
                "missing_ratio": missing_ratio,
                "latest_bar_time": end_date,
                "quality_status": quality_status,
                "source_path": str(profile.path),
            },
            reports,
        )

    def _inspect_csv_with_reader(
        self,
        profile: LocalCsvProfile,
        reader: csv.DictReader,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        rows = list(reader)
        temp_path = profile.path
        del temp_path
        if not rows:
            return None, []
        dates = [value for row in rows if (value := _parse_row_date(row)) is not None]
        expected_rows = _expected_rows(dates, profile.timeframe)
        missing_count = max(expected_rows - len(set(dates)), 0) if expected_rows else 0
        missing_ratio = round(missing_count / expected_rows, 6) if expected_rows else 0.0
        reports = _futures_quality_reports(profile, rows)
        return (
            {
                "asset_type": profile.asset_type,
                "symbol": profile.symbol,
                "timeframe": profile.timeframe,
                "provider": profile.provider,
                "start_date": min(dates).isoformat() if dates else None,
                "end_date": max(dates).isoformat() if dates else None,
                "row_count": len(rows),
                "missing_count": missing_count,
                "missing_ratio": missing_ratio,
                "latest_bar_time": max(dates).isoformat() if dates else None,
                "quality_status": "pass" if missing_ratio <= 0.05 else "warning",
                "source_path": str(profile.path),
            },
            reports,
        )

    @staticmethod
    def _quality_reports_from_counts(
        profile: LocalCsvProfile,
        counts: dict[str, int],
        samples: dict[str, Any],
    ) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        severities = {
            "duplicate_date": "warning",
            "null_ohlc": "error",
            "abnormal_price": "error",
            "abnormal_volume": "warning",
        }
        for issue_type, count in counts.items():
            if count <= 0:
                continue
            reports.append(
                _report_payload(
                    profile,
                    issue_type=issue_type,
                    severity=severities[issue_type],
                    issue_count=count,
                    sample_payload=samples.get(issue_type) or {},
                )
            )
        return reports

    async def _upsert_coverage(self, values: dict[str, Any]) -> MarketDataCoverageModel:
        async with async_session_maker() as session:
            result = await session.execute(
                select(MarketDataCoverageModel).where(
                    MarketDataCoverageModel.asset_type == values["asset_type"],
                    MarketDataCoverageModel.symbol == values["symbol"],
                    MarketDataCoverageModel.timeframe == values["timeframe"],
                    MarketDataCoverageModel.provider == values["provider"],
                )
            )
            model = result.scalars().first()
            if model is None:
                model = MarketDataCoverageModel(**values)
                session.add(model)
            else:
                for key, value in values.items():
                    setattr(model, key, value)
            await session.commit()
            await session.refresh(model)
            return model

    async def _replace_quality_reports(
        self,
        *,
        asset_type: str,
        symbol: str,
        timeframe: str,
        provider: str,
        reports: list[dict[str, Any]],
    ) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(MarketDataQualityReportModel).where(
                    MarketDataQualityReportModel.asset_type == asset_type,
                    MarketDataQualityReportModel.symbol == symbol,
                    MarketDataQualityReportModel.timeframe == timeframe,
                    MarketDataQualityReportModel.provider == provider,
                )
            )
            session.add_all([MarketDataQualityReportModel(**report) for report in reports])
            await session.commit()


def _parse_row_date(row: dict[str, Any]) -> date | None:
    value = _first_present(row, *_DATE_KEYS)
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt, size in (
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y/%m/%d %H:%M:%S", 19),
        ("%Y/%m/%d", 10),
        ("%Y-%m-%d", 10),
        ("%Y%m%d", 8),
    ):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def _iso_date_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value in (None, ""):
        return None
    parsed = _parse_row_date({"date": value})
    return parsed.isoformat() if parsed else str(value)


def _warehouse_quality_status(asset_type: str, latest_date: str | None) -> str:
    if not latest_date:
        return "unknown"
    try:
        latest = date.fromisoformat(latest_date[:10])
    except ValueError:
        return "unknown"
    age = max((date.today() - latest).days, 0)
    tolerance = _WAREHOUSE_FRESHNESS_DAYS.get(asset_type, 5)
    if age > tolerance * 2:
        return "failed"
    if age > tolerance:
        return "warning"
    return "pass"


def _warehouse_freshness_reports(
    *,
    asset_type: str,
    symbol: str,
    timeframe: str,
    latest_date: str | None,
    quality_status: str,
) -> list[dict[str, Any]]:
    if quality_status not in {"warning", "failed"}:
        return []
    age_days = None
    if latest_date:
        try:
            age_days = max((date.today() - date.fromisoformat(latest_date[:10])).days, 0)
        except ValueError:
            pass
    return [
        {
            "asset_type": asset_type,
            "symbol": symbol,
            "timeframe": timeframe,
            "provider": "akshare_data",
            "issue_type": "stale_market_data",
            "severity": "error" if quality_status == "failed" else "warning",
            "issue_count": 1,
            "sample_payload": {
                "latest_date": latest_date,
                "age_days": age_days,
                "max_age_days": _WAREHOUSE_FRESHNESS_DAYS.get(asset_type, 5),
            },
        }
    ]


def _parse_row_datetime(row: dict[str, Any]) -> datetime | None:
    """Parse a naive local market timestamp from the standard CSV columns."""
    value = _first_present(row, *_DATE_KEYS)
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass
    for fmt, size in (
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y/%m/%d %H:%M:%S", 19),
        ("%Y-%m-%d %H:%M", 16),
        ("%Y/%m/%d %H:%M", 16),
        ("%Y-%m-%d", 10),
        ("%Y/%m/%d", 10),
        ("%Y%m%d", 8),
    ):
        try:
            return datetime.strptime(text[:size], fmt)
        except ValueError:
            continue
    return None


def _futures_trading_day(value: datetime) -> date:
    """Map night-session bars to the following futures trading day.

    Chinese futures night sessions start at 21:00.  A bar at 21:00 on
    Monday and bars after midnight on Tuesday therefore belong to the same
    Tuesday trading day, which prevents a harmless cross-midnight session
    from being reported as two separate coverage gaps.
    """
    trading_day = value.date()
    if value.hour >= 21:
        return trading_day + timedelta(days=1)
    return trading_day


def _futures_quality_reports(
    profile: LocalCsvProfile,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return deterministic futures-only roll, session, and calendar checks.

    Large adjacent closing-price jumps are informative around a continuous
    contract roll, so they are a warning rather than a block.  A missing bar
    *inside an observed night-session sequence* and data on a known closure
    date are deterministic coverage violations and remain blocking errors.
    """
    if profile.asset_type != "futures" or not rows:
        return []

    reports: list[dict[str, Any]] = []
    parsed_rows = [(value, row) for row in rows if (value := _parse_row_datetime(row)) is not None]
    parsed_rows.sort(key=lambda item: item[0])

    closure_rows = [
        (value, row)
        for value, row in parsed_rows
        if value.date().weekday() >= 5 or value.date() in _CN_FUTURES_CLOSURE_DATES
    ]
    if closure_rows:
        reports.append(
            _report_payload(
                profile,
                issue_type="futures_holiday_bar",
                severity="error",
                issue_count=len(closure_rows),
                sample_payload={
                    "datetime": closure_rows[0][0].isoformat(sep=" "),
                    "trading_day": _futures_trading_day(closure_rows[0][0]).isoformat(),
                },
            )
        )

    jumps = 0
    jump_sample: dict[str, Any] | None = None
    previous_close: float | None = None
    for value, row in parsed_rows:
        close = _float_or_none(_first_present(row, *_CLOSE_KEYS))
        if close is None or close <= 0:
            continue
        if previous_close is not None and abs(close / previous_close - 1) >= 0.10:
            jumps += 1
            jump_sample = {
                "datetime": value.isoformat(sep=" "),
                "previous_close": previous_close,
                "close": close,
            }
        previous_close = close
    if jumps:
        reports.append(
            _report_payload(
                profile,
                issue_type="futures_roll_price_jump",
                severity="warning",
                issue_count=jumps,
                sample_payload=jump_sample or {},
            )
        )

    if profile.timeframe not in {"1h", "1m"}:
        return reports
    session_groups: dict[date, list[datetime]] = {}
    for value, _ in parsed_rows:
        if value.hour >= 21 or value.hour < 3:
            session_groups.setdefault(_futures_trading_day(value), []).append(value)
    gaps: list[dict[str, str]] = []
    interval = timedelta(hours=1 if profile.timeframe == "1h" else 1 / 60)
    for trading_day, values in session_groups.items():
        ordered = sorted(set(values))
        for left, right in zip(ordered, ordered[1:], strict=False):
            difference = right - left
            if difference <= interval or difference > timedelta(hours=3):
                continue
            missing = left + interval
            while missing < right:
                gaps.append(
                    {
                        "trading_day": trading_day.isoformat(),
                        "missing_at": missing.isoformat(sep=" "),
                    }
                )
                missing += interval
    if gaps:
        reports.append(
            _report_payload(
                profile,
                issue_type="futures_night_session_gap",
                severity="error",
                issue_count=len(gaps),
                sample_payload=gaps[0],
            )
        )
    return reports


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _row_has_null_ohlc(row: dict[str, Any]) -> bool:
    return any(
        _first_present(row, *keys) in (None, "")
        for keys in (_OPEN_KEYS, _HIGH_KEYS, _LOW_KEYS, _CLOSE_KEYS)
    )


def _row_has_abnormal_price(row: dict[str, Any]) -> bool:
    open_price = _float_or_none(_first_present(row, *_OPEN_KEYS))
    high = _float_or_none(_first_present(row, *_HIGH_KEYS))
    low = _float_or_none(_first_present(row, *_LOW_KEYS))
    close = _float_or_none(_first_present(row, *_CLOSE_KEYS))
    prices = [item for item in (open_price, high, low, close) if item is not None]
    if any(item <= 0 or not math.isfinite(item) for item in prices):
        return True
    if high is not None and low is not None and high < low:
        return True
    if high is not None and close is not None and close > high * 1.2:
        return True
    if low is not None and close is not None and close < low * 0.8:
        return True
    return False


def _row_has_abnormal_volume(row: dict[str, Any]) -> bool:
    volume = _float_or_none(_first_present(row, *_VOLUME_KEYS))
    return volume is not None and volume < 0


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _expected_rows(dates: list[date], timeframe: str) -> int:
    if not dates:
        return 0
    start = min(dates)
    end = max(dates)
    if timeframe == "1d":
        count = 0
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                count += 1
            cursor += timedelta(days=1)
        return count
    elapsed_days = max((end - start).days + 1, 1)
    if timeframe == "1h":
        return elapsed_days * 4
    if timeframe == "1m":
        return elapsed_days * 240
    return len(set(dates))


def _quality_status(missing_ratio: float, reports: list[dict[str, Any]]) -> str:
    if any(report.get("severity") == "error" for report in reports) or missing_ratio > 0.35:
        return "failed"
    if reports or missing_ratio > 0.05:
        return "warning"
    return "pass"


def _report_payload(
    profile: LocalCsvProfile,
    *,
    issue_type: str,
    severity: str,
    issue_count: int,
    sample_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "asset_type": profile.asset_type,
        "symbol": profile.symbol,
        "timeframe": profile.timeframe,
        "provider": profile.provider,
        "issue_type": issue_type,
        "severity": severity,
        "issue_count": issue_count,
        "sample_payload": sample_payload,
    }


def _sample_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in list(row.items())[:12]}


def _normalize_symbol_filter(symbol: str | None) -> str:
    if not symbol:
        return ""
    return re.sub(r"[^0-9A-Za-z]", "", symbol).upper()


def _symbol_match_keys(symbol: str) -> set[str]:
    compact = _normalize_symbol_filter(symbol)
    keys = {compact}
    if compact.startswith(("SH", "SZ")):
        keys.add(compact[2:])
    if len(compact) == 6 and compact.isdigit():
        keys.update({f"SH{compact}", f"SZ{compact}"})
    return {key for key in keys if key}


@lru_cache
def get_market_data_coverage_service() -> MarketDataCoverageService:
    return MarketDataCoverageService()
