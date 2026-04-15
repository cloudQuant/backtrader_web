import logging
from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockHkIndexSpotSina(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HK_INDEX_SPOT_SINA"
        self.create_table_sql = """
            CREATE TABLE `STOCK_HK_INDEX_SPOT_SINA` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `INDEX_NAME` VARCHAR(100) COMMENT '指数名称',
                `LATEST_PRICE` DECIMAL(20, 4) COMMENT '最新价',
                `CHANGE_AMOUNT` DECIMAL(20, 4) COMMENT '涨跌额',
                `CHANGE_PERCENT` DECIMAL(10, 4) COMMENT '涨跌幅(%)',
                `PREV_CLOSE` DECIMAL(20, 4) COMMENT '昨收',
                `OPEN` DECIMAL(20, 4) COMMENT '今开',
                `HIGH` DECIMAL(20, 4) COMMENT '最高',
                `LOW` DECIMAL(20, 4) COMMENT '最低',
                `TRADE_DATE` DATE COMMENT '交易日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '新浪财经-港股' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE_DATE` (`INDEX_CODE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股指数实时行情表(新浪财经)';
        """

    def fetch_index_data(self):
        """Fetch Hong Kong index spot data from Sina Finance.

        Returns:
            pd.DataFrame: Processed DataFrame with index data or empty DataFrame on error
        """
        try:
            # 1. Fetch data from AKShare
            df = self.fetch_ak_data("stock_hk_index_spot_sina")

            if df is None or df.empty:
                self.logger.warning("No Hong Kong index data found from Sina")
                return pd.DataFrame()

            # 2. Rename and process columns
            df = df.rename(
                columns={
                    "代码": "INDEX_CODE",
                    "名称": "INDEX_NAME",
                    "最新价": "LATEST_PRICE",
                    "涨跌额": "CHANGE_AMOUNT",
                    "涨跌幅": "CHANGE_PERCENT",
                    "昨收": "PREV_CLOSE",
                    "今开": "OPEN",
                    "最高": "HIGH",
                    "最低": "LOW",
                }
            )

            # 3. Process numeric columns
            numeric_columns = [
                "LATEST_PRICE",
                "CHANGE_AMOUNT",
                "CHANGE_PERCENT",
                "PREV_CLOSE",
                "OPEN",
                "HIGH",
                "LOW",
            ]

            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 4. Add metadata columns
            trade_date = datetime.now().date()
            df["TRADE_DATE"] = trade_date
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["DATA_SOURCE"] = "新浪财经-港股"
            df["IS_ACTIVE"] = 1

            # 5. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "INDEX_NAME",
                "LATEST_PRICE",
                "CHANGE_AMOUNT",
                "CHANGE_PERCENT",
                "PREV_CLOSE",
                "OPEN",
                "HIGH",
                "LOW",
                "TRADE_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE", "TRADE_DATE"])

        except Exception as e:
            self.logger.error(
                f"Error fetching Hong Kong index data from Sina: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self):
        """Main method to run the data fetching and saving process.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info("Starting Hong Kong index spot data update")

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Fetch and process data
            df = self.fetch_index_data()

            if not df.empty:
                # Handle NaN values
                df = df.replace(np.nan, None)

                # Save data using INSERT ... ON DUPLICATE KEY UPDATE
                success = self.save_data(
                    df=df,
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["INDEX_CODE", "TRADE_DATE"],
                )

                if success:
                    self.logger.info(f"Successfully updated {len(df)} records in {self.table_name}")
                return success
            else:
                self.logger.warning("No data found to save")
                return False

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    try:
        fetcher = StockHkIndexSpotSina(logger=logger)
        success = fetcher.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
