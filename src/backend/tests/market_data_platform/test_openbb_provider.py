"""Protocol tests for the isolated OpenBB market-data adapter."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    name for name in ("DATABASE_URL", "JWT_SECRET_KEY", "HTTP_PROXY", "PYTHONPATH", "HOME")
    if os.getenv(name)
]
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


@pytest.mark.parametrize(
    ("frequency", "expected_interval"),
    [
        ("1d", "1d"),
        ("1w", "1W"),
        ("1mo", "1M"),
    ],
)
def test_openbb_yfinance_translates_platform_frequency_to_openbb_interval(
    frequency: str,
    expected_interval: str,
) -> None:
    """The platform's lowercase frequency stays separate from OpenBB's provider enum."""
    request = replace(_request(), frequency=frequency)

    assert _yfinance_historical_arguments(request.dto_payload)["interval"] == expected_interval


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


def test_openbb_runner_blocks_yfinance_before_import_when_outbound_end_is_unattested(
    tmp_path: Path,
) -> None:
    """A valid-looking exact candidate cannot reach OpenBB until the actual call is bounded."""
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
        "OPENBB_YFINANCE_OUTBOUND_END_BOUND_UNATTESTED"
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
