"""
Stock Cash Flow Sheet By Report Delisted StockCashFlowSheetByReportDelistedEm

数据源: AkShare
函数: stock_cash_flow_sheet_by_report_delisted_em
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockCashFlowSheetByReportDelistedEm(AkshareToMySql):
    """Stock Cash Flow Sheet By Report Delisted StockCashFlowSheetByReportDelistedEm"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_CASH_FLOW_SHEET_BY_REPORT_DELISTED_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_CASH_FLOW_SHEET_BY_REPORT_DELISTED_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Cash Flow Sheet By Report Delisted StockCashFlowSheetByReportDelistedEm'
    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_cash_flow_sheet_by_report_delisted_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("stock_cash_flow_sheet_by_report_delisted_em", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            if "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockCashFlowSheetByReportDelistedEm()
    script.run()


if __name__ == "__main__":
    main()
