"""Built-in stress test scenario definitions."""

from app.schemas.risk_analytics import StressScenario

BUILT_IN_STRESS_SCENARIOS: tuple[StressScenario, ...] = (
    StressScenario(
        id="china_crash_2015_06",
        name="2015-06 中国股灾",
        start_date="2015-06-12",
        end_date="2015-08-26",
    ),
    StressScenario(
        id="global_selloff_2018_q4",
        name="2018-Q4 全球股市暴跌",
        start_date="2018-10-01",
        end_date="2018-12-31",
    ),
    StressScenario(
        id="covid_2020_03",
        name="2020-03 COVID 黑天鹅",
        start_date="2020-02-20",
        end_date="2020-03-31",
    ),
    StressScenario(
        id="crypto_winter_2022_11",
        name="2022-11 加密寒冬",
        start_date="2022-11-01",
        end_date="2022-11-30",
    ),
    StressScenario(
        id="jpy_carry_unwind_2024_08",
        name="2024-08 日元 carry trade 反转",
        start_date="2024-08-01",
        end_date="2024-08-15",
    ),
)
