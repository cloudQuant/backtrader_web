import os
from types import SimpleNamespace

import pytest


def test_akshare_proxy_detection_skips_dead_env_and_uses_working_candidate(monkeypatch):
    from app.data_fetch.utils import akshare_network_proxy as proxy

    proxy.reset_akshare_proxy_detection_cache()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:15732")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:15732")
    monkeypatch.setenv("AKSHARE_PROXY_CANDIDATE_PORTS", "18888")

    def fake_connect(address, timeout=0):
        host, port = address
        if host == "127.0.0.1" and port == 18888:
            return SimpleNamespace(close=lambda: None)
        raise OSError("closed")

    def fake_get(url, **kwargs):
        proxies = kwargs.get("proxies") or {}
        if proxies.get("https") == "http://127.0.0.1:18888":
            return SimpleNamespace(
                status_code=200,
                text='{"data":{"total":1,"diff":[{"f12":"000001"}]}}',
            )
        raise OSError("remote closed")

    detected = proxy.configure_akshare_network_proxy(
        force_recheck=True,
        request_get=fake_get,
        socket_connect=fake_connect,
        listening_ports=lambda: [],
        system_proxies=lambda: {},
    )

    assert detected == "http://127.0.0.1:18888"
    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:18888"
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:18888"


def test_akshare_proxy_detection_clears_proxy_env_when_direct_eastmoney_works(monkeypatch):
    from app.data_fetch.utils import akshare_network_proxy as proxy

    proxy.reset_akshare_proxy_detection_cache()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:15732")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:15732")

    def fake_get(url, **kwargs):
        assert kwargs.get("proxies") in (None, {})
        return SimpleNamespace(
            status_code=200,
            text='{"data":{"total":1,"diff":[{"f12":"000001"}]}}',
        )

    detected = proxy.configure_akshare_network_proxy(
        force_recheck=True,
        request_get=fake_get,
        socket_connect=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("unused")),
        listening_ports=lambda: [],
        system_proxies=lambda: {},
    )

    assert detected == ""
    assert "HTTP_PROXY" not in os.environ
    assert "HTTPS_PROXY" not in os.environ


def test_akshare_proxy_detection_reads_candidate_port_from_env_file(monkeypatch, tmp_path):
    from app.data_fetch.utils import akshare_network_proxy as proxy

    env_file = tmp_path / ".env"
    env_file.write_text("PROXY_HOST=127.0.0.1:18889\n", encoding="utf-8")

    proxy.reset_akshare_proxy_detection_cache()
    monkeypatch.setenv("AKSHARE_PROXY_ENV_FILES", str(env_file))

    def fake_connect(address, timeout=0):
        host, port = address
        if host == "127.0.0.1" and port == 18889:
            return SimpleNamespace(close=lambda: None)
        raise OSError("closed")

    def fake_get(url, **kwargs):
        proxies = kwargs.get("proxies") or {}
        if proxies.get("https") == "http://127.0.0.1:18889":
            return SimpleNamespace(
                status_code=200,
                text='{"data":{"total":1,"diff":[{"f12":"000001"}]}}',
            )
        raise OSError("remote closed")

    detected = proxy.configure_akshare_network_proxy(
        force_recheck=True,
        request_get=fake_get,
        socket_connect=fake_connect,
        listening_ports=lambda: [],
        system_proxies=lambda: {},
    )

    assert detected == "http://127.0.0.1:18889"


def test_akshare_proxy_detection_reads_proxy_port_from_env_file(monkeypatch, tmp_path):
    from app.data_fetch.utils import akshare_network_proxy as proxy

    env_file = tmp_path / ".env"
    env_file.write_text("PROXY_PORT=18890\n", encoding="utf-8")

    proxy.reset_akshare_proxy_detection_cache()
    monkeypatch.setenv("AKSHARE_PROXY_ENV_FILES", str(env_file))

    def fake_connect(address, timeout=0):
        host, port = address
        if host == "127.0.0.1" and port == 18890:
            return SimpleNamespace(close=lambda: None)
        raise OSError("closed")

    def fake_get(url, **kwargs):
        proxies = kwargs.get("proxies") or {}
        if proxies.get("https") == "http://127.0.0.1:18890":
            return SimpleNamespace(
                status_code=200,
                text='{"data":{"total":1,"diff":[{"f12":"000001"}]}}',
            )
        raise OSError("remote closed")

    detected = proxy.configure_akshare_network_proxy(
        force_recheck=True,
        request_get=fake_get,
        socket_connect=fake_connect,
        listening_ports=lambda: [],
        system_proxies=lambda: {},
    )

    assert detected == "http://127.0.0.1:18890"


@pytest.mark.asyncio
async def test_akshare_script_execution_configures_network_proxy(monkeypatch):
    import app.services.akshare.script as script_module
    from app.services.akshare.script import AkshareScriptService

    calls = []

    def fake_configure():
        calls.append("configured")
        return "http://127.0.0.1:18888"

    def callable_obj():
        return {"ok": True}

    monkeypatch.setattr(script_module, "configure_akshare_network_proxy", fake_configure)

    result = await AkshareScriptService._execute_callable(callable_obj, {}, 5)

    assert calls == ["configured"]
    assert result == {"ok": True}
