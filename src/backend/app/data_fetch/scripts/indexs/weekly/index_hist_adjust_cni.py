import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexHistAdjustCNI(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_HIST_ADJUST_CNI"
        self.create_table_sql = """
            CREATE TABLE `INDEX_HIST_ADJUST_CNI` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `START_DATE` DATE NOT NULL COMMENT '开始日期',
                `END_DATE` DATE COMMENT '结束日期',
                `STOCK_CODE` VARCHAR(20) NOT NULL COMMENT '样本代码',
                `STOCK_NAME` VARCHAR(100) COMMENT '样本简称',
                `INDUSTRY` VARCHAR(100) COMMENT '所属行业',
                `ADJUST_TYPE` VARCHAR(10) COMMENT '调整类型',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '国证指数' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_STOCK_DATES` (`INDEX_CODE`, `STOCK_CODE`, `START_DATE`),
                KEY `IDX_INDEX_CODE` (`INDEX_CODE`),
                KEY `IDX_STOCK_CODE` (`STOCK_CODE`),
                KEY `IDX_START_DATE` (`START_DATE`),
                KEY `IDX_END_DATE` (`END_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国证指数历史调样数据';
        """

    def fetch_hist_adjust_data(self, symbol):
        """
        Fetch historical adjustment data for an index from CNI

        Args:
            symbol: Index code, e.g., '399005' for SME Index

        Returns:
            DataFrame containing historical adjustment data
        """
        try:
            self.logger.info(f"Fetching historical adjustment data for index {symbol}")

            # Fetch data using parent class method
            df = self.fetch_ak_data("index_detail_hist_adjust_cni", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No historical adjustment data found for index {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "开始日期": "START_DATE",
                    "结束日期": "END_DATE",
                    "样本代码": "STOCK_CODE",
                    "样本简称": "STOCK_NAME",
                    "所属行业": "INDUSTRY",
                    "调整类型": "ADJUST_TYPE",
                }
            )
            # print(df)
            # Process dates
            for date_col in ["START_DATE", "END_DATE"]:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date

            # Generate unique ID and add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["INDEX_CODE"] = symbol
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "国证指数"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "START_DATE",
                "END_DATE",
                "STOCK_CODE",
                "STOCK_NAME",
                "INDUSTRY",
                "ADJUST_TYPE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates()

        except Exception as e:
            self.logger.error(
                f"Error fetching historical adjustment data for {symbol}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, symbol=None):
        """
        Main method to run the historical adjustment data update

        Args:
            symbol: Index code (e.g., '399005')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not symbol:
                # Get all index codes if not specified
                df = self.get_data_by_columns("INDEX_ALL_CNI_DAILY", ["INDEX_CODE"])
                symbol_list = list(df["INDEX_CODE"].unique())
            else:
                symbol_list = [symbol]

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            success = True
            for symbol in symbol_list:
                # Fetch and save data
                df = self.fetch_hist_adjust_data(symbol)
                if not df.empty:
                    # Save new data
                    self.save_data(
                        df=df.replace(np.nan, None),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDEX_CODE", "STOCK_CODE", "START_DATE"],
                    )
                    self.logger.info(
                        f"Saved {len(df)} historical adjustment records for index {symbol}"
                    )
                else:
                    self.logger.warning(f"No historical adjustment data found for index {symbol}")

            return success

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Update CNI index historical adjustment data")
    parser.add_argument("--symbol", help="Index code (e.g., 399005)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = IndexHistAdjustCNI(logger=logger)
        success = fetcher.run(symbol=args.symbol)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
