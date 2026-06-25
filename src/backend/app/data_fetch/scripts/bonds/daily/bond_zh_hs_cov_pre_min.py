"""
Bond Zh Hs Cov Pre Min

数据源: AkShare
函数: bond_zh_hs_cov_pre_min
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class BondZhHsCovPreMin(AkshareToMySql):
    """Bond Zh Hs Cov Pre Min"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "BOND_ZH_HS_COV_PRE_MIN"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `BOND_ZH_HS_COV_PRE_MIN` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `时间` DATETIME COMMENT '交易时间',
            `开盘` DOUBLE COMMENT '开盘',
            `收盘` DOUBLE COMMENT '收盘',
            `最高` DOUBLE COMMENT '最高',
            `最低` DOUBLE COMMENT '最低',
            `成交量` BIGINT COMMENT '成交量',
            `成交额` DOUBLE COMMENT '成交额',
            `最新价` DOUBLE COMMENT '最新价',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_time (`symbol`, `时间`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bond Zh Hs Cov Pre Min'
    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.bond_zh_hs_cov_pre_min

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            kwargs.setdefault("symbol", "sh113693")
            kwargs.setdefault("_call_timeout", 30)
            # Fetch data from AkShare
            df = self.fetch_ak_data("bond_zh_hs_cov_pre_min", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            if "时间" in df.columns:
                df["时间"] = pd.to_datetime(df["时间"], errors="coerce")
                df = df.dropna(subset=["时间"]).drop_duplicates(subset=["时间"])
                df["data_date"] = df["时间"].dt.date
            elif "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()
            if "symbol" not in df.columns:
                df["symbol"] = str(kwargs.get("symbol") or "sh113693")
            if "name" not in df.columns:
                df["name"] = str(kwargs.get("symbol") or "sh113693")

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["symbol", "时间"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = BondZhHsCovPreMin()
    script.run()


if __name__ == "__main__":
    main()
