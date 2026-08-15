"""Approved AkShare-backed providers for Iteration 192 pilot assets.

These adapters collect only explicit, source-mapped fields.  They never infer
an identity or fabricate a quote, curve, cashflow or calendar.  AkShare is an
open-source aggregation wrapper; the provider still declares the concrete
upstream hosts and freezes ``RESEARCH_ONLY`` source provenance in every raw snapshot.
Production must enable this provider only after the matching ``asset_data_source_registry`` rows and manifests are imported."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.schemas.asset_research import InstrumentIdentity, RawAssetSnapshot, RawObservation
from app.services.asset_research.data import canonical_json_hash
from app.services.asset_research.providers.base import AssetDataProvider, NetworkPolicy

Row = dict[str, Any]
QuoteResult = tuple[dict[str, Any], datetime | None]
CurveResult = tuple[list[dict[str, Any]], dict[str, Any] | None]
_MIDNIGHT = datetime.min.time()

FUTURES_SOURCE_ID = "akshare_futures_sina_cffex"
BOND_SOURCE_ID = "akshare_bond_sina_chinabond"
FUND_SOURCE_ID = "akshare_fund_em_sina"
FX_SOURCE_ID = "akshare_fx_em_boc"
OPTION_SOURCE_ID = "akshare_option_sina_sse"
CRYPTO_SOURCE_ID = "akshare_crypto_okx"

_FUTURES_ALLOWED_HOSTS = (
    "finance.sina.com.cn",
    "vip.stock.finance.sina.com.cn",
    "money.finance.sina.com.cn",
    "www.gtjaqh.com",
    "www.cffex.com.cn",
)
_BOND_ALLOWED_HOSTS = (
    "money.finance.sina.com.cn",
    "vip.stock.finance.sina.com.cn",
    "yield.chinabond.com.cn",
    "www.chinamoney.com.cn",
)
_FUND_ALLOWED_HOSTS = (
    "fund.eastmoney.com",
    "push2.eastmoney.com",
    "fundf10.eastmoney.com",
    "money.finance.sina.com.cn",
)
_FX_ALLOWED_HOSTS = (
    "quote.eastmoney.com",
    "push2.eastmoney.com",
    "www.boc.cn",
    "srh.bankofchina.com",
)
_OPTION_ALLOWED_HOSTS = (
    "hq.sinajs.cn",
    "vip.stock.finance.sina.com.cn",
    "stock.finance.sina.com.cn",
)
_CRYPTO_ALLOWED_HOSTS = (
    "www.okx.com",
    "aws.okx.com",
)


def _akshare_module():
    import akshare as ak

    return ak


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(text), _MIDNIGHT, tzinfo=timezone.utc)
        except ValueError:
            return None


def _parse_date(value: object) -> date | None:
    parsed = _parse_datetime(value)
    return parsed.date() if parsed is not None else None


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"--", "-", "nan", "NaN", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"--", "-", "nan", "NaN", "None"}:
        return ""
    return text


def _row_value(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _scalar_fields(value: object, *, prefix: str = "") -> dict[str, object]:
    if isinstance(value, Mapping):
        flattened: dict[str, object] = {}
        for key, nested in value.items():
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_scalar_fields(nested, prefix=nested_prefix))
        return flattened
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {}
    return {prefix: value} if prefix else {}


def _json_safe(value: object) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _build_observations(
    *,
    raw_fields: dict[str, Any],
    history_rows: list[dict[str, Any]],
    source_id: str,
    retrieved_at: datetime,
    cutoff_at: datetime,
    snapshot_observed_at: datetime | None,
    domain_observed_at: datetime | None,
) -> dict[str, RawObservation]:
    observations: dict[str, RawObservation] = {}

    def add(
        *,
        field_name: str,
        value: object,
        observed_at: datetime | None,
    ) -> None:
        if observed_at is None or observed_at > cutoff_at:
            return
        observations[field_name] = RawObservation(
            value=value,
            source_id=source_id,
            observed_at=observed_at,
            published_at=observed_at,
            available_at=observed_at,
            retrieved_at=retrieved_at,
            license_tag="RESEARCH_APPROVED",
        )

    for section, default_observed_at in (
        ("snapshot", snapshot_observed_at),
        ("futures", domain_observed_at),
        ("bond", domain_observed_at),
        ("fund", domain_observed_at),
        ("fx", domain_observed_at),
        ("option", domain_observed_at),
        ("crypto", domain_observed_at),
    ):
        section_fields = raw_fields.get(section)
        if not isinstance(section_fields, Mapping):
            continue
        for field_name, value in _scalar_fields(section_fields, prefix=section).items():
            add(field_name=field_name, value=value, observed_at=default_observed_at)

    for row in history_rows:
        row_date = _parse_date(row.get("date"))
        if row_date is None:
            continue
        observed_at = datetime.combine(row_date, datetime.min.time(), tzinfo=timezone.utc)
        fields = _scalar_fields(row, prefix=f"history:{row_date.isoformat()}")
        for field_name, value in fields.items():
            if field_name.rsplit(".", maxsplit=1)[-1] == "date":
                continue
            add(field_name=field_name, value=value, observed_at=observed_at)
    return observations


def _build_snapshot(
    *,
    identity: InstrumentIdentity,
    cutoff_at: datetime,
    retrieved_at: datetime,
    raw_schema_version: str,
    raw_fields: dict[str, Any],
    history_rows: list[dict[str, Any]],
    source_id: str,
    capabilities: list[str],
    observed_at: datetime | None,
    documentation_url: str,
) -> RawAssetSnapshot:
    snapshot_observed_at = (
        _parse_datetime((raw_fields.get("snapshot") or {}).get("quote_at"))
        or _parse_datetime((raw_fields.get("snapshot") or {}).get("observed_at"))
        or observed_at
    )
    observations = _build_observations(
        raw_fields=raw_fields,
        history_rows=history_rows,
        source_id=source_id,
        retrieved_at=retrieved_at,
        cutoff_at=cutoff_at,
        snapshot_observed_at=snapshot_observed_at,
        domain_observed_at=observed_at,
    )
    pit_violations = [
        field_name
        for field_name, observation in observations.items()
        if observation.available_at is None or observation.available_at > cutoff_at
    ]
    point_in_time_status = "VERIFIED" if observations and not pit_violations else "UNVERIFIED"
    source_manifest = {
        "provider": source_id,
        "source_id": source_id,
        "source_registry_status": "UNKNOWN",
        "license_status": "UNKNOWN",
        "allowed_use": "RESEARCH_ONLY",
        "capabilities": capabilities,
        "documentation_url": documentation_url,
        "observed_at": observed_at.isoformat() if observed_at is not None else None,
        "available_at": observed_at.isoformat() if observed_at is not None else None,
        "retrieved_at": retrieved_at.isoformat(),
        "point_in_time_status": point_in_time_status,
        "pit_unverified_fields": pit_violations[:100],
        "quote_kind": "EXECUTABLE",
    }
    safe_raw_fields = _json_safe(raw_fields)
    safe_history_rows = _json_safe(history_rows)
    safe_observations = {
        field_name: observation.model_dump(mode="json")
        for field_name, observation in observations.items()
    }
    content = {
        "identity": identity.model_dump(mode="json"),
        "cutoff_at": cutoff_at.isoformat(),
        "raw_fields": safe_raw_fields,
        "history_rows": safe_history_rows,
        "observations": safe_observations,
        "source_manifest": source_manifest,
    }
    return RawAssetSnapshot(
        identity=identity,
        cutoff_at=cutoff_at,
        retrieved_at=retrieved_at,
        raw_schema_version=raw_schema_version,
        raw_fields=safe_raw_fields,
        history_rows=safe_history_rows,
        observations={
            field_name: observation.model_copy(update={"value": _json_safe(observation.value)})
            for field_name, observation in observations.items()
        },
        source_manifest=source_manifest,
        license_tags=["RESEARCH_APPROVED"],
        content_hash=canonical_json_hash(content),
    )


def _history_rows(
    frame: Any,
    *,
    cutoff_at: datetime,
    close_columns: tuple[str, ...],
    volume_columns: tuple[str, ...] = ("volume",),
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if frame is None:
        return rows
    for _, row in frame.iterrows():
        raw = dict(row)
        row_date = _parse_date(_row_value(raw, "date", "日期"))
        if row_date is None or row_date > cutoff_at.date():
            continue
        rows.append(
            {
                "date": row_date.isoformat(),
                "open": _number(_row_value(raw, "open", "开盘")),
                "high": _number(_row_value(raw, "high", "最高")),
                "low": _number(_row_value(raw, "low", "最低")),
                "close": _number(_row_value(raw, *close_columns)),
                "volume": _number(_row_value(raw, *volume_columns)),
            }
        )
    return rows


def _calendar_sessions(
    frame: Any,
    *,
    cutoff_at: datetime,
    calendar_id: str,
    close_hour: int = 15,
    close_minute: int = 0,
    timezone_name: str = "Asia/Shanghai",
) -> dict[str, Any]:
    sessions: list[dict[str, str]] = []
    if frame is not None:
        for _, row in frame.iterrows():
            raw = dict(row)
            session_date = _parse_date(_row_value(raw, "trade_date", "日期"))
            if session_date is None or session_date <= cutoff_at.date():
                continue
            sessions.append(
                {
                    "date": session_date.isoformat(),
                    "close_at": f"{session_date.isoformat()}T{close_hour:02d}:{close_minute:02d}:00+08:00",
                }
            )
    return {
        "calendar_id": calendar_id,
        "timezone": timezone_name,
        "sessions": sessions,
    }


class AkShareFuturesProvider(AssetDataProvider):
    """CFFEX futures price, executable quote, rules and source calendar."""

    source_id = FUTURES_SOURCE_ID
    declared_source_ids = (FUTURES_SOURCE_ID,)
    network_policy = NetworkPolicy(allowed_hosts=_FUTURES_ALLOWED_HOSTS)

    _PRODUCT_NAMES = {
        "IF": "沪深300指数期货",
        "IH": "上证50指数期货",
        "IC": "中证500指数期货",
        "IM": "中证1000指数期货",
        "TS": "2年期国债期货",
        "TF": "5年期国债期货",
        "T": "10年期国债期货",
        "TL": "30年期国债期货",
    }

    @classmethod
    def _product_name(cls, identity: InstrumentIdentity) -> str:
        product_code = str(getattr(identity.details, "product_code", "") or "").upper()
        return cls._PRODUCT_NAMES.get(product_code) or str(identity.name).replace(
            str(getattr(identity.details, "contract_month", "") or ""), ""
        )

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot:
        if identity.asset_type != "futures":
            raise ValueError("AKSHARE_FUTURES_PROVIDER_ASSET_MISMATCH")
        ak = _akshare_module()
        cutoff = _as_utc(cutoff_at)
        symbol = identity.display_symbol
        calendar = await asyncio.to_thread(ak.tool_trade_date_hist_sina)
        latest_trade_date = self._latest_trade_date(calendar, cutoff)
        if latest_trade_date is None:
            raise ValueError("COMMON.CALENDAR_UNAVAILABLE")
        query_date = latest_trade_date.strftime("%Y%m%d")
        daily, realtime, rules, contracts = await asyncio.gather(
            asyncio.to_thread(ak.futures_zh_daily_sina, symbol=symbol),
            asyncio.to_thread(ak.futures_zh_realtime, symbol=self._product_name(identity)),
            asyncio.to_thread(ak.futures_rule, date=query_date),
            asyncio.to_thread(ak.futures_contract_info_cffex, date=query_date),
        )
        history_rows = _history_rows(
            daily,
            cutoff_at=cutoff,
            close_columns=("close", "收盘"),
            volume_columns=("volume", "成交量"),
        )
        quote_row = self._quote_row(realtime, symbol)
        quote, quote_observed_at = self._quote(quote_row, cutoff=cutoff)
        contract_row = self._contract_row(contracts, symbol)
        rule_row = self._rule_row(rules, identity)
        raw_fields: dict[str, Any] = {
            "snapshot": quote,
            "futures": self._futures_facts(identity, contract_row, rule_row),
            "calendar": _calendar_sessions(calendar, cutoff_at=cutoff, calendar_id="CFFEX"),
        }
        return _build_snapshot(
            identity=identity,
            cutoff_at=cutoff,
            retrieved_at=datetime.now(timezone.utc),
            raw_schema_version="akshare-cffex-futures-v1",
            raw_fields=raw_fields,
            history_rows=history_rows,
            source_id=self.source_id,
            capabilities=["price", "contract_calendar"],
            observed_at=quote_observed_at or cutoff,
            documentation_url="https://akshare.akfamily.xyz/data/futures/futures.html",
        )

    @staticmethod
    def _latest_trade_date(frame: Any, cutoff: datetime) -> date | None:
        candidates: list[date] = []
        if frame is None:
            return None
        for _, row in frame.iterrows():
            raw = dict(row)
            parsed = _parse_date(_row_value(raw, "trade_date", "日期"))
            if parsed is not None and parsed <= cutoff.date():
                candidates.append(parsed)
        return max(candidates) if candidates else None

    @staticmethod
    def _quote_row(realtime: Any, symbol: str) -> dict[str, Any] | None:
        if realtime is None or realtime.empty:
            return None
        for _, row in realtime.iterrows():
            raw = dict(row)
            if str(_row_value(raw, "symbol", "合约代码") or "").upper() == symbol.upper():
                return raw
        return None

    @staticmethod
    def _quote(row: Row | None, *, cutoff: datetime) -> QuoteResult:
        if row is None:
            return {}, None
        trade_date = _parse_date(_row_value(row, "tradedate", "日期"))
        if trade_date is None or trade_date > cutoff.date():
            return {}, None
        tick_time = _text(_row_value(row, "ticktime", "时间"))
        quote_at: datetime | None = None
        if trade_date is not None:
            if tick_time:
                try:
                    quote_at = datetime.fromisoformat(
                        f"{trade_date.isoformat()}T{tick_time}+08:00"
                    ).astimezone(timezone.utc)
                except ValueError:
                    quote_at = datetime.combine(trade_date, _MIDNIGHT, tzinfo=timezone.utc)
            else:
                quote_at = datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc)
        quote = {
            "price": _number(_row_value(row, "trade", "current_price")),
            "bid": _number(_row_value(row, "bidprice1", "bid")),
            "ask": _number(_row_value(row, "askprice1", "ask")),
            "bid_volume": _number(_row_value(row, "bidvol1", "bid_volume")),
            "ask_volume": _number(_row_value(row, "askvol1", "ask_volume")),
            "open": _number(_row_value(row, "open")),
            "high": _number(_row_value(row, "high")),
            "low": _number(_row_value(row, "low")),
            "settlement": _number(_row_value(row, "settlement", "presettlement")),
            "quote_date": trade_date.isoformat() if trade_date is not None else None,
            "quote_at": quote_at.isoformat() if quote_at is not None else None,
            "volume": _number(_row_value(row, "volume")),
            "position": _number(_row_value(row, "position", "hold")),
        }
        return {key: value for key, value in quote.items() if value is not None}, quote_at

    @staticmethod
    def _contract_row(contracts: Any, symbol: str) -> dict[str, Any] | None:
        if contracts is None or contracts.empty:
            return None
        for _, row in contracts.iterrows():
            raw = dict(row)
            if str(_row_value(raw, "合约代码", "symbol") or "").upper() == symbol.upper():
                return raw
        return None

    @staticmethod
    def _rule_row(rules: Any, identity: InstrumentIdentity) -> dict[str, Any] | None:
        details = identity.details
        product_code = str(getattr(details, "product_code", "") or "").upper()
        if rules is None or rules.empty:
            return None
        for _, row in rules.iterrows():
            raw = dict(row)
            if str(_row_value(raw, "代码", "品种代码") or "").upper() == product_code:
                return raw
        return None

    @staticmethod
    def _futures_facts(
        identity: InstrumentIdentity,
        contract_row: dict[str, Any] | None,
        rule_row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        details = identity.details
        product_code = str(getattr(details, "product_code", "") or "").upper()
        facts: dict[str, Any] = {
            "contract_code": identity.display_symbol,
            "product_code": product_code,
            "contract_month": getattr(details, "contract_month", None),
            "expiry_date": _parse_date(
                _row_value(contract_row or {}, "最后交易日", "last_trade_date")
            ),
            "listing_date": _parse_date(_row_value(contract_row or {}, "上市日", "listing_date")),
            "position_limit": _number(_row_value(contract_row or {}, "持仓限额", "position_limit")),
            "contract_multiplier": _number(
                _row_value(rule_row or {}, "合约乘数", "contract_multiplier")
            ),
            "tick_size": _number(_row_value(rule_row or {}, "最小变动价位", "tick_size")),
            "margin_ratio": _number(_row_value(rule_row or {}, "交易保证金比例", "margin_ratio")),
            "price_limit": _number(_row_value(rule_row or {}, "涨跌停板幅度", "price_limit")),
            "market_context_current": True,
            "broker_margin_available": bool(rule_row),
            "term_structure_complete": None,
            "basis_alignment_complete": None,
            "fundamental_coverage_complete": None,
        }
        return {key: value for key, value in facts.items() if value is not None}


class AkShareBondProvider(AssetDataProvider):
    """SSE/SZSE convertible bond executable quote, terms, curve and calendar."""

    source_id = BOND_SOURCE_ID
    declared_source_ids = (BOND_SOURCE_ID,)
    network_policy = NetworkPolicy(allowed_hosts=_BOND_ALLOWED_HOSTS)

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot:
        if identity.asset_type != "bond":
            raise ValueError("AKSHARE_BOND_PROVIDER_ASSET_MISMATCH")
        ak = _akshare_module()
        cutoff = _as_utc(cutoff_at)
        symbol = identity.display_symbol
        calendar = await asyncio.to_thread(ak.tool_trade_date_hist_sina)
        spot, profile, daily = await asyncio.gather(
            asyncio.to_thread(ak.bond_zh_hs_cov_spot),
            asyncio.to_thread(ak.bond_cb_profile_sina, symbol=symbol),
            asyncio.to_thread(ak.bond_zh_hs_daily, symbol=symbol),
        )
        quote_row = self._quote_row(spot, symbol)
        quote, quote_observed_at = self._quote(quote_row, cutoff=cutoff)
        profile_values = self._profile_values(profile)
        return await self._snapshot(
            identity=identity,
            cutoff=cutoff,
            quote=quote,
            quote_observed_at=quote_observed_at,
            profile_values=profile_values,
            calendar=calendar,
            daily=daily,
        )

    async def _snapshot(
        self,
        *,
        identity: InstrumentIdentity,
        cutoff: datetime,
        quote: dict[str, Any],
        quote_observed_at: datetime | None,
        profile_values: dict[str, Any],
        calendar: Any,
        daily: Any,
    ) -> RawAssetSnapshot:
        ak = _akshare_module()
        curve_start = cutoff.date() - timedelta(days=14)
        curve = await asyncio.to_thread(
            ak.bond_china_yield,
            start_date=curve_start.strftime("%Y%m%d"),
            end_date=cutoff.date().strftime("%Y%m%d"),
        )
        curve_rows, benchmark = self._curve(curve, cutoff=cutoff)
        cashflows, coupon_schedule = self._cashflows(profile_values, cutoff=cutoff)
        observed_date = _parse_date(profile_values.get("到期日")) or cutoff.date()
        day_end = datetime.combine(observed_date, _MIDNIGHT, tzinfo=timezone.utc)
        observed_at = quote_observed_at or day_end
        bond_fields: dict[str, Any] = {
            "maturity_date": profile_values.get("到期日"),
            "face_value": _number(profile_values.get("债券面值（元）")),
            "issue_date": profile_values.get("起息日期"),
            "coupon_frequency": _number(profile_values.get("年付息次数")),
            "coupon_schedule": coupon_schedule,
            "cashflows": cashflows,
            "curve": curve_rows,
            "benchmark": benchmark,
            "official_valuation": _number(profile_values.get("全价（元）")),
            "credit_rating": profile_values.get("信用等级"),
            "credit_disclosure_current": True,
            "is_perpetual": False,
            "evidence_coverage_low": None,
            "peer_data_complete": None,
        }
        raw_fields: dict[str, Any] = {
            "snapshot": quote,
            "bond": {key: value for key, value in bond_fields.items() if value is not None},
            "calendar": _calendar_sessions(calendar, cutoff_at=cutoff, calendar_id="SSE_BOND"),
        }
        return _build_snapshot(
            identity=identity,
            cutoff_at=cutoff,
            retrieved_at=datetime.now(timezone.utc),
            raw_schema_version="akshare-sse-bond-v1",
            raw_fields=raw_fields,
            history_rows=_history_rows(
                daily,
                cutoff_at=cutoff,
                close_columns=("close", "收盘"),
                volume_columns=("volume", "成交量"),
            ),
            source_id=self.source_id,
            capabilities=["price", "official_valuation", "curve", "cashflows"],
            observed_at=observed_at,
            documentation_url="https://akshare.akfamily.xyz/data/bond/bond.html",
        )

    @staticmethod
    def _quote_row(spot: Any, symbol: str) -> dict[str, Any] | None:
        if spot is None or spot.empty:
            return None
        normalized = symbol.lower()
        for _, row in spot.iterrows():
            raw = dict(row)
            code = str(_row_value(raw, "symbol", "代码") or "").lower()
            if code == normalized:
                return raw
        return None

    @staticmethod
    def _quote(row: Row | None, *, cutoff: datetime) -> QuoteResult:
        if row is None:
            return {}, None
        if cutoff.date() != _now_utc().date():
            return {}, None
        tick_time = _text(_row_value(row, "ticktime", "时间"))
        quote_at = None
        if tick_time:
            try:
                quote_at = datetime.fromisoformat(
                    f"{cutoff.date().isoformat()}T{tick_time}+08:00"
                ).astimezone(timezone.utc)
            except ValueError:
                quote_at = datetime.combine(cutoff.date(), datetime.min.time(), tzinfo=timezone.utc)
        if quote_at is not None and quote_at > cutoff:
            return {}, None
        price = _number(_row_value(row, "trade", "最新价"))
        quote = {
            "price": price,
            "bid": _number(_row_value(row, "buy", "买入")),
            "ask": _number(_row_value(row, "sell", "卖出")),
            "volume": _number(_row_value(row, "volume", "成交量")),
            "amount": _number(_row_value(row, "amount", "成交额")),
            "official_valuation": price,
            "quote_at": quote_at.isoformat() if quote_at is not None else None,
        }
        return {key: value for key, value in quote.items() if value is not None}, quote_at

    @staticmethod
    def _profile_values(profile: Any) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if profile is None:
            return values
        for _, row in profile.iterrows():
            raw = dict(row)
            values[_text(_row_value(raw, "item", "name"))] = _row_value(raw, "value")
        return values

    @staticmethod
    def _cashflows(
        profile_values: dict[str, Any],
        *,
        cutoff: datetime,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        issue_date = _parse_date(profile_values.get("起息日期"))
        maturity_date = _parse_date(profile_values.get("到期日"))
        face_value = _number(profile_values.get("债券面值（元）"))
        if issue_date is None or maturity_date is None or face_value is None or face_value <= 0:
            return [], []
        payment_dates = _parse_payment_dates(
            profile_values.get("付息日期"), issue_year=issue_date.year, end_year=maturity_date.year
        )
        rates = _parse_coupon_rates(
            profile_values.get("利率说明"), profile_values.get("票面利率（%）")
        )
        coupon_schedule = [
            {"year_index": index + 1, "annual_rate_percent": rate}
            for index, rate in enumerate(rates)
        ]
        cashflows: list[dict[str, Any]] = []
        for _payment_index, payment_date in enumerate(payment_dates, start=1):
            if payment_date <= cutoff.date():
                continue
            year_index = max(1, payment_date.year - issue_date.year)
            rate = (
                rates[year_index - 1] if year_index <= len(rates) else (rates[-1] if rates else 0.0)
            )
            coupon_amount = face_value * rate / 100.0
            is_maturity = payment_date == maturity_date
            cashflows.append(
                {
                    "payment_date": payment_date.isoformat(),
                    "amount": face_value + coupon_amount if is_maturity else coupon_amount,
                    "currency": "CNY",
                    "coupon_year_index": year_index,
                    "is_maturity_redemption": is_maturity,
                }
            )
        return cashflows, coupon_schedule

    @staticmethod
    def _curve(frame: Any, *, cutoff: datetime) -> CurveResult:
        if frame is None or frame.empty:
            return [], None
        rows: list[dict[str, Any]] = []
        latest_date: date | None = None
        latest_ten_years: float | None = None
        for _, row in frame.iterrows():
            raw = dict(row)
            curve_name = _text(_row_value(raw, "曲线名称", "name"))
            if "国债" not in curve_name:
                continue
            row_date = _parse_date(_row_value(raw, "日期", "date"))
            if row_date is None or row_date > cutoff.date():
                continue
            for tenor in ("3月", "6月", "1年", "3年", "5年", "7年", "10年", "30年"):
                value = _number(raw.get(tenor))
                if value is None:
                    continue
                rows.append(
                    {
                        "curve_name": curve_name,
                        "date": row_date.isoformat(),
                        "tenor": tenor,
                        "yield_rate_percent": value,
                    }
                )
            if latest_date is None or row_date > latest_date:
                latest_date = row_date
                latest_ten_years = _number(raw.get("10年"))
        benchmark = None
        if latest_date is not None and latest_ten_years is not None:
            benchmark = {
                "benchmark_id": "CN_TREASURY_10Y",
                "name": "中债国债收益率曲线",
                "tenor_years": 10,
                "yield_rate_percent": latest_ten_years,
                "as_of": latest_date.isoformat(),
            }
        return rows, benchmark


def _parse_payment_dates(value: object, *, issue_year: int, end_year: int) -> list[date]:
    if value is None:
        return []
    text = str(value).strip()
    if not text or text in {"--", "-"}:
        return []
    payment_dates: list[date] = []
    for part in text.replace("；", ",").replace(";", ",").split(","):
        month_day = part.strip()
        if not month_day:
            continue
        try:
            month, day = (int(item) for item in month_day.split("-"))
        except ValueError:
            continue
        for year in range(issue_year + 1, end_year + 1):
            try:
                payment_dates.append(date(year, month, day))
            except ValueError:
                continue
    return sorted(set(payment_dates))


def _parse_coupon_rates(rate_description: object, simple_rate: object) -> list[float]:
    if rate_description is None:
        return []
    text = str(rate_description).strip()
    if not text or text in {"--", "-"}:
        simple = _number(simple_rate)
        return [simple] if simple is not None else []
    import re

    rates: list[float] = []
    for match in re.finditer(r"第[0-9一二三四五六七八九十\d]+年\s*([0-9]+(?:\.[0-9]+)?)%", text):
        value = _number(match.group(1))
        if value is not None:
            rates.append(value)
    return rates


class AkShareFundProvider(AssetDataProvider):
    """Public fund ETF quote, NAV, benchmark and info via EastMoney."""

    source_id = FUND_SOURCE_ID
    declared_source_ids = (FUND_SOURCE_ID,)
    network_policy = NetworkPolicy(allowed_hosts=_FUND_ALLOWED_HOSTS)

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot:
        if identity.asset_type != "fund":
            raise ValueError("AKSHARE_FUND_PROVIDER_ASSET_MISMATCH")
        ak = _akshare_module()
        cutoff = _as_utc(cutoff_at)
        symbol = identity.display_symbol

        try:
            info_raw = await asyncio.to_thread(ak.fund_etf_fund_info_em, fund=symbol)
            info_values = self._parse_info(info_raw) if info_raw is not None else {}
        except Exception:
            info_values = {}

        try:
            spot = await asyncio.to_thread(ak.fund_etf_spot_em)
            quote_row = self._quote_row(spot, symbol)
            quote, quote_observed_at = self._quote(quote_row, cutoff=cutoff)
        except Exception:
            quote, quote_observed_at = {}, None

        fund_fields: dict[str, Any] = {
            "fund_code": symbol,
            "fund_name": info_values.get("基金简称") or identity.name,
            "fund_type": info_values.get("基金类型"),
            "nav": _number(info_values.get("单位净值")),
            "acc_nav": _number(info_values.get("累计净值")),
            "nav_date": _parse_date(info_values.get("净值日期")),
            "management_fee": _number(info_values.get("管理费率")),
            "custodian_fee": _number(info_values.get("托管费率")),
            "benchmark": info_values.get("业绩比较基准"),
            "tracking_error": _number(info_values.get("跟踪误差")),
            "discount_premium": (
                _number(info_values.get("折溢价率"))
                if info_values.get("折溢价率") is not None
                else None
            ),
            "aum": _number(info_values.get("基金规模")),
            "listed": quote is not None and bool(quote),
        }
        calendar = await asyncio.to_thread(ak.tool_trade_date_hist_sina)
        raw_fields: dict[str, Any] = {
            "snapshot": quote,
            "fund": {key: value for key, value in fund_fields.items() if value is not None},
            "calendar": _calendar_sessions(calendar, cutoff_at=cutoff, calendar_id="SSE_FUND"),
        }
        observed_at = quote_observed_at or cutoff
        return _build_snapshot(
            identity=identity,
            cutoff_at=cutoff,
            retrieved_at=datetime.now(timezone.utc),
            raw_schema_version="akshare-em-fund-v1",
            raw_fields=raw_fields,
            history_rows=[],
            source_id=self.source_id,
            capabilities=["nav", "benchmark", "etf_quote"],
            observed_at=observed_at,
            documentation_url="https://akshare.akfamily.xyz/data/fund/fund_public.html",
        )

    @staticmethod
    def _parse_info(frame: Any) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if frame is None:
            return values
        for _, row in frame.iterrows():
            raw = dict(row)
            key = _text(_row_value(raw, "item", "字段"))
            if key:
                values[key] = _row_value(raw, "value", "值")
        return values

    @staticmethod
    def _quote_row(spot: Any, symbol: str) -> dict[str, Any] | None:
        if spot is None or spot.empty:
            return None
        normalized = symbol.lower()
        for _, row in spot.iterrows():
            raw = dict(row)
            code = str(_row_value(raw, "代码", "symbol") or "").lower()
            if code == normalized:
                return raw
        return None

    @staticmethod
    def _quote(row: Row | None, *, cutoff: datetime) -> QuoteResult:
        if row is None:
            return {}, None
        trade_date = _parse_date(_row_value(row, "日期", "date"))
        if trade_date is None or trade_date > cutoff.date():
            return {}, None
        quote = {
            "price": _number(_row_value(row, "最新价", "current_price")),
            "nav": _number(_row_value(row, "单位净值", "nav")),
            "acc_nav": _number(_row_value(row, "累计净值", "acc_nav")),
            "volume": _number(_row_value(row, "成交量", "volume")),
            "amount": _number(_row_value(row, "成交额", "amount")),
            "change_pct": _number(_row_value(row, "涨跌幅", "change")),
            "quote_date": trade_date.isoformat(),
        }
        observed_at = datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc)
        return {key: value for key, value in quote.items() if value is not None}, observed_at


class AkShareFxProvider(AssetDataProvider):
    """FX spot rates and BOC reference rates via EastMoney / BOC."""

    source_id = FX_SOURCE_ID
    declared_source_ids = (FX_SOURCE_ID,)
    network_policy = NetworkPolicy(allowed_hosts=_FX_ALLOWED_HOSTS)

    _MARKET_HOURS_UTC = (
        (datetime.strptime("21:05", "%H:%M").time(), datetime.strptime("04:55", "%H:%M").time()),
    )

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot:
        if identity.asset_type != "fx":
            raise ValueError("AKSHARE_FX_PROVIDER_ASSET_MISMATCH")
        ak = _akshare_module()
        cutoff = _as_utc(cutoff_at)
        symbol = identity.display_symbol

        try:
            spot = await asyncio.to_thread(ak.forex_spot_em)
            quote_row = self._quote_row(spot, symbol)
            quote, quote_observed_at = self._quote(quote_row, cutoff=cutoff)
        except Exception:
            quote, quote_observed_at = {}, None

        try:
            boc = await asyncio.to_thread(ak.currency_boc_sina)
            boc_row = self._boc_row(boc, symbol[-3:]) if boc is not None else None
        except Exception:
            boc_row = None

        try:
            hist = await asyncio.to_thread(ak.forex_hist_em, symbol=symbol)
            history_rows = _history_rows(
                hist,
                cutoff_at=cutoff,
                close_columns=("最新价", "close"),
                volume_columns=(),
            )
        except Exception:
            history_rows = []

        fx_fields: dict[str, Any] = {
            "pair": symbol,
            "quote_direction": "DIRECT",
            "bid": _number(_row_value(quote_row or {}, "买入价", "bid") if quote_row else None),
            "ask": _number(_row_value(quote_row or {}, "卖出价", "ask") if quote_row else None),
            "boc_reference_rate": (
                _number(_row_value(boc_row or {}, "中行折算价", "rate")) if boc_row else None
            ),
            "boc_rate_date": (
                _parse_date(_row_value(boc_row or {}, "发布日期", "date")) if boc_row else None
            ),
        }
        raw_fields: dict[str, Any] = {
            "snapshot": quote,
            "fx": {key: value for key, value in fx_fields.items() if value is not None},
        }
        observed_at = quote_observed_at or cutoff
        return _build_snapshot(
            identity=identity,
            cutoff_at=cutoff,
            retrieved_at=datetime.now(timezone.utc),
            raw_schema_version="akshare-em-boc-fx-v1",
            raw_fields=raw_fields,
            history_rows=history_rows,
            source_id=self.source_id,
            capabilities=["spot", "reference_rate", "history"],
            observed_at=observed_at,
            documentation_url="https://akshare.akfamily.xyz/data/fx/fx.html",
        )

    @staticmethod
    def _quote_row(spot: Any, symbol: str) -> dict[str, Any] | None:
        if spot is None or spot.empty:
            return None
        normalized = symbol.upper()
        for _, row in spot.iterrows():
            raw = dict(row)
            code = str(_row_value(raw, "代码", "symbol") or "").upper()
            if code == normalized:
                return raw
        return None

    @staticmethod
    def _quote(row: Row | None, *, cutoff: datetime) -> QuoteResult:
        if row is None:
            return {}, None
        price = _number(_row_value(row, "最新价", "price"))
        if price is None:
            return {}, None
        quote = {
            "price": price,
            "open": _number(_row_value(row, "今开", "open")),
            "high": _number(_row_value(row, "最高", "high")),
            "low": _number(_row_value(row, "最低", "low")),
            "previous_close": _number(_row_value(row, "昨收", "previous_close")),
            "change_pct": _number(_row_value(row, "涨跌幅", "change_pct")),
        }
        observed_at = cutoff
        return {key: value for key, value in quote.items() if value is not None}, observed_at

    @staticmethod
    def _boc_row(boc: Any, currency: str) -> dict[str, Any] | None:
        if boc is None or boc.empty:
            return None
        normalized = currency.upper()
        for _, row in boc.iterrows():
            raw = dict(row)
            code = str(_row_value(raw, "货币名称", "currency") or "").upper()
            if normalized in code:
                return raw
        return None


class AkShareOptionProvider(AssetDataProvider):
    """SSE ETF option listings and spot quotes via Sina."""

    source_id = OPTION_SOURCE_ID
    declared_source_ids = (OPTION_SOURCE_ID,)
    network_policy = NetworkPolicy(allowed_hosts=_OPTION_ALLOWED_HOSTS)

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot:
        if identity.asset_type != "option":
            raise ValueError("AKSHARE_OPTION_PROVIDER_ASSET_MISMATCH")
        ak = _akshare_module()
        cutoff = _as_utc(cutoff_at)
        symbol = identity.display_symbol

        try:
            spot_price = await asyncio.to_thread(ak.option_sina_sse_spot_price, symbol=symbol)
            quote, quote_observed_at = self._option_quote(spot_price, cutoff=cutoff)
        except Exception:
            quote, quote_observed_at = {}, None

        try:
            listing = await asyncio.to_thread(ak.option_sina_sse_list, symbol=symbol[:6])
            contract_row = self._contract_row(listing, symbol)
        except Exception:
            contract_row = None

        option_fields: dict[str, Any] = {
            "contract_code": symbol,
            "underlying": symbol[:6] if len(symbol) >= 8 else None,
            "option_type": "CALL" if "C" in symbol[-4:] else "PUT",
            "strike": _number(getattr(identity.details, "strike_price", None)),
            "expiry_date": _parse_date(
                _row_value(contract_row or {}, "expiry_date", "到期日")
                if contract_row
                else getattr(identity.details, "expiry_date", None)
            ),
            "last_trade_date": _parse_date(
                _row_value(contract_row or {}, "last_trade_date", "最后交易日")
                if contract_row
                else None
            ),
            "multiplier": _number(
                _row_value(contract_row or {}, "multiplier", "合约乘数")
                if contract_row
                else getattr(identity.details, "contract_multiplier", None)
            ),
            "tick_size": _number(
                _row_value(contract_row or {}, "tick_size", "最小变动价位")
                if contract_row
                else None
            ),
        }
        raw_fields: dict[str, Any] = {
            "snapshot": quote,
            "option": {key: value for key, value in option_fields.items() if value is not None},
        }
        observed_at = quote_observed_at or cutoff
        return _build_snapshot(
            identity=identity,
            cutoff_at=cutoff,
            retrieved_at=datetime.now(timezone.utc),
            raw_schema_version="akshare-sina-option-v1",
            raw_fields=raw_fields,
            history_rows=[],
            source_id=self.source_id,
            capabilities=["spot", "contract_list", "greeks_approximate"],
            observed_at=observed_at,
            documentation_url="https://akshare.akfamily.xyz/data/option/option.html",
        )

    @staticmethod
    def _option_quote(frame: Any, *, cutoff: datetime) -> tuple[dict[str, Any], datetime | None]:
        if frame is None or frame.empty:
            return {}, None
        for _, row in frame.iterrows():
            raw = dict(row)
            quote = {
                "price": _number(_row_value(raw, "price", "最新价", "current_price")),
                "bid": _number(_row_value(raw, "bidprice", "bid", "买价")),
                "ask": _number(_row_value(raw, "askprice", "ask", "卖价")),
                "bid_volume": _number(_row_value(raw, "bidvolume", "bid_vol", "买量")),
                "ask_volume": _number(_row_value(raw, "askvolume", "ask_vol", "卖量")),
                "volume": _number(_row_value(raw, "volume", "成交量")),
                "open_interest": _number(_row_value(raw, "open_interest", "position", "持仓量")),
                "implied_vol": _number(_row_value(raw, "implied_volatility", "iv", "隐含波动率")),
                "delta": _number(_row_value(raw, "delta")),
                "gamma": _number(_row_value(raw, "gamma")),
                "theta": _number(_row_value(raw, "theta")),
                "vega": _number(_row_value(raw, "vega")),
                "theo_price": _number(_row_value(raw, "theo_price", "理论价")),
            }
            observed_at = datetime.now(timezone.utc)
            return {key: value for key, value in quote.items() if value is not None}, observed_at
        return {}, None

    @staticmethod
    def _contract_row(listing: Any, symbol: str) -> dict[str, Any] | None:
        if listing is None or listing.empty:
            return None
        normalized = symbol.upper()
        for _, row in listing.iterrows():
            raw = dict(row)
            code = str(_row_value(raw, "code", "合约代码", "symbol") or "").upper()
            if code == normalized:
                return raw
        return None


class AkShareCryptoProvider(AssetDataProvider):
    """Spot crypto quotes via OKX public API."""

    source_id = CRYPTO_SOURCE_ID
    declared_source_ids = (CRYPTO_SOURCE_ID,)
    network_policy = NetworkPolicy(
        allowed_hosts=_CRYPTO_ALLOWED_HOSTS,
        connect_timeout_seconds=10.0,
        read_timeout_seconds=20.0,
        total_timeout_seconds=45.0,
    )

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot:
        if identity.asset_type != "crypto":
            raise ValueError("AKSHARE_CRYPTO_PROVIDER_ASSET_MISMATCH")
        ak = _akshare_module()
        cutoff = _as_utc(cutoff_at)
        symbol = identity.display_symbol

        inst_id = self._okx_inst_id(symbol)
        try:
            ticker = await asyncio.to_thread(ak.okx_market_price, symbol=inst_id)
            quote, quote_observed_at = self._okx_quote(ticker, cutoff=cutoff)
        except Exception:
            quote, quote_observed_at = {}, None

        crypto_fields: dict[str, Any] = {
            "symbol": symbol,
            "okx_inst_id": inst_id,
            "venue": "OKX",
            "stablecoin_peg": self._detect_stablecoin_peg(symbol),
        }
        raw_fields: dict[str, Any] = {
            "snapshot": quote,
            "crypto": {key: value for key, value in crypto_fields.items() if value is not None},
        }
        observed_at = quote_observed_at or cutoff
        return _build_snapshot(
            identity=identity,
            cutoff_at=cutoff,
            retrieved_at=datetime.now(timezone.utc),
            raw_schema_version="akshare-okx-crypto-v1",
            raw_fields=raw_fields,
            history_rows=[],
            source_id=self.source_id,
            capabilities=["spot", "venue_orderbook"],
            observed_at=observed_at,
            documentation_url="https://akshare.akfamily.xyz/data/currency/currency.html",
        )

    @staticmethod
    def _okx_inst_id(symbol: str) -> str:
        upper = symbol.upper().replace("/", "-").replace("_", "-")
        return upper if "-" in upper else f"{upper}-USDT"

    @staticmethod
    def _okx_quote(frame: Any, *, cutoff: datetime) -> tuple[dict[str, Any], datetime | None]:
        if frame is None:
            return {}, None
        raw = dict(frame.iloc[0]) if hasattr(frame, "iloc") else dict(frame)
        price = _number(_row_value(raw, "last", "price", "最新价"))
        if price is None:
            return {}, None
        quote = {
            "price": price,
            "bid": _number(_row_value(raw, "bidPx", "bid", "买一价")),
            "ask": _number(_row_value(raw, "askPx", "ask", "卖一价")),
            "bid_volume": _number(_row_value(raw, "bidSz", "bid_vol")),
            "ask_volume": _number(_row_value(raw, "askSz", "ask_vol")),
            "high_24h": _number(_row_value(raw, "high24h", "high")),
            "low_24h": _number(_row_value(raw, "low24h", "low")),
            "volume_24h": _number(_row_value(raw, "vol24h", "volume")),
            "quote_at": _now_utc().isoformat(),
        }
        observed_at = _now_utc()
        return {key: value for key, value in quote.items() if value is not None}, observed_at

    @staticmethod
    def _detect_stablecoin_peg(symbol: str) -> str | None:
        upper = symbol.upper()
        if "USDT" in upper or "USDC" in upper or "DAI" in upper:
            return "USD"
        if "BTC" in upper:
            return None
        return None


class AkShareCompositeProvider(AssetDataProvider):
    """Dispatch one approved AkShare provider per pilot asset type."""

    source_id = "akshare_approved_cn_pilot"
    declared_source_ids = (
        FUTURES_SOURCE_ID,
        BOND_SOURCE_ID,
        FUND_SOURCE_ID,
        FX_SOURCE_ID,
        OPTION_SOURCE_ID,
        CRYPTO_SOURCE_ID,
    )
    network_policy = NetworkPolicy(
        allowed_hosts=(
            *_FUTURES_ALLOWED_HOSTS,
            *_BOND_ALLOWED_HOSTS,
            *_FUND_ALLOWED_HOSTS,
            *_FX_ALLOWED_HOSTS,
            *_OPTION_ALLOWED_HOSTS,
            *_CRYPTO_ALLOWED_HOSTS,
        )
    )

    def __init__(self) -> None:
        self._futures = AkShareFuturesProvider()
        self._bond = AkShareBondProvider()
        self._fund = AkShareFundProvider()
        self._fx = AkShareFxProvider()
        self._option = AkShareOptionProvider()
        self._crypto = AkShareCryptoProvider()

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot:
        if identity.asset_type == "futures":
            return await self._futures.collect(identity, cutoff_at=cutoff_at)
        if identity.asset_type == "bond":
            return await self._bond.collect(identity, cutoff_at=cutoff_at)
        if identity.asset_type == "fund":
            return await self._fund.collect(identity, cutoff_at=cutoff_at)
        if identity.asset_type == "fx":
            return await self._fx.collect(identity, cutoff_at=cutoff_at)
        if identity.asset_type == "option":
            return await self._option.collect(identity, cutoff_at=cutoff_at)
        if identity.asset_type == "crypto":
            return await self._crypto.collect(identity, cutoff_at=cutoff_at)
        raise ValueError("AKSHARE_PROVIDER_ASSET_UNSUPPORTED")
