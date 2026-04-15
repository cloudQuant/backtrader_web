import argparse
import logging
import sys
from datetime import date

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class Option500ETFMinQVIX(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "OPTION_500ETF_MIN_QVIX"
        self.create_table_sql = """
            CREATE TABLE `OPTION_500ETF_MIN_QVIX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `TIME` TIME NOT NULL COMMENT '时间',
                `QVIX` DECIMAL(10, 6) COMMENT '波动率指数',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_TRADE_DATE_TIME` (`TRADE_DATE`, `TIME`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='500ETF期权波动率指数-分时数据';
        """

    def fetch_min_qvix_data(self):
        """
        Fetch 500ETF Option Volatility Index (QVIX) minute-level data

        Returns:
            DataFrame containing QVIX minute data with date and time
        """
        try:
            self.logger.info("Fetching 500ETF Option Volatility Index (QVIX) minute data")

            # Fetch data using parent class method
            df = self.fetch_ak_data("index_option_500etf_min_qvix")

            if df is None or df.empty:
                self.logger.warning("No 500ETF QVIX minute data found")
                return pd.DataFrame()

            # Get today's date
            trade_date = date.today()

            # Rename and process columns
            df = df.rename(columns={"time": "TIME_STR", "qvix": "QVIX"})

            # Process time and date
            df["TIME"] = pd.to_datetime(df["TIME_STR"], format="%H:%M:%S").dt.time
            df["TRADE_DATE"] = trade_date

            # Generate unique ID and add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "TRADE_DATE",
                "TIME",
                "QVIX",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["TRADE_DATE", "TIME"])

        except Exception as e:
            self.logger.error(f"Error fetching 500ETF QVIX minute data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self):
        """
        Main method to run the 500ETF QVIX minute data update

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Fetch data
            df = self.fetch_min_qvix_data()
            if df.empty:
                self.logger.error("No 500ETF QVIX minute data to save")
                return False

            # Get today's date
            today = date.today()

            # # Delete existing data for today if any
            # self.execute_sql(
            #     f"DELETE FROM {self.table_name} WHERE TRADE_DATE = %s",
            #     (today,)
            # )
            #
            # Save new data
            if not df.empty:
                self.save_data(
                    df=df.replace({np.nan: None}),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["TRADE_DATE", "TIME"],
                )
                self.logger.info(f"Saved {len(df)} 500ETF QVIX minute records for {today}")

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
    parser = argparse.ArgumentParser(
        description="Update 500ETF Option Volatility Index (QVIX) minute data"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = Option500ETFMinQVIX(logger=logger)
        success = fetcher.run()
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
