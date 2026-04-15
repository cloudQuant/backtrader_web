# 4075_sw_fund_index_realtime.py
import argparse
import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class SWFundIndexRealtime(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "SW_FUND_INDEX_REALTIME"
        self.create_table_sql = """
            CREATE TABLE `SW_FUND_INDEX_REALTIME` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) COMMENT '指数代码',
                `INDEX_NAME` VARCHAR(100) COMMENT '指数名称',
                `SYMBOL_TYPE` VARCHAR(20) COMMENT '指数类型',
                `PREV_CLOSE` DECIMAL(12, 2) COMMENT '昨收盘',
                `DAILY_CHANGE_PCT` DECIMAL(8, 4) COMMENT '日涨跌幅(%)',
                `YTD_CHANGE_PCT` DECIMAL(8, 4) COMMENT '年涨跌幅(%)',
                `UPDATE_TIME` DATETIME COMMENT '更新时间',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_CODE_TYPE` (`INDEX_CODE`, `SYMBOL_TYPE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万基金指数实时行情';
        """
        self.valid_symbols = ["基础一级", "基础二级", "基础三级", "特色指数"]

    def fetch_index_data(self, symbol):
        """Fetch Shenwan Hongyuan Fund Index real-time data"""
        try:
            if symbol not in self.valid_symbols:
                self.logger.error(f"Invalid symbol: {symbol}. Must be one of {self.valid_symbols}")
                return pd.DataFrame()

            self.logger.info(f"Fetching Shenwan Hongyuan Fund Index data for {symbol}")

            df = self.fetch_ak_data("index_realtime_fund_sw", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No data found for Shenwan Hongyuan Fund Index - {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "指数代码": "INDEX_CODE",
                    "指数名称": "INDEX_NAME",
                    "昨收盘": "PREV_CLOSE",
                    "日涨跌幅": "DAILY_CHANGE_PCT",
                    "年涨跌幅": "YTD_CHANGE_PCT",
                }
            )

            # Add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["SYMBOL_TYPE"] = symbol
            df["UPDATE_TIME"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(
                f"Error fetching Shenwan Hongyuan Fund Index data: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, symbol=None):
        """Run the Shenwan Hongyuan Fund Index update"""
        try:
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")
            for symbol in self.valid_symbols:
                df = self.fetch_index_data(symbol)

                if not df.empty:
                    # Insert new records
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDEX_CODE", "SYMBOL_TYPE"],
                    )
                    self.logger.info(
                        f"Updated {len(df)} Shenwan Hongyuan Fund Index records for {symbol}"
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
        description="Update Shenwan Hongyuan Fund Index Real-time Data"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="基础一级",
        choices=["基础一级", "基础二级", "基础三级", "特色指数"],
        help="Index type to fetch (default: 基础一级)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = SWFundIndexRealtime(logger=logger)
        success = fetcher.run(symbol=args.symbol)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
