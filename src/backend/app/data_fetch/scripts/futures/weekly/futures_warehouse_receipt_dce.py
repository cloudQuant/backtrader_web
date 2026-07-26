"""
Futures Warehouse Receipt Dce

数据源: AkShare
函数: futures_warehouse_receipt_dce
频率: weekly
"""

from datetime import datetime, timedelta

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesWarehouseReceiptDce(AkshareToMySql):
    """Futures Warehouse Receipt Dce"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_WAREHOUSE_RECEIPT_DCE"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `FUTURES_WAREHOUSE_RECEIPT_DCE` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Futures Warehouse Receipt Dce'
    """

    def _candidate_dce_trade_dates(self, max_days: int = 5) -> list[str]:
        end_date = self.get_current_date()
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=14)).strftime(
            "%Y-%m-%d"
        )
        try:
            trading_days = self.get_trading_day_list(start_date, end_date, exchange="DCE")
        except Exception as exc:
            self.logger.warning(f"获取大商所交易日失败，改用境内交易日历: {exc}")
            try:
                trading_days = self.get_trading_day_list(start_date, end_date, exchange="XSHG")
            except Exception as fallback_exc:
                self.logger.warning(f"获取境内交易日失败，使用工作日回退: {fallback_exc}")
                trading_days = []
        if not trading_days:
            trading_days = [
                (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=offset)).strftime(
                    "%Y-%m-%d"
                )
                for offset in range(0, 14)
                if (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=offset)).weekday() < 5
            ]
        trading_days = sorted(trading_days)
        return [item.replace("-", "") for item in trading_days[-max_days:]][::-1]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.futures_warehouse_receipt_dce

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            date_list = (
                [str(kwargs["date"]).replace("-", "")]
                if "date" in kwargs
                else (self._candidate_dce_trade_dates())
            )

            for date_str in date_list:
                call_kwargs = dict(kwargs)
                call_kwargs["date"] = date_str
                df = self.fetch_ak_data("futures_warehouse_receipt_dce", **call_kwargs)

                if df is None or df.empty:
                    self.logger.warning(f"No data found for {date_str}")
                    continue

                if "data_date" not in df.columns:
                    df["data_date"] = pd.to_datetime(date_str).date()
                if "symbol" not in df.columns and "品种代码" in df.columns:
                    df["symbol"] = df["品种代码"]

                self.create_table_if_not_exists(self.table_name, self.create_table_sql)
                self.save_data(df, self.table_name, ignore_duplicates=True)

                return df

            self.logger.warning("No data found")
            return pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = FuturesWarehouseReceiptDce()
    script.fetch_data()


if __name__ == "__main__":
    main()
