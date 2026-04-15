import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesDailyMarket(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_DAILY_MARKET"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_DAILY_MARKET` (
                                  `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                  `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUTURES_DAILY' COMMENT '参考编码',
                                  `REFERENCE_NAME` VARCHAR(100) DEFAULT '期货历史行情数据' COMMENT '参考名称',

                                  -- 合约信息
                                  `SYMBOL` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                  `VARIETY` VARCHAR(20) COMMENT '品种代码',
                                  `MARKET` VARCHAR(10) NOT NULL COMMENT '交易所(CFFEX/INE/CZCE/DCE/SHFE/GFEX)',

                                  -- 交易日期
                                  `TRADE_DATE` DATE NOT NULL COMMENT '交易日',

                                  -- 价格数据
                                  `OPEN_PRICE` DECIMAL(20, 4) COMMENT '开盘价',
                                  `HIGH_PRICE` DECIMAL(20, 4) COMMENT '最高价',
                                  `LOW_PRICE` DECIMAL(20, 4) COMMENT '最低价',
                                  `CLOSE_PRICE` DECIMAL(20, 4) COMMENT '收盘价',
                                  `SETTLE_PRICE` DECIMAL(20, 4) COMMENT '结算价',
                                  `PREV_SETTLE` DECIMAL(20, 4) COMMENT '前结算价',

                                  -- 成交量持仓量
                                  `VOLUME` BIGINT COMMENT '成交量(手)',
                                  `OPEN_INTEREST` BIGINT COMMENT '持仓量(手)',
                                  `TURNOVER` DECIMAL(30, 4) COMMENT '成交额(元)',

                                  -- 系统字段
                                  `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                  `DATA_SOURCE` VARCHAR(50) DEFAULT '交易所' COMMENT '数据来源',
                                  `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                  `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                  `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                  `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                  PRIMARY KEY (`R_ID`),
                                  UNIQUE KEY `IDX_DAILY_MARKET_UNIQUE` (`SYMBOL`, `TRADE_DATE`),
                                  KEY `IDX_MARKET_SYMBOL` (`MARKET`, `SYMBOL`),
                                  KEY `IDX_MARKET_VARIETY` (`MARKET`, `VARIETY`),
                                  KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                                  KEY `IDX_VARIETY` (`VARIETY`),
                                  KEY `IDX_MARKET` (`MARKET`),
                                  KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国内期货交易所历史行情数据表';

                                """

    def run(self):
        """
        Fetches and stores historical daily market data for all domestic futures exchanges.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting futures daily market data update for all exchanges.")
        table_name = "FUTURES_DAILY_MARKET"
        exchanges = ["CFFEX", "INE", "CZCE", "DCE", "SHFE", "GFEX"]

        for market in exchanges:
            try:
                self.logger.info(f"--- Processing market: {market} ---")

                # 1. Determine date range for the current market
                latest_date_in_db = self.get_latest_date(
                    self.table_name, "TRADE_DATE", conditions={"MARKET": market}
                )

                if latest_date_in_db:
                    start_date = (
                        datetime.strptime(latest_date_in_db, "%Y-%m-%d") + timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                    self.logger.info(
                        f"Latest data for {market} is from {latest_date_in_db}. Starting update from {start_date}."
                    )
                else:
                    start_date = "2010-01-01"
                    self.logger.info(
                        f"No existing data for {market} found. Starting update from {start_date}."
                    )

                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

                if datetime.strptime(start_date, "%Y-%m-%d") > datetime.strptime(
                    end_date, "%Y-%m-%d"
                ):
                    self.logger.info(f"Data for {market} is already up to date. Skipping.")
                    continue

                # 2. Fetch data in monthly intervals
                current_start = datetime.strptime(start_date, "%Y-%m-%d")
                final_end = datetime.strptime(end_date, "%Y-%m-%d")

                while current_start <= final_end:
                    current_end = current_start + relativedelta(days=7) - timedelta(days=1)
                    if current_end > final_end:
                        current_end = final_end

                    start_str = current_start.strftime("%Y%m%d")
                    end_str = current_end.strftime("%Y%m%d")

                    self.logger.info(f"Fetching {market} data from {start_str} to {end_str}")

                    try:
                        kwargs = {
                            "start_date": start_str,
                            "end_date": end_str,
                            "market": market,
                        }
                        df = self.fetch_ak_data("get_futures_daily", **kwargs)
                        # df = ak.get_futures_daily(start_date=start_str, end_date=end_str, market=market)
                        # print(df)
                        time.sleep(2)  # Be respectful
                        if df.empty:
                            self.logger.warning(
                                f"No data returned for {market} in range {start_str}-{end_str}."
                            )
                            current_start += relativedelta(days=7)
                            continue

                        # 3. Data Transformation
                        # Drop the 'index' column if it exists to avoid SQL syntax errors
                        if "index" in df.columns:
                            df = df.drop(columns=["index"])

                        # Create a copy to avoid SettingWithCopyWarning
                        df = df.copy()

                        # Define expected columns and create rename mapping
                        expected_columns = {
                            "symbol": "SYMBOL",
                            "date": "TRADE_DATE",
                            "open": "OPEN_PRICE",
                            "high": "HIGH_PRICE",
                            "low": "LOW_PRICE",
                            "close": "CLOSE_PRICE",
                            "volume": "VOLUME",
                            "open_interest": "OPEN_INTEREST",
                            "turnover": "TURNOVER",
                            "settle": "SETTLE_PRICE",
                            "pre_settle": "PREV_SETTLE",
                            "variety": "VARIETY",
                        }

                        # Create a rename mapping only for columns that exist
                        rename_dict = {k: v for k, v in expected_columns.items() if k in df.columns}
                        df.rename(columns=rename_dict, inplace=True)

                        # Add missing columns with NaN values
                        for old_col, new_col in expected_columns.items():
                            if new_col not in df.columns:
                                self.logger.warning(
                                    f"Column {old_col} missing in data, adding {new_col} with NaN values"
                                )
                                df[new_col] = None

                        # Add custom and default columns
                        df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                        df["REFERENCE_CODE"] = "FUTURES_DAILY"
                        df["REFERENCE_NAME"] = "期货历史行情数据"
                        df["MARKET"] = market
                        df["IS_ACTIVE"] = 1
                        df["DATA_SOURCE"] = "交易所"
                        df["CREATEUSER"] = "system"
                        df["UPDATEUSER"] = "system"

                        # Format and clean data
                        # Safely convert date column
                        try:
                            df["TRADE_DATE"] = pd.to_datetime(
                                df["TRADE_DATE"], format="%Y%m%d", errors="coerce"
                            ).dt.strftime("%Y-%m-%d")
                        except Exception as e:
                            self.logger.warning(f"Error formatting TRADE_DATE: {e}")

                        # Handle numeric columns
                        numeric_cols = [
                            "OPEN_PRICE",
                            "HIGH_PRICE",
                            "LOW_PRICE",
                            "CLOSE_PRICE",
                            "SETTLE_PRICE",
                            "PREV_SETTLE",
                            "VOLUME",
                            "OPEN_INTEREST",
                            "TURNOVER",
                        ]
                        for col in numeric_cols:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors="coerce")

                        # Ensure VARIETY has values
                        if "VARIETY" in df.columns and df["VARIETY"].isna().any():
                            # Extract variety from symbol where missing
                            df.loc[df["VARIETY"].isna(), "VARIETY"] = df.loc[
                                df["VARIETY"].isna(), "SYMBOL"
                            ].str.extract(r"([A-Za-z]+)", expand=False)
                            self.logger.info(
                                f"Filled {df['VARIETY'].isna().sum()} missing VARIETY values"
                            )

                        # Remove rows with missing essential data
                        if "SYMBOL" in df.columns and "TRADE_DATE" in df.columns:
                            before_count = len(df)
                            df = df.dropna(subset=["SYMBOL", "TRADE_DATE"])
                            dropped_count = before_count - len(df)
                            if dropped_count > 0:
                                self.logger.warning(
                                    f"Dropped {dropped_count} rows with missing SYMBOL or TRADE_DATE"
                                )

                        # Remove duplicate records before saving
                        if len(df) > 0:
                            before_dedup = len(df)
                            df = df.drop_duplicates(subset=["SYMBOL", "TRADE_DATE"])
                            dupes_removed = before_dedup - len(df)
                            if dupes_removed > 0:
                                self.logger.info(f"Removed {dupes_removed} duplicate records")

                            # 4. Save to DB
                            try:
                                if len(df) > 0:
                                    self.logger.info(f"Saving {len(df)} records to database")
                                    df = df.replace(np.nan, None)
                                    self.save_data(
                                        df,
                                        table_name,
                                        unique_keys=["SYMBOL", "TRADE_DATE"],
                                    )
                                    self.logger.info("Data saved successfully")
                                else:
                                    self.logger.warning("No valid data to save after filtering")
                            except Exception as e:
                                self.logger.error(
                                    f"Error saving data to database: {e}", exc_info=True
                                )
                                raise
                        else:
                            self.logger.warning("No data to save after processing")

                        current_start += relativedelta(days=7)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to process data for {market} in range {start_str}-{end_str}: {e}",
                            exc_info=True,
                        )
                        # Move to next period if there's an error
                        current_start += relativedelta(days=7)

            except Exception as e:
                self.logger.error(
                    f"An error occurred while processing market {market}: {e}",
                    exc_info=True,
                )
                continue

        self.logger.info("Futures daily market data update for all exchanges finished.")


if __name__ == "__main__":
    data_updater = FuturesDailyMarket()
    data_updater.run()
