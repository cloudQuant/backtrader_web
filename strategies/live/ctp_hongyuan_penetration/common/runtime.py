"""Store / Broker / Feed initialisation helpers and subprocess entry-point (宏源期货)."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

_SUITE_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SUITE_DIR.parents[2]

for _p in (_SUITE_DIR, _REPO_ROOT):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

try:
    from dotenv import load_dotenv

    load_dotenv(_SUITE_DIR / ".env")
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

import backtrader as bt  # noqa: E402
from backtrader.brokers.btapibroker import BtApiBroker  # noqa: E402
from backtrader.feeds.btapifeed import BtApiFeed  # noqa: E402
from backtrader.stores.btapistore import BtApiStore  # noqa: E402

from common import config as cfg  # noqa: E402
from common.ctp_callback_bridge import (  # noqa: E402
    enable_ctp_order_query_callback,
    install_ctp_callback_bridge,
)
from common.evidence import (  # noqa: E402
    attach_reconciliation,
    capture_store_snapshot,
    mask_account_id,
)
from common.result import CaseTimer, save_result  # noqa: E402


_SENSITIVE_RUNTIME_EVENT_KEYS = frozenset(
    {
        "password",
        "authcode",
        "investorid",
        "userid",
        "accountid",
        "token",
        "accesstoken",
        "secret",
        "clientsecret",
    }
)
REMOTE_VALIDATION_ENV = "HONGYUAN_CERTIFICATION_REMOTE_VALIDATION"

# These scenarios submit a normal opening order before they can evaluate their
# monitoring/threshold behavior.  They are deliberately stopped before the
# broker call when the authoritative CTP Available field is not positive.
_AVAILABLE_FUNDS_REQUIRED_CASE_IDS = frozenset(
    {
        "T01",
        "T03",
        "M04",
        "M05",
        "O01",
        "O03",
        "TH02",
        "TH04",
        "TH06",
        "B01",
        "B02",
        "L01",
        "L03",
    }
)
_TARGET_POSITION_REQUIRED_CASE_IDS = frozenset({"T02", "O02"})
_POSITION_SYMBOL_KEYS = (
    "instrument",
    "symbol",
    "InstrumentID",
    "Instrument",
    "contract",
    "contract_code",
)


class CertificationBlocked(BaseException):
    """A known live-certification precondition prevents a safe execution.

    Case implementations intentionally use broad ``except Exception`` blocks
    to turn runtime defects into result files.  This control-flow sentinel is
    outside that hierarchy so ``case_main`` can preserve a safety preflight as
    BLOCKED instead of accidentally relabelling it as a failure.
    """

    def __init__(
        self,
        reason: str,
        *,
        next_action: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.next_action = next_action
        self.details = details or {}


def _remote_validation_enabled() -> bool:
    """Return whether this child is an explicitly acknowledged CTP run."""
    return os.getenv(REMOTE_VALIDATION_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _available_funds_state(balance: Any) -> str:
    """Classify CTP Available without retaining the monetary amount."""
    if not isinstance(balance, dict):
        return "unavailable"
    normalized = {
        "".join(char for char in str(key).lower() if char.isalnum()): value
        for key, value in balance.items()
    }
    available = next(
        (
            normalized[key]
            for key in ("available", "availablefunds", "cash")
            if key in normalized
        ),
        None,
    )
    if available is None:
        return "unavailable"
    try:
        return "positive" if float(available) > 0 else "zero"
    except (TypeError, ValueError):
        return "unavailable"


def _target_position_state(store: Any, symbol: str) -> str:
    """Classify whether the configured test contract has any closeable position."""
    try:
        positions = store.get_positions()
    except Exception:
        return "unavailable"
    if not isinstance(positions, list):
        return "unavailable"
    expected = symbol.strip().lower()
    for position in positions:
        if not isinstance(position, dict):
            continue
        matches_symbol = any(
            str(position.get(key) or "").strip().lower() == expected
            for key in _POSITION_SYMBOL_KEYS
        )
        if not matches_symbol:
            continue
        try:
            if float(position.get("volume") or position.get("Volume") or 0) > 0:
                return "present"
        except (TypeError, ValueError):
            return "unavailable"
    return "absent"


def build_order_preflight_block(
    store: Any,
    case_id: str,
    symbol: str | None = None,
) -> CertificationBlocked | None:
    """Return a safe BLOCKED condition for funded order scenarios, if needed.

    This preflight is active only in a child launched with ``--execute``.  It
    protects the account by not calling the order API at all when the CTP
    counter reports no usable funds or an unreadable available-funds response.
    Deliberate remote-rejection cases such as E01 are not in this set.
    """
    if not _remote_validation_enabled():
        return None
    if case_id in _TARGET_POSITION_REQUIRED_CASE_IDS:
        target_position = _target_position_state(store, symbol or cfg.get_order_symbol())
        if target_position != "present":
            if target_position == "absent":
                reason = "目标合约无持仓，已停止平仓认证且未向柜台提交订单"
                next_action = "准备专用测试合约持仓后重跑该平仓认证项"
            else:
                reason = "无法确认目标合约持仓，已停止平仓认证且未向柜台提交订单"
                next_action = "确认持仓查询回调正常后重跑该平仓认证项"
            return CertificationBlocked(
                reason,
                next_action=next_action,
                details={
                    "preflight": "target_position",
                    "target_position": target_position,
                    "counter_order_submitted": False,
                },
            )
    if case_id not in _AVAILABLE_FUNDS_REQUIRED_CASE_IDS:
        return None
    try:
        available_funds = _available_funds_state(store.get_balance())
    except Exception:
        available_funds = "unavailable"
    if available_funds == "positive":
        return None
    if available_funds == "zero":
        reason = "柜台可用资金为零，已停止正常委托认证且未向柜台提交订单"
        next_action = "为仿真账户入金或释放保证金后重跑该认证项"
    else:
        reason = "无法确认柜台可用资金，已停止正常委托认证且未向柜台提交订单"
        next_action = "确认资金查询回调正常后重跑该认证项"
    return CertificationBlocked(
        reason,
        next_action=next_action,
        details={
            "preflight": "available_funds",
            "available_funds": available_funds,
            "counter_order_submitted": False,
        },
    )


def _safe_runtime_event_value(value: Any) -> Any:
    """Make a runtime event safe to persist as local evidence."""
    if isinstance(value, dict):
        return {
            str(key): (
                "***"
                if "".join(char for char in str(key).lower() if char.isalnum())
                in _SENSITIVE_RUNTIME_EVENT_KEYS
                else _safe_runtime_event_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe_runtime_event_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _runtime_event_from_notification(notification: Any) -> dict[str, Any] | None:
    """Extract a structured runtime event from a Backtrader store notification."""
    candidates: list[Any]
    if isinstance(notification, tuple):
        candidates = list(reversed(notification))
    else:
        candidates = [notification]

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        event = candidate.get("event", candidate)
        if isinstance(event, dict) and event.get("event_type"):
            return dict(event)
    return None


def record_runtime_events(notifications: Iterable[Any], log_path: Path) -> set[str]:
    """Persist Store runtime events without leaking credentials or invalid UTF-8 text."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    event_types: set[str] = set()
    with log_path.open("w", encoding="utf-8") as handle:
        for notification in notifications:
            event = _runtime_event_from_notification(notification)
            if event is None:
                continue
            safe_event = _safe_runtime_event_value(event)
            event_type = str(safe_event.get("event_type") or "")
            if event_type:
                event_types.add(event_type)
            handle.write(json.dumps(safe_event, ensure_ascii=True, default=str))
            handle.write("\n")
    return event_types


@contextlib.contextmanager
def started_store(env_key=None, stop_on_exit=True, case_id=None, report_dir=None):
    """Create a live BtApiStore in a subprocess-safe context."""
    env_key = env_key or cfg.get_env_key()
    hy_config = cfg.create_config(env_key)
    env_info = cfg.HONGYUAN_ENVIRONMENTS[env_key]
    store = BtApiStore(provider="ctp", **hy_config)
    case_id = case_id or os.getenv("CERTIFICATION_CASE_ID", "")
    report_dir = report_dir or os.getenv("CERTIFICATION_REPORT_DIR", "")

    print(f"\n使用宏源期货环境: {env_info['name']}")
    print(f"  交易前置: {hy_config['td_address']}")
    print(f"  行情前置: {hy_config['md_address']}")
    print(f"  InvestorID: {mask_account_id(hy_config['investor_id'])}")

    preflight_blocked = False
    try:
        enable_ctp_order_query_callback()
        store.start()
        install_ctp_callback_bridge(store)
        if report_dir:
            capture_store_snapshot(
                report_dir=report_dir,
                case_id=case_id,
                label="before_action",
                store=store,
                env_key=env_key,
                config=hy_config,
                tracked_symbol=cfg.get_order_symbol(),
            )
        preflight_block = build_order_preflight_block(
            store,
            case_id,
            symbol=cfg.get_order_symbol(),
        )
        if preflight_block is not None:
            preflight_blocked = True
            raise preflight_block
        yield store, hy_config, env_key
    finally:
        if report_dir:
            capture_store_snapshot(
                report_dir=report_dir,
                case_id=case_id,
                label="after_action_before_stop",
                store=store,
                env_key=env_key,
                config=hy_config,
                tracked_symbol=cfg.get_order_symbol(),
            )
        if stop_on_exit or preflight_blocked:
            print("\n断开宏源期货连接...")
            store.stop()


def _get_store_seed_bars(store: Any, symbol: str) -> list[Any] | None:
    """Return explicit local test bars without invoking the CTP history API.

    Certification cases register deterministic bars with ``Store.set_history``.
    The CTP gateway may advertise a history method but return no bars, which
    otherwise replaces that local seed cache during feed startup.
    """
    cached_history = getattr(store, "_historical_bars", None)
    if not hasattr(cached_history, "get"):
        return None
    seed_bars = cached_history.get(symbol)
    return list(seed_bars) if seed_bars else None


def _explicit_order_offset(order: Any) -> str:
    """Return the explicit CTP offset attached to one Backtrader order."""
    info = getattr(order, "info", None)
    getter = getattr(info, "get", None)
    if not callable(getter):
        return ""
    return str(getter("offset") or "").strip().lower()


def _enable_remote_negative_close_probe(broker: Any) -> None:
    """Let E02 reach CTP for one explicit close-only rejection probe.

    The normal broker correctly blocks a close order that exceeds local
    position state.  E02 is specifically an integration test for CTP's own
    insufficient-position response, so the one local rejection is bypassed
    only in an explicitly acknowledged remote run.  Opening offsets and every
    other pre-trade rejection remain unchanged.
    """
    if not _remote_validation_enabled():
        raise RuntimeError("remote negative close probes require explicit CTP validation")

    original = getattr(broker, "_ensure_required_net_offset", None)
    if not callable(original):
        raise RuntimeError("broker does not expose the CTP close-position precheck")

    def allow_negative_close_probe(order: Any) -> Any:
        rejection = original(order)
        if (
            isinstance(rejection, tuple)
            and rejection
            and rejection[0] == "close_size_exceeds_position"
            and _explicit_order_offset(order) in {"close", "close_today", "close_yesterday"}
        ):
            return None
        return rejection

    broker._ensure_required_net_offset = allow_negative_close_probe


def create_broker(store: Any, **broker_kwargs: Any) -> BtApiBroker:
    """Create a broker while preserving local safety outside explicit certification.

    The CTP account's available-funds query is the authoritative pre-trade
    control.  For an explicitly confirmed certification run, bypass only the
    adapter's duplicate local cash estimate so the report captures the remote
    accept/reject response.  Contract, price, lot-size, and close-position
    validation remain enabled.
    """
    remote_negative_close_probe = bool(broker_kwargs.pop("remote_negative_close_probe", False))
    if remote_negative_close_probe and not _remote_validation_enabled():
        raise RuntimeError("remote negative close probes require explicit CTP validation")
    if _remote_validation_enabled():
        broker_kwargs.setdefault("cash_check_enabled", False)
        broker_kwargs.setdefault("cancel_wait_remote", True)
    if remote_negative_close_probe:
        broker_kwargs.setdefault("validation_enabled", False)
    broker = BtApiBroker(store=store, **broker_kwargs)
    if remote_negative_close_probe:
        _enable_remote_negative_close_probe(broker)
    return broker


def _ctp_quote_cache_keys(symbol: str) -> tuple[str, ...]:
    """Return common instrument aliases used by the direct CTP tick cache."""
    text = str(symbol or "").strip()
    if not text:
        return ()
    parts = [text]
    for separator in (".", "_"):
        if separator in text:
            parts.append(text.split(separator, 1)[-1])
    return tuple(dict.fromkeys(part.strip() for part in parts if part.strip()))


def wait_for_live_market_price(
    store: Any,
    symbol: str,
    *,
    timeout_seconds: float = 10.0,
) -> float:
    """Subscribe and return a positive CTP last price for a bounded probe.

    Certification orders must be priced from a current CTP tick.  Fixed seed
    prices can fall outside a rolled contract's daily price band and create an
    unrelated exchange rejection before the scenario under test is reached.
    """
    subscriber = getattr(store, "subscribe", None)
    if not callable(subscriber):
        raise RuntimeError("CTP store does not expose live market-data subscription")
    subscriber(symbol)

    keys = _ctp_quote_cache_keys(symbol)
    deadline = time.monotonic() + max(float(timeout_seconds), 0.0)
    while True:
        api = getattr(store, "_api", None)
        prices = getattr(api, "_last_tick_price", None)
        if hasattr(prices, "get"):
            for key in keys:
                try:
                    price = float(prices.get(key) or 0.0)
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    return price
        if time.monotonic() >= deadline:
            break
        time.sleep(0.05)

    raise RuntimeError("CTP live quote did not arrive before the probe timeout")


def create_cerebro(
    store,
    symbol=None,
    bar_seconds=5,
    with_trade_logger=False,
    log_dir=None,
    historical_bars=None,
    **broker_kwargs,
):
    """Create a Cerebro pre-wired with BtApiBroker + BtApiFeed."""
    symbol = symbol or cfg.get_order_symbol()
    if historical_bars is None:
        historical_bars = _get_store_seed_bars(store, symbol)
    broker = create_broker(store, **broker_kwargs)
    data = BtApiFeed(
        store=store,
        dataname=symbol,
        timeframe=bt.TimeFrame.Seconds,
        compression=bar_seconds,
        backfill_start=False,
        historical_bars=historical_bars,
    )
    store._cerebro_managed_lifecycle = False
    cerebro = bt.Cerebro()
    cerebro.setbroker(broker)
    cerebro.adddata(data)

    if with_trade_logger and log_dir:
        cerebro.addobserver(
            bt.observers.TradeLogger, log_dir=log_dir, log_format="json"
        )
    return cerebro


def run_with_timeout(cerebro, timeout_seconds=60):
    """Run *cerebro* with a daemon-timer hard timeout."""
    timer = threading.Timer(timeout_seconds, cerebro.runstop)
    timer.daemon = True
    timer.start()
    try:
        return cerebro.run()
    finally:
        timer.cancel()
        broker = getattr(cerebro, "broker", None)
        drain_updates = getattr(broker, "next", None)
        if callable(drain_updates):
            try:
                drain_updates()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Subprocess entry-point shared by all case files
# ---------------------------------------------------------------------------


def case_main(run_fn, meta: dict):
    """Standard ``if __name__ == '__main__'`` handler for every case file.

    *run_fn(report_dir) -> CaseResult*
    *meta* must contain ``case_id``.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--report-dir", default="")
    args, _ = parser.parse_known_args()

    case_id = meta["case_id"]
    report_dir = (
        Path(args.report_dir)
        if args.report_dir
        else _SUITE_DIR / "reports" / "latest" / case_id
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    old_report_dir = os.environ.get("CERTIFICATION_REPORT_DIR")
    old_case_id = os.environ.get("CERTIFICATION_CASE_ID")
    os.environ["CERTIFICATION_REPORT_DIR"] = str(report_dir)
    os.environ["CERTIFICATION_CASE_ID"] = case_id

    # Tee stdout / stderr to stdout.log
    stdout_log = report_dir / "stdout.log"
    _orig_stdout = sys.stdout
    _orig_stderr = sys.stderr

    class _Tee:
        """Tee stream that writes to both console and file with timestamps."""

        def __init__(self, stream, fh, label):
            """Initialize tee stream.

            Args:
                stream: Original stream to write to.
                fh: File handle to write to.
                label: Label for log entries.
            """
            self._stream = stream
            self._fh = fh
            self._label = label
            self._buffer = ""

        @staticmethod
        def _timestamp():
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        def _write_formatted_line(self, line):
            if not line:
                return

            if line.endswith("\n"):
                content = line[:-1]
                newline = "\n"
            else:
                content = line
                newline = ""

            if not content:
                self._fh.write(newline)
                return

            prefix = f"[{self._timestamp()}] [{self._label}] "
            self._fh.write(f"{prefix}{content}{newline}")

        def write(self, data):
            """Write data to both streams.

            Args:
                data: Data to write.
            """
            self._stream.write(data)
            if not data:
                return

            self._buffer += data
            while True:
                newline_index = self._buffer.find("\n")
                if newline_index < 0:
                    break
                line = self._buffer[: newline_index + 1]
                self._buffer = self._buffer[newline_index + 1 :]
                self._write_formatted_line(line)

        def flush(self):
            """Flush both streams."""
            if self._buffer:
                self._write_formatted_line(self._buffer)
                self._buffer = ""
            self._stream.flush()
            self._fh.flush()

    log_fh = open(stdout_log, "w", encoding="utf-8")
    log_fh.write(f"# stdout log for {case_id}\n")
    log_fh.write(f"# case_name: {meta.get('case_name', case_id)}\n")
    log_fh.write(f"# report_dir: {report_dir}\n")
    log_fh.write(f"# started_at: {datetime.now().isoformat(timespec='seconds')}\n\n")
    sys.stdout = _Tee(_orig_stdout, log_fh, "STDOUT")
    sys.stderr = _Tee(_orig_stderr, log_fh, "STDERR")

    try:
        result = run_fn(report_dir)
    except CertificationBlocked as blocked:
        env_key = cfg.get_env_key()
        with CaseTimer(case_id, meta.get("case_name", case_id), env_key) as timer:
            result = timer.blocked_result(
                blocked.reason,
                next_action=blocked.next_action,
                details=blocked.details,
            )
    except Exception:
        traceback.print_exc()
        env_key = cfg.get_env_key()
        with CaseTimer(case_id, meta.get("case_name", case_id), env_key) as timer:
            result = timer.fail_result(traceback.format_exc())

    result = attach_reconciliation(result, report_dir)
    save_result(result, report_dir)
    if old_report_dir is None:
        os.environ.pop("CERTIFICATION_REPORT_DIR", None)
    else:
        os.environ["CERTIFICATION_REPORT_DIR"] = old_report_dir
    if old_case_id is None:
        os.environ.pop("CERTIFICATION_CASE_ID", None)
    else:
        os.environ["CERTIFICATION_CASE_ID"] = old_case_id

    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr
    log_fh.close()

    print(f"\n[{case_id}] {result.status}  report -> {report_dir}")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(result.exit_code())
