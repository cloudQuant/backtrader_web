# 4077_sw_index_realtime.py
import argparse
import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class SWIndexRealtime(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "SW_INDEX_REALTIME"
        self.create_table_sql = """
            CREATE TABLE `SW_INDEX_REALTIME` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) COMMENT '指数代码',
                `INDEX_NAME` VARCHAR(100) COMMENT '指数名称',
                `SYMBOL_TYPE` VARCHAR(20) COMMENT '指数类型',
                `PREV_CLOSE` DECIMAL(12, 2) COMMENT '昨收盘',
                `OPEN_PRICE` DECIMAL(12, 2) COMMENT '今开盘',
                `LAST_PRICE` DECIMAL(12, 2) COMMENT '最新价',
                `TURNOVER` DECIMAL(18, 2) COMMENT '成交额(百万元)',
                `VOLUME` DECIMAL(18, 2) COMMENT '成交量(百万股)',
                `HIGH_PRICE` DECIMAL(12, 2) COMMENT '最高价',
                `LOW_PRICE` DECIMAL(12, 2) COMMENT '最低价',
                `UPDATE_TIME` DATETIME COMMENT '更新时间',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_CODE_TYPE` (`INDEX_CODE`, `SYMBOL_TYPE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`),
                KEY `IDX_UPDATE_TIME` (`UPDATE_TIME`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万指数实时行情';
        """
        self.valid_symbols = ["市场表征", "一级行业", "二级行业", "风格指数"]

    def fetch_index_data(self, symbol):
        """Fetch Shenwan Index real-time data"""
        try:
            if symbol not in self.valid_symbols:
                self.logger.error(f"Invalid symbol: {symbol}. Must be one of {self.valid_symbols}")
                return pd.DataFrame()

            self.logger.info(f"Fetching Shenwan Index real-time data for {symbol}")

            df = self.fetch_ak_data("index_realtime_sw", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No data found for Shenwan Index - {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "指数代码": "INDEX_CODE",
                    "指数名称": "INDEX_NAME",
                    "昨收盘": "PREV_CLOSE",
                    "今开盘": "OPEN_PRICE",
                    "最新价": "LAST_PRICE",
                    "成交额": "TURNOVER",
                    "成交量": "VOLUME",
                    "最高价": "HIGH_PRICE",
                    "最低价": "LOW_PRICE",
                }
            )

            # Add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["SYMBOL_TYPE"] = symbol
            df["UPDATE_TIME"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"
            require_columns = [
                "INDEX_CODE",
                "INDEX_NAME",
                "PREV_CLOSE",
                "OPEN_PRICE",
                "LAST_PRICE",
                "TURNOVER",
                "VOLUME",
                "HIGH_PRICE",
                "LOW_PRICE",
                "DATA_SOURCE",
                "R_ID",
                "SYMBOL_TYPE",
                "UPDATE_TIME",
                "IS_ACTIVE",
            ]
            df = df[require_columns]
            return df

        except Exception as e:
            self.logger.error(f"Error fetching Shenwan Index data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, symbol="市场表征"):
        """Run the Shenwan Index real-time data update"""
        try:
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")
            for symbol in self.valid_symbols:
                df = self.fetch_index_data(symbol)
                # print(df)
                if not df.empty:
                    # Insert new records
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDEX_CODE", "SYMBOL_TYPE"],
                    )
                    self.logger.info(f"Updated {len(df)} Shenwan Index records for {symbol}")
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
    parser = argparse.ArgumentParser(description="Update Shenwan Index Real-time Data")
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        choices=[
            "市场表征",
            "一级行业",
            "二级行业",
            "风格指数",
            "大类风格指数",
            "金创指数",
        ],
        help="Index type to fetch (default: 市场表征)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = SWIndexRealtime(logger=logger)
        success = fetcher.run(symbol=args.symbol)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
