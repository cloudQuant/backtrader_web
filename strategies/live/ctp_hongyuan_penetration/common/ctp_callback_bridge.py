"""Certification-local CTP request/callback correlation safeguards.

The installed CTP adapter accepts Backtrader's local ``bt_order_ref`` as a CTP
``OrderRef``.  That local counter restarts at one, while a newly logged-in CTP
session exposes its own monotonically increasing ``MaxOrderRef``.  A stale
local reference can therefore be rejected by the counter before an
``OnRtnOrder`` callback arrives.  In addition, a bare ``OnRspError`` contains
only a request id, so the adapter cannot otherwise associate it with its
order.

This module is intentionally scoped to the certification workspace.  It does
not change the installed shared package, and it only enriches order-insert
responses that were initiated through this exact store instance.
"""
from __future__ import annotations

from collections import OrderedDict
import importlib
import threading
import time
from typing import Any


_INSTALLED_ATTR = "_hongyuan_ctp_callback_bridge_installed"
_MAX_PENDING_REQUESTS = 128
_ORDER_QUERY_ROWS_ATTR = "_hongyuan_ctp_order_query_rows"
_ORDER_QUERY_ERROR_ATTR = "_hongyuan_ctp_order_query_error_id"
_ORDER_QUERY_DONE_ATTR = "_hongyuan_ctp_order_query_done"
_ORDER_QUERY_LOCK_ATTR = "_hongyuan_ctp_order_query_lock"
_CTP_CLIENT_MODULE_NAMES = (
    "bt_api_ctp.ctp.client",
    "bt_api_py.ctp.client",
)

_CTP_ORDER_STATUS = {
    "0": "completed",
    "1": "partial",
    "2": "canceled",
    "3": "accepted",
    "4": "canceled",
    "5": "canceled",
    "a": "submitted",
    "b": "submitted",
    "c": "submitted",
}
_CTP_ORDER_SUBMIT_STATUS = {"4": "rejected", "5": "cancel_rejected", "6": "rejected"}
_CTP_DIRECTION = {"0": "buy", "1": "sell"}
_CTP_OFFSET = {
    "0": "open",
    "1": "close",
    "2": "force_close",
    "3": "close_today",
    "4": "close_yesterday",
    "5": "force_close_yesterday",
    "6": "local_force_close",
}
_TERMINAL_ORDER_STATUSES = frozenset({"completed", "canceled", "rejected", "expired"})


def _as_request_id(value: Any) -> int | None:
    """Return a normalized CTP request id when it is an integer-like value."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_order_ref(value: Any) -> str:
    """Return a non-empty CTP order reference string, if available."""
    return str(value or "").strip()


def _field_text(field: Any, name: str) -> str:
    """Read one CTP field without serializing the rest of the callback object."""
    return str(getattr(field, name, "") or "").strip()


def _field_int(field: Any, name: str, default: int = 0) -> int:
    """Read a CTP integer field with a stable fallback."""
    try:
        return int(getattr(field, name, default) or default)
    except (TypeError, ValueError):
        return default


def _field_float(field: Any, name: str, default: float = 0.0) -> float:
    """Read a CTP price field with a stable fallback."""
    try:
        return float(getattr(field, name, default) or default)
    except (TypeError, ValueError):
        return default


def _normalise_ctp_order_status(order_status: Any, submit_status: Any) -> str:
    """Normalize the CTP order and submit-state pair used in query responses."""
    status = _CTP_ORDER_STATUS.get(str(order_status or "").strip().lower(), "submitted")
    return _CTP_ORDER_SUBMIT_STATUS.get(str(submit_status or "").strip().lower(), status)


def _normalise_ctp_order_row(order: Any) -> dict[str, Any] | None:
    """Create the minimal non-credential order shape required by reconciliation."""
    if order is None:
        return None
    order_ref = _field_text(order, "OrderRef")
    order_sys_id = _field_text(order, "OrderSysID")
    instrument = _field_text(order, "InstrumentID")
    if not order_ref and not order_sys_id:
        return None
    size = _field_int(order, "VolumeTotalOriginal")
    filled = _field_int(order, "VolumeTraded")
    remaining = _field_int(order, "VolumeTotal", max(size - filled, 0))
    return {
        "id": order_sys_id or order_ref,
        "external_order_id": order_sys_id,
        "order_ref": order_ref,
        "symbol": instrument,
        "instrument": instrument,
        "exchange_id": _field_text(order, "ExchangeID"),
        "status": _normalise_ctp_order_status(
            _field_text(order, "OrderStatus"),
            _field_text(order, "OrderSubmitStatus"),
        ),
        "side": _CTP_DIRECTION.get(_field_text(order, "Direction"), "buy"),
        "offset": _CTP_OFFSET.get(_field_text(order, "CombOffsetFlag"), "open"),
        "price": _field_float(order, "LimitPrice"),
        "size": size,
        "filled": filled,
        "remaining": remaining,
    }


def _on_rsp_qry_order(
    spi: Any,
    order: Any,
    rsp_info: Any,
    _request_id: Any,
    is_last: bool,
) -> None:
    """Capture a CTP ``OnRspQryOrder`` response using only safe order fields."""
    trader = getattr(spi, "_c", None)
    if trader is None:
        return
    rows = getattr(trader, _ORDER_QUERY_ROWS_ATTR, None)
    if isinstance(rows, list):
        normalized = _normalise_ctp_order_row(order)
        if normalized is not None:
            rows.append(normalized)
    if rsp_info is not None:
        error_id = _field_int(rsp_info, "ErrorID")
        if error_id:
            setattr(trader, _ORDER_QUERY_ERROR_ATTR, error_id)
    if is_last:
        done = getattr(trader, _ORDER_QUERY_DONE_ATTR, None)
        if callable(getattr(done, "set", None)):
            done.set()


def _active_spi_class(trader: Any | None) -> type[Any] | None:
    """Return the runtime SPI class selected by the active CTP adapter."""
    spi = getattr(trader, "_spi", None)
    return type(spi) if spi is not None else None


def _ctp_client_module_names(trader: Any | None = None) -> tuple[str, ...]:
    """Return active-first client modules supported by the local CTP adapters."""
    active_spi = _active_spi_class(trader)
    active_module = str(getattr(active_spi, "__module__", "") or "").strip()
    names: list[str] = []
    if active_module:
        names.append(active_module)
    names.extend(_CTP_CLIENT_MODULE_NAMES)
    return tuple(dict.fromkeys(names))


def enable_ctp_order_query_callback(trader: Any | None = None) -> bool:
    """Register ``OnRspQryOrder`` on the active CTP package before it starts.

    ``BtApiStore`` prefers ``bt_api_ctp`` when installed, while older local
    environments may expose only ``bt_api_py``.  Both need the callback before
    their ``TraderClient`` creates and registers its native SPI instance.
    """
    spi_classes: list[type[Any]] = []
    active_spi = _active_spi_class(trader)
    if active_spi is not None:
        spi_classes.append(active_spi)

    for module_name in _ctp_client_module_names(trader):
        try:
            ctp_client_module = importlib.import_module(module_name)
        except ImportError:
            continue
        spi_class = getattr(ctp_client_module, "_TraderSpi", None)
        if isinstance(spi_class, type):
            spi_classes.append(spi_class)

    registered = False
    for spi_class in dict.fromkeys(spi_classes):
        setattr(spi_class, "OnRspQryOrder", _on_rsp_qry_order)
        registered = True
    return registered


def _default_query_field_factory(trader: Any | None = None) -> Any:
    """Load the query struct from the package owning the active SPI class."""
    for client_module_name in _ctp_client_module_names(trader):
        if not client_module_name.endswith(".client"):
            continue
        query_module_name = f"{client_module_name.rsplit('.', 1)[0]}.ctp_structs_query"
        try:
            query_module = importlib.import_module(query_module_name)
        except ImportError:
            continue
        field_factory = getattr(query_module, "CThostFtdcQryOrderField", None)
        if callable(field_factory):
            return field_factory
    raise RuntimeError("CTP order-query request struct is not available")


def _query_lock_for(trader: Any) -> threading.RLock:
    """Return the lock used to keep order-query callbacks paired with one request."""
    lock = getattr(trader, _ORDER_QUERY_LOCK_ATTR, None)
    if lock is None:
        lock = threading.RLock()
        setattr(trader, _ORDER_QUERY_LOCK_ATTR, lock)
    return lock


def query_ctp_open_orders(
    api: Any,
    *,
    timeout_seconds: float = 5.0,
    field_factory: Any | None = None,
) -> list[dict[str, Any]]:
    """Query and return only counter-confirmed, non-terminal CTP orders.

    An unavailable CTP query raises instead of returning ``[]``.  That avoids
    treating a missing counter response as proof that no orders are open.
    """
    trader = getattr(api, "trader_client", None)
    native_api = getattr(trader, "api", None)
    if trader is None or native_api is None or not callable(getattr(native_api, "ReqQryOrder", None)):
        raise RuntimeError("CTP open-order query is not available")
    if not bool(getattr(trader, "is_ready", False)):
        raise RuntimeError("CTP trader is not ready for an open-order query")
    factory = field_factory or _default_query_field_factory(trader)

    with _query_lock_for(trader):
        for attempt in range(3):
            done = threading.Event()
            setattr(trader, _ORDER_QUERY_DONE_ATTR, done)
            setattr(trader, _ORDER_QUERY_ROWS_ATTR, [])
            setattr(trader, _ORDER_QUERY_ERROR_ATTR, 0)

            field = factory()
            field.BrokerID = str(getattr(trader, "broker_id", "") or "")
            field.InvestorID = str(getattr(trader, "user_id", "") or "")
            trader._req_id = _field_int(trader, "_req_id") + 1
            request_id = trader._req_id
            request_return = native_api.ReqQryOrder(field, request_id)
            if request_return != 0:
                raise RuntimeError(f"CTP open-order query send failed: ret={request_return}")
            if not done.wait(timeout_seconds):
                raise TimeoutError("CTP open-order query did not complete before the timeout")

            error_id = _field_int(trader, _ORDER_QUERY_ERROR_ATTR)
            if error_id == 0:
                rows = list(getattr(trader, _ORDER_QUERY_ROWS_ATTR, []) or [])
                return [
                    row
                    for row in rows
                    if str(row.get("status") or "") not in _TERMINAL_ORDER_STATUSES
                ]
            if error_id != 90 or attempt == 2:
                raise RuntimeError(f"CTP open-order query returned error code {error_id}")
            time.sleep(0.2)

    raise RuntimeError("CTP open-order query did not produce a result")


def install_ctp_callback_bridge(store: Any) -> bool:
    """Install a per-store bridge for CTP order references and response errors.

    The bridge is a no-op for stores that do not expose the CTP wrapper
    surface.  It allocates the CTP ``OrderRef`` from the authenticated trader
    session and only associates a bare response error when its request id was
    recorded for one of this session's order-insert requests.
    """
    api = getattr(store, "_api", None)
    if api is None:
        return False
    if getattr(api, _INSTALLED_ATTR, False):
        return True

    trader = getattr(api, "trader_client", None)
    submit_order = getattr(api, "submit_order", None)
    next_request_id = getattr(api, "_next_request_id", None)
    wait_error_event = getattr(trader, "wait_error_event", None)
    next_order_ref = getattr(trader, "next_order_ref", None)
    if not all(
        callable(item)
        for item in (submit_order, next_request_id, wait_error_event, next_order_ref)
    ):
        return False

    if enable_ctp_order_query_callback(trader):
        api.fetch_open_orders = lambda: query_ctp_open_orders(api)

    pending_requests: OrderedDict[int, dict[str, Any]] = OrderedDict()
    request_lock = threading.Lock()
    request_context = threading.local()

    def wrapped_next_request_id() -> Any:
        request_id = next_request_id()
        context = getattr(request_context, "value", None)
        normalized_request_id = _as_request_id(request_id)
        if isinstance(context, dict) and normalized_request_id is not None:
            with request_lock:
                pending_requests[normalized_request_id] = dict(context)
                while len(pending_requests) > _MAX_PENDING_REQUESTS:
                    pending_requests.popitem(last=False)
        return request_id

    def wrapped_submit_order(payload: Any) -> Any:
        if not isinstance(payload, dict):
            return submit_order(payload)

        normalized_payload = dict(payload)
        ctp_order_ref = _as_order_ref(normalized_payload.get("order_ref"))
        if not ctp_order_ref:
            ctp_order_ref = _as_order_ref(next_order_ref())
            if ctp_order_ref:
                normalized_payload["order_ref"] = ctp_order_ref

        request_context.value = {
            "operation": "order_insert",
            "order_ref": ctp_order_ref,
            "bt_order_ref": normalized_payload.get("bt_order_ref"),
        }
        try:
            return submit_order(normalized_payload)
        finally:
            request_context.value = None

    def wrapped_wait_error_event(timeout: float = 5) -> Any:
        event = wait_error_event(timeout=timeout)
        if not isinstance(event, dict):
            return event

        request_id = _as_request_id(event.get("request_id"))
        if request_id is None:
            return event
        with request_lock:
            context = pending_requests.get(request_id)
        if not isinstance(context, dict) or context.get("operation") != "order_insert":
            return event

        field = event.get("field")
        if isinstance(field, dict) and _as_order_ref(field.get("OrderRef")):
            return event

        order_ref = _as_order_ref(context.get("order_ref"))
        if not order_ref:
            return event
        enriched_event = dict(event)
        enriched_field = {"OrderRef": order_ref}
        bt_order_ref = context.get("bt_order_ref")
        if bt_order_ref not in (None, ""):
            enriched_field["bt_order_ref"] = bt_order_ref
        enriched_event["field"] = enriched_field
        with request_lock:
            pending_requests.pop(request_id, None)
        return enriched_event

    api._next_request_id = wrapped_next_request_id
    api.submit_order = wrapped_submit_order
    trader.wait_error_event = wrapped_wait_error_event
    setattr(api, _INSTALLED_ATTR, True)
    return True
