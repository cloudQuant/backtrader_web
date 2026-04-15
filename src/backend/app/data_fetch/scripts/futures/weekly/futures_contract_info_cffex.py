import re
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesContractInfoCffex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_CONTRACT_INFO_CFFEX"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_CONTRACT_INFO_CFFEX` (
                                  `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                  `REFERENCE_CODE` VARCHAR(50) DEFAULT 'CFFEX_CONTRACT_INFO' COMMENT '参考编码',
                                  `REFERENCE_NAME` VARCHAR(100) DEFAULT '中国金融期货交易所合约信息' COMMENT '参考名称',

                                  -- 合约基本信息
                                  `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                  `CONTRACT_MONTH` VARCHAR(20) COMMENT '合约月份',
                                  `LISTING_PRICE` DECIMAL(20, 6) COMMENT '挂盘基准价',
                                  `LISTING_DATE` DATE COMMENT '上市日',
                                  `EXPIRY_DATE` DATE COMMENT '最后交易日',
                                  `PRODUCT_CATEGORY` VARCHAR(10) COMMENT '品种代码',

                                  -- 价格限制信息
                                  `UP_DOWN_LIMIT_RATIO` VARCHAR(50) COMMENT '涨跌停板幅度',
                                  `UP_LIMIT_PRICE` DECIMAL(20, 6) COMMENT '涨停板价位',
                                  `DOWN_LIMIT_PRICE` DECIMAL(20, 6) COMMENT '跌停板价位',

                                  -- 持仓限制
                                  `POSITION_LIMIT` BIGINT COMMENT '持仓限额(手)',

                                  -- 期权特定字段
                                  `OPTION_TYPE` CHAR(1) COMMENT '期权类型(C:看涨期权/P:看跌期权)',
                                  `STRIKE_PRICE` DECIMAL(20, 6) COMMENT '行权价(期权)',

                                  -- 系统字段
                                  `TRADE_DATE` DATE NOT NULL COMMENT '查询交易日',
                                  `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效合约(1:是,0:否)',
                                  `DATA_SOURCE` VARCHAR(50) DEFAULT '中国金融期货交易所' COMMENT '数据来源',
                                  `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                  `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                  `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                  `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                  PRIMARY KEY (`R_ID`),
                                  UNIQUE KEY `IDX_CFFEX_CONTRACT_UNIQUE` (`CONTRACT_CODE`, `TRADE_DATE`),
                                  KEY `IDX_CFFEX_CONTRACT_CODE` (`CONTRACT_CODE`),
                                  KEY `IDX_CFFEX_TRADE_DATE` (`TRADE_DATE`),
                                  KEY `IDX_CFFEX_PRODUCT_CATEGORY` (`PRODUCT_CATEGORY`),
                                  KEY `IDX_CFFEX_CONTRACT_MONTH` (`CONTRACT_MONTH`),
                                  KEY `IDX_CFFEX_IS_ACTIVE` (`IS_ACTIVE`),
                                  KEY `IDX_CFFEX_EXPIRY_DATE` (`EXPIRY_DATE`),
                                  KEY `IDX_CFFEX_LISTING_DATE` (`LISTING_DATE`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中国金融期货交易所合约信息表';

                                """

    def run(self, start_date=None, end_date=None):
        """
        Fetches and stores daily contract information from the China Financial Futures Exchange (CFFEX).
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting CFFEX contract info update.")
        table_name = "FUTURES_CONTRACT_INFO_CFFEX"

        try:
            # 1. Determine date range
            if end_date is None:
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            if start_date is None:
                latest_date_in_db = self.get_latest_date(table_name, "TRADE_DATE")
                if latest_date_in_db:
                    start_date = (
                        datetime.strptime(latest_date_in_db, "%Y-%m-%d") + timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                    self.logger.info(
                        f"Latest data is from {latest_date_in_db}. Starting update from {start_date}."
                    )
                else:
                    start_date = "2010-04-16"  # CFFEX launch date
                    self.logger.info(f"No existing data found. Starting update from {start_date}.")

            if datetime.strptime(start_date, "%Y-%m-%d") > datetime.strptime(end_date, "%Y-%m-%d"):
                self.logger.info("Data is already up to date.")
                return

            trading_days = self.get_trading_day_list(start_date, end_date)
            if not trading_days:
                self.logger.info("No trading days to update in the specified range.")
                return

            self.logger.info(
                f"Fetching data for {len(trading_days)} trading days from {trading_days[0]} to {trading_days[-1]}."
            )

            # 2. Loop through each trading day
            for trade_date in trading_days:
                try:
                    self.logger.info(f"Fetching data for trade date: {trade_date}")
                    # df = ak.futures_contract_info_cffex(date=trade_date.replace('-', ''))
                    df = self.fetch_ak_data(
                        "futures_contract_info_cffex", trade_date.replace("-", "")
                    )
                    time.sleep(2)  # Be respectful

                    if df.empty:
                        self.logger.warning(f"No data returned for {trade_date}.")
                        continue

                    # 3. Data Transformation
                    df.rename(
                        columns={
                            "合约代码": "CONTRACT_CODE",
                            "合约月份": "CONTRACT_MONTH",
                            "挂盘基准价": "LISTING_PRICE",
                            "上市日": "LISTING_DATE",
                            "最后交易日": "EXPIRY_DATE",
                            "涨停板幅度": "UP_DOWN_LIMIT_RATIO",
                            "涨停板价位": "UP_LIMIT_PRICE",
                            "跌停板价位": "DOWN_LIMIT_PRICE",
                            "持仓限额": "POSITION_LIMIT",
                            "品种": "PRODUCT_CATEGORY",
                            "查询交易日": "TRADE_DATE",
                        },
                        inplace=True,
                    )

                    # Drop the redundant limit column if it exists
                    df.drop(columns=["跌停板幅度"], inplace=True, errors="ignore")

                    # Add custom and default columns
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = "CFFEX_CONTRACT_INFO"
                    df["REFERENCE_NAME"] = "中国金融期货交易所合约信息"
                    df["IS_ACTIVE"] = 1
                    df["DATA_SOURCE"] = "中国金融期货交易所"
                    df["CREATEUSER"] = "system"
                    df["UPDATEUSER"] = "system"

                    # Extract Option specific data
                    option_pattern = re.compile(r"-([CP])-(\d+)")
                    df[["OPTION_TYPE", "STRIKE_PRICE"]] = df["CONTRACT_CODE"].str.extract(
                        option_pattern
                    )
                    df["STRIKE_PRICE"] = pd.to_numeric(df["STRIKE_PRICE"], errors="coerce")

                    # Format date columns
                    date_cols = ["LISTING_DATE", "EXPIRY_DATE", "TRADE_DATE"]
                    for col in date_cols:
                        df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")
                    df = df.replace(np.nan, None)
                    # 4. Save to DB
                    self.save_data(df, table_name, unique_keys=["CONTRACT_CODE", "TRADE_DATE"])

                except Exception as e:
                    self.logger.error(
                        f"Failed to process data for {trade_date}: {e}", exc_info=True
                    )
                    continue

            self.logger.info("CFFEX contract info update finished.")

        except Exception as e:
            self.logger.error(
                f"An error occurred during the main CFFEX update process: {e}",
                exc_info=True,
            )
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesContractInfoCffex()
    data_updater.run()
