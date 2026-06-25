"""
Stock Hsgt Individual Detail Em

数据源: AkShare
函数: stock_hsgt_individual_detail_em
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockHsgtIndividualDetailEm(AkshareToMySql):
    """Stock Hsgt Individual Detail Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HSGT_INDIVIDUAL_DETAIL_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_HSGT_INDIVIDUAL_DETAIL_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `institution_name` VARCHAR(150) COMMENT '机构名称',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_institution_date (`institution_name`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Hsgt Individual Detail Em'
    """

    @staticmethod
    def normalize_columns(df: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        df["symbol"] = str(symbol)
        if "机构名称" in df.columns:
            df["institution_name"] = df["机构名称"].astype(str).str.strip()
            df["name"] = df["institution_name"]
        else:
            df["name"] = str(symbol)
        if "持股日期" in df.columns:
            df["data_date"] = pd.to_datetime(df["持股日期"], errors="coerce").dt.date
        elif "data_date" not in df.columns:
            df["data_date"] = pd.Timestamp.now().date()
        front_columns = ["symbol", "name", "data_date", "institution_name"]
        ordered = [col for col in front_columns if col in df.columns]
        ordered.extend(col for col in df.columns if col not in ordered)
        return df[ordered]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_hsgt_individual_detail_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("stock_hsgt_individual_detail_em", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            symbol = str(kwargs.get("symbol", "002008"))
            df = self.normalize_columns(df, symbol=symbol)

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            for data_date in sorted(df["data_date"].dropna().astype(str).unique()):
                self.delete_data(self.table_name, {"symbol": symbol, "data_date": data_date})
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockHsgtIndividualDetailEm()
    script.run()


if __name__ == "__main__":
    main()
