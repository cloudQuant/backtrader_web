import importlib
import time
from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class ForeignFuturesHistoryEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FOREIGN_FUTURES_HISTORY_EM"
        self.create_table_sql = r"""
                                CREATE TABLE `FOREIGN_FUTURES_HISTORY_EM` (
                                  `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                  `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FOREIGN_FUTURES_HISTORY' COMMENT '参考编码',
                                  `REFERENCE_NAME` VARCHAR(100) DEFAULT '外盘期货历史行情数据(东方财富)' COMMENT '参考名称',

                                  -- 基础信息
                                  `SYMBOL_CODE` VARCHAR(20) NOT NULL COMMENT '品种代码',
                                  `SYMBOL_NAME` VARCHAR(100) NOT NULL COMMENT '品种名称',
                                  `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',

                                  -- 价格数据
                                  `OPEN_PRICE` DECIMAL(20, 6) COMMENT '开盘价',
                                  `LAST_PRICE` DECIMAL(20, 6) COMMENT '最新价',
                                  `HIGH_PRICE` DECIMAL(20, 6) COMMENT '最高价',
                                  `LOW_PRICE` DECIMAL(20, 6) COMMENT '最低价',

                                  -- 成交量持仓量
                                  `VOLUME` BIGINT COMMENT '成交量',
                                  `OPEN_INTEREST` BIGINT COMMENT '持仓量',
                                  `OPEN_INTEREST_CHG` BIGINT COMMENT '日增仓',

                                  -- 涨跌数据
                                  `CHANGE_PERCENT` DECIMAL(10, 4) COMMENT '涨跌幅(%)',

                                  -- 系统字段
                                  `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                  `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                                  `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                  `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                  `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                  `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                  PRIMARY KEY (`R_ID`),
                                  UNIQUE KEY `IDX_SYMBOL_DATE` (`SYMBOL_CODE`, `TRADE_DATE`),
                                  KEY `IDX_SYMBOL_NAME` (`SYMBOL_NAME`),
                                  KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                                  KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='外盘期货历史行情数据表(东方财富)';

                                """

    def run(self):
        """
        Fetches and stores historical data for all foreign futures contracts from Eastmoney.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("Starting foreign futures historical data update.")
        table_name = "FOREIGN_FUTURES_HISTORY_EM"

        # Avoid hard-coded local paths. Import the companion script dynamically.
        mod = importlib.import_module(
            "app.data_fetch.scripts.futures.daily.foreign_futures_realtime_em"
        )
        ForeignFuturesRealtimeEm = mod.ForeignFuturesRealtimeEm

        symbols = ForeignFuturesRealtimeEm().run()
        if not symbols:
            self.logger.error("No symbols found to update. Exiting.")
            return

        for symbol in symbols:
            try:
                self.logger.info(f"--- Processing symbol: {symbol} ---")

                # 1. Get latest date for this symbol
                latest_date_str = self.get_latest_date(
                    self.table_name, "TRADE_DATE", conditions={"SYMBOL_CODE": symbol}
                )
                if latest_date_str:
                    self.logger.info(
                        f"Latest data for {symbol} is from {latest_date_str}. Fetching newer data."
                    )
                else:
                    self.logger.info(f"No existing data for {symbol}. Performing full fetch.")

                # 2. Fetch Data
                # df = ak.futures_global_hist_em(symbol=symbol)
                df = self.fetch_ak_data("futures_global_hist_em", symbol)
                time.sleep(2)  # Be respectful
                # print(df.head())
                if df.empty:
                    self.logger.warning(f"No historical data returned for {symbol}.")
                    continue

                # 3. Data Transformation
                df.rename(
                    columns={
                        "日期": "TRADE_DATE",
                        "代码": "SYMBOL_CODE",
                        "名称": "SYMBOL_NAME",
                        "开盘": "OPEN_PRICE",
                        "最新价": "LAST_PRICE",
                        "最高": "HIGH_PRICE",
                        "最低": "LOW_PRICE",
                        "总量": "VOLUME",
                        "涨幅": "CHANGE_PERCENT",
                        "持仓": "OPEN_INTEREST",
                        "日增": "OPEN_INTEREST_CHG",
                    },
                    inplace=True,
                )

                df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"], errors="coerce")
                df.dropna(subset=["TRADE_DATE"], inplace=True)

                # 4. Filter for new records
                if latest_date_str:
                    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d")
                    df = df[df["TRADE_DATE"] > latest_date]

                if df.empty:
                    self.logger.info(f"No new historical data to update for {symbol}.")
                    continue

                self.logger.info(f"Found {len(df)} new historical records for {symbol}.")

                # Add custom and default columns
                df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                df["REFERENCE_CODE"] = "FOREIGN_FUTURES_HISTORY"
                df["REFERENCE_NAME"] = "外盘期货历史行情数据(东方财富)"
                df["IS_ACTIVE"] = 1
                df["DATA_SOURCE"] = "东方财富"
                df["CREATEUSER"] = "system"
                df["UPDATEUSER"] = "system"

                # Clean and format data
                numeric_cols = [
                    "OPEN_PRICE",
                    "LAST_PRICE",
                    "HIGH_PRICE",
                    "LOW_PRICE",
                    "VOLUME",
                    "OPEN_INTEREST",
                    "OPEN_INTEREST_CHG",
                ]
                for col in numeric_cols:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                df["CHANGE_PERCENT"] = pd.to_numeric(df["CHANGE_PERCENT"], errors="coerce") / 100
                df["TRADE_DATE"] = df["TRADE_DATE"].dt.strftime("%Y-%m-%d")

                # 5. Save to DB
                self.save_data(df, table_name, unique_keys=["SYMBOL_CODE", "TRADE_DATE"])

            except Exception as e:
                self.logger.error(f"Failed to process symbol {symbol}: {e}", exc_info=True)
                continue

        self.logger.info("Foreign futures historical data update finished.")
        return True


if __name__ == "__main__":
    data_updater = ForeignFuturesHistoryEm()
    data_updater.run()
