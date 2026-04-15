import logging
from datetime import date

import akshare as ak
import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockZhIndexDailyEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_ZH_INDEX_DAILY_EM"
        self.create_table_sql = """
            CREATE TABLE `STOCK_ZH_INDEX_DAILY_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(20, 4) COMMENT '开盘价',
                `CLOSE` DECIMAL(20, 4) COMMENT '收盘价',
                `HIGH` DECIMAL(20, 4) COMMENT '最高价',
                `LOW` DECIMAL(20, 4) COMMENT '最低价',
                `VOLUME` BIGINT COMMENT '成交量(手)',
                `AMOUNT` DECIMAL(30, 2) COMMENT '成交额(元)',
                `MARKET_TYPE` VARCHAR(10) COMMENT '市场类型: sh/sz/csi',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE_DATE` (`INDEX_CODE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_MARKET_TYPE` (`MARKET_TYPE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指数日线行情表(东方财富)';
        """

    def get_em_index_code(self):
        """Get list of index codes from East Money spot data."""
        table_name = "STOCK_ZH_INDEX_SPOT_EM"
        df = self.get_data_by_columns(table_name, ["INDEX_CODE"])
        return list(df["INDEX_CODE"].unique())

    def fetch_index_daily(self, symbol, start_date=None, end_date=None):
        """Fetch daily index data from East Money and process it.

        Args:
            symbol: Index code (e.g., 'sz399812', 'sh000001', 'csi000905')
            start_date: Start date in format 'YYYYMMDD' (optional)
            end_date: End date in format 'YYYYMMDD' (optional)

        Returns:
            pd.DataFrame: Processed DataFrame with daily index data or empty DataFrame on error
        """
        try:
            # 1. Set default date range if not provided
            if start_date is None:
                start_date = "19900101"  # Default start from 1990
            if end_date is None:
                end_date = date.today().strftime("%Y%m%d")
            symbol = ak.stock_a_code_to_symbol(symbol)
            # print(f"symbol: {symbol}, start_date: {start_date}, end_date: {end_date}")
            # 2. Fetch data from AKShare
            df = self.fetch_ak_data(
                "stock_zh_index_daily_em",
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )

            if df is None or df.empty:
                self.logger.warning(f"No daily data found for index {symbol}")
                return pd.DataFrame()

            # 3. Rename and process columns
            df = df.rename(
                columns={
                    "date": "TRADE_DATE",
                    "open": "OPEN",
                    "close": "CLOSE",
                    "high": "HIGH",
                    "low": "LOW",
                    "volume": "VOLUME",
                    "amount": "AMOUNT",
                }
            )

            # 4. Process date and numeric columns
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date

            numeric_columns = ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "AMOUNT"]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 5. Process volume (convert to integer)
            if "VOLUME" in df.columns:
                df["VOLUME"] = df["VOLUME"].fillna(0).astype("int64")

            # 6. Add metadata columns
            df["INDEX_CODE"] = symbol
            df["MARKET_TYPE"] = symbol[:2].lower() if not symbol.startswith("csi") else "csi"
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]  # Generate unique IDs
            df["DATA_SOURCE"] = "东方财富"
            df["IS_ACTIVE"] = 1

            # 7. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "TRADE_DATE",
                "OPEN",
                "CLOSE",
                "HIGH",
                "LOW",
                "VOLUME",
                "AMOUNT",
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

    def run(self, symbol=None, start_date=None, end_date=None):
        """Main method to run the data fetching and saving process.

        Args:
            symbol: Index code (e.g., 'sz399812') or None to process all indices
            start_date: Start date in format 'YYYYMMDD' (optional)
            end_date: End date in format 'YYYYMMDD' (optional)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info("Starting East Money daily index data update")

            # 创建表（如果不存在）
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # 获取要处理的指数代码列表
            if symbol is None:
                symbol_list = self.get_em_index_code()
                self.logger.info(f"Found {len(symbol_list)} indices to process")
            else:
                symbol_list = [symbol]

            all_success = True
            for symbol in symbol_list:
                try:
                    if start_date is None:
                        start_date = self.get_latest_date(
                            self.table_name, "TRADE_DATE", {"INDEX_CODE": symbol}
                        )
                        if start_date is None:
                            start_date = "19900101"
                    if end_date is None:
                        end_date = self.get_previous_date().replace("-", "")
                    # print(f"symbol: {symbol}, start_date: {start_date}, end_date: {end_date}")
                    # 获取数据
                    df = self.fetch_index_daily(symbol, start_date, end_date)

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
                            all_success = False
                            self.logger.error(f"Failed to save data for index {symbol}")
                    else:
                        self.logger.warning(f"No data found for index {symbol}")

                except Exception as e:
                    all_success = False
                    self.logger.error(f"Error processing index {symbol}: {str(e)}", exc_info=True)

            return all_success

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
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
        description="Fetch historical daily index data from East Money"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        required=False,
        help="指数代码，例如: sz399812, sh000001, csi000905",
    )
    parser.add_argument("--start-date", type=str, help="开始日期，格式: YYYYMMDD，默认: 19900101")
    parser.add_argument("--end-date", type=str, help="结束日期，格式: YYYYMMDD，默认: 当前日期")

    try:
        args = parser.parse_args()
        fetcher = StockZhIndexDailyEm(logger=logger)
        success = fetcher.run(args.symbol, args.start_date, args.end_date)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)
