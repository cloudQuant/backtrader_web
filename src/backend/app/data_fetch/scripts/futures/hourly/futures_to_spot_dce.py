"""
Futures To Spot Dce

数据源: AkShare
函数: futures_to_spot_dce
频率: hourly
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesToSpotDce(AkshareToMySql):
    """Futures To Spot Dce"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_TO_SPOT_DCE"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `FUTURES_TO_SPOT_DCE` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `合约代码` VARCHAR(50) COMMENT '合约代码',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date_contract (`symbol`, `data_date`, `合约代码`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Futures To Spot Dce'
    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.futures_to_spot_dce

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            month_list = (
                [str(kwargs["date"])]
                if "date" in kwargs
                else [
                    self.get_current_month(),
                    self.get_previous_month(),
                ]
            )

            for month in month_list:
                call_kwargs = dict(kwargs)
                call_kwargs["date"] = month
                df = self.fetch_ak_data("futures_to_spot_dce", **call_kwargs)

                if df is None or df.empty:
                    self.logger.warning(f"No data found for {month}")
                    continue

                if "data_date" not in df.columns:
                    if "期转现发生日期" in df.columns:
                        df["data_date"] = pd.to_datetime(
                            df["期转现发生日期"], errors="coerce"
                        ).dt.date
                    else:
                        df["data_date"] = pd.to_datetime(f"{month}01").date()

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

    script = FuturesToSpotDce()
    script.fetch_data()


if __name__ == "__main__":
    main()
