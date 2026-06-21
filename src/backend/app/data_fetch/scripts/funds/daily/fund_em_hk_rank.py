"""
Fund Em Hk Rank

数据源: AkShare
函数: fund_em_hk_rank
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundEmHkRank(AkshareToMySql):
    """Fund Em Hk Rank"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_EM_HK_RANK"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `FUND_EM_HK_RANK` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Fund Em Hk Rank'
    """

    @staticmethod
    def normalize_rank_data(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["symbol", "name", "data_date"])

        required_columns = {"基金代码", "基金简称", "日期"}
        if not required_columns.issubset(df.columns):
            return pd.DataFrame(columns=["symbol", "name", "data_date"])

        normalized = df[["基金代码", "基金简称", "日期"]].copy()
        normalized.rename(
            columns={
                "基金代码": "symbol",
                "基金简称": "name",
                "日期": "data_date",
            },
            inplace=True,
        )
        normalized["data_date"] = pd.to_datetime(
            normalized["data_date"], errors="coerce"
        ).dt.date
        normalized.dropna(subset=["symbol", "data_date"], inplace=True)
        return normalized

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.fund_em_hk_rank

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("fund_em_hk_rank", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = self.normalize_rank_data(df)
            if df.empty:
                self.logger.warning("No normalized Hong Kong fund rank data found")
                return pd.DataFrame()

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

    script = FundEmHkRank()
    script.run()


if __name__ == "__main__":
    main()
