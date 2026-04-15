import argparse
import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexDailyMarketCNI(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_DAILY_MARKET_CNI"
        self.create_table_sql = """
            CREATE TABLE `INDEX_DAILY_MARKET_CNI` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `OPEN_PRICE` DECIMAL(18, 4) COMMENT '开盘价',
                `HIGH_PRICE` DECIMAL(18, 4) COMMENT '最高价',
                `LOW_PRICE` DECIMAL(18, 4) COMMENT '最低价',
                `CLOSE_PRICE` DECIMAL(18, 4) COMMENT '收盘价',
                `CHANGE_PCT` DECIMAL(10, 6) COMMENT '涨跌幅(%)',
                `VOLUME` DECIMAL(20, 2) COMMENT '成交量(万手)',
                `TURNOVER` DECIMAL(20, 2) COMMENT '成交额(亿元)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '国证指数' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_DATE_INDEX` (`TRADE_DATE`, `INDEX_CODE`),
                KEY `IDX_INDEX_CODE` (`INDEX_CODE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国证指数日行情数据';
        """

    def fetch_index_market_data(self, symbol, start_date=None, end_date=None):
        """
        Fetch index market data from CNI

        Args:
            symbol: Index code, e.g., '399005' for Small and Medium Enterprise Index
            start_date: Start date in 'YYYYMMDD' format
            end_date: End date in 'YYYYMMDD' format

        Returns:
            DataFrame containing index market data
        """
        try:
            # Set default date range if not provided
            # end_date = end_date or datetime.now().strftime('%Y%m%d')
            # start_date = start_date or (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
            #
            self.logger.info(
                f"Fetching market data for index {symbol} from {start_date} to {end_date}"
            )

            # Fetch data using parent class method
            df = self.fetch_ak_data(
                "index_hist_cni",
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )

            if df is None or df.empty:
                self.logger.warning(f"No market data found for index {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE_STR",
                    "开盘价": "OPEN_PRICE",
                    "最高价": "HIGH_PRICE",
                    "最低价": "LOW_PRICE",
                    "收盘价": "CLOSE_PRICE",
                    "涨跌幅": "CHANGE_PCT",
                    "成交量": "VOLUME",
                    "成交额": "TURNOVER",
                }
            )

            # Process dates and numeric values
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE_STR"], errors="coerce").dt.date
            df["TRADE_DATE"] = df["TRADE_DATE"].fillna(datetime.now().date())

            numeric_columns = [
                "OPEN_PRICE",
                "HIGH_PRICE",
                "LOW_PRICE",
                "CLOSE_PRICE",
                "CHANGE_PCT",
                "VOLUME",
                "TURNOVER",
            ]
            for col in numeric_columns:
                df[col] = df[col].apply(self.parse_numeric)

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
                "OPEN_PRICE",
                "HIGH_PRICE",
                "LOW_PRICE",
                "CLOSE_PRICE",
                "CHANGE_PCT",
                "VOLUME",
                "TURNOVER",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates()

        except Exception as e:
            self.logger.error(
                f"Error fetching market data for index {symbol}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, symbol=None, start_date=None, end_date=None):
        """
        Main method to run the market data update

        Args:
            symbol: Index code (e.g., '399005')
            start_date: Start date in 'YYYYMMDD' format
            end_date: End date in 'YYYYMMDD' format

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not symbol:
                df = self.get_data_by_columns("INDEX_ALL_CNI_DAILY", ["INDEX_CODE"])
                symbol_list = list(df["INDEX_CODE"].unique())
            else:
                symbol_list = [symbol]
            if not start_date:
                start_date = self.get_latest_date(
                    self.table_name, "TRADE_DATE", {"INDEX_CODE": symbol}
                )
                if start_date is None:
                    start_date = "20050101"
                else:
                    start_date = self.get_next_date(start_date).replace("-", "")
            if not end_date:
                end_date = self.get_previous_date().replace("-", "")
            self.logger.info(f"Starting market data update for index {symbol}")

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            for symbol in symbol_list:
                # Fetch and save data
                df = self.fetch_index_market_data(symbol, start_date, end_date)
                # print(symbol, start_date, end_date)
                # print(df)
                if not df.empty:
                    self.save_data(
                        df.replace(np.nan, None),
                        self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["TRADE_DATE", "INDEX_CODE"],
                    )
                else:
                    self.logger.warning("No data to process")
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
    parser = argparse.ArgumentParser(description="Update CNI index market data")
    parser.add_argument("--symbol", help="Index code (e.g., 399005)")
    parser.add_argument("--start-date", help="Start date in YYYYMMDD format (default: 1 year ago)")
    parser.add_argument("--end-date", help="End date in YYYYMMDD format (default: today)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = IndexDailyMarketCNI(logger=logger)
        success = fetcher.run(
            symbol=args.symbol, start_date=args.start_date, end_date=args.end_date
        )
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
