"""Protocol tests for the isolated OpenBB market-data adapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.market_data import openbb_runtime
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    OpenBBProviderError,
    OpenBBSubprocessProvider,
    ProviderMarketObservation,
    _openbb_runner_environment,
    _openbb_runner_workdir,
)
from scripts import openbb_market_data_runner
from scripts.openbb_market_data_runner import (
    _has_active_runtime_route_permit,
    _normalize_records,
    _provider_error_code,
    _records,
    _route,
    _RunnerRuntimeRoutePermit,
    _yfinance_historical_arguments,
    _yfinance_historical_window,
)

UTC = timezone.utc


def _request() -> MarketDataProviderRequest:
    return MarketDataProviderRequest(
        query_fingerprint="a" * 64,
        canonical_id="instrument:stock:NASDAQ:AAPL",
        asset_type="stock",
        provider_symbol="AAPL",
        market="NASDAQ",
        data_kind="bars",
        frequency="1d",
        start_at=datetime(2026, 1, 2, tzinfo=UTC),
        end_at=datetime(2026, 1, 4, tzinfo=UTC),
        required_fields=frozenset({"open", "close"}),
        provider="yfinance",
    )


def _runner_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_openbb_runner.py"
    script.write_text(body, encoding="utf-8")
    return script


@pytest.fixture(autouse=True)
def _controlled_openbb_runner_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every subprocess test names dedicated HOME and working directories.

    The production adapter must never quietly reuse the web process home,
    checkout, or system temporary root.  A test-only fixture keeps fake runner
    protocols focused on their own behavior while exercising that requirement.
    """
    runner_home = tmp_path / "controlled-runner-home"
    runner_workdir = tmp_path / "controlled-runner-workdir"
    runner_home.mkdir()
    runner_workdir.mkdir()
    monkeypatch.setenv("OPENBB_RUNNER_HOME", str(runner_home))
    monkeypatch.setenv("OPENBB_RUNNER_WORKDIR", str(runner_workdir))


def test_provider_observation_rejects_duplicate_normalized_field_names() -> None:
    """A direct adapter cannot overwrite a field by adding surrounding whitespace."""
    with pytest.raises(ValueError, match="duplicate normalized field"):
        ProviderMarketObservation(
            event_at=datetime(2026, 1, 2, tzinfo=UTC),
            available_at=datetime(2026, 1, 2, tzinfo=UTC),
            fields={"close": 101.5, " close ": 99.0},
        )


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_uses_a_json_dto_and_normalizes_rows(
    tmp_path: Path,
) -> None:
    """The API process talks only JSON to an isolated runner process."""
    script = _runner_script(
        tmp_path,
        """
import json
import hashlib
import sys

request = json.load(sys.stdin)
raw_payload = {
    "format": "openbb-records-pre-normalization-v1",
    "records": [
        {"date": "2026-01-02", "open": 100.0, "close": 101.5},
        {"date": "2026-01-03", "open": 101.5, "close": 99.0},
    ],
}
raw_payload_sha256 = hashlib.sha256(
    json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
).hexdigest()
json.dump(
    {
        "protocol_version": "openbb-market-data-v1",
        "request_id": request["request_id"],
        "request": request["request"],
        "provider_id": "openbb:yfinance",
        "retrieved_at": "2026-01-04T00:00:00+00:00",
        "source_revision": "yfinance-response-v1",
        "raw_payload": raw_payload,
        "raw_payload_sha256": raw_payload_sha256,
        "records": [
            {"event_at": "2026-01-02T00:00:00+00:00", "fields": {"open": 100.0, "close": 101.5}},
            {"event_at": "2026-01-03T00:00:00+00:00", "fields": {"open": 101.5, "close": 99.0}},
        ],
        "warnings": [],
    },
    sys.stdout,
)
""",
    )
    provider = OpenBBSubprocessProvider(command=(sys.executable, str(script)))

    request = _request()
    result = await provider.fetch(request)

    assert result.provider_id == "openbb:yfinance"
    assert result.request is request
    assert result.source_revision == "yfinance-response-v1"
    assert [item.event_at.day for item in result.observations] == [2, 3]
    assert result.observations[0].fields == {"open": 100.0, "close": 101.5}
    assert result.raw_payload["format"] == "openbb-records-pre-normalization-v1"
    assert result.raw_payload["records"][0]["date"] == "2026-01-02"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_rejects_a_receipt_with_a_changed_outbound_dto(
    tmp_path: Path,
) -> None:
    """Matching a correlation ID alone cannot authenticate a runner receipt."""
    script = _runner_script(
        tmp_path,
        """
import json
import sys

envelope = json.load(sys.stdin)
request = dict(envelope["request"])
request["provider_symbol"] = "SUBSTITUTED"
json.dump(
    {
        "protocol_version": "openbb-market-data-v1",
        "request_id": envelope["request_id"],
        "request": request,
    },
    sys.stdout,
)
""",
    )

    with pytest.raises(OpenBBProviderError) as rejected:
        await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert rejected.value.code == "OPENBB_RUNNER_PROTOCOL_MISMATCH"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_rejects_duplicate_normalized_field_names(
    tmp_path: Path,
) -> None:
    """Runner records cannot exploit a whitespace-normalized field collision."""
    script = _runner_script(
        tmp_path,
        """
import hashlib
import json
import sys

request = json.load(sys.stdin)
raw_payload = {
    "format": "openbb-records-pre-normalization-v1",
    "records": [{"date": "2026-01-02", "close": 101.5, " close ": 99.0}],
}
raw_payload_sha256 = hashlib.sha256(
    json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
).hexdigest()
json.dump(
    {
        "protocol_version": "openbb-market-data-v1",
        "request_id": request["request_id"],
        "request": request["request"],
        "provider_id": "openbb:yfinance",
        "retrieved_at": "2026-01-04T00:00:00+00:00",
        "source_revision": "yfinance-response-v1",
        "raw_payload": raw_payload,
        "raw_payload_sha256": raw_payload_sha256,
        "records": [
            {
                "event_at": "2026-01-02T00:00:00+00:00",
                "fields": {"close": 101.5, " close ": 99.0},
            }
        ],
        "warnings": [],
    },
    sys.stdout,
)
""",
    )

    with pytest.raises(OpenBBProviderError) as rejected:
        await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert rejected.value.code == "OPENBB_RUNNER_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_rejects_records_not_bound_to_raw_receipt(
    tmp_path: Path,
) -> None:
    """A correct raw receipt hash cannot authorize substituted normalized values."""
    script = _runner_script(
        tmp_path,
        """
import hashlib
import json
import sys

request = json.load(sys.stdin)
raw_payload = {
    "format": "openbb-records-pre-normalization-v1",
    "records": [{"date": "2026-01-02", "open": 100.0, "close": 101.5}],
}
raw_payload_sha256 = hashlib.sha256(
    json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
).hexdigest()
json.dump(
    {
        "protocol_version": "openbb-market-data-v1",
        "request_id": request["request_id"],
        "request": request["request"],
        "provider_id": "openbb:yfinance",
        "retrieved_at": "2026-01-04T00:00:00+00:00",
        "source_revision": "yfinance-response-v1",
        "raw_payload": raw_payload,
        "raw_payload_sha256": raw_payload_sha256,
        "records": [
            {
                "event_at": "2026-01-02T00:00:00+00:00",
                "fields": {"open": 100.0, "close": 999.0},
            }
        ],
        "warnings": [],
    },
    sys.stdout,
)
""",
    )

    with pytest.raises(OpenBBProviderError) as rejected:
        await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert rejected.value.code == "OPENBB_RUNNER_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_rejects_process_wide_overload_before_launching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full gate rejects the second instance without starting another child process."""
    import app.services.market_data.providers as providers

    monkeypatch.setattr(providers, "_PROCESS_OPENBB_RUNNER_GATE", providers._OpenBBRunnerGate())
    launches = tmp_path / "runner-launches"
    script = _runner_script(
        tmp_path,
        f"""
import hashlib
import json
from pathlib import Path
import sys
import time

request = json.load(sys.stdin)
with Path({str(launches)!r}).open("a", encoding="utf-8") as output:
    output.write("1")
time.sleep(0.3)
raw_payload = {{"format": "openbb-records-pre-normalization-v1", "records": []}}
raw_payload_sha256 = hashlib.sha256(
    json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
).hexdigest()
json.dump(
    {{
        "protocol_version": "openbb-market-data-v1",
        "request_id": request["request_id"],
        "request": request["request"],
        "provider_id": "openbb:yfinance",
        "retrieved_at": "2026-01-04T00:00:00+00:00",
        "source_revision": "yfinance-response-v1",
        "raw_payload": raw_payload,
        "raw_payload_sha256": raw_payload_sha256,
        "records": [],
        "warnings": [],
    }},
    sys.stdout,
)
""",
    )
    first_provider = OpenBBSubprocessProvider(
        command=(sys.executable, str(script)),
        max_concurrent_runs=1,
    )
    second_provider = OpenBBSubprocessProvider(
        command=(sys.executable, str(script)),
        max_concurrent_runs=1,
    )
    first = asyncio.create_task(first_provider.fetch(_request()))
    for _ in range(100):
        if launches.exists():
            break
        await asyncio.sleep(0.01)
    assert launches.exists()

    with pytest.raises(OpenBBProviderError) as overloaded:
        await second_provider.fetch(_request())

    assert overloaded.value.code == "OPENBB_RUNNER_OVERLOADED"
    assert launches.read_text(encoding="utf-8") == "1"
    assert (await first).source_revision == "yfinance-response-v1"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_rejects_a_cross_instance_cap_change_before_launching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first admitted cap stays process-wide instead of being raised later."""
    import app.services.market_data.providers as providers

    monkeypatch.setattr(providers, "_PROCESS_OPENBB_RUNNER_GATE", providers._OpenBBRunnerGate())
    launches = tmp_path / "runner-launches"
    script = _runner_script(
        tmp_path,
        f"""
import hashlib
import json
from pathlib import Path
import sys

request = json.load(sys.stdin)
with Path({str(launches)!r}).open("a", encoding="utf-8") as output:
    output.write("1")
raw_payload = {{"format": "openbb-records-pre-normalization-v1", "records": []}}
raw_payload_sha256 = hashlib.sha256(
    json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
).hexdigest()
json.dump(
    {{
        "protocol_version": "openbb-market-data-v1",
        "request_id": request["request_id"],
        "request": request["request"],
        "provider_id": "openbb:yfinance",
        "retrieved_at": "2026-01-04T00:00:00+00:00",
        "source_revision": "yfinance-response-v1",
        "raw_payload": raw_payload,
        "raw_payload_sha256": raw_payload_sha256,
        "records": [],
        "warnings": [],
    }},
    sys.stdout,
)
""",
    )
    first_provider = OpenBBSubprocessProvider(
        command=(sys.executable, str(script)),
        max_concurrent_runs=1,
    )
    changed_cap_provider = OpenBBSubprocessProvider(
        command=(sys.executable, str(script)),
        max_concurrent_runs=2,
    )

    assert (await first_provider.fetch(_request())).source_revision == "yfinance-response-v1"
    with pytest.raises(OpenBBProviderError) as rejected:
        await changed_cap_provider.fetch(_request())

    assert rejected.value.code == "OPENBB_RUNNER_CONCURRENCY_CONFIG_MISMATCH"
    assert launches.read_text(encoding="utf-8") == "1"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_rejects_a_mismatched_runner_response(
    tmp_path: Path,
) -> None:
    """A stale or swapped process response can never be persisted for this request."""
    script = _runner_script(
        tmp_path,
        """
import json
import sys

json.load(sys.stdin)
json.dump(
    {
        "protocol_version": "openbb-market-data-v1",
        "request_id": "wrong-request-id",
        "provider_id": "openbb:yfinance",
        "retrieved_at": "2026-01-04T00:00:00+00:00",
        "source_revision": "yfinance-response-v1",
        "records": [],
        "warnings": [],
    },
    sys.stdout,
)
""",
    )

    with pytest.raises(OpenBBProviderError) as mismatch:
        await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert mismatch.value.code == "OPENBB_RUNNER_PROTOCOL_MISMATCH"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_fails_closed_when_no_runner_is_configured() -> None:
    """The FastAPI process does not import or dynamically load a local OpenBB checkout."""
    with pytest.raises(OpenBBProviderError) as unavailable:
        await OpenBBSubprocessProvider(command=None).fetch(_request())

    assert unavailable.value.code == "OPENBB_RUNNER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_normalizes_an_invalid_runner_command_to_a_stable_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed operator command cannot break route dependency construction."""
    monkeypatch.setenv("OPENBB_MARKET_DATA_RUNNER", '"unterminated')

    with pytest.raises(OpenBBProviderError) as invalid:
        await OpenBBSubprocessProvider.from_environment().fetch(_request())

    assert invalid.value.code == "OPENBB_RUNNER_COMMAND_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_command",
    (
        "relative-openbb-runner",
        "python relative-openbb-runner.py",
        f"{sys.executable} -c 'print(1)'",
    ),
)
async def test_openbb_subprocess_provider_requires_a_small_absolute_runner_command(
    monkeypatch: pytest.MonkeyPatch,
    raw_command: str,
) -> None:
    """Environment configuration cannot select a relative or arbitrary program."""
    monkeypatch.setenv("OPENBB_MARKET_DATA_RUNNER", raw_command)

    with pytest.raises(OpenBBProviderError) as invalid:
        await OpenBBSubprocessProvider.from_environment().fetch(_request())

    assert invalid.value.code == "OPENBB_RUNNER_COMMAND_INVALID"


def test_openbb_subprocess_provider_rejects_an_unsafe_direct_runner_command() -> None:
    """Internal construction keeps the same absolute command boundary as settings."""
    with pytest.raises(ValueError, match="explicit absolute executable"):
        OpenBBSubprocessProvider(command=("relative-openbb-runner",))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment_key", "expected_code"),
    (
        ("OPENBB_RUNNER_HOME", "OPENBB_RUNNER_HOME_INVALID"),
        ("OPENBB_RUNNER_WORKDIR", "OPENBB_RUNNER_WORKDIR_INVALID"),
    ),
)
async def test_openbb_subprocess_provider_requires_explicit_runner_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment_key: str,
    expected_code: str,
) -> None:
    """Missing isolated HOME/workdir cannot fall back to app or temporary paths."""
    monkeypatch.delenv(environment_key)
    script = _runner_script(tmp_path, "import sys\nsys.stdin.read()\n")

    with pytest.raises(OpenBBProviderError) as invalid:
        await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert invalid.value.code == expected_code


def test_openbb_runner_workdir_rejects_the_web_process_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit setting cannot disguise the web working tree as runner isolation."""
    monkeypatch.setenv("OPENBB_RUNNER_WORKDIR", os.getcwd())

    with pytest.raises(OpenBBProviderError) as rejected:
        _openbb_runner_workdir()

    assert rejected.value.code == "OPENBB_RUNNER_WORKDIR_INVALID"


@pytest.mark.parametrize("environment_key", ("OPENBB_RUNNER_HOME", "OPENBB_RUNNER_WORKDIR"))
def test_openbb_runner_directories_reject_checkout_ancestors_and_descendants(
    monkeypatch: pytest.MonkeyPatch,
    environment_key: str,
) -> None:
    """A nested application directory cannot masquerade as a dedicated runner root."""
    checkout_root = next(
        parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()
    )
    nested_checkout_directory = checkout_root / "src" / "backend" / "app"
    expected_code = (
        "OPENBB_RUNNER_HOME_INVALID"
        if environment_key == "OPENBB_RUNNER_HOME"
        else "OPENBB_RUNNER_WORKDIR_INVALID"
    )
    resolver = (
        _openbb_runner_environment
        if environment_key == "OPENBB_RUNNER_HOME"
        else _openbb_runner_workdir
    )

    for unsafe_directory in (checkout_root.parent, nested_checkout_directory):
        monkeypatch.setenv(environment_key, str(unsafe_directory))
        with pytest.raises(OpenBBProviderError) as rejected:
            resolver()
        assert rejected.value.code == expected_code


def test_openbb_subprocess_provider_rejects_a_runner_script_inside_the_checkout() -> None:
    """A command cannot execute a script selected from the web application checkout."""
    checkout_root = next(
        parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()
    )
    runner_script = checkout_root / "src" / "backend" / "scripts" / "openbb_market_data_runner.py"

    with pytest.raises(ValueError, match="explicit absolute executable"):
        OpenBBSubprocessProvider(command=(sys.executable, str(runner_script)))


def test_openbb_runner_directory_rejects_a_no_git_parent_of_the_application_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A packaged deployment cannot use a parent directory that contains its app cwd."""
    import app.services.market_data.providers as providers

    synthetic_module = tmp_path / "wheel" / "app" / "services" / "market_data" / "providers.py"
    synthetic_module.parent.mkdir(parents=True)
    synthetic_module.write_text("# package fixture\n", encoding="utf-8")
    monkeypatch.setattr(providers, "__file__", str(synthetic_module))
    for unsafe_directory in (
        synthetic_module.parents[2],
        Path.cwd().resolve().parent,
    ):
        monkeypatch.setenv("OPENBB_RUNNER_WORKDIR", str(unsafe_directory))

        with pytest.raises(OpenBBProviderError) as rejected:
            _openbb_runner_workdir()

        assert rejected.value.code == "OPENBB_RUNNER_WORKDIR_INVALID"


def test_openbb_runner_home_rejects_the_inherited_web_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A runner must not reuse the parent application's HOME as its own state."""
    inherited_home = tmp_path / "inherited-web-home"
    inherited_home.mkdir()
    monkeypatch.setenv("HOME", str(inherited_home))
    monkeypatch.setenv("OPENBB_RUNNER_HOME", str(inherited_home))

    with pytest.raises(OpenBBProviderError) as rejected:
        _openbb_runner_environment()

    assert rejected.value.code == "OPENBB_RUNNER_HOME_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_name", ("stdout", "stderr"))
async def test_openbb_subprocess_provider_bounds_every_runner_output_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stream_name: str,
) -> None:
    """A noisy isolated runner cannot force unbounded web-process buffering."""
    import app.services.market_data.providers as providers

    monkeypatch.setattr(providers, "_MAX_RUNNER_OUTPUT_BYTES", 1024)
    script = _runner_script(
        tmp_path,
        f"""
import sys

sys.stdin.read()
sys.{stream_name}.write("x" * 2048)
""",
    )

    with pytest.raises(OpenBBProviderError) as rejected:
        await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert rejected.value.code == "OPENBB_RUNNER_OUTPUT_TOO_LARGE"


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX runner process group")
async def test_openbb_subprocess_provider_timeout_terminates_runner_descendants(
    tmp_path: Path,
) -> None:
    """A timed-out runner cannot leave an inherited-pipe grandchild running."""
    ready = tmp_path / "grandchild-ready"
    survived = tmp_path / "grandchild-survived"
    script = _runner_script(
        tmp_path,
        f"""
import os
from pathlib import Path
import sys
import time

sys.stdin.read()
child = os.fork()
if child == 0:
    Path({str(ready)!r}).touch()
    time.sleep(0.5)
    Path({str(survived)!r}).touch()
    time.sleep(10)
    os._exit(0)
while not Path({str(ready)!r}).exists():
    time.sleep(0.01)
time.sleep(10)
""",
    )

    with pytest.raises(OpenBBProviderError) as timed_out:
        await OpenBBSubprocessProvider(
            command=(sys.executable, str(script)),
            timeout_seconds=0.2,
        ).fetch(_request())

    await asyncio.sleep(0.6)
    assert timed_out.value.code == "OPENBB_RUNNER_TIMEOUT"
    assert ready.exists()
    assert not survived.exists()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX runner process group")
async def test_openbb_timeout_terminates_descendant_after_runner_leader_exits(
    tmp_path: Path,
) -> None:
    """Leader exit cannot prevent cleanup of a descendant holding response pipes."""
    ready = tmp_path / "orphan-ready"
    survived = tmp_path / "orphan-survived"
    script = _runner_script(
        tmp_path,
        f"""
import os
from pathlib import Path
import sys
import time

sys.stdin.read()
child = os.fork()
if child == 0:
    Path({str(ready)!r}).touch()
    time.sleep(0.5)
    Path({str(survived)!r}).touch()
    time.sleep(10)
    os._exit(0)
os._exit(0)
""",
    )

    with pytest.raises(OpenBBProviderError) as timed_out:
        await OpenBBSubprocessProvider(
            command=(sys.executable, str(script)),
            timeout_seconds=0.2,
        ).fetch(_request())

    await asyncio.sleep(0.6)
    assert timed_out.value.code == "OPENBB_RUNNER_TIMEOUT"
    assert ready.exists()
    assert not survived.exists()


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_does_not_forward_application_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The isolated runner receives no parent database, JWT, proxy, or import configuration."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:secret@example.test/market")
    monkeypatch.setenv("JWT_SECRET_KEY", "web-session-secret")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy-user:proxy-secret@example.test")
    monkeypatch.setenv("PYTHONPATH", "/private/application/imports")
    monkeypatch.setenv("HOME", "/private/application/home")
    monkeypatch.setenv("OPENBB_ALLOWED_PROVIDERS", "yfinance")
    script = _runner_script(
        tmp_path,
        """
import json
import hashlib
import os
import sys

request = json.load(sys.stdin)
blocked = [
    name for name in ("DATABASE_URL", "JWT_SECRET_KEY", "HTTP_PROXY", "PYTHONPATH")
    if os.getenv(name)
]
if os.getenv("HOME") == "/private/application/home":
    blocked.append("HOME")
if blocked:
    json.dump(
        {
            "protocol_version": "openbb-market-data-v1",
            "request_id": request["request_id"],
        "request": request["request"],
            "error": {"code": "OPENBB_ENV_LEAK", "detail": ",".join(blocked)},
        },
        sys.stdout,
    )
else:
    raw_payload = {"format": "openbb-records-pre-normalization-v1", "records": []}
    raw_payload_sha256 = hashlib.sha256(
        json.dumps(raw_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    json.dump(
        {
            "protocol_version": "openbb-market-data-v1",
            "request_id": request["request_id"],
        "request": request["request"],
            "provider_id": "openbb:yfinance",
            "retrieved_at": "2026-01-04T00:00:00+00:00",
            "source_revision": "isolated-env-v1",
            "raw_payload": raw_payload,
            "raw_payload_sha256": raw_payload_sha256,
            "records": [],
            "warnings": [],
        },
        sys.stdout,
    )
""",
    )

    result = await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert result.source_revision == "isolated-env-v1"
    assert _openbb_runner_environment()["OPENBB_ALLOWED_PROVIDERS"] == "yfinance"
    assert "DATABASE_URL" not in _openbb_runner_environment()
    assert "JWT_SECRET_KEY" not in _openbb_runner_environment()
    assert _openbb_runner_environment()["HOME"] != "/private/application/home"


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_uses_a_controlled_runner_workdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner starts outside the web checkout even when it shares a host."""
    runner_workdir = tmp_path / "runner-workdir"
    runner_workdir.mkdir()
    monkeypatch.setenv("OPENBB_RUNNER_WORKDIR", str(runner_workdir))
    script = _runner_script(
        tmp_path,
        f"""
import hashlib
import json
import os
import sys

request = json.load(sys.stdin)
if os.getcwd() != {str(runner_workdir)!r}:
    json.dump(
        {{
            "protocol_version": "openbb-market-data-v1",
            "request_id": request["request_id"],
        "request": request["request"],
            "error": {{"code": "OPENBB_WORKDIR_LEAK", "detail": os.getcwd()}},
        }},
        sys.stdout,
    )
else:
    raw_payload = {{"format": "openbb-records-pre-normalization-v1", "records": []}}
    raw_payload_sha256 = hashlib.sha256(
        json.dumps(raw_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    json.dump(
        {{
            "protocol_version": "openbb-market-data-v1",
            "request_id": request["request_id"],
        "request": request["request"],
            "provider_id": "openbb:yfinance",
            "retrieved_at": "2026-01-04T00:00:00+00:00",
            "source_revision": "isolated-workdir-v1",
            "raw_payload": raw_payload,
            "raw_payload_sha256": raw_payload_sha256,
            "records": [],
            "warnings": [],
        }},
        sys.stdout,
    )
""",
    )

    result = await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert result.source_revision == "isolated-workdir-v1"
    assert _openbb_runner_workdir() == str(runner_workdir)


@pytest.mark.asyncio
async def test_openbb_subprocess_provider_rejects_an_unverifiable_raw_payload(
    tmp_path: Path,
) -> None:
    """A runner cannot substitute a source summary for raw receipt evidence."""
    script = _runner_script(
        tmp_path,
        """
import hashlib
import json
import sys

request = json.load(sys.stdin)
raw_payload = {"record_count": 1}
raw_payload_sha256 = hashlib.sha256(
    json.dumps(raw_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
).hexdigest()
json.dump(
    {
        "protocol_version": "openbb-market-data-v1",
        "request_id": request["request_id"],
        "request": request["request"],
        "provider_id": "openbb:yfinance",
        "retrieved_at": "2026-01-04T00:00:00+00:00",
        "source_revision": "unverifiable-v1",
        "raw_payload": raw_payload,
        "raw_payload_sha256": raw_payload_sha256,
        "records": [
            {
                "event_at": "2026-01-02T00:00:00+00:00",
                "fields": {"open": 100.0, "close": 101.5},
            }
        ],
        "warnings": [],
    },
    sys.stdout,
)
""",
    )

    with pytest.raises(OpenBBProviderError) as rejected:
        await OpenBBSubprocessProvider(command=(sys.executable, str(script))).fetch(_request())

    assert rejected.value.code == "OPENBB_RUNNER_INVALID_RESPONSE"


def test_openbb_yfinance_translates_half_open_date_windows_and_discards_end_records() -> None:
    """The runner must not return a provider row at the exclusive parent end instant."""
    request = _request()
    arguments = _yfinance_historical_arguments(request.dto_payload)
    records = _normalize_records(
        [
            {"date": "2026-01-02", "close": 100.0},
            {"date": "2026-01-03", "close": 101.0},
            {"date": "2026-01-04", "close": 102.0},
        ],
        start_at=request.start_at,
        end_at=request.end_at,
    )

    assert arguments["start_date"] == "2026-01-02"
    assert arguments["end_date"] == "2026-01-03"
    assert arguments["interval"] == "1d"
    assert [item["event_at"][:10] for item in records] == ["2026-01-02", "2026-01-03"]


def test_openbb_yfinance_accepts_only_the_reviewed_daily_frequency() -> None:
    """The runner's future fallback scope remains one day-aligned daily route."""
    assert _yfinance_historical_arguments(_request().dto_payload)["interval"] == "1d"

    for unsupported_frequency in ("1w", "1mo", "5min"):
        with pytest.raises(ValueError, match="OPENBB_FREQUENCY_UNSUPPORTED"):
            _yfinance_historical_arguments(
                replace(_request(), frequency=unsupported_frequency).dto_payload
            )


def test_openbb_yfinance_rejects_daily_windows_larger_than_3650_days() -> None:
    """An exact 3650-day half-open interval is allowed; any larger one is not."""
    request = _request()
    largest_supported = replace(
        request,
        end_at=request.start_at + timedelta(days=3650),
    )
    too_large = replace(
        request,
        end_at=request.start_at + timedelta(days=3651),
    )

    assert _yfinance_historical_window(largest_supported.dto_payload) == (
        largest_supported.start_at,
        largest_supported.end_at,
    )
    with pytest.raises(ValueError, match="OPENBB_WINDOW_TOO_LARGE"):
        _yfinance_historical_window(too_large.dto_payload)


def test_openbb_runner_preserves_date_from_a_default_date_indexed_obbject() -> None:
    """OpenBB's default ``to_df`` index must remain an event field in child output."""

    class RecordsFrame:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self._rows = rows

        def to_dict(self, *, orient: str) -> list[dict[str, object]]:
            assert orient == "records"
            return self._rows

    class DateIndexedOBBject:
        def __init__(self) -> None:
            self.requested_indexes: list[str | None] = []

        def to_df(self, *, index: str | None = "date") -> RecordsFrame:
            self.requested_indexes.append(index)
            if index == "date":
                # This is what pandas orient="records" produces after OpenBB's
                # default date index has been applied.
                return RecordsFrame([{"open": 100.0, "close": 101.5}])
            assert index is None
            return RecordsFrame(
                [
                    {
                        "date": "2026-01-02",
                        "open": 100.0,
                        "close": 101.5,
                    }
                ]
            )

    result = DateIndexedOBBject()
    rows = _records(result)
    normalized = _normalize_records(
        rows,
        start_at=datetime(2026, 1, 2, tzinfo=UTC),
        end_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert result.requested_indexes == [None]
    assert normalized == [
        {
            "event_at": "2026-01-02T00:00:00+00:00",
            "fields": {"open": 100.0, "close": 101.5},
        }
    ]


def test_openbb_yfinance_rejects_unreviewed_intraday_window_semantics() -> None:
    """Until a provider-specific contract exists, an intraday OpenBB fallback stays disabled."""
    request = replace(_request(), frequency="5min")

    with pytest.raises(ValueError, match="OPENBB_FREQUENCY_UNSUPPORTED"):
        _yfinance_historical_arguments(request.dto_payload)


def test_openbb_provider_request_rejects_naive_or_unbounded_inputs() -> None:
    """The runner cannot be invoked with ambiguous time or identity semantics."""
    with pytest.raises(ValueError):
        replace(_request(), start_at=datetime(2026, 1, 2))


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Too Many Requests. Rate limited.", "OPENBB_RATE_LIMITED"),
        ("HTTP 429 from provider", "OPENBB_RATE_LIMITED"),
        ("unauthorized API key", "OPENBB_AUTH_REQUIRED"),
        ("[Empty] -> No results found.", "OPENBB_EMPTY_RESPONSE"),
        ("unexpected transport error", "OPENBB_ROUTE_FAILED"),
    ],
)
def test_openbb_runner_classifies_provider_failures_without_exposing_them(
    message: str,
    expected: str,
) -> None:
    """Operational failures become stable protocol codes, not web-process traces."""
    assert _provider_error_code(RuntimeError(message)) == expected


def test_openbb_runner_rejects_declared_semantics_before_importing_openbb() -> None:
    """The isolated runner cannot relabel provider-native prices as adjusted data."""
    request = replace(_request(), adjustment="qfq")
    runner = Path(__file__).parents[2] / "scripts" / "openbb_market_data_runner.py"
    completed = subprocess.run(
        [sys.executable, str(runner)],
        input=json.dumps(
            {
                "protocol_version": "openbb-market-data-v1",
                "request_id": request.request_id,
                "request": request.dto_payload,
            }
        ),
        capture_output=True,
        check=False,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["error"]["code"] == "OPENBB_SEMANTICS_UNSUPPORTED"


def _actual_openbb_runner() -> Path:
    """Return the checked-in runner, rather than a permissive fake protocol peer."""
    return Path(__file__).parents[2] / "scripts" / "openbb_market_data_runner.py"


def _run_actual_openbb_runner(
    *,
    arguments: list[str] | None = None,
    payload: dict[str, object] | None = None,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute the real runner in a controlled process without network access."""
    return subprocess.run(
        [sys.executable, str(_actual_openbb_runner()), *(arguments or [])],
        input=None if payload is None else json.dumps(payload),
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )


class _FakeRuntimeDistribution:
    """Minimal metadata distribution fake for offline artifact attestation tests."""

    def __init__(self, *, version: str, root: Path, relative_paths: tuple[str, ...]) -> None:
        self.version = version
        self._root = root
        self.files = relative_paths

    def locate_file(self, relative_path: object) -> Path:
        return self._root / str(relative_path)


def _candidate_runtime_artifact_fixture(
    tmp_path: Path,
) -> tuple[Path, dict[str, _FakeRuntimeDistribution]]:
    """Create a complete exact fork candidate without importing OpenBB."""
    site_packages = tmp_path / "fake-site-packages"
    package_files = {
        "openbb": ("4.7.3-test", "openbb/__init__.py", b"fake-openbb"),
        "openbb-core": ("1.6.13-test", "openbb_core/__init__.py", b"fake-openbb-core"),
        "openbb-yfinance": (
            "1.6.3-test",
            "openbb_yfinance/utils/helpers.py",
            b"fake-openbb-yfinance-helper",
        ),
        "yfinance": ("1.7.0-test", "yfinance/__init__.py", b"fake-yfinance"),
    }
    artifacts: list[dict[str, object]] = []
    distributions: dict[str, _FakeRuntimeDistribution] = {}
    for distribution_name, (version, relative_path, content) in package_files.items():
        target = site_packages / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        artifacts.append(
            {
                "distribution": distribution_name,
                "version": version,
                "files": [
                    {
                        "relative_path": relative_path,
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
            }
        )
        distributions[distribution_name] = _FakeRuntimeDistribution(
            version=version,
            root=site_packages,
            relative_paths=(relative_path,),
        )
    manifest_path = tmp_path / "candidate-runtime-artifacts.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "openbb-yfinance-runtime-artifact-manifest-v1",
                "artifact_set_version": "openbb-yfinance-runtime-test-v1",
                "attestation_state": "candidate",
                "outbound_end_bound_contract": (
                    "openbb-yfinance-daily-inclusive-to-yfinance-exclusive-v1"
                ),
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path, distributions


def _load_fake_runtime_artifact_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, dict[str, _FakeRuntimeDistribution]]:
    """Install a test-only static manifest in the runner module boundary."""
    manifest_path, distributions = _candidate_runtime_artifact_fixture(tmp_path)
    monkeypatch.setattr(openbb_market_data_runner, "_RUNTIME_ARTIFACT_MANIFEST_PATH", manifest_path)
    manifest, error = openbb_market_data_runner._load_static_runtime_artifact_manifest()
    assert error is None
    assert manifest is not None
    monkeypatch.setattr(openbb_market_data_runner, "_RUNTIME_ARTIFACT_MANIFEST", manifest)
    return manifest, distributions


def test_openbb_runner_verifies_exact_candidate_distribution_versions_and_owned_file_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A static fork candidate verifies exact package-owned source files pre-import."""
    _manifest, distributions = _load_fake_runtime_artifact_manifest(tmp_path, monkeypatch)
    monkeypatch.setattr(
        openbb_market_data_runner.metadata,
        "distribution",
        lambda distribution_name: distributions[distribution_name],
    )

    attestation = openbb_market_data_runner._runtime_artifact_attestation()

    assert attestation.status == "candidate"
    assert attestation.code == "OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED"
    assert attestation.distribution_names == (
        "openbb",
        "openbb-core",
        "openbb-yfinance",
        "yfinance",
    )
    assert attestation.verified_file_count == 4


@pytest.mark.parametrize("mismatch", ("version", "file_hash", "missing"))
def test_openbb_runner_rejects_unattested_or_missing_runtime_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    """Any exact-package mismatch fails closed through one non-path-bearing code."""
    _manifest, distributions = _load_fake_runtime_artifact_manifest(tmp_path, monkeypatch)

    def fake_distribution(distribution_name: str) -> _FakeRuntimeDistribution:
        if mismatch == "missing" and distribution_name == "yfinance":
            raise openbb_market_data_runner.metadata.PackageNotFoundError(distribution_name)
        return distributions[distribution_name]

    if mismatch == "version":
        distributions["openbb"].version = "4.7.4-test"
    elif mismatch == "file_hash":
        (tmp_path / "fake-site-packages" / "openbb_yfinance/utils/helpers.py").write_bytes(
            b"substituted-helper"
        )
    monkeypatch.setattr(openbb_market_data_runner.metadata, "distribution", fake_distribution)

    attestation = openbb_market_data_runner._runtime_artifact_attestation()

    assert attestation.status == "unattested"
    assert attestation.code == "OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED"
    assert attestation.verified_file_count == 0


@pytest.mark.parametrize("manifest_body", ("{", "{}"))
def test_openbb_runner_treats_missing_or_malformed_runtime_artifact_manifest_as_unattested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_body: str,
) -> None:
    """A bad static manifest cannot turn into a metadata or package fallback."""
    manifest_path = tmp_path / "runtime-artifacts.json"
    manifest_path.write_text(manifest_body, encoding="utf-8")
    monkeypatch.setattr(openbb_market_data_runner, "_RUNTIME_ARTIFACT_MANIFEST_PATH", manifest_path)
    manifest, error = openbb_market_data_runner._load_static_runtime_artifact_manifest()

    assert manifest is None
    assert error == "invalid"
    monkeypatch.setattr(openbb_market_data_runner, "_RUNTIME_ARTIFACT_MANIFEST", manifest)
    attestation = openbb_market_data_runner._runtime_artifact_attestation()
    assert attestation.status == "unattested"
    assert attestation.code == "OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED"


def test_openbb_runner_treats_a_missing_runtime_artifact_manifest_as_unattested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The static artifact verifier has no implicit source-checkout fallback."""
    monkeypatch.setattr(
        openbb_market_data_runner,
        "_RUNTIME_ARTIFACT_MANIFEST_PATH",
        tmp_path / "missing-runtime-artifacts.json",
    )
    manifest, error = openbb_market_data_runner._load_static_runtime_artifact_manifest()

    assert manifest is None
    assert error == "invalid"


@pytest.mark.parametrize(
    "relative_path",
    ("C:/outside.py", "C:outside.py", "//server/share.py", "../outside.py", "openbb\\file.py"),
)
def test_openbb_runner_rejects_cross_platform_or_escaping_artifact_paths(
    relative_path: str,
) -> None:
    """A manifest cannot use a native or foreign absolute path as a package file."""
    with pytest.raises(ValueError, match="invalid static runtime artifact manifest"):
        openbb_market_data_runner._artifact_manifest_relative_path(relative_path)


def test_openbb_runner_rejects_data_only_execution_attestation_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing JSON alone cannot promote a reviewed fork candidate to executable."""
    manifest_path, _distributions = _candidate_runtime_artifact_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["attestation_state"] = "attested"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(openbb_market_data_runner, "_RUNTIME_ARTIFACT_MANIFEST_PATH", manifest_path)

    loaded, error = openbb_market_data_runner._load_static_runtime_artifact_manifest()

    assert loaded is None
    assert error == "invalid"


def test_openbb_runner_treats_corrupt_distribution_metadata_as_unattested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected metadata objects cannot raise a traceback through the runner boundary."""
    _manifest, _distributions = _load_fake_runtime_artifact_manifest(tmp_path, monkeypatch)
    monkeypatch.setattr(openbb_market_data_runner.metadata, "distribution", lambda _name: object())

    attestation = openbb_market_data_runner._runtime_artifact_attestation()

    assert attestation.status == "unattested"
    assert attestation.code == "OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED"
    assert attestation.verified_file_count == 0


def test_openbb_runner_rejects_a_symlinked_owned_artifact_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forged RECORD entry cannot point a reviewed file outside its package root."""
    _manifest, distributions = _load_fake_runtime_artifact_manifest(tmp_path, monkeypatch)
    target = tmp_path / "fake-site-packages" / "openbb_yfinance/utils/helpers.py"
    replacement = tmp_path / "outside-helper.py"
    replacement.write_bytes(b"fake-openbb-yfinance-helper")
    target.unlink()
    target.symlink_to(replacement)
    monkeypatch.setattr(
        openbb_market_data_runner.metadata,
        "distribution",
        lambda distribution_name: distributions[distribution_name],
    )

    attestation = openbb_market_data_runner._runtime_artifact_attestation()

    assert attestation.status == "unattested"
    assert attestation.code == "OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED"


def test_openbb_runner_self_check_reports_a_safe_blocked_attestation(
    tmp_path: Path,
) -> None:
    """The operator-only attestation stays local and never serializes secret values."""
    environment = os.environ.copy()
    environment.update(
        {
            "OPENBB_ALLOWED_PROVIDERS": "yfinance",
            "OPENBB_ALLOW_MUTABLE_EXTENSIONS": "true",
            "FMP_API_KEY": "must-not-appear-in-runner-attestation",
            "PYTHONPATH": str(tmp_path),
        }
    )
    # If the self-check imports OpenBB, this module makes the subprocess fail.
    (tmp_path / "openbb.py").write_text("raise RuntimeError('OpenBB import attempted')\n")

    completed = _run_actual_openbb_runner(arguments=["--self-check"], environment=environment)

    assert completed.returncode == 0
    attestation = json.loads(completed.stdout)
    assert attestation["protocol_version"] == "openbb-market-data-v1"
    assert attestation["self_check_version"] == "openbb-market-data-self-check-v1"
    assert attestation["status"] == "blocked"
    runtime_attestation = attestation["attestation"]["runtime"]
    assert set(runtime_attestation["distribution_versions"]) == {
        "openbb",
        "openbb-core",
        "openbb-yfinance",
        "yfinance",
    }
    assert runtime_attestation["artifact_attestation"] == {
        "status": "unattested",
        "code": "OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED",
        "manifest_status": "valid",
        "manifest_version": "openbb-yfinance-runtime-artifact-manifest-v1",
        "artifact_set_version": "openbb-yfinance-us-nyse-1d-fork-candidate-v1",
        "attestation_state": "candidate",
        "distribution_names": ["openbb", "openbb-core", "openbb-yfinance", "yfinance"],
        "verified_file_count": 0,
        "paths_included": False,
        "hashes_included": False,
    }
    assert attestation["attestation"]["coverage"]["coverage_source"] == (
        "canonical-static-permit-manifest"
    )
    assert attestation["attestation"]["coverage"]["permit_manifest_status"] == "valid"
    assert attestation["attestation"]["coverage"]["active_route_ids"] == []
    assert attestation["attestation"]["configuration"] == {
        "configured_provider_names": ["yfinance"],
        "provider_allow_list_status": "exact",
        "dangerous_openbb_environment_keys": ["OPENBB_ALLOW_MUTABLE_EXTENSIONS"],
        "secret_values_included": False,
    }
    assert attestation["attestation"]["outbound_end_bound"] == {
        "code": "OPENBB_YFINANCE_OUTBOUND_END_BOUND_UNATTESTED",
        "status": "unattested",
    }
    assert "must-not-appear-in-runner-attestation" not in completed.stdout
    assert str(tmp_path) not in completed.stdout
    assert "relative_path" not in completed.stdout
    assert "sha256" not in completed.stdout


def test_openbb_runtime_and_runner_read_the_same_canonical_zero_permit_manifest() -> None:
    """The runner mirrors reviewed data without importing the web application."""
    manifest_path = Path(openbb_runtime.__file__).with_name("openbb_runtime_permit_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == openbb_runtime.OPENBB_RUNTIME_PERMIT_MANIFEST_VERSION
    assert manifest["permit_matrix_version"] == openbb_runtime.OPENBB_RUNTIME_PERMIT_MATRIX_VERSION
    assert manifest["permit_matrix_version"] == openbb_market_data_runner._PERMIT_MATRIX_VERSION
    assert tuple(manifest["supported_runner_providers"]) == tuple(
        sorted(openbb_runtime.SUPPORTED_OPENBB_RUNNER_PROVIDERS)
    )
    assert tuple(manifest["supported_runner_providers"]) == (
        openbb_market_data_runner._EXACT_ALLOWED_PROVIDER_NAMES
    )
    assert tuple(manifest["dangerous_extension_environment_keys"]) == tuple(
        sorted(openbb_runtime.DANGEROUS_OPENBB_EXTENSION_ENVIRONMENT_KEYS)
    )
    assert tuple(manifest["dangerous_extension_environment_keys"]) == (
        openbb_market_data_runner._DANGEROUS_OPENBB_ENVIRONMENT_KEYS
    )
    assert manifest["runtime_route_permits"] == []
    assert openbb_runtime.OPENBB_RUNTIME_PERMIT_MATRIX == ()
    assert openbb_market_data_runner._ACTIVE_RUNTIME_ROUTE_PERMITS == ()


def test_openbb_runner_blocks_yfinance_before_import_when_runtime_artifact_is_unattested(
    tmp_path: Path,
) -> None:
    """A mismatched fork candidate blocks an otherwise valid request pre-import."""
    request = replace(_request(), market="US-NYSE")
    environment = os.environ.copy()
    environment.update(
        {
            "OPENBB_ALLOWED_PROVIDERS": "yfinance",
            "PYTHONPATH": str(tmp_path),
        }
    )
    (tmp_path / "openbb.py").write_text("raise RuntimeError('OpenBB import attempted')\n")

    completed = _run_actual_openbb_runner(
        payload={
            "protocol_version": "openbb-market-data-v1",
            "request_id": request.request_id,
            "request": request.dto_payload,
        },
        environment=environment,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["error"]["code"] == (
        "OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED"
    )


def test_openbb_runner_keeps_yfinance_outbound_end_bound_fail_closed_for_candidate() -> None:
    """A verified fork candidate cannot become executable through static data alone."""
    candidate = openbb_market_data_runner._RuntimeArtifactAttestation(
        status="candidate",
        code="OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED",
        manifest_status="valid",
        manifest_version="openbb-yfinance-runtime-artifact-manifest-v1",
        artifact_set_version="openbb-yfinance-runtime-test-v1",
        attestation_state="candidate",
        distribution_names=("openbb", "openbb-core", "openbb-yfinance", "yfinance"),
        verified_file_count=4,
    )

    assert not openbb_market_data_runner._yfinance_outbound_end_bound_is_attested(
        artifact_attestation=candidate
    )


def test_openbb_runner_rejects_an_overlarge_daily_window_before_importing_openbb(
    tmp_path: Path,
) -> None:
    """The stable ten-year bound applies even while runtime artifacts remain disabled."""
    request = replace(
        _request(),
        end_at=_request().start_at + timedelta(days=3651),
    )
    environment = os.environ.copy()
    environment.update(
        {
            "OPENBB_ALLOWED_PROVIDERS": "yfinance",
            "PYTHONPATH": str(tmp_path),
        }
    )
    (tmp_path / "openbb.py").write_text("raise RuntimeError('OpenBB import attempted')\n")

    completed = _run_actual_openbb_runner(
        payload={
            "protocol_version": "openbb-market-data-v1",
            "request_id": request.request_id,
            "request": request.dto_payload,
        },
        environment=environment,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["error"]["code"] == "OPENBB_WINDOW_TOO_LARGE"


@pytest.mark.parametrize(
    "dangerous_key",
    ("OPENBB_ALLOW_MUTABLE_EXTENSIONS", "OPENBB_ALLOW_ON_COMMAND_OUTPUT"),
)
def test_openbb_runner_rejects_dangerous_extension_environment_before_import(
    tmp_path: Path,
    dangerous_key: str,
) -> None:
    """An actual request cannot activate a mutable OpenBB extension setting."""
    request = replace(_request(), market="US-NYSE")
    environment = os.environ.copy()
    environment.update(
        {
            "OPENBB_ALLOWED_PROVIDERS": "yfinance",
            dangerous_key: "true",
            "PYTHONPATH": str(tmp_path),
        }
    )
    (tmp_path / "openbb.py").write_text("raise RuntimeError('OpenBB import attempted')\n")

    completed = _run_actual_openbb_runner(
        payload={
            "protocol_version": "openbb-market-data-v1",
            "request_id": request.request_id,
            "request": request.dto_payload,
        },
        environment=environment,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["error"]["code"] == (
        "OPENBB_RUNNER_DANGEROUS_ENVIRONMENT"
    )


def test_openbb_runner_future_permit_requires_family_and_endpoint_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A future enablement cannot select a sibling family or OpenBB endpoint."""
    permit = _RunnerRuntimeRoutePermit(
        route_id="openbb-yfinance-stock-us-nyse-1d-v1",
        family_id="stock.realtime",
        provider="yfinance",
        asset_type="stock",
        market="US-NYSE",
        data_kind="bars",
        frequency="1d",
        adjustment=None,
        price_basis=None,
        currency=None,
        unit=None,
        endpoint="equity.price.historical",
    )
    monkeypatch.setattr(openbb_market_data_runner, "_ACTIVE_RUNTIME_ROUTE_PERMITS", (permit,))
    request = replace(
        _request(),
        market="US-NYSE",
        route_id=permit.route_id,
        family_id=permit.family_id,
        provider_endpoint=permit.endpoint,
    ).dto_payload

    assert _has_active_runtime_route_permit(request)
    assert not _has_active_runtime_route_permit({**request, "family_id": "stock.valuation"})
    assert not _has_active_runtime_route_permit(
        {**request, "provider_endpoint": "etf.historical"}
    )


def test_openbb_runner_dispatches_only_the_endpoint_bound_by_a_permit() -> None:
    """Endpoint selection cannot be widened by an otherwise valid stock asset type."""
    def historical(**_kwargs: object) -> None:
        return None

    obb = SimpleNamespace(equity=SimpleNamespace(price=SimpleNamespace(historical=historical)))

    assert (
        _route(
            obb,
            asset_type="stock",
            endpoint="equity.price.historical",
        )
        is historical
    )
    with pytest.raises(ValueError, match="OPENBB_ENDPOINT_UNSUPPORTED"):
        _route(obb, asset_type="stock", endpoint="etf.historical")


@pytest.mark.parametrize("provider_environment", ("yfinance,unreviewed-provider", "yfinance,"))
def test_openbb_runner_rejects_a_nonexact_provider_environment_before_import(
    tmp_path: Path,
    provider_environment: str,
) -> None:
    """Extra tokens, including an empty trailing token, cannot expand runner authority."""
    request = replace(_request(), market="US-NYSE")
    environment = os.environ.copy()
    environment.update(
        {
            "OPENBB_ALLOWED_PROVIDERS": provider_environment,
            "PYTHONPATH": str(tmp_path),
        }
    )
    (tmp_path / "openbb.py").write_text("raise RuntimeError('OpenBB import attempted')\n")

    completed = _run_actual_openbb_runner(
        payload={
            "protocol_version": "openbb-market-data-v1",
            "request_id": request.request_id,
            "request": request.dto_payload,
        },
        environment=environment,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["error"]["code"] == (
        "OPENBB_RUNNER_PROVIDER_ALLOW_LIST_INVALID"
    )
