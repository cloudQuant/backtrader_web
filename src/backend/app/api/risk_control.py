"""
Risk Control API - 风控API端点

提供风控配置管理和告警查询接口。
"""


from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.services.risk_control_service import (
    RiskAlertLevel,
    RiskControlConfig,
    RiskControlService,
    get_risk_control_service,
)

router = APIRouter(prefix="/risk-control", tags=["Risk Control"])


# ============== Schemas ==============

class RiskControlConfigRequest(BaseModel):
    """风控配置请求"""
    max_position_pct: float = Field(30.0, ge=1, le=100, description="单品种最大仓位比例(%)")
    max_total_position_pct: float = Field(80.0, ge=1, le=100, description="总仓位上限(%)")
    max_daily_loss_pct: float = Field(5.0, ge=0.1, le=50, description="日亏损上限(%)")
    max_drawdown_pct: float = Field(20.0, ge=1, le=50, description="最大回撤限制(%)")
    stop_loss_pct: float = Field(5.0, ge=0.1, le=50, description="止损比例(%)")
    take_profit_pct: float = Field(20.0, ge=1, le=100, description="止盈比例(%)")
    max_daily_trades: int = Field(50, ge=1, le=500, description="每日最大交易次数")
    max_order_size: float = Field(100000.0, ge=1000, description="单笔最大金额")
    enable_stop_loss: bool = Field(True, description="启用止损")
    enable_take_profit: bool = Field(True, description="启用止盈")
    enable_position_limit: bool = Field(True, description="启用仓位限制")


class RiskControlConfigResponse(BaseModel):
    """风控配置响应"""
    max_position_pct: float
    max_total_position_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    max_daily_trades: int
    max_order_size: float
    enable_stop_loss: bool
    enable_take_profit: bool
    enable_position_limit: bool


class RiskAlertResponse(BaseModel):
    """风控告警响应"""
    alert_type: str
    level: str
    message: str
    instance_id: str
    timestamp: str
    details: dict


class AlertListResponse(BaseModel):
    """告警列表响应"""
    total: int
    alerts: list[RiskAlertResponse]


# ============== Dependencies ==============

def get_risk_service() -> RiskControlService:
    """获取风控服务"""
    return get_risk_control_service()


# ============== Endpoints ==============

@router.get("/config", summary="Get risk control config")
async def get_config(
    current_user=Depends(get_current_user),
    service: RiskControlService = Depends(get_risk_service),
) -> RiskControlConfigResponse:
    """
    获取当前风控配置

    需要认证。
    """
    config = service.config
    return RiskControlConfigResponse(
        max_position_pct=config.max_position_pct,
        max_total_position_pct=config.max_total_position_pct,
        max_daily_loss_pct=config.max_daily_loss_pct,
        max_drawdown_pct=config.max_drawdown_pct,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        max_daily_trades=config.max_daily_trades,
        max_order_size=config.max_order_size,
        enable_stop_loss=config.enable_stop_loss,
        enable_take_profit=config.enable_take_profit,
        enable_position_limit=config.enable_position_limit,
    )


@router.put("/config", summary="Update risk control config")
async def update_config(
    request: RiskControlConfigRequest,
    current_user=Depends(get_current_user),
    service: RiskControlService = Depends(get_risk_service),
) -> RiskControlConfigResponse:
    """
    更新风控配置

    需要认证。
    """
    config = RiskControlConfig(
        max_position_pct=request.max_position_pct,
        max_total_position_pct=request.max_total_position_pct,
        max_daily_loss_pct=request.max_daily_loss_pct,
        max_drawdown_pct=request.max_drawdown_pct,
        stop_loss_pct=request.stop_loss_pct,
        take_profit_pct=request.take_profit_pct,
        max_daily_trades=request.max_daily_trades,
        max_order_size=request.max_order_size,
        enable_stop_loss=request.enable_stop_loss,
        enable_take_profit=request.enable_take_profit,
        enable_position_limit=request.enable_position_limit,
    )

    service.update_config(config)

    return RiskControlConfigResponse(
        max_position_pct=config.max_position_pct,
        max_total_position_pct=config.max_total_position_pct,
        max_daily_loss_pct=config.max_daily_loss_pct,
        max_drawdown_pct=config.max_drawdown_pct,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        max_daily_trades=config.max_daily_trades,
        max_order_size=config.max_order_size,
        enable_stop_loss=config.enable_stop_loss,
        enable_take_profit=config.enable_take_profit,
        enable_position_limit=config.enable_position_limit,
    )


@router.get("/alerts", summary="Get risk alerts")
async def get_alerts(
    instance_id: str | None = None,
    level: str | None = None,
    limit: int = 100,
    current_user=Depends(get_current_user),
    service: RiskControlService = Depends(get_risk_service),
) -> AlertListResponse:
    """
    获取风控告警列表

    Args:
        instance_id: 实例ID过滤
        level: 告警级别过滤 (info/warning/critical)
        limit: 返回数量限制

    需要认证。
    """
    alert_level = None
    if level:
        try:
            alert_level = RiskAlertLevel(level)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid alert level: {level}. Must be one of: info, warning, critical",
            )

    alerts = service.get_alerts(
        instance_id=instance_id,
        level=alert_level,
        limit=limit,
    )

    return AlertListResponse(
        total=len(alerts),
        alerts=[
            RiskAlertResponse(
                alert_type=a.alert_type.value,
                level=a.level.value,
                message=a.message,
                instance_id=a.instance_id,
                timestamp=a.timestamp.isoformat(),
                details=a.details,
            )
            for a in alerts
        ],
    )


@router.delete("/alerts", summary="Clear risk alerts")
async def clear_alerts(
    instance_id: str | None = None,
    current_user=Depends(get_current_user),
    service: RiskControlService = Depends(get_risk_service),
) -> dict:
    """
    清除风控告警

    Args:
        instance_id: 实例ID(可选，不指定则清除全部)

    需要认证。
    """
    count = service.clear_alerts(instance_id)
    return {
        "cleared": count,
        "message": f"Cleared {count} alerts",
    }


@router.post("/reset-daily", summary="Reset daily counters")
async def reset_daily_counters(
    instance_id: str | None = None,
    current_user=Depends(get_current_user),
    service: RiskControlService = Depends(get_risk_service),
) -> dict:
    """
    重置每日计数器

    通常在每日开盘时自动调用，也可手动触发。

    Args:
        instance_id: 实例ID(可选，不指定则重置全部)

    需要认证。
    """
    service.reset_daily_counters(instance_id)
    return {
        "success": True,
        "message": f"Daily counters reset for instance: {instance_id or 'all'}",
    }
