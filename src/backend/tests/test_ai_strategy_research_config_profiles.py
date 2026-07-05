from __future__ import annotations

import pytest

from app.schemas.ai_strategy_research import (
    AIStrategyResearchConfigProfileCreate,
    AIStrategyResearchConfigProfileUpdate,
)
from app.services.ai_strategy_research_config_profiles import (
    AIStrategyResearchConfigProfileService,
)


@pytest.mark.asyncio
async def test_ai_strategy_research_config_profiles_crud_round_trip(tmp_path):
    service = AIStrategyResearchConfigProfileService(tmp_path / "profiles.yaml")

    created = await service.create_profile(
        AIStrategyResearchConfigProfileCreate(
            id="daily-a-share",
            name="A股日线",
            description="daily profile",
            config={
                "symbol": "000001.SZ",
                "target_sharpe": 1.2,
                "use_max_drawdown_limit": True,
                "max_drawdown_limit": 15,
            },
        )
    )

    assert created.id == "daily-a-share"
    listed = await service.list_profiles()
    assert listed.total == 1
    assert listed.items[0].config["symbol"] == "000001.SZ"

    updated = await service.update_profile(
        "daily-a-share",
        AIStrategyResearchConfigProfileUpdate(
            name="A股日线稳健",
            config={"symbol": "600519.SH", "target_sharpe": 1.5},
        ),
    )

    assert updated is not None
    assert updated.name == "A股日线稳健"
    assert updated.config["symbol"] == "600519.SH"

    assert await service.delete_profile("daily-a-share") is True
    assert (await service.list_profiles()).items == []


@pytest.mark.asyncio
async def test_ai_strategy_research_config_profiles_imports_profile_yaml(tmp_path):
    service = AIStrategyResearchConfigProfileService(tmp_path / "profiles.yaml")

    imported = await service.import_profiles(
        """
id: futures-hourly
name: 期货小时线
description: imported profile
config:
  symbol: IF2409.CFE
  timeframe: 1h
  target_sharpe: 1.1
  out_of_sample_validation: true
""",
    )

    assert imported.total == 1
    assert imported.items[0].id == "futures-hourly"
    listed = await service.list_profiles()
    assert listed.items[0].config["timeframe"] == "1h"


@pytest.mark.asyncio
async def test_ai_strategy_research_config_profiles_imports_inline_yaml(tmp_path):
    service = AIStrategyResearchConfigProfileService(tmp_path / "profiles.yaml")

    imported = await service.import_profiles(
        """
symbol: 000300.SH
timeframe: 1d
target_sharpe: 0.9
""",
        fallback_name="沪深300日线",
    )

    assert imported.total == 1
    profile = imported.items[0]
    assert profile.name == "沪深300日线"
    assert profile.config["symbol"] == "000300.SH"
    assert profile.config["target_sharpe"] == 0.9
