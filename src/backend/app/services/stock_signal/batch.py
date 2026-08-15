"""After-close SSE 50 signal batch with durable run ownership and no execution side effects."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db.database import async_session_maker
from app.models.stock_signal import StockSignalPrediction, StockSignalRun
from app.services.market_instrument import MarketInstrumentService
from app.services.stock_analysis.data_collector import StockAnalysisDataCollector
from app.services.stock_signal.calendar import TradingCalendar
from app.services.stock_signal.decision_policy import SignalPolicy
from app.services.stock_signal.quality import DataQualityGate
from app.services.stock_signal.service import StockSignalService
from app.services.stock_signal.universe import Sse50UniverseProvider
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Sse50SignalBatchRunner:
    """Generate one public, auditable SSE 50 snapshot for a completed session."""

    source = "nightly_sse50"
    universe_code = "SSE50"

    def __init__(
        self,
        *,
        calendar: TradingCalendar | None = None,
        universe: Sse50UniverseProvider | None = None,
    ) -> None:
        settings = get_settings()
        self.settings = settings
        self.calendar = calendar or TradingCalendar()
        self.universe = universe or Sse50UniverseProvider()
        self.policy = SignalPolicy(
            round_trip_cost_bps=float(settings.STOCK_SIGNAL_ROUND_TRIP_COST_BPS or 0.0),
            buy_success_threshold_bps=float(settings.STOCK_SIGNAL_BUY_SUCCESS_THRESHOLD_BPS or 0.0),
            sell_success_threshold_bps=float(
                settings.STOCK_SIGNAL_SELL_SUCCESS_THRESHOLD_BPS or 0.0
            ),
        )
        self.quality_gate = DataQualityGate(
            min_history_bars=settings.STOCK_SIGNAL_MIN_HISTORY_BARS,
            max_financial_age_days=settings.STOCK_SIGNAL_MAX_FINANCIAL_AGE_DAYS,
            max_news_age_days=settings.STOCK_SIGNAL_MAX_NEWS_AGE_DAYS,
        )

    def configuration_ready(self) -> bool:
        universe = str(getattr(self.settings, "STOCK_SIGNAL_UNIVERSE", "sse50") or "").lower()
        return universe == "sse50" and all(
            value is not None
            for value in (
                self.settings.STOCK_SIGNAL_ROUND_TRIP_COST_BPS,
                self.settings.STOCK_SIGNAL_BUY_SUCCESS_THRESHOLD_BPS,
                self.settings.STOCK_SIGNAL_SELL_SUCCESS_THRESHOLD_BPS,
            )
        )

    async def run(self, *, as_of_date: date | None = None) -> StockSignalRun | None:
        """Run only on an official exchange date; never submit an order."""
        target_date = as_of_date or date.today()
        if not self.configuration_ready():
            raise RuntimeError("stock_signal_evaluation_configuration_incomplete")
        if not await self.calendar.is_trading_day(target_date):
            return None
        next_trading_date = await self.calendar.next_trading_day(target_date)
        if next_trading_date is None:
            raise RuntimeError("next_trading_date_unavailable")
        members = await self.universe.members()
        run, claimed = await self._claim_run(target_date, members)
        if not claimed:
            return run

        semaphore = asyncio.Semaphore(self.settings.STOCK_SIGNAL_MAX_CONCURRENCY)

        async def process(member: dict[str, str]) -> tuple[str, str | None]:
            async with semaphore:
                return await self._process_member(
                    run_id=run.id,
                    member=member,
                    as_of_date=target_date,
                    next_trading_date=next_trading_date,
                )

        results = await asyncio.gather(
            *(process(member) for member in members), return_exceptions=True
        )
        created = eligible = degraded = failed = 0
        errors: dict[str, str] = {}
        for member, result in zip(members, results, strict=True):
            if isinstance(result, BaseException):
                failed += 1
                errors[member["symbol"]] = f"{type(result).__name__}:{result}"
                continue
            status, error = result
            if error:
                failed += 1
                errors[member["symbol"]] = error
                continue
            created += 1
            if status == "eligible":
                eligible += 1
            else:
                degraded += 1
        async with async_session_maker() as session:
            persisted = await session.get(StockSignalRun, run.id)
            if persisted is None:
                raise RuntimeError("stock_signal_run_lost")
            persisted.created_count = created
            persisted.eligible_count = eligible
            persisted.degraded_count = degraded
            persisted.failed_count = failed
            persisted.error_summary_json = errors
            persisted.status = "completed" if created else "failed"
            persisted.finished_at = _now()
            await session.commit()
            await session.refresh(persisted)
            return persisted

    async def _claim_run(
        self, as_of_date: date, members: list[dict[str, str]]
    ) -> tuple[StockSignalRun, bool]:
        run_key = _digest(
            {
                "source": self.source,
                "universe_code": self.universe_code,
                "as_of_date": as_of_date.isoformat(),
                "feature_version": "ohlcv-v1",
                "policy_version": self.policy.decision_policy_version,
                "model_version": self.policy.model_version,
            }
        )
        async with async_session_maker() as session:
            existing = await session.scalar(
                select(StockSignalRun).where(StockSignalRun.run_key == run_key)
            )
            if existing is not None:
                return existing, False
            run = StockSignalRun(
                run_key=run_key,
                owner_scope="system",
                source=self.source,
                universe_code=self.universe_code,
                as_of_date=as_of_date,
                scheduled_for_at=_now(),
                started_at=_now(),
                status="running",
                expected_count=len(members),
                universe_snapshot_json=members,
                config_snapshot_json={
                    "max_concurrency": self.settings.STOCK_SIGNAL_MAX_CONCURRENCY,
                    "policy": self.policy.snapshot(),
                },
            )
            try:
                async with session.begin_nested():
                    session.add(run)
                    await session.flush()
            except IntegrityError:
                existing = await session.scalar(
                    select(StockSignalRun).where(StockSignalRun.run_key == run_key)
                )
                if existing is not None:
                    return existing, False
                raise
            await session.commit()
            await session.refresh(run)
            return run, True

    async def _process_member(
        self,
        *,
        run_id: str,
        member: dict[str, str],
        as_of_date: date,
        next_trading_date: date,
    ) -> tuple[str, str | None]:
        async with async_session_maker() as session:
            collector = StockAnalysisDataCollector(session)
            snapshot = await collector.collect(
                user_id="system",
                symbol=member["symbol"],
                market_type="A股",
                analysis_date=as_of_date,
            )
            prediction = await StockSignalService(
                session,
                policy=self.policy,
                quality_gate=self.quality_gate,
            ).create_prediction(
                snapshot=snapshot,
                symbol=member["symbol"],
                market_type="A股",
                as_of_date=as_of_date,
                owner_scope="system",
                source=self.source,
                universe_code=self.universe_code,
                next_trading_date=next_trading_date,
                run_id=run_id,
            )
            if not prediction.symbol_name and member.get("name"):
                prediction.symbol_name = member["name"]
            await session.commit()
            return prediction.eligibility_status, None

    async def score_pending(self, *, through_date: date | None = None) -> int:
        """Refresh mature outcomes using subsequent market rows; never alter prediction inputs."""
        target_date = through_date or date.today()
        async with async_session_maker() as session:
            records = list(
                (
                    await session.execute(
                        select(StockSignalPrediction).where(
                            StockSignalPrediction.outcome_status.in_(("pending", "partial")),
                            StockSignalPrediction.as_of_date <= target_date,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not records:
                return 0
            for record in records:
                if record.next_trading_date is not None:
                    continue
                try:
                    record.next_trading_date = await self.calendar.next_trading_day(
                        record.as_of_date
                    )
                except RuntimeError as exc:
                    logger.warning(
                        "Unable to resolve next trading date for stock signal %s: %s",
                        record.id,
                        exc,
                    )
            records = [
                record
                for record in records
                if record.next_trading_date is not None and record.next_trading_date <= target_date
            ]
            if not records:
                await session.commit()
                return 0
            service = StockSignalService(session)
            market = MarketInstrumentService()
            first_entry_date = min(
                record.next_trading_date
                for record in records
                if record.next_trading_date is not None
            )
            benchmark_rows = await self._sse50_benchmark_rows(
                start_date=first_entry_date,
                end_date=target_date,
            )
            updated = 0
            for record in records:
                if record.next_trading_date is None:
                    continue
                try:
                    payload = await market.lookup(
                        asset_type="stock",
                        symbol=record.symbol,
                        start_date=record.next_trading_date,
                        end_date=target_date,
                        period="daily",
                        refresh_online=True,
                    )
                except Exception as exc:
                    logger.warning(
                        "Unable to score stock signal %s for %s: %s",
                        record.id,
                        record.symbol,
                        exc,
                    )
                    continue
                await service.apply_outcome(
                    prediction=record,
                    price_rows=(payload.get("history") or {}).get("rows") or [],
                    benchmark_rows=benchmark_rows,
                )
                updated += 1
            await session.commit()
            return updated

    async def _sse50_benchmark_rows(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Return real SSE 50 rows when available; relative return stays unavailable otherwise."""
        try:
            return await asyncio.to_thread(
                self._fetch_sse50_benchmark_rows,
                start_date,
                end_date,
            )
        except Exception as exc:
            logger.warning("Unable to load SSE50 benchmark rows for signal scoring: %s", exc)
            return []

    @staticmethod
    def _fetch_sse50_benchmark_rows(start_date: date, end_date: date) -> list[dict[str, Any]]:
        import akshare as ak

        frame = ak.stock_zh_index_daily_em(
            symbol="sh000016",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if frame is None or frame.empty:
            return []
        required = {"date", "open", "close"}
        if not required.issubset(frame.columns):
            return []
        return [
            {
                "date": str(row["date"])[:10],
                "open": row["open"],
                "close": row["close"],
            }
            for row in frame.to_dict(orient="records")
        ]
