"""
Macro China Swap Rate

数据源: AkShare
函数: macro_china_swap_rate
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class MacroChinaSwapRate(AkshareToMySql):
    """Macro China Swap Rate"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MACRO_CHINA_SWAP_RATE"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `MACRO_CHINA_SWAP_RATE` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `日期` DATE COMMENT '曲线日期',
            `曲线名称` VARCHAR(100) COMMENT '曲线名称',
            `时刻` VARCHAR(50) COMMENT '报价时刻',
            `价格类型` VARCHAR(50) COMMENT '价格类型',
            `1M` DOUBLE COMMENT '1月利率',
            `3M` DOUBLE COMMENT '3月利率',
            `6M` DOUBLE COMMENT '6月利率',
            `9M` DOUBLE COMMENT '9月利率',
            `1Y` DOUBLE COMMENT '1年利率',
            `2Y` DOUBLE COMMENT '2年利率',
            `3Y` DOUBLE COMMENT '3年利率',
            `4Y` DOUBLE COMMENT '4年利率',
            `5Y` DOUBLE COMMENT '5年利率',
            `7Y` DOUBLE COMMENT '7年利率',
            `10Y` DOUBLE COMMENT '10年利率',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_curve_quote (`日期`, `曲线名称`, `时刻`, `价格类型`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Macro China Swap Rate'
    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.macro_china_swap_rate

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("macro_china_swap_rate", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            if "日期" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
                df["data_date"] = df["日期"]
            elif "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()

            for column in ["1M", "3M", "6M", "9M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y"]:
                if column in df.columns:
                    df[column] = pd.to_numeric(df[column], errors="coerce")

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = MacroChinaSwapRate()
    script.fetch_data()


if __name__ == "__main__":
    main()
