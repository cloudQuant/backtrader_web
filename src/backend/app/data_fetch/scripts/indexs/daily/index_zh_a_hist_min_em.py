import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexZhAHistMinEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_ZH_A_HIST_MIN_EM"
        self.create_table_sql = """
            CREATE TABLE `INDEX_ZH_A_HIST_MIN_EM` (
                `R_ID` VARCHAR(64) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `TRADE_TIME` DATETIME NOT NULL COMMENT '交易时间',
                `TRADE_DATE` DATE COMMENT '交易日期',
                `PERIOD` VARCHAR(5) COMMENT '周期: 1/5/15/30/60分钟',
                `OPEN` DECIMAL(20, 4) COMMENT '开盘价',
                `CLOSE` DECIMAL(20, 4) COMMENT '收盘价',
                `HIGH` DECIMAL(20, 4) COMMENT '最高价',
                `LOW` DECIMAL(20, 4) COMMENT '最低价',
                `VOLUME` BIGINT COMMENT '成交量(手)',
                `AMOUNT` DECIMAL(30, 2) COMMENT '成交额(元)',
                `AVG_PRICE` DECIMAL(20, 4) COMMENT '均价',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_CODE_TIME_PERIOD` (`INDEX_CODE`, `TRADE_TIME`, `PERIOD`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_INDEX_CODE` (`INDEX_CODE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指数分时行情表(东方财富)';
        """

    def get_em_index_code(self):
        """Get list of index codes from East Money spot data."""
        table_name = "STOCK_ZH_INDEX_SPOT_EM"
        df = self.get_data_by_columns(table_name, ["INDEX_CODE"])
        return list(df["INDEX_CODE"].unique())

    def fetch_minute_data(self, symbol, period, start_date=None, end_date=None):
        """Fetch minute-level index data from East Money and process it.

        Args:
            symbol: Index code (e.g., 'sh000001')
            period: Time period in minutes (1, 5, 15, 30, 60)
            start_date: Start datetime in format 'YYYY-MM-DD HH:MM:SS' (optional)
            end_date: End datetime in format 'YYYY-MM-DD HH:MM:SS' (optional)

        Returns:
            pd.DataFrame: Processed DataFrame with minute data or empty DataFrame on error
        """
        try:
            # 1. Set default date range if not provided
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 09:30:00")
            if end_date is None:
                end_date = datetime.now().strftime("%Y-%m-%d 15:00:00")

            # 2. Fetch data from AKShare
            df = self.fetch_ak_data(
                "index_zh_a_hist_min_em",
                symbol=symbol,
                period=str(period),
                start_date=start_date,
                end_date=end_date,
            )

            if df is None or df.empty:
                self.logger.warning(f"No minute data found for index {symbol} period {period}")
                return pd.DataFrame()

            # 3. Rename and process columns
            df = df.rename(
                columns={
                    "时间": "TRADE_TIME_STR",
                    "开盘": "OPEN",
                    "收盘": "CLOSE",
                    "最高": "HIGH",
                    "最低": "LOW",
                    "成交量": "VOLUME",
                    "成交额": "AMOUNT",
                    "均价": "AVG_PRICE",
                }
            )

            # 4. Process datetime and numeric columns
            df["TRADE_TIME"] = pd.to_datetime(df["TRADE_TIME_STR"])
            df["TRADE_DATE"] = df["TRADE_TIME"].dt.date

            numeric_columns = [
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "VOLUME",
                "AMOUNT",
                "AVG_PRICE",
            ]
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
            df["PERIOD"] = str(period)
            # Stable primary key: avoid updating random UUID on duplicate rows.
            df["R_ID"] = (
                df["INDEX_CODE"].astype(str)
                + "_"
                + df["PERIOD"].astype(str)
                + "_"
                + df["TRADE_TIME"].dt.strftime("%Y%m%d%H%M%S")
            )
            df["DATA_SOURCE"] = "东方财富"
            df["IS_ACTIVE"] = 1

            # 7. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "TRADE_TIME",
                "TRADE_DATE",
                "PERIOD",
                "OPEN",
                "CLOSE",
                "HIGH",
                "LOW",
                "VOLUME",
                "AMOUNT",
                "AVG_PRICE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE", "TRADE_TIME", "PERIOD"])

        except Exception as e:
            self.logger.error(
                f"Error fetching minute data for index {symbol} period {period}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, symbol=None, period="1", start_date=None, end_date=None):
        """Main method to run the data fetching and saving process.

        Args:
            symbol: Index code (e.g., 'sh000001') or None to process all indices
            period: Time period in minutes (1, 5, 15, 30, 60)
            start_date: Start datetime in format 'YYYY-MM-DD HH:MM:SS' (optional)
            end_date: End datetime in format 'YYYY-MM-DD HH:MM:SS' (optional)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info(f"Starting East Money minute index data update (period: {period}min)")

            # 创建表（如果不存在）
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # 获取要处理的指数代码列表
            if symbol is None:
                symbol_list = self.get_em_index_code()
                self.logger.info(f"Found {len(symbol_list)} indices to process")
                # Keep runtime bounded: shard the full symbol list into deterministic daily batches.
                # This makes the default scheduled run finish within a reasonable time while still
                # eventually covering all indices across days.
                batch_size = int(os.getenv("INDEX_MIN_BATCH_SIZE") or "20")
                batch_size = max(1, batch_size)
                batches = max(1, (len(symbol_list) + batch_size - 1) // batch_size)
                batch_idx = datetime.utcnow().date().toordinal() % batches
                start = batch_idx * batch_size
                symbol_list = symbol_list[start : start + batch_size]
                self.logger.info(
                    f"Processing batch {batch_idx+1}/{batches}: {len(symbol_list)} indices"
                )
            else:
                symbol_list = [symbol]

            all_success = True
            for symbol in symbol_list:
                try:
                    period_list = ["1", "15", "60"] if period is None else [period]
                    for period in period_list:
                        # 获取数据
                        df = self.fetch_minute_data(symbol, period, start_date, end_date)
                        if not df.empty:
                            # 处理NaN值
                            df = df.replace(np.nan, None)

                            # 保存数据，使用INSERT ... ON DUPLICATE KEY UPDATE
                            success = self.save_data(
                                df=df,
                                table_name=self.table_name,
                                on_duplicate_update=True,
                                unique_keys=[
                                    "R_ID",
                                    "INDEX_CODE",
                                    "TRADE_TIME",
                                    "PERIOD",
                                ],
                            )

                            if success:
                                self.logger.info(
                                    f"Successfully updated {len(df)} records for index {symbol} "
                                    f"(period: {period}min) in {self.table_name}"
                                )
                            else:
                                all_success = False
                                self.logger.error(f"Failed to save data for index {symbol}")
                        else:
                            self.logger.warning(
                                f"No data found for index {symbol} (period: {period}min)"
                            )

                except Exception as e:
                    all_success = False
                    self.logger.error(f"Error processing index {symbol}: {str(e)}", exc_info=True)

            return all_success

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():
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
        description="Fetch historical minute index data from East Money"
    )
    parser.add_argument("--symbol", type=str, required=False, help="指数代码，例如: sh000001")
    parser.add_argument(
        "--period",
        type=str,
        default="1",
        choices=["1", "5", "15", "30", "60"],
        help="K线周期(分钟): 1/5/15/30/60，默认: 1",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="开始日期时间，格式: YYYY-MM-DD HH:MM:SS，默认: 前一天09:30:00",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="结束日期时间，格式: YYYY-MM-DD HH:MM:SS，默认: 当前时间",
    )

    try:
        args = parser.parse_args()
        fetcher = IndexZhAHistMinEm(logger=logger)
        success = fetcher.run(args.symbol, args.period, args.start_date, args.end_date)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
