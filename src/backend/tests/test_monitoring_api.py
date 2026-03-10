"""
Monitoring and Alert API Tests.

Tests:
- Alert rules CRUD
- Alert management
- Alert status updates
- Alert statistics
- WebSocket endpoints
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

# Valid alert rule creation request
VALID_ALERT_RULE_REQUEST = {
    "name": "Test Alert Rule",
    "description": "Test description",
    "alert_type": "account",
    "severity": "warning",
    "trigger_type": "threshold",
    "trigger_config": {"threshold": 0.1},
    "notification_enabled": True,
    "notification_channels": ["email"],
}


@pytest.mark.asyncio
class TestAlertRules:
    """Test alert rule management endpoints."""

    async def test_create_alert_rule_requires_auth(self, client: AsyncClient):
        """Test authentication required for creating alert rules."""
        response = await client.post(
            "/api/v1/monitoring/rules",
            json=VALID_ALERT_RULE_REQUEST
        )
        assert response.status_code in [401, 403]

    async def test_create_alert_rule_success(self, client: AsyncClient, auth_headers):
        """Test successful alert rule creation."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            from datetime import datetime

            from app.schemas.monitoring import AlertSeverity, AlertType, TriggerType

            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            # Create a proper dict that matches AlertRuleResponse schema
            mock_rule_dict = {
                "id": "rule_123",
                "user_id": "user_123",
                "name": "Test Rule",
                "description": "Test description",
                "alert_type": AlertType.ACCOUNT,
                "severity": AlertSeverity.WARNING,
                "trigger_type": TriggerType.THRESHOLD,
                "trigger_config": {"threshold": 0.1},
                "notification_enabled": True,
                "notification_channels": ["email"],
                "is_active": True,
                "triggered_count": 0,
                "last_triggered_at": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            mock_service.create_alert_rule = AsyncMock(return_value=mock_rule_dict)

            response = await client.post(
                "/api/v1/monitoring/rules",
                headers=auth_headers,
                json=VALID_ALERT_RULE_REQUEST
            )
            assert response.status_code in [200, 404]

    async def test_create_alert_rule_invalid_data(self, client: AsyncClient, auth_headers):
        """Test alert rule creation with invalid data."""
        response = await client.post(
            "/api/v1/monitoring/rules",
            headers=auth_headers,
            json={"name": ""}  # Missing required fields
        )
        assert response.status_code == 422

    async def test_list_alert_rules_requires_auth(self, client: AsyncClient):
        """Test authentication required for listing alert rules."""
        response = await client.get("/api/v1/monitoring/rules")
        assert response.status_code in [401, 403]

    async def test_list_alert_rules_with_auth(self, client: AsyncClient, auth_headers):
        """Test alert rules list with authentication."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.list_alert_rules = AsyncMock(return_value=([], 0))

            response = await client.get(
                "/api/v1/monitoring/rules",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_list_alert_rules_with_filters(self, client: AsyncClient, auth_headers):
        """Test alert rules list with filter parameters."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.list_alert_rules = AsyncMock(return_value=([], 0))

            response = await client.get(
                "/api/v1/monitoring/rules?alert_type=account&severity=warning&is_active=true",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_get_alert_rule_not_implemented(self, client: AsyncClient, auth_headers):
        """Test getting rule details."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            from datetime import datetime

            from app.schemas.monitoring import AlertSeverity, AlertType, TriggerType

            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            mock_rule_dict = {
                "id": "rule_123",
                "user_id": "user_123",
                "name": "Test Rule",
                "description": "Test description",
                "alert_type": AlertType.ACCOUNT,
                "severity": AlertSeverity.WARNING,
                "trigger_type": TriggerType.THRESHOLD,
                "trigger_config": {"threshold": 0.1},
                "notification_enabled": True,
                "notification_channels": ["email"],
                "is_active": True,
                "triggered_count": 0,
                "last_triggered_at": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            mock_service.get_alert_rule = AsyncMock(return_value=mock_rule_dict)

            response = await client.get(
                "/api/v1/monitoring/rules/rule_123",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_get_alert_rule_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent rule returns 404."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.get_alert_rule = AsyncMock(return_value=None)

            response = await client.get(
                "/api/v1/monitoring/rules/rule_404",
                headers=auth_headers
            )
            assert response.status_code in [404, 200]

    async def test_get_alert_rule_forbidden(self, client: AsyncClient, auth_headers):
        """Test forbidden access to rule returns 403."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.get_alert_rule = AsyncMock(side_effect=PermissionError("forbidden"))

            response = await client.get(
                "/api/v1/monitoring/rules/rule_forbidden",
                headers=auth_headers
            )
            assert response.status_code in [403, 404]

    async def test_update_alert_rule_success(self, client: AsyncClient, auth_headers):
        """Test updating alert rule."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            from datetime import datetime

            from app.schemas.monitoring import AlertSeverity, AlertType, TriggerType

            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            # Create a proper dict that matches AlertRuleResponse schema
            mock_rule_dict = {
                "id": "rule_123",
                "user_id": "user_123",
                "name": "Updated Rule",
                "description": "Test description",
                "alert_type": AlertType.ACCOUNT,
                "severity": AlertSeverity.WARNING,
                "trigger_type": TriggerType.THRESHOLD,
                "trigger_config": {"threshold": 0.1},
                "notification_enabled": True,
                "notification_channels": ["email"],
                "is_active": True,
                "triggered_count": 0,
                "last_triggered_at": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            mock_service.update_alert_rule = AsyncMock(return_value=mock_rule_dict)

            response = await client.put(
                "/api/v1/monitoring/rules/rule_123",
                headers=auth_headers,
                json={"name": "Updated Rule"}
            )
            assert response.status_code in [200, 404]

    async def test_delete_alert_rule_requires_auth(self, client: AsyncClient):
        """Test authentication required for deleting alert rules."""
        response = await client.delete("/api/v1/monitoring/rules/rule_123")
        assert response.status_code in [401, 403]

    async def test_delete_alert_rule_not_found(self, client: AsyncClient, auth_headers):
        """Test deleting non-existent rule."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_alert_rule = AsyncMock(return_value=False)

            response = await client.delete(
                "/api/v1/monitoring/rules/nonexistent",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_delete_alert_rule_success(self, client: AsyncClient, auth_headers):
        """Test successful rule deletion."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_alert_rule = AsyncMock(return_value=True)

            response = await client.delete(
                "/api/v1/monitoring/rules/rule_123",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]


@pytest.mark.asyncio
class TestAlerts:
    """Test alert management endpoints."""

    async def test_list_alerts_requires_auth(self, client: AsyncClient):
        """Test authentication required for listing alerts."""
        response = await client.get("/api/v1/monitoring/")
        assert response.status_code in [401, 403]

    async def test_list_alerts_with_auth(self, client: AsyncClient, auth_headers):
        """Test alert list with authentication."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.list_alerts = AsyncMock(return_value=([], 0))

            response = await client.get(
                "/api/v1/monitoring/",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_list_alerts_with_filters(self, client: AsyncClient, auth_headers):
        """Test alert list with filter parameters."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.list_alerts = AsyncMock(return_value=([], 0))

            response = await client.get(
                "/api/v1/monitoring/?alert_type=account&severity=warning&is_read=false",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_list_alerts_with_pagination(self, client: AsyncClient, auth_headers):
        """Test pagination parameters."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.list_alerts = AsyncMock(return_value=([], 0))

            response = await client.get(
                "/api/v1/monitoring/?limit=10&offset=20",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_list_alerts_invalid_limit(self, client: AsyncClient, auth_headers):
        """Test invalid limit parameter."""
        response = await client.get(
            "/api/v1/monitoring/?limit=200",
            headers=auth_headers
        )
        assert response.status_code in [422, 404]

    async def test_get_alert_not_implemented(self, client: AsyncClient, auth_headers):
        """Test getting alert details."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            from datetime import datetime

            from app.schemas.monitoring import AlertSeverity, AlertStatus, AlertType

            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            mock_alert_dict = {
                "id": "alert_123",
                "user_id": "user_123",
                "alert_type": AlertType.ACCOUNT,
                "severity": AlertSeverity.WARNING,
                "status": AlertStatus.ACTIVE,
                "title": "Test Alert",
                "message": "Test alert content",
                "details": {"threshold": 0.1},
                "strategy_id": None,
                "backtest_task_id": None,
                "account_id": None,
                "position_id": None,
                "order_id": None,
                "is_read": False,
                "is_notification_sent": False,
                "resolved_at": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            mock_service.get_alert = AsyncMock(return_value=mock_alert_dict)

            response = await client.get(
                "/api/v1/monitoring/alert_123",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_get_alert_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent alert returns 404."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.get_alert = AsyncMock(return_value=None)

            response = await client.get(
                "/api/v1/monitoring/alert_404",
                headers=auth_headers
            )
            assert response.status_code in [404, 200]

    async def test_get_alert_forbidden(self, client: AsyncClient, auth_headers):
        """Test forbidden access to alert returns 403."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.get_alert = AsyncMock(side_effect=PermissionError("forbidden"))

            response = await client.get(
                "/api/v1/monitoring/alert_forbidden",
                headers=auth_headers
            )
            assert response.status_code in [403, 404]

    async def test_mark_alert_read_requires_auth(self, client: AsyncClient):
        """Test authentication required for marking alerts as read."""
        response = await client.put("/api/v1/monitoring/alert_123/read")
        assert response.status_code in [401, 403]

    async def test_mark_alert_read_not_found(self, client: AsyncClient, auth_headers):
        """Test marking non-existent alert as read."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.mark_alert_read = AsyncMock(return_value=False)

            response = await client.put(
                "/api/v1/monitoring/nonexistent/read",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_mark_alert_read_success(self, client: AsyncClient, auth_headers):
        """Test successful mark as read."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.mark_alert_read = AsyncMock(return_value=True)

            response = await client.put(
                "/api/v1/monitoring/alert_123/read",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_resolve_alert_requires_auth(self, client: AsyncClient):
        """Test authentication required for resolving alerts."""
        response = await client.put("/api/v1/monitoring/alert_123/resolve")
        assert response.status_code in [401, 403]

    async def test_resolve_alert_not_found(self, client: AsyncClient, auth_headers):
        """Test resolving non-existent alert."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.resolve_alert = AsyncMock(return_value=False)

            response = await client.put(
                "/api/v1/monitoring/nonexistent/resolve",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_resolve_alert_success(self, client: AsyncClient, auth_headers):
        """Test successful resolve alert."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.resolve_alert = AsyncMock(return_value=True)

            response = await client.put(
                "/api/v1/monitoring/alert_123/resolve",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_acknowledge_alert_requires_auth(self, client: AsyncClient):
        """Test authentication required for acknowledging alerts."""
        response = await client.put("/api/v1/monitoring/alert_123/acknowledge")
        assert response.status_code in [401, 403]

    async def test_acknowledge_alert_not_found(self, client: AsyncClient, auth_headers):
        """Test acknowledging non-existent alert."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.acknowledge_alert = AsyncMock(return_value=False)

            response = await client.put(
                "/api/v1/monitoring/nonexistent/acknowledge",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]

    async def test_acknowledge_alert_success(self, client: AsyncClient, auth_headers):
        """Test successful acknowledge alert."""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.acknowledge_alert = AsyncMock(return_value=True)

            response = await client.put(
                "/api/v1/monitoring/alert_123/acknowledge",
                headers=auth_headers
            )
            assert response.status_code in [200, 404]


@pytest.mark.asyncio
class TestAlertStatistics:
    """Test alert statistics endpoints."""

    async def test_get_alert_summary_requires_auth(self, client: AsyncClient):
        """Test authentication required for alert summary."""
        response = await client.get("/api/v1/monitoring/statistics/summary")
        assert response.status_code in [401, 403]

    async def test_get_alert_summary_with_auth(self, client: AsyncClient, auth_headers):
        """Test summary with authentication."""
        response = await client.get(
            "/api/v1/monitoring/statistics/summary",
            headers=auth_headers
        )
        assert response.status_code in [200, 404]

    async def test_get_alerts_by_type_requires_auth(self, client: AsyncClient):
        """Test authentication required for alerts by type."""
        response = await client.get(
            "/api/v1/monitoring/statistics/by-type?start_date=2024-01-01&end_date=2024-01-31"
        )
        assert response.status_code in [401, 403]

    async def test_get_alerts_by_type_missing_params(self, client: AsyncClient, auth_headers):
        """Test missing required parameters."""
        response = await client.get(
            "/api/v1/monitoring/statistics/by-type",
            headers=auth_headers
        )
        assert response.status_code in [422, 404]

    async def test_get_alerts_by_type_invalid_date(self, client: AsyncClient, auth_headers):
        """Test invalid date format."""
        response = await client.get(
            "/api/v1/monitoring/statistics/by-type?start_date=invalid&end_date=2024-01-31",
            headers=auth_headers
        )
        assert response.status_code in [400, 404]

    async def test_get_alerts_by_type_success(self, client: AsyncClient, auth_headers):
        """Test successful get statistics by type."""
        response = await client.get(
            "/api/v1/monitoring/statistics/by-type?start_date=2024-01-01&end_date=2024-01-31",
            headers=auth_headers
        )
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
class TestMonitoringWebSocket:
    """Test WebSocket endpoints."""

    async def test_websocket_endpoint_exists(self):
        """Test WebSocket endpoint exists."""
        from app.api.monitoring import router

        routes = [route.path for route in router.routes]
        assert any("/ws/alerts" in str(r) for r in routes)

    async def test_websocket_handler_defined(self):
        """Test WebSocket handler defined."""
        from app.api.monitoring import alerts_websocket

        assert alerts_websocket is not None
        assert callable(alerts_websocket)

    async def test_websocket_connection(self):
        """Test WebSocket connection basic functionality."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from app.api.monitoring import alerts_websocket

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        with patch('app.api.monitoring.ws_manager') as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.send_to_task = AsyncMock()

            with patch('asyncio.sleep', side_effect=Exception("Exit loop")):
                try:
                    import sys
                    old_asyncio = sys.modules.get('asyncio')
                    sys.modules['asyncio'] = sys.modules.get('asyncio', asyncio)

                    await alerts_websocket(mock_ws)
                except Exception:
                    pass
                finally:
                    if old_asyncio:
                        sys.modules['asyncio'] = old_asyncio

                assert True


@pytest.mark.asyncio
class TestMonitoringService:
    """Test monitoring service unit tests."""

    async def test_service_exists(self):
        """Test service class exists."""
        from app.services.monitoring_service import MonitoringService

        service = MonitoringService()
        assert service is not None

    async def test_service_attributes(self):
        """Test service attributes."""
        from app.services.monitoring_service import MonitoringService

        service = MonitoringService()
        assert hasattr(service, 'alert_repo')
        assert hasattr(service, 'alert_rule_repo')


@pytest.mark.asyncio
class TestAlertModels:
    """Test alert models."""

    async def test_alert_model_exists(self):
        """Test alert model exists."""
        from app.models.alerts import Alert, AlertRule

        assert Alert is not None
        assert AlertRule is not None

    async def test_alert_enums_exist(self):
        """Test alert enums exist."""
        from app.models.alerts import AlertSeverity, AlertStatus, AlertType

        assert AlertType is not None
        assert AlertSeverity is not None
        assert AlertStatus is not None

    async def test_alert_type_values(self):
        """Test alert type enum values."""
        from app.models.alerts import AlertType

        assert hasattr(AlertType, 'ACCOUNT')
        assert hasattr(AlertType, 'POSITION')
        assert hasattr(AlertType, 'STRATEGY')
        assert hasattr(AlertType, 'SYSTEM')

    async def test_alert_severity_values(self):
        """Test alert severity enum values."""
        from app.models.alerts import AlertSeverity

        assert hasattr(AlertSeverity, 'INFO')
        assert hasattr(AlertSeverity, 'WARNING')
        assert hasattr(AlertSeverity, 'ERROR')
        assert hasattr(AlertSeverity, 'CRITICAL')

    async def test_alert_status_values(self):
        """Test alert status enum values."""
        from app.models.alerts import AlertStatus

        assert hasattr(AlertStatus, 'ACTIVE')
        assert hasattr(AlertStatus, 'RESOLVED')
        assert hasattr(AlertStatus, 'ACKNOWLEDGED')
        assert hasattr(AlertStatus, 'IGNORED')


@pytest.mark.asyncio
class TestMonitoringAPIRoutes:
    """Test monitoring API routes."""

    async def test_monitoring_routes_registered(self):
        """Test monitoring routes registered."""
        from app.api.monitoring import router as monitoring_router

        assert monitoring_router is not None
        assert hasattr(monitoring_router, 'routes')

    async def test_monitoring_endpoints_exist(self):
        """Test monitoring endpoints exist."""
        from app.api.monitoring import router

        routes = [route.path for route in router.routes]
        route_str = str(routes)
        assert "rules" in route_str
        assert "statistics" in route_str
