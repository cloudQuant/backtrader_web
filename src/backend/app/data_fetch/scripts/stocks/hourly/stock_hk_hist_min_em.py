"""
Stock Hk Hist Min Em

数据源: AkShare
函数: stock_hk_hist_min_em
频率: hourly
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockHkHistMinEm(AkshareToMySql):
    """Stock Hk Hist Min Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HK_HIST_MIN_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_HK_HIST_MIN_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `period` VARCHAR(10) COMMENT '分钟周期',
            `时间` DATETIME COMMENT '交易时间',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_period_time (`symbol`, `period`, `时间`),
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Hk Hist Min Em'
    """

    @staticmethod
    def normalize_columns(
        df: pd.DataFrame, symbol: str | None = None, period: str | None = None
    ) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        for column in ("开盘", "收盘", "最高", "最低", "成交量", "成交额", "最新价"):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        if symbol is not None:
            df["symbol"] = str(symbol).strip()
            df["name"] = str(symbol).strip()
        elif "symbol" in df.columns:
            df["symbol"] = df["symbol"].astype(str).str.strip()
        if "name" in df.columns:
            df["name"] = df["name"].astype(str).str.strip()
        if period is not None:
            df["period"] = str(period).strip()
        if "时间" in df.columns:
            df["时间"] = pd.to_datetime(df["时间"], errors="coerce")
            df["data_date"] = df["时间"].dt.date
        if "data_date" not in df.columns:
            df["data_date"] = pd.Timestamp.now().date()
        return df.dropna(subset=["时间"]) if "时间" in df.columns else df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_hk_hist_min_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            symbol = kwargs.get("symbol")
            period = kwargs.get("period")
            df = self.fetch_ak_data("stock_hk_hist_min_em", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            df = self.normalize_columns(df, symbol=symbol, period=period)

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            if {"symbol", "data_date"}.issubset(df.columns):
                for symbol_value in sorted(df["symbol"].dropna().astype(str).unique()):
                    symbol_df = df[df["symbol"].astype(str) == symbol_value]
                    for data_date in sorted(symbol_df["data_date"].dropna().astype(str).unique()):
                        self.delete_data(
                            self.table_name,
                            {"symbol": symbol_value, "data_date": data_date},
                        )
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockHkHistMinEm()
    script.run()


if __name__ == "__main__":
    main()
