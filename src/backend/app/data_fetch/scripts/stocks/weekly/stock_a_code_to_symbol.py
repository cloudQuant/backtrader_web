"""
Stock A Code To Symbol

数据源: AkShare
函数: stock_a_code_to_symbol
频率: weekly
"""

from datetime import date
from typing import Any

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

PREFER_LOCAL_SCRIPT = True


class StockACodeToSymbol(AkshareToMySql):
    """Stock A Code To Symbol"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_A_CODE_TO_SYMBOL"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_A_CODE_TO_SYMBOL` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock A Code To Symbol'
    """

    @staticmethod
    def normalize_code_to_symbol(
        result: Any, source_code: str | None = None, data_date: date | None = None
    ) -> pd.DataFrame:
        """Normalize AkShare's scalar code-to-symbol response to this table schema."""
        if isinstance(result, pd.DataFrame):
            df = result.copy()
        elif result is None:
            return pd.DataFrame(columns=["symbol", "name", "data_date"])
        else:
            value = str(result).strip()
            if not value:
                return pd.DataFrame(columns=["symbol", "name", "data_date"])
            df = pd.DataFrame(
                [
                    {
                        "symbol": source_code or "",
                        "name": value,
                    }
                ]
            )

        if "symbol" not in df.columns and source_code is not None:
            df["symbol"] = source_code
        if "name" not in df.columns and len(df.columns) == 1:
            df = df.rename(columns={df.columns[0]: "name"})
        if "data_date" not in df.columns:
            df["data_date"] = data_date or pd.Timestamp.now().date()

        return df[["symbol", "name", "data_date"]]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_a_code_to_symbol

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            source_code = str(kwargs.get("symbol", "000300"))
            # Fetch data from AkShare
            result = self.fetch_ak_data("stock_a_code_to_symbol", **kwargs)
            df = self.normalize_code_to_symbol(result, source_code=source_code)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockACodeToSymbol()
    script.run()


if __name__ == "__main__":
    main()
