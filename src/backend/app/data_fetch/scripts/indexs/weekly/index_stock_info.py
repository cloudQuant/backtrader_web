import logging

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexStockInfo(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_STOCK_INFO"
        self.create_table_sql = """
            CREATE TABLE `INDEX_STOCK_INFO` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `DISPLAY_NAME` VARCHAR(100) NOT NULL COMMENT '指数名称',
                `PUBLISH_DATE` DATE COMMENT '发布日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'AKShare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE` (`INDEX_CODE`),
                KEY `IDX_DISPLAY_NAME` (`DISPLAY_NAME`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票指数信息表';
        """

    def parse_date(self, date_str):
        """Parse date string to date object with error handling"""
        try:
            if pd.isna(date_str) or not date_str or not str(date_str).strip():
                return None
            date_str = str(date_str).strip()
            return pd.to_datetime(date_str, errors="coerce").date()
        except Exception as e:
            self.logger.warning(f"Error parsing date {date_str}: {e}")
            return None

    def fetch_index_info(self):
        """Fetch index information from AKShare"""
        try:
            self.logger.info("Fetching index stock info from AKShare")
            df = self.fetch_ak_data("index_stock_info")

            if df is None or df.empty:
                self.logger.warning("No index information found")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "index_code": "INDEX_CODE",
                    "display_name": "DISPLAY_NAME",
                    "publish_date": "PUBLISH_DATE_STR",
                }
            )

            # Process dates and add metadata
            df["PUBLISH_DATE"] = df["PUBLISH_DATE_STR"].apply(self.parse_date)
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["DATA_SOURCE"] = "AKShare"
            df["IS_ACTIVE"] = 1

            # Select and return final columns
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "DISPLAY_NAME",
                "PUBLISH_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE"])

        except Exception as e:
            self.logger.error(f"Error fetching index information: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self):
        """Main method to run the index information update"""
        try:
            self.logger.info("Starting index information update")

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Fetch and save data
            df = self.fetch_index_info()
            if not df.empty:
                return self.save_data(
                    df=df.replace(np.nan, None),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["INDEX_NAME"],
                )

            self.logger.warning("No data to process")
            return False

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():
    import argparse
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Update stock index information")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = IndexStockInfo(logger=logger)
        success = fetcher.run()
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
