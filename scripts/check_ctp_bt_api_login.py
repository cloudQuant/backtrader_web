#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / 'src' / 'backend'
BT_API_PY_DIR = PROJECT_ROOT.parent / 'bt_api_py'
BACKEND_ENV_FILE = BACKEND_DIR / '.env'

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BT_API_PY_DIR) not in sys.path:
    sys.path.insert(0, str(BT_API_PY_DIR))


def load_backend_env_file() -> None:
    if not BACKEND_ENV_FILE.is_file():
        return
    for raw_line in BACKEND_ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_backend_env_file()

from app.config import get_settings
from bt_api_py.ctp.client import MdClient, TraderClient

SIMNOW_PRESETS: dict[str, dict[str, str]] = {
    'simnow_1': {
        'td_front': 'tcp://182.254.243.31:30001',
        'md_front': 'tcp://182.254.243.31:30011',
    },
    'simnow_2': {
        'td_front': 'tcp://182.254.243.31:30002',
        'md_front': 'tcp://182.254.243.31:30012',
    },
    'simnow_3': {
        'td_front': 'tcp://182.254.243.31:30003',
        'md_front': 'tcp://182.254.243.31:30013',
    },
    'simnow_7x24': {
        'td_front': 'tcp://182.254.243.31:40001',
        'md_front': 'tcp://182.254.243.31:40011',
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', default='simnow_1', choices=sorted(SIMNOW_PRESETS))
    parser.add_argument(
        '--mode',
        default='direct',
        choices=('direct', 'isolated-trader', 'raw-trader-api'),
    )
    parser.add_argument('--all-presets', action='store_true')
    parser.add_argument('--broker-id', default='')
    parser.add_argument('--user-id', default='')
    parser.add_argument('--password', default='')
    parser.add_argument('--app-id', default='')
    parser.add_argument('--auth-code', default='')
    parser.add_argument('--td-front', default='')
    parser.add_argument('--md-front', default='')
    parser.add_argument('--timeout', type=float, default=20.0)
    parser.add_argument('--output-json', default='')
    return parser.parse_args()


def mask_user_id(user_id: str) -> str:
    if len(user_id) <= 4:
        return '*' * len(user_id)
    return f'{user_id[:2]}***{user_id[-2:]}'


def normalize_message(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('gbk', errors='replace')
    return str(value)


def resolve_credentials(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    preset = SIMNOW_PRESETS[args.preset]
    broker_id = args.broker_id or getattr(settings, 'CTP_BROKER_ID', '') or '9999'
    user_id = args.user_id or getattr(settings, 'CTP_INVESTOR_ID', '') or getattr(settings, 'CTP_USER_ID', '')
    password = args.password or getattr(settings, 'CTP_PASSWORD', '')
    app_id = args.app_id or getattr(settings, 'CTP_APP_ID', '') or 'simnow_client_test'
    auth_code = args.auth_code or getattr(settings, 'CTP_AUTH_CODE', '') or '0000000000000000'
    td_front = args.td_front or preset['td_front']
    md_front = args.md_front or preset['md_front']
    return {
        'broker_id': broker_id,
        'user_id': user_id,
        'password': password,
        'app_id': app_id,
        'auth_code': auth_code,
        'td_front': td_front,
        'md_front': md_front,
        'preset': args.preset,
        'timeout': args.timeout,
    }


def test_md(credentials: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    client = MdClient(
        credentials['md_front'],
        credentials['broker_id'],
        credentials['user_id'],
        credentials['password'],
    )

    def on_login(field: Any) -> None:
        events.append(
            {
                'event': 'login',
                'trading_day': normalize_message(getattr(field, 'TradingDay', '')),
            }
        )

    def on_error(rsp: Any) -> None:
        events.append(
            {
                'event': 'error',
                'error_id': getattr(rsp, 'ErrorID', None),
                'error_msg': normalize_message(getattr(rsp, 'ErrorMsg', '')),
            }
        )

    client.on_login = on_login
    client.on_error = on_error
    started_at = time.time()
    try:
        client.start(block=False)
        ready = client.wait_ready(timeout=credentials['timeout'])
        return {
            'ready': ready,
            'elapsed_sec': round(time.time() - started_at, 3),
            'events': events,
        }
    finally:
        try:
            client.stop()
        except Exception as exc:
            events.append({'event': 'stop_error', 'message': str(exc)})


def test_td(credentials: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    client = TraderClient(
        credentials['td_front'],
        credentials['broker_id'],
        credentials['user_id'],
        credentials['password'],
        app_id=credentials['app_id'],
        auth_code=credentials['auth_code'],
    )

    def on_login(field: Any) -> None:
        events.append(
            {
                'event': 'login',
                'trading_day': normalize_message(getattr(field, 'TradingDay', '')),
                'front_id': getattr(field, 'FrontID', None),
                'session_id': getattr(field, 'SessionID', None),
            }
        )

    def on_error(rsp: Any) -> None:
        events.append(
            {
                'event': 'error',
                'error_id': getattr(rsp, 'ErrorID', None),
                'error_msg': normalize_message(getattr(rsp, 'ErrorMsg', '')),
            }
        )

    client.on_login = on_login
    client.on_error = on_error
    started_at = time.time()
    try:
        client.start(block=False)
        ready = client.wait_ready(timeout=credentials['timeout'])
        account_ok = False
        if ready:
            account_ok = client.query_account(timeout=5) is not None
        return {
            'ready': ready,
            'query_account_ok': account_ok,
            'elapsed_sec': round(time.time() - started_at, 3),
            'events': events,
        }
    finally:
        try:
            client.stop()
        except Exception as exc:
            events.append({'event': 'stop_error', 'message': str(exc)})


def run_isolated_trader_probe(credentials: dict[str, Any]) -> dict[str, Any]:
    child_script = """
import json
import os
import sys
import traceback

sys.path.insert(0, os.environ['BT_API_PY_ROOT'])

from bt_api_py.ctp.client import TraderClient

events = []
exit_code = 1
client = TraderClient(
    os.environ['BTAPI_TD_FRONT'],
    os.environ['BTAPI_BROKER_ID'],
    os.environ['BTAPI_USER_ID'],
    os.environ['BTAPI_PASSWORD'],
    app_id=os.environ['BTAPI_APP_ID'],
    auth_code=os.environ['BTAPI_AUTH_CODE'],
)
client.on_login = lambda field: events.append(
    {
        'event': 'login',
        'trading_day': str(getattr(field, 'TradingDay', '') or ''),
        'front_id': getattr(field, 'FrontID', None),
        'session_id': getattr(field, 'SessionID', None),
    }
)
client.on_error = lambda rsp: events.append(
    {
        'event': 'error',
        'error_id': getattr(rsp, 'ErrorID', None),
        'error_msg': str(getattr(rsp, 'ErrorMsg', '') or ''),
    }
)
payload = {}
try:
    client.start(block=False)
    ready = client.wait_ready(timeout=float(os.environ['BTAPI_TIMEOUT']))
    payload = {
        'ready': ready,
        'events': events,
        'lifecycle_events': list(getattr(client, '_lifecycle_events', [])),
        'connected_flag': bool(getattr(client, '_connected', False)),
        'ready_flag': bool(getattr(client, '_ready', False)),
        'thread_alive': bool(getattr(client, '_thread', None) and client._thread.is_alive()),
        'join_returned': bool(getattr(client, '_join_returned', False)),
        'join_error': str(getattr(client, '_join_error', '') or ''),
    }
    exit_code = 0 if ready else 1
except Exception as exc:
    payload = {
        'ready': False,
        'events': events,
        'lifecycle_events': list(getattr(client, '_lifecycle_events', [])),
        'exception': {
            'type': type(exc).__name__,
            'message': str(exc),
            'traceback': traceback.format_exc(),
        },
    }
finally:
    try:
        client.stop()
    except Exception as exc:
        events.append({'event': 'stop_error', 'message': str(exc)})
print(json.dumps(payload, ensure_ascii=False))
sys.stdout.flush()
sys.stderr.flush()
os._exit(exit_code)
""".strip()

    child_env = os.environ.copy()
    child_env.update(
        {
            'BT_API_PY_ROOT': str(BT_API_PY_DIR),
            'BTAPI_TD_FRONT': credentials['td_front'],
            'BTAPI_BROKER_ID': credentials['broker_id'],
            'BTAPI_USER_ID': credentials['user_id'],
            'BTAPI_PASSWORD': credentials['password'],
            'BTAPI_APP_ID': credentials['app_id'],
            'BTAPI_AUTH_CODE': credentials['auth_code'],
            'BTAPI_TIMEOUT': str(credentials['timeout']),
        }
    )
    try:
        completed = subprocess.run(
            [sys.executable, '-c', child_script],
            cwd=str(PROJECT_ROOT),
            env=child_env,
            capture_output=True,
            text=True,
            timeout=max(int(credentials['timeout']) + 20, 40),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        payload = {
            'ready': False,
            'timed_out': True,
            'stdout_partial': (exc.stdout or '').strip(),
            'stderr_partial': (exc.stderr or '').strip(),
            'returncode': None,
        }
        return payload
    payload: dict[str, Any] = {}
    stdout_text = completed.stdout.strip()
    if stdout_text:
        try:
            payload = json.loads(stdout_text.splitlines()[-1])
        except json.JSONDecodeError:
            payload = {'raw_stdout': stdout_text}
    payload['returncode'] = completed.returncode
    stderr_text = completed.stderr.strip()
    if stderr_text:
        payload['stderr'] = stderr_text
    return payload


def run_direct_mode(credentials: dict[str, Any]) -> dict[str, Any]:
    result = {
        'status': 'ok',
        'mode': 'direct',
        'preset': credentials['preset'],
        'broker_id': credentials['broker_id'],
        'user_id_masked': mask_user_id(credentials['user_id']),
        'td_front': credentials['td_front'],
        'md_front': credentials['md_front'],
        'timeout': credentials['timeout'],
        'market': test_md(credentials),
        'trade': test_td(credentials),
    }
    result['summary'] = {
        'market_ready': result['market']['ready'],
        'trade_ready': result['trade']['ready'],
        'direct_bt_api_py_login_ok': bool(result['market']['ready'] and result['trade']['ready']),
    }
    return result


def run_isolated_trader_mode(credentials: dict[str, Any], all_presets: bool) -> dict[str, Any]:
    preset_names = sorted(SIMNOW_PRESETS) if all_presets else [credentials['preset']]
    results: list[dict[str, Any]] = []
    for preset_name in preset_names:
        preset = SIMNOW_PRESETS[preset_name]
        probe_credentials = dict(credentials)
        probe_credentials['preset'] = preset_name
        probe_credentials['td_front'] = preset['td_front']
        probe_credentials['md_front'] = preset['md_front']
        probe = run_isolated_trader_probe(probe_credentials)
        results.append(
            {
                'preset': preset_name,
                'td_front': probe_credentials['td_front'],
                'md_front': probe_credentials['md_front'],
                **probe,
            }
        )
    successful = [item['preset'] for item in results if item.get('ready')]
    return {
        'status': 'ok',
        'mode': 'isolated-trader',
        'broker_id': credentials['broker_id'],
        'user_id_masked': mask_user_id(credentials['user_id']),
        'timeout': credentials['timeout'],
        'results': results,
        'summary': {
            'any_ready': bool(successful),
            'successful_presets': successful,
        },
    }


def run_raw_trader_api_probe(credentials: dict[str, Any]) -> dict[str, Any]:
    child_script = """
import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.environ['BT_API_PY_ROOT'])

from bt_api_py.ctp.ctp_structs_common import CThostFtdcReqAuthenticateField, CThostFtdcReqUserLoginField
from bt_api_py.ctp.ctp_trader_api import CThostFtdcTraderApi, CThostFtdcTraderSpi

events = []
done = threading.Event()
flow = str(os.path.join(tempfile.gettempdir(), 'ctp_raw_probe')) + os.sep
os.makedirs(flow, exist_ok=True)

class Spi(CThostFtdcTraderSpi):
    def OnFrontConnected(self):
        events.append({'event': 'front_connected'})
        field = CThostFtdcReqAuthenticateField()
        field.BrokerID = os.environ['BTAPI_BROKER_ID']
        field.UserID = os.environ['BTAPI_USER_ID']
        field.AppID = os.environ['BTAPI_APP_ID']
        field.AuthCode = os.environ['BTAPI_AUTH_CODE']
        ret = api.ReqAuthenticate(field, 1)
        events.append({'event': 'req_authenticate', 'result': ret})

    def OnFrontDisconnected(self, nReason):
        events.append({'event': 'front_disconnected', 'reason': nReason})
        done.set()

    def OnRspAuthenticate(self, pRspAuthenticateField, pRspInfo, nRequestID, bIsLast):
        events.append({
            'event': 'rsp_authenticate',
            'request_id': nRequestID,
            'is_last': bIsLast,
            'error_id': getattr(pRspInfo, 'ErrorID', None),
            'error_msg': str(getattr(pRspInfo, 'ErrorMsg', '') or ''),
        })
        if pRspInfo and pRspInfo.ErrorID == 0:
            field = CThostFtdcReqUserLoginField()
            field.BrokerID = os.environ['BTAPI_BROKER_ID']
            field.UserID = os.environ['BTAPI_USER_ID']
            field.Password = os.environ['BTAPI_PASSWORD']
            ret = api.ReqUserLogin(field, 2)
            events.append({'event': 'req_user_login', 'result': ret})
        else:
            done.set()

    def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
        events.append({
            'event': 'rsp_user_login',
            'request_id': nRequestID,
            'is_last': bIsLast,
            'error_id': getattr(pRspInfo, 'ErrorID', None),
            'error_msg': str(getattr(pRspInfo, 'ErrorMsg', '') or ''),
        })
        done.set()

    def OnRspError(self, pRspInfo, nRequestID, bIsLast):
        events.append({
            'event': 'rsp_error',
            'request_id': nRequestID,
            'is_last': bIsLast,
            'error_id': getattr(pRspInfo, 'ErrorID', None),
            'error_msg': str(getattr(pRspInfo, 'ErrorMsg', '') or ''),
        })
        done.set()

api = CThostFtdcTraderApi.CreateFtdcTraderApi(flow)
spi = Spi()
api.RegisterSpi(spi)
register_front_ret = api.RegisterFront(os.environ['BTAPI_TD_FRONT'])
api.SubscribePrivateTopic(2)
api.SubscribePublicTopic(2)
api.Init()
thread = threading.Thread(target=api.Join, daemon=True)
thread.start()
done.wait(float(os.environ['BTAPI_TIMEOUT']))
payload = {
    'register_front_ret': register_front_ret,
    'events': events,
    'join_alive': thread.is_alive(),
}
print(json.dumps(payload, ensure_ascii=False))
sys.stdout.flush()
sys.stderr.flush()
os._exit(0 if any(item.get('event') == 'rsp_user_login' and not item.get('error_id') for item in events) else 1)
""".strip()

    child_env = os.environ.copy()
    child_env.update(
        {
            'BT_API_PY_ROOT': str(BT_API_PY_DIR),
            'BTAPI_TD_FRONT': credentials['td_front'],
            'BTAPI_BROKER_ID': credentials['broker_id'],
            'BTAPI_USER_ID': credentials['user_id'],
            'BTAPI_PASSWORD': credentials['password'],
            'BTAPI_APP_ID': credentials['app_id'],
            'BTAPI_AUTH_CODE': credentials['auth_code'],
            'BTAPI_TIMEOUT': str(credentials['timeout']),
        }
    )
    try:
        completed = subprocess.run(
            [sys.executable, '-c', child_script],
            cwd=str(PROJECT_ROOT),
            env=child_env,
            capture_output=True,
            text=True,
            timeout=max(int(credentials['timeout']) + 20, 40),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            'ready': False,
            'timed_out': True,
            'stdout_partial': (exc.stdout or '').strip(),
            'stderr_partial': (exc.stderr or '').strip(),
            'returncode': None,
        }
    payload: dict[str, Any] = {}
    stdout_text = completed.stdout.strip()
    if stdout_text:
        try:
            payload = json.loads(stdout_text.splitlines()[-1])
        except json.JSONDecodeError:
            payload = {'raw_stdout': stdout_text}
    payload['returncode'] = completed.returncode
    stderr_text = completed.stderr.strip()
    if stderr_text:
        payload['stderr'] = stderr_text
    payload['ready'] = completed.returncode == 0
    return payload


def run_raw_trader_api_mode(credentials: dict[str, Any], all_presets: bool) -> dict[str, Any]:
    preset_names = sorted(SIMNOW_PRESETS) if all_presets else [credentials['preset']]
    results: list[dict[str, Any]] = []
    for preset_name in preset_names:
        preset = SIMNOW_PRESETS[preset_name]
        probe_credentials = dict(credentials)
        probe_credentials['preset'] = preset_name
        probe_credentials['td_front'] = preset['td_front']
        probe_credentials['md_front'] = preset['md_front']
        probe = run_raw_trader_api_probe(probe_credentials)
        results.append(
            {
                'preset': preset_name,
                'td_front': probe_credentials['td_front'],
                'md_front': probe_credentials['md_front'],
                **probe,
            }
        )
    successful = [item['preset'] for item in results if item.get('ready')]
    return {
        'status': 'ok',
        'mode': 'raw-trader-api',
        'broker_id': credentials['broker_id'],
        'user_id_masked': mask_user_id(credentials['user_id']),
        'timeout': credentials['timeout'],
        'results': results,
        'summary': {
            'any_ready': bool(successful),
            'successful_presets': successful,
        },
    }


def main() -> int:
    args = parse_args()
    credentials = resolve_credentials(args)
    missing = [
        key
        for key in ('broker_id', 'user_id', 'password', 'td_front', 'md_front')
        if not credentials.get(key)
    ]
    if missing:
        payload = {
            'status': 'error',
            'message': f'missing required credentials: {", ".join(missing)}',
            'preset': credentials['preset'],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    if args.mode == 'isolated-trader':
        result = run_isolated_trader_mode(credentials, all_presets=args.all_presets)
        success = bool(result['summary']['any_ready'])
    elif args.mode == 'raw-trader-api':
        result = run_raw_trader_api_mode(credentials, all_presets=args.all_presets)
        success = bool(result['summary']['any_ready'])
    else:
        result = run_direct_mode(credentials)
        success = bool(result['summary']['direct_bt_api_py_login_ok'])

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output_json:
        Path(args.output_json).write_text(text, encoding='utf-8')
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
