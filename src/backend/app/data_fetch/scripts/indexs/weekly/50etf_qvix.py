import argparse
import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class Option50ETFQVIX(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "OPTION_50ETF_QVIX"
        self.create_table_sql = """
            CREATE TABLE `OPTION_50ETF_QVIX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(10, 6) COMMENT '开盘价',
                `HIGH` DECIMAL(10, 6) COMMENT '最高价',
                `LOW` DECIMAL(10, 6) COMMENT '最低价',
                `CLOSE` DECIMAL(10, 6) COMMENT '收盘价',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='50ETF期权波动率指数(QVIX)';
        """

    def fetch_qvix_data(self):
        """
        Fetch 50ETF Option Volatility Index (QVIX) data

        Returns:
            DataFrame containing QVIX data
        """
        try:
            self.logger.info("Fetching 50ETF Option Volatility Index (QVIX) data")

            # Fetch data directly (akshare function broken with pandas 3.0)
            url = "http://1.optbbs.com/d/csv/d/k.csv"
            raw_df = pd.read_csv(url, encoding="gbk")
            df = raw_df.iloc[:, :5].copy()
            df.columns = ["date", "open", "high", "low", "close"]
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            if df is None or df.empty:
                self.logger.warning("No QVIX data found")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "date": "TRADE_DATE_STR",
                    "open": "OPEN",
                    "high": "HIGH",
                    "low": "LOW",
                    "close": "CLOSE",
                }
            )

            # Process date
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE_STR"], errors="coerce").dt.date
            df["TRADE_DATE"] = df["TRADE_DATE"].fillna(datetime.now().date())

            # Generate unique ID and add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "TRADE_DATE",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].sort_values("TRADE_DATE").drop_duplicates()

        except Exception as e:
            self.logger.error(f"Error fetching QVIX data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, update_all=False):
        """
        Main method to run the QVIX data update

        Args:
            update_all: If True, update all historical data; if False, update only the latest data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Fetch data
            df = self.fetch_qvix_data()
            if df.empty:
                self.logger.error("No QVIX data to save")
                return False

            # # If not updating all, get the latest date from DB and filter new data
            # if not update_all:
            #     latest_date = self.get_latest_date(self.table_name, 'TRADE_DATE')
            #     if latest_date:
            #         df = df[df['TRADE_DATE'] > latest_date]
            #         if df.empty:
            #             self.logger.info("No new QVIX data to update")
            #             return True

            # Save data
            if not df.empty:
                self.save_data(
                    df=df.replace({np.nan: None}),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["TRADE_DATE"],
                )
                self.logger.info(f"Saved {len(df)} QVIX records")

            return True

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
    parser = argparse.ArgumentParser(description="Update 50ETF Option Volatility Index (QVIX) data")
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = Option50ETFQVIX(logger=logger)
        success = fetcher.run(update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
