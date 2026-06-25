"""
Macro China Retail Price Index

数据源: AkShare
函数: macro_china_retail_price_index
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql
from app.data_fetch.scripts.common.daily._sina_macro import fetch_sina_macro_pages


class MacroChinaRetailPriceIndex(AkshareToMySql):
    """Macro China Retail Price Index"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MACRO_CHINA_RETAIL_PRICE_INDEX"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `MACRO_CHINA_RETAIL_PRICE_INDEX` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Macro China Retail Price Index'
    """

    @staticmethod
    def _parse_month(series: pd.Series) -> pd.Series:
        return pd.to_datetime(series.astype(str), format="%Y.%m", errors="coerce").dt.date

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.macro_china_retail_price_index

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            kwargs.pop("_call_timeout", None)
            max_pages = kwargs.pop("max_pages", None)
            df = fetch_sina_macro_pages(
                callback="SINAREMOTECALLCALLBACK1601651495761",
                cate="price",
                event="12",
                data_path=("data",),
                max_pages=max_pages,
            )

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = df.copy()
            df.sort_values(by=["统计月份"], ignore_index=True, inplace=True)
            df["零售商品价格指数"] = pd.to_numeric(df["零售商品价格指数"], errors="coerce")
            df["symbol"] = df["居民消费项目"].astype(str)
            df["name"] = df["居民消费项目"].astype(str)
            df["data_date"] = self._parse_month(df["统计月份"])
            df["data_date"] = df["data_date"].fillna(pd.Timestamp.now().date())

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["symbol", "data_date"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = MacroChinaRetailPriceIndex()
    script.run()


if __name__ == "__main__":
    main()
