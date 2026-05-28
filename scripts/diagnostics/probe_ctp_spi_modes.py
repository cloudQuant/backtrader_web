from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path('/Users/yunjinqi/Documents/new_projects/backtrader_web')
BT_API_ROOT = Path('/Users/yunjinqi/Documents/new_projects/bt_api_py')
BACKEND_ENV = PROJECT_ROOT / 'src' / 'backend' / '.env'

for raw_line in BACKEND_ENV.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    key = key.strip()
    value = value.strip()
    if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    os.environ.setdefault(key, value)

sys.path.insert(0, str(BT_API_ROOT))

from bt_api_py.ctp.ctp_structs_common import CThostFtdcReqAuthenticateField, CThostFtdcReqUserLoginField
from bt_api_py.ctp.ctp_trader_api import CThostFtdcTraderApi, CThostFtdcTraderSpi

BROKER_ID = os.environ['CTP_BROKER_ID']
USER_ID = os.environ.get('CTP_USER_ID') or os.environ.get('CTP_INVESTOR_ID') or ''
PASSWORD = os.environ['CTP_PASSWORD']
APP_ID = os.environ.get('CTP_APP_ID', 'simnow_client_test')
AUTH_CODE = os.environ.get('CTP_AUTH_CODE', '0000000000000000')
TD_FRONT = os.environ.get('CTP_TD_FRONT') or 'tcp://182.254.243.31:30001'
TIMEOUT_SEC = 12.0


class ProbeSpi(CThostFtdcTraderSpi):
    def __init__(self, events: list[dict[str, object]], done: threading.Event, api_ref: dict[str, object]):
        super().__init__()
        self._events = events
        self._done = done
        self._api_ref = api_ref

    def OnFrontConnected(self):
        self._events.append({'event': 'front_connected'})
        field = CThostFtdcReqAuthenticateField()
        field.BrokerID = BROKER_ID
        field.UserID = USER_ID
        field.AppID = APP_ID
        field.AuthCode = AUTH_CODE
        result = self._api_ref['api'].ReqAuthenticate(field, 1)
        self._events.append({'event': 'req_authenticate', 'result': result})

    def OnFrontDisconnected(self, nReason):
        self._events.append({'event': 'front_disconnected', 'reason': nReason})
        self._done.set()

    def OnRspAuthenticate(self, pRspAuthenticateField, pRspInfo, nRequestID, bIsLast):
        self._events.append(
            {
                'event': 'rsp_authenticate',
                'request_id': nRequestID,
                'is_last': bool(bIsLast),
                'error_id': getattr(pRspInfo, 'ErrorID', None),
                'error_msg': str(getattr(pRspInfo, 'ErrorMsg', '') or ''),
            }
        )
        if pRspInfo and pRspInfo.ErrorID == 0:
            field = CThostFtdcReqUserLoginField()
            field.BrokerID = BROKER_ID
            field.UserID = USER_ID
            field.Password = PASSWORD
            result = self._api_ref['api'].ReqUserLogin(field, 2)
            self._events.append({'event': 'req_user_login', 'result': result})
        else:
            self._done.set()

    def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
        self._events.append(
            {
                'event': 'rsp_user_login',
                'request_id': nRequestID,
                'is_last': bool(bIsLast),
                'error_id': getattr(pRspInfo, 'ErrorID', None),
                'error_msg': str(getattr(pRspInfo, 'ErrorMsg', '') or ''),
            }
        )
        self._done.set()

    def OnRspError(self, pRspInfo, nRequestID, bIsLast):
        self._events.append(
            {
                'event': 'rsp_error',
                'request_id': nRequestID,
                'is_last': bool(bIsLast),
                'error_id': getattr(pRspInfo, 'ErrorID', None),
                'error_msg': str(getattr(pRspInfo, 'ErrorMsg', '') or ''),
            }
        )
        self._done.set()


def run_probe(*, disown_spi: bool, front_as_bytes: bool) -> dict[str, object]:
    flow_dir = Path(tempfile.gettempdir()) / 'ctp_probe_modes' / f"d{int(disown_spi)}_b{int(front_as_bytes)}"
    flow_dir.mkdir(parents=True, exist_ok=True)
    done = threading.Event()
    events: list[dict[str, object]] = []
    api_ref: dict[str, object] = {}
    api = CThostFtdcTraderApi.CreateFtdcTraderApi(str(flow_dir) + os.sep)
    api_ref['api'] = api
    spi = ProbeSpi(events, done, api_ref)
    registered_spi = spi.__disown__() if disown_spi else spi
    join_thread: threading.Thread | None = None
    started_at = time.time()
    try:
        api.RegisterSpi(registered_spi)
        front_value = TD_FRONT.encode('utf-8') if front_as_bytes else TD_FRONT
        register_front_result = api.RegisterFront(front_value)
        api.SubscribePrivateTopic(2)
        api.SubscribePublicTopic(2)
        api.Init()
        join_thread = threading.Thread(target=api.Join, daemon=True)
        join_thread.start()
        done.wait(TIMEOUT_SEC)
        return {
            'disown_spi': disown_spi,
            'front_as_bytes': front_as_bytes,
            'register_front_result': register_front_result,
            'events': events,
            'elapsed_sec': round(time.time() - started_at, 3),
            'thread_alive': join_thread.is_alive(),
        }
    except Exception as exc:
        return {
            'disown_spi': disown_spi,
            'front_as_bytes': front_as_bytes,
            'events': events,
            'elapsed_sec': round(time.time() - started_at, 3),
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
            'thread_alive': bool(join_thread and join_thread.is_alive()),
        }


if __name__ == '__main__':
    payload = [
        run_probe(disown_spi=False, front_as_bytes=False),
        run_probe(disown_spi=True, front_as_bytes=False),
        run_probe(disown_spi=False, front_as_bytes=True),
        run_probe(disown_spi=True, front_as_bytes=True),
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
