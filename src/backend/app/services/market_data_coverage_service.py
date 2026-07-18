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

from sqlalchemy import delete, select

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

        try:
            with profile.path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for raw_row in reader:
                    row_count += 1
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
        reports: list[dict[str, Any]] = []
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
