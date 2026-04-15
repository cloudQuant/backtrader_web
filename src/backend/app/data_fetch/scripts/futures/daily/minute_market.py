import re
import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesMinuteMarket(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_MINUTE_MARKET"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_MINUTE_MARKET` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUTURES_MINUTE' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '期货分时行情数据' COMMENT '参考名称',

                                      -- 合约信息
                                      `SYMBOL` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                      `PERIOD` VARCHAR(10) NOT NULL COMMENT '周期(1/5/15/30/60分钟)',
                                      `VARIETY` VARCHAR(10) COMMENT '品种代码',

                                      -- 时间信息
                                      `TRADE_DATETIME` DATETIME NOT NULL COMMENT '交易时间',
                                      `TRADE_DATE` DATE GENERATED ALWAYS AS (DATE(TRADE_DATETIME)) STORED COMMENT '交易日期',

                                      -- 价格数据
                                      `OPEN_PRICE` DECIMAL(20, 4) COMMENT '开盘价',
                                      `HIGH_PRICE` DECIMAL(20, 4) COMMENT '最高价',
                                      `LOW_PRICE` DECIMAL(20, 4) COMMENT '最低价',
                                      `CLOSE_PRICE` DECIMAL(20, 4) COMMENT '收盘价',

                                      -- 成交量持仓量
                                      `VOLUME` BIGINT COMMENT '成交量(手)',
                                      `OPEN_INTEREST` BIGINT COMMENT '持仓量(手)',

                                      -- 系统字段
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '新浪财经' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_MINUTE_MARKET_UNIQUE` (`SYMBOL`, `PERIOD`, `TRADE_DATETIME`),
                                      KEY `IDX_SYMBOL_PERIOD` (`SYMBOL`, `PERIOD`),
                                      KEY `IDX_TRADE_DATETIME` (`TRADE_DATETIME`),
                                      KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                                      KEY `IDX_VARIETY` (`VARIETY`),
                                      KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国内期货分时行情数据表';

                                """

    def run(self):
        """
        Fetches and stores 1-minute futures data for all current main contracts.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting 1-minute futures market data update.")
        table_name = "FUTURES_MINUTE_MARKET"
        period = "1"

        symbols = self.get_current_futures_contract_list()
        if not symbols:
            self.logger.error("No symbols found to update. Exiting.")
            return

        for symbol in symbols:
            try:
                self.logger.info(f"--- Processing symbol: {symbol} ---")

                # 1. Get latest timestamp for this symbol
                latest_dt = self.get_latest_date(
                    self.table_name, "TRADE_DATETIME", conditions={"SYMBOL": symbol}
                )
                if latest_dt:
                    self.logger.info(
                        f"Latest data for {symbol} is from {latest_dt}. Fetching newer data."
                    )
                else:
                    self.logger.info(f"No existing data for {symbol}. Performing full fetch.")

                # 2. Fetch Data
                # df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
                df = self.fetch_ak_data(
                    "futures_zh_minute_sina", **{"symbol": symbol, "period": period}
                )
                time.sleep(2)  # Be respectful

                if df.empty:
                    self.logger.warning(f"No data returned for {symbol}.")
                    continue

                # 3. Data Transformation
                df.rename(
                    columns={
                        "datetime": "TRADE_DATETIME",
                        "open": "OPEN_PRICE",
                        "high": "HIGH_PRICE",
                        "low": "LOW_PRICE",
                        "close": "CLOSE_PRICE",
                        "volume": "VOLUME",
                        "hold": "OPEN_INTEREST",
                    },
                    inplace=True,
                )

                # Convert TRADE_DATETIME to datetime and then to MySQL format string
                df["TRADE_DATETIME"] = pd.to_datetime(df["TRADE_DATETIME"], errors="coerce")
                df = df.dropna(subset=["TRADE_DATETIME"])

                # Convert datetime to MySQL format string (YYYY-MM-DD HH:MM:SS)
                df["TRADE_DATETIME"] = df["TRADE_DATETIME"].dt.strftime("%Y-%m-%d %H:%M:%S")

                # 4. Filter for new records
                if latest_dt:
                    # Convert latest_dt to string for comparison since we're now storing dates as strings
                    latest_dt_str = latest_dt.strftime("%Y-%m-%d %H:%M:%S")
                    df = df[df["TRADE_DATETIME"] > latest_dt_str]

                if df.empty:
                    self.logger.info(f"No new 1-minute data to update for {symbol}.")
                    continue

                self.logger.info(f"Found {len(df)} new 1-minute records for {symbol}.")

                # Add custom and default columns
                df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                df["REFERENCE_CODE"] = "FUTURES_MINUTE"
                df["REFERENCE_NAME"] = "期货分时行情数据"
                df["SYMBOL"] = symbol
                df["PERIOD"] = period
                df["VARIETY"] = (
                    re.match(r"([A-Z]+)", symbol, re.IGNORECASE).group(1).upper()
                    if re.match(r"([A-Z]+)", symbol, re.IGNORECASE)
                    else ""
                )
                df["IS_ACTIVE"] = 1
                df["DATA_SOURCE"] = "新浪财经"
                df["CREATEUSER"] = "system"
                df["UPDATEUSER"] = "system"

                # 5. Save to DB
                self.save_data(df, table_name, unique_keys=["SYMBOL", "PERIOD", "TRADE_DATETIME"])

            except Exception as e:
                self.logger.error(f"Failed to process symbol {symbol}: {e}", exc_info=True)
                continue

        self.logger.info("Futures 1-minute market data update finished.")


if __name__ == "__main__":
    data_updater = FuturesMinuteMarket()
    data_updater.run()
