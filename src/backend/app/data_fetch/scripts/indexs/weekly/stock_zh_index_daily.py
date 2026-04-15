import logging

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockZhIndexDaily(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_ZH_INDEX_DAILY"
        self.create_table_sql = """
            CREATE TABLE `STOCK_ZH_INDEX_DAILY` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(20, 4) COMMENT '开盘价',
                `HIGH` DECIMAL(20, 4) COMMENT '最高价',
                `LOW` DECIMAL(20, 4) COMMENT '最低价',
                `CLOSE` DECIMAL(20, 4) COMMENT '收盘价',
                `VOLUME` BIGINT COMMENT '成交量(手)',
                `MARKET_TYPE` VARCHAR(10) COMMENT '市场类型: sh/sz',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '新浪财经' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE_DATE` (`INDEX_CODE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_MARKET_TYPE` (`MARKET_TYPE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指数日线行情表(新浪财经)';
        """

    def fetch_index_daily(self, symbol):
        """Fetch daily index data from Sina and process it.

        Args:
            symbol: Index code (e.g., 'sz399552')

        Returns:
            pd.DataFrame: Processed DataFrame with daily index data or empty DataFrame on error
        """
        try:
            # 1. Fetch data from AKShare
            df = self.fetch_ak_data("stock_zh_index_daily", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No daily data found for index {symbol}")
                return pd.DataFrame()

            # 2. Rename and process columns
            df = df.rename(
                columns={
                    "date": "TRADE_DATE",
                    "open": "OPEN",
                    "high": "HIGH",
                    "low": "LOW",
                    "close": "CLOSE",
                    "volume": "VOLUME",
                }
            )

            # 3. Process date and numeric columns
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date

            numeric_columns = ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 4. Add metadata columns
            df["INDEX_CODE"] = symbol
            df["MARKET_TYPE"] = symbol[:2].lower()
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]  # Generate unique IDs
            df["DATA_SOURCE"] = "新浪财经"
            df["IS_ACTIVE"] = 1

            # 5. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "TRADE_DATE",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "VOLUME",
                "MARKET_TYPE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE", "TRADE_DATE"])

        except Exception as e:
            self.logger.error(
                f"Error fetching daily data for index {symbol}: {str(e)}", exc_info=True
            )
            return pd.DataFrame()

    def get_sina_index_code(self):
        table_name = "STOCK_ZH_INDEX_SPOT_SINA"
        df = self.get_data_by_columns(table_name, ["INDEX_CODE"])
        # print(df)
        return df["INDEX_CODE"].to_list()

    def run(self, symbol=None):
        """Main method to run the data fetching and saving process.

        Args:
            symbol: Index code (e.g., 'sz399552')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info(f"Starting daily index data update for {symbol}")

            # 创建表（如果不存在）
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # print("symbol = ", symbol)
            if symbol is None:
                symbol_list = self.get_sina_index_code()
                # print(symbol_list)
            else:
                symbol_list = [symbol]

            for symbol in symbol_list:
                # 获取数据
                df = self.fetch_index_daily(symbol)
                if not df.empty:
                    # 处理NaN值
                    df = df.replace(np.nan, None)

                    # 保存数据，使用INSERT ... ON DUPLICATE KEY UPDATE
                    success = self.save_data(
                        df=df,
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDEX_CODE", "TRADE_DATE"],
                    )

                    if success:
                        self.logger.info(
                            f"Successfully updated {len(df)} records for index {symbol} in {self.table_name}"
                        )
                else:
                    self.logger.warning(f"No data found for index {symbol}")

            return True

        except Exception as e:
            self.logger.error(f"Error in run for index {symbol}: {str(e)}", exc_info=True)
            return False


if __name__ == "__main__":
    import argparse
    import logging
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Fetch historical daily index data from Sina Finance"
    )
    parser.add_argument("--symbol", type=str, required=False, help="指数代码，例如: sz399552")

    try:
        args = parser.parse_args()
        fetcher = StockZhIndexDaily(logger=logger)
        success = fetcher.run(args.symbol)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)
