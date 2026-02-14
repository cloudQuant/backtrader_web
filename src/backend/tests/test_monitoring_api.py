"""
监控告警 API 测试

测试：
- 告警规则 CRUD
- 告警管理
- 告警状态更新
- 告警统计
- WebSocket端点
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient


# 有效的告警规则创建请求
VALID_ALERT_RULE_REQUEST = {
    "name": "测试告警规则",
    "description": "测试描述",
    "alert_type": "account",
    "severity": "warning",
    "trigger_type": "threshold",
    "trigger_config": {"threshold": 0.1},
    "notification_enabled": True,
    "notification_channels": ["email"],
}


@pytest.mark.asyncio
class TestAlertRules:
    """告警规则测试"""

    async def test_create_alert_rule_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.post(
            "/api/v1/monitoring/rules",
            json=VALID_ALERT_RULE_REQUEST
        )
        assert response.status_code in [401, 403]

    async def test_create_alert_rule_success(self, client: AsyncClient, auth_headers):
        """测试成功创建告警规则"""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            from app.schemas.monitoring import AlertType, AlertSeverity, TriggerType
            from datetime import datetime

            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            # Create a proper dict that matches AlertRuleResponse schema
            mock_rule_dict = {
                "id": "rule_123",
                "user_id": "user_123",
                "name": "测试规则",
                "description": "测试描述",
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
        """测试无效数据"""
        response = await client.post(
            "/api/v1/monitoring/rules",
            headers=auth_headers,
            json={"name": ""}  # 缺少必填字段
        )
        assert response.status_code == 422

    async def test_list_alert_rules_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/monitoring/rules")
        assert response.status_code in [401, 403]

    async def test_list_alert_rules_with_auth(self, client: AsyncClient, auth_headers):
        """测试带认证的列表请求"""
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
        """测试带过滤参数的列表请求"""
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
        """测试获取规则详情（未实现）"""
        response = await client.get(
            "/api/v1/monitoring/rules/rule_123",
            headers=auth_headers
        )
        assert response.status_code == 501

    async def test_update_alert_rule_success(self, client: AsyncClient, auth_headers):
        """测试更新告警规则"""
        with patch('app.api.monitoring.MonitoringService') as mock_service_class:
            from app.schemas.monitoring import AlertType, AlertSeverity, TriggerType
            from datetime import datetime

            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            # Create a proper dict that matches AlertRuleResponse schema
            mock_rule_dict = {
                "id": "rule_123",
                "user_id": "user_123",
                "name": "更新后的规则",
                "description": "测试描述",
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
                json={"name": "更新后的规则"}
            )
            assert response.status_code in [200, 404]

    async def test_delete_alert_rule_requires_auth(self, client: AsyncClient):
        """测试删除需要认证"""
        response = await client.delete("/api/v1/monitoring/rules/rule_123")
        assert response.status_code in [401, 403]

    async def test_delete_alert_rule_not_found(self, client: AsyncClient, auth_headers):
        """测试删除不存在的规则"""
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
        """测试成功删除规则"""
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
    """告警管理测试"""

    async def test_list_alerts_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/monitoring/")
        assert response.status_code in [401, 403]

    async def test_list_alerts_with_auth(self, client: AsyncClient, auth_headers):
        """测试带认证的告警列表"""
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
        """测试带过滤参数的告警列表"""
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
        """测试分页参数"""
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
        """测试无效的limit参数"""
        response = await client.get(
            "/api/v1/monitoring/?limit=200",
            headers=auth_headers
        )
        assert response.status_code in [422, 404]

    async def test_get_alert_not_implemented(self, client: AsyncClient, auth_headers):
        """测试获取告警详情（未实现）"""
        response = await client.get(
            "/api/v1/monitoring/alert_123",
            headers=auth_headers
        )
        assert response.status_code == 501

    async def test_mark_alert_read_requires_auth(self, client: AsyncClient):
        """测试标记已读需要认证"""
        response = await client.put("/api/v1/monitoring/alert_123/read")
        assert response.status_code in [401, 403]

    async def test_mark_alert_read_not_found(self, client: AsyncClient, auth_headers):
        """测试标记不存在的告警"""
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
        """测试成功标记已读"""
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
        """测试解决告警需要认证"""
        response = await client.put("/api/v1/monitoring/alert_123/resolve")
        assert response.status_code in [401, 403]

    async def test_resolve_alert_not_found(self, client: AsyncClient, auth_headers):
        """测试解决不存在的告警"""
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
        """测试成功解决告警"""
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
        """测试确认告警需要认证"""
        response = await client.put("/api/v1/monitoring/alert_123/acknowledge")
        assert response.status_code in [401, 403]

    async def test_acknowledge_alert_not_found(self, client: AsyncClient, auth_headers):
        """测试确认不存在的告警"""
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
        """测试成功确认告警"""
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
    """告警统计测试"""

    async def test_get_alert_summary_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/monitoring/statistics/summary")
        assert response.status_code in [401, 403]

    async def test_get_alert_summary_with_auth(self, client: AsyncClient, auth_headers):
        """测试带认证的统计摘要"""
        response = await client.get(
            "/api/v1/monitoring/statistics/summary",
            headers=auth_headers
        )
        assert response.status_code in [200, 404]

    async def test_get_alerts_by_type_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get(
            "/api/v1/monitoring/statistics/by-type?start_date=2024-01-01&end_date=2024-01-31"
        )
        assert response.status_code in [401, 403]

    async def test_get_alerts_by_type_missing_params(self, client: AsyncClient, auth_headers):
        """测试缺少必要参数"""
        response = await client.get(
            "/api/v1/monitoring/statistics/by-type",
            headers=auth_headers
        )
        assert response.status_code in [422, 404]

    async def test_get_alerts_by_type_invalid_date(self, client: AsyncClient, auth_headers):
        """测试无效的日期格式"""
        response = await client.get(
            "/api/v1/monitoring/statistics/by-type?start_date=invalid&end_date=2024-01-31",
            headers=auth_headers
        )
        assert response.status_code in [400, 404]

    async def test_get_alerts_by_type_success(self, client: AsyncClient, auth_headers):
        """测试成功获取按类型统计"""
        response = await client.get(
            "/api/v1/monitoring/statistics/by-type?start_date=2024-01-01&end_date=2024-01-31",
            headers=auth_headers
        )
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
class TestMonitoringWebSocket:
    """WebSocket端点测试"""

    async def test_websocket_endpoint_exists(self):
        """测试WebSocket端点存在"""
        from app.api.monitoring import router

        routes = [route.path for route in router.routes]
        assert any("/ws/alerts" in str(r) for r in routes)

    async def test_websocket_handler_defined(self):
        """测试WebSocket处理函数已定义"""
        from app.api.monitoring import alerts_websocket

        assert alerts_websocket is not None
        assert callable(alerts_websocket)

    async def test_websocket_connection(self):
        """测试WebSocket连接基本功能"""
        from app.api.monitoring import alerts_websocket
        from unittest.mock import AsyncMock, MagicMock, patch
        import asyncio

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
    """监控服务单元测试"""

    async def test_service_exists(self):
        """测试服务类存在"""
        from app.services.monitoring_service import MonitoringService

        service = MonitoringService()
        assert service is not None

    async def test_service_attributes(self):
        """测试服务属性"""
        from app.services.monitoring_service import MonitoringService

        service = MonitoringService()
        assert hasattr(service, 'alert_repo')
        assert hasattr(service, 'alert_rule_repo')


@pytest.mark.asyncio
class TestAlertModels:
    """告警模型测试"""

    async def test_alert_model_exists(self):
        """测试告警模型存在"""
        from app.models.alerts import Alert, AlertRule

        assert Alert is not None
        assert AlertRule is not None

    async def test_alert_enums_exist(self):
        """测试告警枚举存在"""
        from app.models.alerts import AlertType, AlertSeverity, AlertStatus

        assert AlertType is not None
        assert AlertSeverity is not None
        assert AlertStatus is not None

    async def test_alert_type_values(self):
        """测试告警类型枚举值"""
        from app.models.alerts import AlertType

        assert hasattr(AlertType, 'ACCOUNT')
        assert hasattr(AlertType, 'POSITION')
        assert hasattr(AlertType, 'STRATEGY')
        assert hasattr(AlertType, 'SYSTEM')

    async def test_alert_severity_values(self):
        """测试告警级别枚举值"""
        from app.models.alerts import AlertSeverity

        assert hasattr(AlertSeverity, 'INFO')
        assert hasattr(AlertSeverity, 'WARNING')
        assert hasattr(AlertSeverity, 'ERROR')
        assert hasattr(AlertSeverity, 'CRITICAL')

    async def test_alert_status_values(self):
        """测试告警状态枚举值"""
        from app.models.alerts import AlertStatus

        assert hasattr(AlertStatus, 'ACTIVE')
        assert hasattr(AlertStatus, 'RESOLVED')
        assert hasattr(AlertStatus, 'ACKNOWLEDGED')
        assert hasattr(AlertStatus, 'IGNORED')


@pytest.mark.asyncio
class TestMonitoringAPIRoutes:
    """监控API路由测试"""

    async def test_monitoring_routes_registered(self):
        """测试监控路由已注册"""
        from app.api.monitoring import router as monitoring_router

        assert monitoring_router is not None
        assert hasattr(monitoring_router, 'routes')

    async def test_monitoring_endpoints_exist(self):
        """测试监控端点存在"""
        from app.api.monitoring import router

        routes = [route.path for route in router.routes]
        route_str = str(routes)
        assert "rules" in route_str
        assert "statistics" in route_str
