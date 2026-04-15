# 4076_sw_fund_index_historical.py
import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class SWFundIndexHistorical(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "SW_FUND_INDEX_HISTORICAL"
        self.create_table_sql = """
            CREATE TABLE `SW_FUND_INDEX_HISTORICAL` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) COMMENT '指数代码',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `CLOSE_INDEX` DECIMAL(12, 4) COMMENT '收盘指数',
                `OPEN_INDEX` DECIMAL(12, 4) COMMENT '开盘指数',
                `HIGH_INDEX` DECIMAL(12, 4) COMMENT '最高指数',
                `LOW_INDEX` DECIMAL(12, 4) COMMENT '最低指数',
                `CHANGE_PCT` DECIMAL(8, 4) COMMENT '涨跌幅(%)',
                `PERIOD` VARCHAR(10) COMMENT '周期(day/week/month)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_CODE_DATE_PERIOD` (`INDEX_CODE`, `TRADE_DATE`, `PERIOD`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万基金指数历史行情';
        """
        self.valid_periods = ["day", "week", "month"]

    def fetch_historical_data(self, symbol, period):
        """Fetch Shenwan Hongyuan Fund Index historical data"""
        try:
            if period not in self.valid_periods:
                self.logger.error(f"Invalid period: {period}. Must be one of {self.valid_periods}")
                return pd.DataFrame()

            self.logger.info(
                f"Fetching Shenwan Hongyuan Fund Index historical data for {symbol} ({period}ly)"
            )

            df = self.fetch_ak_data("index_hist_fund_sw", symbol=symbol, period=period)

            if df is None or df.empty:
                self.logger.warning(
                    f"No historical data found for index {symbol} with period {period}"
                )
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE",
                    "收盘指数": "CLOSE_INDEX",
                    "开盘指数": "OPEN_INDEX",
                    "最高指数": "HIGH_INDEX",
                    "最低指数": "LOW_INDEX",
                    "涨跌幅": "CHANGE_PCT",
                }
            )

            # Add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["INDEX_CODE"] = symbol
            df["PERIOD"] = period
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(
                f"Error fetching historical data for {symbol}: {str(e)}", exc_info=True
            )
            return pd.DataFrame()

    def get_symbol_list(self):
        df = self.get_data_by_columns("SW_FUND_INDEX_REALTIME", ["INDEX_CODE"])
        return df["INDEX_CODE"].tolist()

    def run(self, symbol=None, period="day", update_all=False):
        """Run the Shenwan Hongyuan Fund Index historical data update"""
        try:
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")
            symbol_list = self.get_symbol_list() if symbol is None else [symbol]
            for symbol in symbol_list:
                df = self.fetch_historical_data(symbol, period)

                if not df.empty:
                    # if not update_all:
                    #     # Get the latest date from database for this index and period
                    #     latest_date = self.get_latest_date(symbol, period)
                    #     if latest_date:
                    #         self.logger.info(f"Latest date in database for {symbol} ({period}): {latest_date}")
                    #         # Filter for new records only
                    #         df = df[df['TRADE_DATE'] > latest_date]
                    #         if df.empty:
                    #             self.logger.info("No new data to update")
                    #             return True

                    # Save data
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDEX_CODE", "TRADE_DATE", "PERIOD"],
                    )
                    self.logger.info(
                        f"Updated {len(df)} historical records for index {symbol} ({period})"
                    )

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
        description="Update Shenwan Hongyuan Fund Index Historical Data"
    )
    parser.add_argument(
        "--symbol", type=str, required=False, help="Symbol to fetch historical data for"
    ),
    parser.add_argument(
        "--period",
        type=str,
        default="day",
        choices=["day", "week", "month"],
        help="Data period (default: day)",
    )
    parser.add_argument(
        "--update-all",
        action="store_true",
        help="Update all historical data (default: only update new data)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = SWFundIndexHistorical(logger=logger)
        success = fetcher.run(symbol=args.symbol, period=args.period, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
