"""Lifecycle and protocol contracts for the isolated AkShare runner adapter."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import runpy
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.market_data import akshare_provider
from app.services.market_data.akshare_provider import (
    AKSHARE_RUNNER_PROTOCOL_VERSION,
    AkShareMarketDataProvider,
    AkShareProviderError,
    _akshare_runner_environment,
)
from app.services.market_data.provider_contracts import AKSHARE_PROVIDER_CONTRACT_REGISTRY
from app.services.market_data.providers import MarketDataProviderRequest

UTC = timezone.utc


def _request(**changes: object) -> MarketDataProviderRequest:
    payload: dict[str, object] = {
        "query_fingerprint": "a" * 64,
        "canonical_id": "instrument:stock:CN-SZSE:000001",
        "asset_type": "stock",
        "provider_symbol": "000001",
        "market": "CN-SZSE",
        "data_kind": "bars",
        "frequency": "1d",
        "start_at": datetime(2026, 1, 2, tzinfo=UTC),
        "end_at": datetime(2026, 1, 4, tzinfo=UTC),
        "required_fields": frozenset({"open", "close"}),
        "provider": "akshare",
        "route_id": "akshare-stock-primary-v1",
        "family_id": "stock.realtime",
        "family_contract_version": "market-data-family-v1",
        "source_policy_id": "akshare-v2",
    }
    payload.update(changes)
    return MarketDataProviderRequest(**payload)  # type: ignore[arg-type]


def _runner_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_akshare_runner.py"
    script.write_text(body, encoding="utf-8")
    return script


def _runner_command(script: Path) -> tuple[str, str, str, str]:
    """Build the only accepted production runner command shape."""
    return (str(Path(sys.executable).resolve()), "-I", "-S", str(script.resolve()))


def _runner_configuration(tmp_path: Path) -> tuple[dict[str, str], str]:
    home = tmp_path / "runner-home"
    workdir = tmp_path / "runner-workdir"
    site_packages = tmp_path / "runner-site-packages"
    home.mkdir()
    workdir.mkdir()
    site_packages.mkdir()
    return (
        {
            "HOME": str(home),
            "AKSHARE_RUNNER_SITE_PACKAGES": str(site_packages),
        },
        str(workdir),
    )


def test_akshare_provider_exposes_no_in_process_source_or_receipt_seam() -> None:
    """No public constructor callback can bypass the POSIX runner boundary."""
    parameters = inspect.signature(AkShareMarketDataProvider).parameters
    assert "callable_resolver" not in parameters
    assert "test_runner" not in parameters

    with pytest.raises(TypeError, match="test_runner"):
        AkShareMarketDataProvider(test_runner=lambda _: {})  # type: ignore[call-arg]


def test_runner_endpoint_allowlist_matches_static_provider_contracts() -> None:
    """A contract cannot select an endpoint that the isolated child lacks."""
    runner = Path(__file__).resolve().parents[2] / "scripts" / "akshare_market_data_runner.py"
    runner_globals = runpy.run_path(str(runner))
    assert runner_globals["_ALLOWED_ENDPOINTS"] == frozenset(
        endpoint
        for contract in AKSHARE_PROVIDER_CONTRACT_REGISTRY.contracts
        for endpoint in contract.endpoints
    )


def _provider(tmp_path: Path, body: str, *, timeout_seconds: float = 1.0) -> AkShareMarketDataProvider:
    environment, workdir = _runner_configuration(tmp_path)
    return AkShareMarketDataProvider(
        command=_runner_command(_runner_script(tmp_path, body)),
        runner_environment=environment,
        runner_workdir=workdir,
        timeout_seconds=timeout_seconds,
    )


def _process_is_alive(process_id: int) -> bool:
    """Return whether a same-user test process remains after adapter cleanup."""
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    return True


_VALID_RESPONSE_SCRIPT = """
import json
import sys

envelope = json.loads(sys.stdin.buffer.readline())
json.dump(
    {
        "protocol_version": "akshare-market-data-v1",
        "request_id": envelope["request_id"],
        "request": envelope["request"],
        "execution": envelope["execution"],
        "source_revision": envelope["execution"]["source_revision"],
        "response_rows": [
            {"日期": "2026-01-02", "股票代码": "000001", "开盘": 10.0, "收盘": 10.5}
        ],
    },
    sys.stdout,
)
sys.stdout.write("\\n")
sys.stdout.flush()
sys.stdin.buffer.read(1)
"""


@pytest.mark.asyncio
async def test_akshare_runner_process_receipt_reuses_parent_normalization(tmp_path: Path) -> None:
    """A valid child receipt is normalized only after complete parent-side echo checks."""
    result = await _provider(tmp_path, _VALID_RESPONSE_SCRIPT).fetch(_request())

    assert result.provider_id == "akshare"
    assert result.observations[0].fields == {"open": 10.0, "close": 10.5}
    assert result.raw_payload["route"]["endpoint"] == "stock_zh_a_hist"


def test_isolated_akshare_runner_accepts_only_preparsed_execution(tmp_path: Path) -> None:
    """The shipped runner imports AkShare only after validating one parent envelope."""
    site_packages = tmp_path / "site-packages"
    workdir = tmp_path / "workdir"
    site_packages.mkdir()
    workdir.mkdir()
    (site_packages / "akshare.py").write_text(
        """
def stock_zh_a_hist(**kwargs):
    assert kwargs == {"symbol": "000001"}
    return [{"日期": "2026-01-02", "股票代码": "000001", "开盘": 10.0, "收盘": 10.5}]
""",
        encoding="utf-8",
    )
    request = _request()
    execution = {
        "route": {"route_id": "akshare-stock-primary-v1"},
        "endpoint": "stock_zh_a_hist",
        "call_kwargs": {"symbol": "000001"},
        "source_revision": "akshare-unknown:stock_zh_a_hist",
    }
    envelope = {
        "protocol_version": AKSHARE_RUNNER_PROTOCOL_VERSION,
        "request_id": request.request_id,
        "request": request.dto_payload,
        "execution": execution,
    }
    runner = Path(__file__).resolve().parents[2] / "scripts" / "akshare_market_data_runner.py"
    completed = subprocess.run(
        [str(Path(sys.executable).resolve()), "-I", "-S", str(runner)],
        input=json.dumps(envelope),
        text=True,
        capture_output=True,
        check=False,
        cwd=workdir,
        env={"AKSHARE_RUNNER_SITE_PACKAGES": str(site_packages)},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    response = json.loads(completed.stdout)
    assert response["execution"] == execution
    assert response["response_rows"][0]["股票代码"] == "000001"


def test_isolated_akshare_runner_echoes_verified_envelope_on_source_error(tmp_path: Path) -> None:
    """A source exception retains the authenticated request/execution receipt."""
    site_packages = tmp_path / "site-packages"
    workdir = tmp_path / "workdir"
    site_packages.mkdir()
    workdir.mkdir()
    (site_packages / "akshare.py").write_text(
        """
def stock_zh_a_hist(**kwargs):
    raise RuntimeError("synthetic source failure")
""",
        encoding="utf-8",
    )
    request = _request()
    execution = {
        "route": {"route_id": "akshare-stock-primary-v1"},
        "endpoint": "stock_zh_a_hist",
        "call_kwargs": {"symbol": "000001"},
        "source_revision": "akshare-unknown:stock_zh_a_hist",
    }
    envelope = {
        "protocol_version": AKSHARE_RUNNER_PROTOCOL_VERSION,
        "request_id": request.request_id,
        "request": request.dto_payload,
        "execution": execution,
    }
    runner = Path(__file__).resolve().parents[2] / "scripts" / "akshare_market_data_runner.py"
    completed = subprocess.run(
        [str(Path(sys.executable).resolve()), "-I", "-S", str(runner)],
        input=json.dumps(envelope),
        text=True,
        capture_output=True,
        check=False,
        cwd=workdir,
        env={"AKSHARE_RUNNER_SITE_PACKAGES": str(site_packages)},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    response = json.loads(completed.stdout)
    assert response["request"] == request.dto_payload
    assert response["execution"] == execution
    assert response["source_revision"] == execution["source_revision"]
    assert response["error"]["code"] == "AKSHARE_FETCH_FAILED"


@pytest.mark.asyncio
async def test_unconfigured_akshare_runner_fails_closed_before_spawn() -> None:
    """The default production factory never falls back to in-process AkShare."""
    provider = AkShareMarketDataProvider.from_environment(parent_environment={})

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request())

    assert rejected.value.code == "AKSHARE_RUNNER_COMMAND_UNCONFIGURED"


@pytest.mark.asyncio
async def test_query_provider_factory_uses_the_fail_closed_runner_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP route construction cannot resurrect the legacy direct-provider default."""
    from app.api.data import queries

    for environment_key in (
        "AKSHARE_MARKET_DATA_RUNNER",
        "AKSHARE_RUNNER_HOME",
        "AKSHARE_RUNNER_WORKDIR",
        "AKSHARE_RUNNER_SITE_PACKAGES",
    ):
        monkeypatch.delenv(environment_key, raising=False)
    queries._shared_akshare_provider.cache_clear()
    try:
        provider = queries._shared_akshare_provider()
        with pytest.raises(AkShareProviderError) as rejected:
            await provider.fetch(_request())
    finally:
        queries._shared_akshare_provider.cache_clear()

    assert rejected.value.code == "AKSHARE_RUNNER_COMMAND_UNCONFIGURED"


def test_akshare_runner_environment_never_forwards_application_secrets(tmp_path: Path) -> None:
    """Only explicit execution settings and the runner package path cross the boundary."""
    home = tmp_path / "runner-home"
    site_packages = tmp_path / "site-packages"
    home.mkdir()
    site_packages.mkdir()
    environment = _akshare_runner_environment(
        {
            "HOME": "/application/home",
            "AKSHARE_RUNNER_HOME": str(home),
            "AKSHARE_RUNNER_SITE_PACKAGES": str(site_packages),
            "DATABASE_URL": "postgresql://application:secret@example.test/market",
            "JWT_SECRET_KEY": "web-secret",
            "HTTP_PROXY": "http://proxy-user:proxy-secret@example.test",
            "PYTHONPATH": "/application/imports",
            "LANG": "C.UTF-8",
        }
    )

    assert environment == {
        "HOME": str(home),
        "AKSHARE_RUNNER_SITE_PACKAGES": str(site_packages),
        "LANG": "C.UTF-8",
    }


@pytest.mark.asyncio
async def test_invalid_akshare_runner_command_fails_closed_before_spawn(tmp_path: Path) -> None:
    """A shell-like or relative command cannot become a subprocess invocation."""
    provider = AkShareMarketDataProvider.from_environment(
        parent_environment={"AKSHARE_MARKET_DATA_RUNNER": f"sh {tmp_path / 'runner.py'}"}
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request())

    assert rejected.value.code == "AKSHARE_RUNNER_COMMAND_INVALID"


@pytest.mark.asyncio
async def test_missing_process_group_capability_fails_closed_before_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter never starts source work if it cannot later kill the group."""
    started = tmp_path / "runner-started"
    provider = _provider(
        tmp_path,
        f"""
from pathlib import Path
import sys

sys.stdin.buffer.readline()
Path({str(started)!r}).touch()
""",
    )
    monkeypatch.setattr(akshare_provider, "_has_safe_akshare_process_group", lambda: False)

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request())

    assert rejected.value.code == "AKSHARE_RUNNER_PROCESS_GROUP_UNSUPPORTED"
    assert not started.exists()


@pytest.mark.asyncio
async def test_route_rejection_happens_before_runner_spawn(tmp_path: Path) -> None:
    """An unsupported identity cannot cause even a fake runner process to launch."""
    started = tmp_path / "runner-started"
    provider = _provider(
        tmp_path,
        f"""
from pathlib import Path
import sys

sys.stdin.buffer.readline()
Path({str(started)!r}).touch()
""",
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request(market="US"))

    assert rejected.value.code == "AKSHARE_MARKET_UNSUPPORTED"
    assert not started.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_name", ("stdout", "stderr"))
async def test_akshare_runner_bounds_every_output_pipe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stream_name: str,
) -> None:
    """A noisy child cannot leave a bounded-but-undrained stream behind."""
    monkeypatch.setattr(akshare_provider, "_MAX_RUNNER_OUTPUT_BYTES", 128)
    provider = _provider(
        tmp_path,
        f"""
import sys

sys.stdin.buffer.readline()
sys.{stream_name}.write("x" * 256)
sys.{stream_name}.flush()
sys.stdin.buffer.read(1)
""",
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request())

    assert rejected.value.code == "AKSHARE_RUNNER_OUTPUT_TOO_LARGE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ('result["protocol_version"] = "other"', "AKSHARE_RUNNER_PROTOCOL_MISMATCH"),
        ('result["request"]["provider_symbol"] = "SUBSTITUTED"', "AKSHARE_RUNNER_PROTOCOL_MISMATCH"),
        ('result["execution"]["endpoint"] = "forex_hist_em"', "AKSHARE_RUNNER_PROTOCOL_MISMATCH"),
        ('result["source_revision"] = "akshare-substituted:stock_zh_a_hist"', "AKSHARE_RUNNER_SOURCE_REVISION_MISMATCH"),
        ('result["response_rows"] = {"not": "a-list"}', "AKSHARE_RUNNER_INVALID_RESPONSE"),
        ('result["unexpected"] = "unreviewed"', "AKSHARE_RUNNER_INVALID_RESPONSE"),
        (
            'result["response_rows"][0]["股票代码"] = "000002"',
            "AKSHARE_IDENTITY_MISMATCH",
        ),
    ),
)
async def test_akshare_runner_rejects_protocol_echo_and_result_tampering(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    """Every mutable child field is checked before persistence-ready rows exist."""
    provider = _provider(
        tmp_path,
        f"""
import json
import sys

envelope = json.loads(sys.stdin.buffer.readline())
result = {{
    "protocol_version": "akshare-market-data-v1",
    "request_id": envelope["request_id"],
    "request": envelope["request"],
    "execution": envelope["execution"],
    "source_revision": envelope["execution"]["source_revision"],
    "response_rows": [
        {{"日期": "2026-01-02", "股票代码": "000001", "开盘": 10.0, "收盘": 10.5}}
    ],
}}
{mutation}
json.dump(result, sys.stdout)
sys.stdout.write("\\n")
sys.stdout.flush()
sys.stdin.buffer.read(1)
""",
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request())

    assert rejected.value.code == expected_code


@pytest.mark.asyncio
async def test_akshare_runner_authenticates_an_error_receipt_before_propagating_it(
    tmp_path: Path,
) -> None:
    """A child error code is usable only when the full frozen envelope echoes."""
    provider = _provider(
        tmp_path,
        """
import json
import sys

envelope = json.loads(sys.stdin.buffer.readline())
json.dump(
    {
        "protocol_version": "akshare-market-data-v1",
        "request_id": envelope["request_id"],
        "request": envelope["request"],
        "execution": envelope["execution"],
        "source_revision": envelope["execution"]["source_revision"],
        "error": {"code": "AKSHARE_FETCH_FAILED", "detail": "source rejected request"},
    },
    sys.stdout,
)
sys.stdout.write("\\n")
sys.stdout.flush()
sys.stdin.buffer.read(1)
""",
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request())

    assert rejected.value.code == "AKSHARE_FETCH_FAILED"


@pytest.mark.asyncio
async def test_isolated_runner_rejects_an_independent_akshare_revision_mismatch(
    tmp_path: Path,
) -> None:
    """The child must refuse a receipt when its installed AkShare differs from the parent."""
    environment, workdir = _runner_configuration(tmp_path)
    site_packages = Path(environment["AKSHARE_RUNNER_SITE_PACKAGES"])
    endpoint = "stock_zh_a_hist"
    parent_revision = akshare_provider._source_revision(endpoint)
    child_version = "999.0.0"
    if parent_revision == f"akshare-{child_version}:{endpoint}":
        child_version = "998.0.0"
    distribution = site_packages / f"akshare-{child_version}.dist-info"
    distribution.mkdir()
    (distribution / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: akshare\nVersion: {child_version}\n",
        encoding="utf-8",
    )
    (site_packages / "akshare.py").write_text(
        "def stock_zh_a_hist(**kwargs):\n    return []\n",
        encoding="utf-8",
    )
    shipped_runner = Path(__file__).resolve().parents[2] / "scripts" / "akshare_market_data_runner.py"
    provider = AkShareMarketDataProvider(
        command=_runner_command(shipped_runner),
        runner_environment=environment,
        runner_workdir=workdir,
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request())

    assert rejected.value.code == "AKSHARE_RUNNER_SOURCE_REVISION_MISMATCH"


def test_runner_cleanup_orders_group_kill_before_direct_child_reap() -> None:
    """The implementation must never signal a numeric process group after reaping it."""
    cleanup_source = inspect.getsource(akshare_provider._cleanup_owned_runner_group)
    runner_source = inspect.getsource(akshare_provider._AkShareSubprocessRunner.execute)

    assert cleanup_source.index("_kill_owned_runner_group") < cleanup_source.index(
        "_reap_owned_runner_process"
    )
    assert "subprocess.Popen" in runner_source
    assert "asyncio.create_subprocess_exec" not in runner_source


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX process group")
async def test_akshare_runner_success_reaps_descendants_before_return(tmp_path: Path) -> None:
    """A successful receipt cannot leave a child behind after its leader is reaped."""
    ready = tmp_path / "success-child-ready"
    survived = tmp_path / "success-child-survived"
    runner_pid = tmp_path / "success-runner-pid"
    provider = _provider(
        tmp_path,
        f"""
import json
import os
from pathlib import Path
import sys
import time

envelope = json.loads(sys.stdin.buffer.readline())
Path({str(runner_pid)!r}).write_text(str(os.getpid()), encoding="utf-8")
child = os.fork()
if child == 0:
    Path({str(ready)!r}).touch()
    time.sleep(0.35)
    Path({str(survived)!r}).touch()
    time.sleep(10)
    os._exit(0)
while not Path({str(ready)!r}).exists():
    time.sleep(0.01)
json.dump(
    {{
        "protocol_version": "akshare-market-data-v1",
        "request_id": envelope["request_id"],
        "request": envelope["request"],
        "execution": envelope["execution"],
        "source_revision": envelope["execution"]["source_revision"],
        "response_rows": [
            {{"日期": "2026-01-02", "股票代码": "000001", "开盘": 10.0, "收盘": 10.5}}
        ],
    }},
    sys.stdout,
)
sys.stdout.write("\\n")
sys.stdout.flush()
sys.stdin.buffer.read(1)
""",
    )

    result = await provider.fetch(_request())

    await asyncio.sleep(0.45)
    assert result.provider_id == "akshare"
    assert ready.exists()
    assert not survived.exists()
    assert not _process_is_alive(int(runner_pid.read_text(encoding="utf-8")))


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX process group")
async def test_akshare_runner_permission_denied_cleanup_fails_closed_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live group after denied signaling cannot become a successful fetch."""
    permission_denied = asyncio.Event()
    group_was_live = asyncio.Event()
    group_confirmed = asyncio.Event()
    actual_killpg = os.killpg
    signal_attempted = False
    process_group_id: int | None = None

    def signal_with_audited_denial(group_id: int, value: int) -> None:
        nonlocal process_group_id, signal_attempted
        if value == signal.SIGKILL and not signal_attempted:
            signal_attempted = True
            process_group_id = group_id
            permission_denied.set()
            raise PermissionError("synthetic group permission denial")
        if value == 0:
            try:
                actual_killpg(group_id, value)
            except ProcessLookupError:
                group_confirmed.set()
                raise
            return
        actual_killpg(group_id, value)

    async def external_operator_terminates_confirmed_live_group() -> None:
        await asyncio.wait_for(permission_denied.wait(), timeout=1.0)
        assert process_group_id is not None
        assert actual_killpg(process_group_id, 0) is None
        group_was_live.set()
        await asyncio.sleep(0.05)
        actual_killpg(process_group_id, signal.SIGKILL)

    monkeypatch.setattr(akshare_provider.os, "killpg", signal_with_audited_denial)
    provider = _provider(
        tmp_path,
        """
import json
import sys
import time

envelope = json.loads(sys.stdin.buffer.readline())
json.dump(
    {
        "protocol_version": "akshare-market-data-v1",
        "request_id": envelope["request_id"],
        "request": envelope["request"],
        "execution": envelope["execution"],
        "source_revision": envelope["execution"]["source_revision"],
        "response_rows": [
            {"日期": "2026-01-02", "股票代码": "000001", "开盘": 10.0, "收盘": 10.5}
        ],
    },
    sys.stdout,
)
sys.stdout.write("\\n")
sys.stdout.flush()
time.sleep(10)
""",
    )
    operator_task = asyncio.create_task(external_operator_terminates_confirmed_live_group())

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(_request())
    await operator_task

    assert signal_attempted
    assert group_was_live.is_set()
    assert group_confirmed.is_set()
    assert rejected.value.code == "AKSHARE_RUNNER_CLEANUP_FAILED"


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX process group")
async def test_akshare_runner_timeout_kills_and_reaps_descendants_before_return(tmp_path: Path) -> None:
    """A timeout does not permit a forked source child to survive the provider call."""
    ready = tmp_path / "child-ready"
    survived = tmp_path / "child-survived"
    runner_pid = tmp_path / "runner-pid"
    provider = _provider(
        tmp_path,
        f"""
import os
from pathlib import Path
import sys
import time

sys.stdin.buffer.readline()
Path({str(runner_pid)!r}).write_text(str(os.getpid()), encoding="utf-8")
child = os.fork()
if child == 0:
    Path({str(ready)!r}).touch()
    time.sleep(0.35)
    Path({str(survived)!r}).touch()
    time.sleep(10)
    os._exit(0)
while not Path({str(ready)!r}).exists():
    time.sleep(0.01)
time.sleep(10)
""",
        timeout_seconds=0.1,
    )

    with pytest.raises(AkShareProviderError) as timed_out:
        await provider.fetch(_request())

    await asyncio.sleep(0.45)
    assert timed_out.value.code == "AKSHARE_TIMEOUT"
    assert ready.exists()
    assert not survived.exists()
    assert not _process_is_alive(int(runner_pid.read_text(encoding="utf-8")))


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX process group")
async def test_akshare_runner_cancellation_kills_and_reaps_descendants_before_propagation(
    tmp_path: Path,
) -> None:
    """Cancellation reaches the caller only after the AkShare runner group is gone."""
    ready = tmp_path / "cancel-child-ready"
    survived = tmp_path / "cancel-child-survived"
    runner_pid = tmp_path / "cancel-runner-pid"
    provider = _provider(
        tmp_path,
        f"""
import os
from pathlib import Path
import sys
import time

sys.stdin.buffer.readline()
Path({str(runner_pid)!r}).write_text(str(os.getpid()), encoding="utf-8")
child = os.fork()
if child == 0:
    Path({str(ready)!r}).touch()
    time.sleep(0.35)
    Path({str(survived)!r}).touch()
    time.sleep(10)
    os._exit(0)
while not Path({str(ready)!r}).exists():
    time.sleep(0.01)
time.sleep(10)
""",
        timeout_seconds=5.0,
    )

    task = asyncio.create_task(provider.fetch(_request()))
    for _ in range(100):
        if ready.exists():
            break
        await asyncio.sleep(0.01)
    assert ready.exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.sleep(0.45)
    assert not survived.exists()
    assert not _process_is_alive(int(runner_pid.read_text(encoding="utf-8")))


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX process group")
async def test_akshare_runner_double_cancellation_waits_for_kill_reap_and_drain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second cancellation cannot bypass the shielded runner cleanup boundary."""
    ready = tmp_path / "double-cancel-child-ready"
    survived = tmp_path / "double-cancel-child-survived"
    drained_marker = tmp_path / "double-cancel-stderr-written"
    runner_pid = tmp_path / "double-cancel-runner-pid"
    cleanup_started = asyncio.Event()
    cleanup_finished = asyncio.Event()
    original_cleanup = akshare_provider._cleanup_owned_runner_group
    original_confirmation = akshare_provider._confirm_runner_group_terminated

    async def delayed_confirmation(process_group_id: int) -> None:
        await original_confirmation(process_group_id)
        await asyncio.sleep(0.05)

    async def observed_cleanup(*args: object, **kwargs: object) -> object:
        cleanup_started.set()
        result = await original_cleanup(*args, **kwargs)
        cleanup_finished.set()
        return result

    monkeypatch.setattr(akshare_provider, "_confirm_runner_group_terminated", delayed_confirmation)
    monkeypatch.setattr(akshare_provider, "_cleanup_owned_runner_group", observed_cleanup)
    provider = _provider(
        tmp_path,
        f"""
import os
from pathlib import Path
import sys
import time

sys.stdin.buffer.readline()
Path({str(runner_pid)!r}).write_text(str(os.getpid()), encoding="utf-8")
child = os.fork()
if child == 0:
    Path({str(ready)!r}).touch()
    time.sleep(0.35)
    Path({str(survived)!r}).touch()
    time.sleep(10)
    os._exit(0)
while not Path({str(ready)!r}).exists():
    time.sleep(0.01)
sys.stderr.write("drain-marker\\n")
sys.stderr.flush()
Path({str(drained_marker)!r}).touch()
time.sleep(10)
""",
        timeout_seconds=5.0,
    )

    task = asyncio.create_task(provider.fetch(_request()))
    for _ in range(100):
        if ready.exists() and drained_marker.exists():
            break
        await asyncio.sleep(0.01)
    assert ready.exists()
    assert drained_marker.exists()

    task.cancel()
    await asyncio.wait_for(cleanup_started.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.sleep(0.45)
    assert cleanup_finished.is_set()
    assert not survived.exists()
    assert not _process_is_alive(int(runner_pid.read_text(encoding="utf-8")))


def test_akshare_runner_command_shape_rejects_extra_flags_and_relative_paths(tmp_path: Path) -> None:
    """No shell, module mode, relative script, or extra flag can cross the boundary."""
    script = _runner_script(tmp_path, "")
    python = str(Path(sys.executable).resolve())

    with pytest.raises(ValueError):
        AkShareMarketDataProvider(command=(python, "-I", "-S", "relative-runner.py"))
    with pytest.raises(ValueError):
        AkShareMarketDataProvider(command=(python, "-I", "-S", str(script), "--extra"))


def test_akshare_runner_protocol_constant_is_versioned() -> None:
    """The parent and child protocol contract remains an explicit versioned value."""
    assert AKSHARE_RUNNER_PROTOCOL_VERSION == "akshare-market-data-v1"
