import pytest

pytest.importorskip(
    "bt_api_py.brokers",
    reason="broker contract is supplied by the external bt_api_py package",
)


@pytest.mark.asyncio
async def test_mock_broker_adapter_passes_contract_cases():
    from bt_api_py.brokers.mock import MockBrokerAdapter
    from bt_api_py.testing.contract_cases import run_broker_contract_cases

    adapter = MockBrokerAdapter()
    report = await run_broker_contract_cases(adapter)

    assert report["passed"] is True
    assert report["method_count"] >= 12
    assert report["capabilities"]["supports_native_paper"] is True


@pytest.mark.asyncio
async def test_gateway_bridge_write_paths_require_feature_flag(monkeypatch):
    from bt_api_py.brokers.errors import BrokerError, BrokerErrorCode
    from bt_api_py.brokers.gateway_bridge import GatewayBridgeAdapter
    from bt_api_py.brokers.types import OrderRequest

    monkeypatch.delenv("BT_API_PY_BRIDGE_ENABLE_WRITE", raising=False)
    adapter = GatewayBridgeAdapter(gateway_service={"health": "ok"})

    with pytest.raises(BrokerError) as exc_info:
        await adapter.place_order(
            OrderRequest(account_id="acct", symbol="RB2510", side="buy", quantity=1)
        )

    assert exc_info.value.code == BrokerErrorCode.NOT_SUPPORTED
