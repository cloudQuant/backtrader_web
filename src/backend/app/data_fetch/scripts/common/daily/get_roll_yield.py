"""
Get Roll Yield

数据源: AkShare
函数: get_roll_yield
频率: daily
"""

from datetime import datetime, timedelta

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


PREFER_LOCAL_SCRIPT = True
DEFAULT_VAR = "CU"
DEFAULT_LOOKBACK_DAYS = 14


class GetRollYield(AkshareToMySql):
    """Get Roll Yield"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "GET_ROLL_YIELD"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `GET_ROLL_YIELD` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `roll_yield` DOUBLE COMMENT '展期收益率',
            `near_by` VARCHAR(50) COMMENT '近月合约',
            `deferred` VARCHAR(50) COMMENT '远月合约',
            `var` VARCHAR(50) COMMENT '品种',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Get Roll Yield'
    """

    @staticmethod
    def _format_date_yyyymmdd(value):
        return pd.to_datetime(str(value), errors="raise").strftime("%Y%m%d")

    @staticmethod
    def _format_date_iso(value):
        return pd.to_datetime(str(value), errors="raise").strftime("%Y-%m-%d")

    @staticmethod
    def _date_candidates(date, current_date, lookback_days):
        if date is not None:
            return [GetRollYield._format_date_yyyymmdd(date)]

        current = datetime.strptime(current_date.replace("-", ""), "%Y%m%d").date()
        return [
            (current - timedelta(days=offset)).strftime("%Y%m%d")
            for offset in range(int(lookback_days or 0) + 1)
        ]

    @staticmethod
    def _normalize_roll_yield_result(result, var, date):
        if result is None or result is False:
            return pd.DataFrame()
        if isinstance(result, pd.DataFrame):
            return result
        if not isinstance(result, tuple) or len(result) != 3:
            return pd.DataFrame()

        roll_yield, near_by, deferred = result
        if roll_yield is None or near_by is None or deferred is None:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "symbol": str(var).upper(),
                    "name": f"{near_by}/{deferred}",
                    "data_date": GetRollYield._format_date_iso(date),
                    "roll_yield": float(roll_yield),
                    "near_by": near_by,
                    "deferred": deferred,
                    "var": str(var).upper(),
                }
            ]
        )

    def fetch_data(
        self,
        date=None,
        var=DEFAULT_VAR,
        symbol1=None,
        symbol2=None,
        lookback_days=DEFAULT_LOOKBACK_DAYS,
        **kwargs,
    ):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.get_roll_yield

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            df = pd.DataFrame()
            call_kwargs = dict(kwargs)
            if symbol1 is not None:
                call_kwargs["symbol1"] = symbol1
            if symbol2 is not None:
                call_kwargs["symbol2"] = symbol2

            for candidate_date in self._date_candidates(
                date, self.get_current_date(), lookback_days
            ):
                result = self.fetch_ak_data(
                    "get_roll_yield",
                    date=candidate_date,
                    var=str(var).upper(),
                    **call_kwargs,
                )
                df = self._normalize_roll_yield_result(result, var=var, date=candidate_date)
                if not df.empty:
                    break

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Save to database
            self.create_table_if_not_exists(
                self.table_name, getattr(self, "create_table_sql", None)
            )
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()

    def run(self, **kwargs):
        return self.fetch_data(**kwargs)


def main():
    """Main function to run the data fetch"""

    script = GetRollYield()
    script.run()


if __name__ == "__main__":
    main()
