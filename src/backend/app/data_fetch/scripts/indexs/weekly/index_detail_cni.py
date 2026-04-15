import argparse
import logging
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexDetailCNI(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_DETAIL_CNI"
        self.create_table_sql = """
                    CREATE TABLE `INDEX_DETAIL_CNI` (
                        `R_ID` VARCHAR(50) PRIMARY KEY,
                        `TRADE_DATE` DATE NOT NULL COMMENT '日期',
                        `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                        `STOCK_CODE` VARCHAR(20) NOT NULL COMMENT '样本代码',
                        `STOCK_NAME` VARCHAR(100) COMMENT '样本简称',
                        `INDUSTRY` VARCHAR(100) COMMENT '所属行业',
                        `TOTAL_MARKET_CAP` DECIMAL(20, 2) COMMENT '总市值(亿元)',
                        `WEIGHT` DECIMAL(10, 6) COMMENT '权重(%)',
                        `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                        `DATA_SOURCE` VARCHAR(50) DEFAULT '国证指数' COMMENT '数据来源',
                        `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                        `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                        `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                        `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                        UNIQUE KEY `IDX_DATE_INDEX_STOCK` (`TRADE_DATE`, `INDEX_CODE`, `STOCK_CODE`),
                        KEY `IDX_INDEX_CODE` (`INDEX_CODE`),
                        KEY `IDX_STOCK_CODE` (`STOCK_CODE`),
                        KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                        KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国证指数样本详情';
                """

    # Update the fetch_index_detail method
    def fetch_index_detail(self, symbol, date=None):
        """
        Fetch index constituent details from CNI

        Args:
            symbol: Index code, e.g., '399001' for SME Index
            date: Date in 'YYYYMM' format, if None, use current month

        Returns:
            DataFrame containing index constituent details
        """
        try:
            # Set default date if not provided
            date = date or datetime.now().strftime("%Y%m")

            self.logger.info(f"Fetching index detail for {symbol} in {date}")

            # Fetch data using parent class method
            df = self.fetch_ak_data("index_detail_cni", symbol=symbol, date=date)

            if df is None or df.empty:
                self.logger.warning(f"No detail data found for index {symbol} in {date}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE_STR",
                    "样本代码": "STOCK_CODE",
                    "样本简称": "STOCK_NAME",
                    "所属行业": "INDUSTRY",
                    "总市值": "TOTAL_MARKET_CAP",
                    "权重": "WEIGHT",
                }
            )

            # Process dates and numeric values
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE_STR"], errors="coerce").dt.date
            df["TRADE_DATE"] = df["TRADE_DATE"].fillna(datetime.now().date())

            # Process numeric columns
            numeric_columns = ["TOTAL_MARKET_CAP", "WEIGHT"]
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Generate unique ID and add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["INDEX_CODE"] = symbol
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "国证指数"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "TRADE_DATE",
                "INDEX_CODE",
                "STOCK_CODE",
                "STOCK_NAME",
                "INDUSTRY",
                "TOTAL_MARKET_CAP",
                "WEIGHT",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates()

        except Exception as e:
            self.logger.error(f"Error fetching index detail for {symbol}: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def generate_date_range(self, start_date=None, end_date=None):
        """
        Generate a list of dates in 'YYYYMM' format from start_date to end_date (inclusive)

        Args:
            start_date: Start date in 'YYYYMM' format (default: '200501' for January 2005)
            end_date: End date in 'YYYYMM' format (default: previous month)

        Returns:
            List of dates in 'YYYYMM' format
        """
        # Set default values if not provided
        end_date = end_date or (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y%m")
        if start_date is None:
            start_date_str = "201001"  # January 2005
        else:
            start_date_str = start_date

        # Convert to datetime objects
        start = datetime.strptime(start_date_str, "%Y%m")
        end = datetime.strptime(end_date, "%Y%m")

        # Generate all months between start and end (inclusive)
        date_list = []
        current = start
        while current <= end:
            date_list.append(current.strftime("%Y%m"))
            # Move to first day of next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return date_list

    def run(self, symbol=None, date=None, start_date=None, end_date=None):
        """
        Main method to run the index detail update

        Args:
            symbol: Index code (e.g., '399001')
            date: Specific date in 'YYYYMM' format (if provided, overrides date range)
            start_date: Start date in 'YYYYMM' format (default: '200501' for January 2005)
            end_date: End date in 'YYYYMM' format (default: previous month)

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

            # Generate date list
            if date:
                # Single date mode
                date_list = [date]
            else:
                # Date range mode
                date_list = self.generate_date_range(start_date, end_date)
                self.logger.info(f"Processing {len(date_list)} months of data")

            success = True
            for symbol in symbol_list:
                for process_date in date_list:
                    # Fetch and save data
                    df = self.fetch_index_detail(symbol, process_date)
                    if not df.empty:
                        self.save_data(
                            df.replace(np.nan, None),
                            self.table_name,
                            on_duplicate_update=True,
                            unique_keys=["TRADE_DATE", "INDEX_CODE"],
                        )
                    else:
                        self.logger.warning(f"No data found for index {symbol} in {process_date}")

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
    parser = argparse.ArgumentParser(description="Update CNI index constituent details")
    parser.add_argument("--symbol", help="Index code (e.g., 399001)")
    parser.add_argument("--date", help="Specific date in YYYYMM format (overrides date range)")
    parser.add_argument("--start-date", help="Start date in YYYYMM format (default: 200501)")
    parser.add_argument("--end-date", help="End date in YYYYMM format (default: previous month)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = IndexDetailCNI(logger=logger)
        success = fetcher.run(
            symbol=args.symbol,
            date=args.date,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
