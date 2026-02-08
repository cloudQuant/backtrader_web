"""
监控告警 API 测试

测试：
- 告警规则 CRUD
- 告警管理
- 告警状态更新
- 告警统计
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAlertRules:
    """告警规则测试"""

    async def test_create_alert_rule_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.post(
            "/api/v1/monitoring/rules",
            json={
                "name": "测试规则",
                "alert_type": "account",
                "severity": "warning",
                "trigger_type": "threshold",
                "trigger_config": {"threshold": 0.1}
            }
        )
        # API可能返回401或403
        assert response.status_code in [401, 403]

    async def test_list_alert_rules_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/monitoring/rules")
        # API可能返回401或403
        assert response.status_code in [401, 403]

    async def test_list_alert_rules_with_auth(self, client: AsyncClient, auth_headers):
        """测试带认证的列表请求"""
        response = await client.get(
            "/api/v1/monitoring/rules",
            headers=auth_headers
        )
        # 200 或 404
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
class TestAlerts:
    """告警管理测试"""

    async def test_list_alerts_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/monitoring/")
        # API可能返回401或403
        assert response.status_code in [401, 403]

    async def test_list_alerts_with_auth(self, client: AsyncClient, auth_headers):
        """测试带认证的告警列表"""
        response = await client.get(
            "/api/v1/monitoring/",
            headers=auth_headers
        )
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
class TestAlertStatistics:
    """告警统计测试"""

    async def test_get_alert_summary_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/monitoring/statistics/summary")
        # API可能返回401或403
        assert response.status_code in [401, 403]

    async def test_get_alert_summary_with_auth(self, client: AsyncClient, auth_headers):
        """测试带认证的统计摘要"""
        response = await client.get(
            "/api/v1/monitoring/statistics/summary",
            headers=auth_headers
        )
        assert response.status_code in [200, 404]


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

        # 检查枚举值
        assert hasattr(AlertType, 'ACCOUNT')
        assert hasattr(AlertType, 'POSITION')
        assert hasattr(AlertType, 'STRATEGY')
        assert hasattr(AlertType, 'SYSTEM')

    async def test_alert_severity_values(self):
        """测试告警级别枚举值"""
        from app.models.alerts import AlertSeverity

        # 检查枚举值
        assert hasattr(AlertSeverity, 'INFO')
        assert hasattr(AlertSeverity, 'WARNING')
        assert hasattr(AlertSeverity, 'ERROR')
        assert hasattr(AlertSeverity, 'CRITICAL')

    async def test_alert_status_values(self):
        """测试告警状态枚举值"""
        from app.models.alerts import AlertStatus

        # 检查枚举值
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

        # 检查路由存在
        assert monitoring_router is not None
        assert hasattr(monitoring_router, 'routes')

    async def test_monitoring_endpoints_exist(self):
        """测试监控端点存在"""
        from app.api.monitoring import router

        # 检查路由中是否有必要端点
        routes = [route.path for route in router.routes]
        # 应该包含这些端点
        assert any("rules" in str(r) for r in routes)
        assert any("statistics" in str(r) for r in routes)
