from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesDeliveryMatchCzce(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_DELIVERY_MATCH_CZCE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_DELIVERY_MATCH_CZCE` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'CZCE_DELIVERY_MATCH' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '郑州商品交易所交割配对' COMMENT '参考名称',
                                      `SELLER_MEMBER_ID` VARCHAR(20) NOT NULL COMMENT '卖方会员代码',
                                      `SELLER_MEMBER_NAME` VARCHAR(100) COMMENT '卖方会员简称',
                                      `BUYER_MEMBER_ID` VARCHAR(20) NOT NULL COMMENT '买方会员代码',
                                      `BUYER_MEMBER_NAME` VARCHAR(100) COMMENT '买方会员简称',
                                      `DELIVERY_VOLUME` DECIMAL(18, 4) NOT NULL COMMENT '交割量(手)',
                                      `MATCH_DATE` DATE NOT NULL COMMENT '配对日期',
                                      `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                      `PRODUCT_CATEGORY` VARCHAR(10) GENERATED ALWAYS AS (UPPER(SUBSTRING(CONTRACT_CODE, 1, 2))) STORED COMMENT '品种代码',
                                      `UNIT` VARCHAR(10) DEFAULT '手' COMMENT '单位',
                                      `CURRENCY` VARCHAR(3) DEFAULT 'CNY' COMMENT '币种',
                                      `TRADE_DATE` DATE COMMENT '交易日期(数据获取日期)',
                                      `CREATEDATE` DATETIME COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                      PRIMARY KEY (`R_ID`),
                                      -- UNIQUE KEY `IDX_CZCE_DELIVERY_MATCH_UNIQUE` (`SELLER_MEMBER_ID`, `BUYER_MEMBER_ID`, `CONTRACT_CODE`, `MATCH_DATE`, `DELIVERY_VOLUME`),
                                      KEY `IDX_CZCE_DELIVERY_MATCH_CONTRACT` (`CONTRACT_CODE`),
                                      KEY `IDX_CZCE_DELIVERY_MATCH_DATE` (`MATCH_DATE`),
                                      KEY `IDX_CZCE_DELIVERY_MATCH_SELLER` (`SELLER_MEMBER_ID`),
                                      KEY `IDX_CZCE_DELIVERY_MATCH_BUYER` (`BUYER_MEMBER_ID`),
                                      KEY `IDX_CZCE_DELIVERY_MATCH_PRODUCT` (`PRODUCT_CATEGORY`),
                                      KEY `IDX_CZCE_DELIVERY_MATCH_TRADE_DATE` (`TRADE_DATE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='郑州商品交易所交割配对表';

                                """

    def run(self, start_date=None, end_date=None):
        """
        更新郑州商品交易所交割配对数据。

        :param start_date: 开始日期，格式为'YYYY-MM-DD'，如果为None则从数据库最新日期或最早可用日期开始
        :param end_date: 结束日期，格式为'YYYY-MM-DD'，如果为None则为当前日期前一天
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("正在获取郑州商品交易所交割配对数据")
        table_name = "FUTURES_DELIVERY_MATCH_CZCE"

        try:
            # 1. Date Handling
            if end_date is None:
                end_date = self.get_previous_date()

            if start_date is None:
                latest_date_in_db = self.get_latest_date(table_name, "TRADE_DATE")
                if latest_date_in_db:
                    start_date = (
                        datetime.strptime(latest_date_in_db, "%Y-%m-%d") + timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                    self.logger.info(f"最新数据日期: {latest_date_in_db}，从 {start_date} 开始更新")
                else:
                    start_date = "2025-07-01"  # Earliest data found in example
                    self.logger.info(f"无历史数据，从 {start_date} 开始获取")

            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

            if start_date_dt > end_date_dt:
                self.logger.info(f"开始日期 {start_date} 不能晚于结束日期 {end_date}")
                return pd.DataFrame()

            trading_days = self.get_trading_day_list(
                start_date_dt.strftime("%Y-%m-%d"), end_date_dt.strftime("%Y-%m-%d")
            )

            if not trading_days:
                self.logger.info("在指定范围内没有需要更新的交易日")
                return pd.DataFrame()

            self.logger.info(
                f"准备更新从 {trading_days[0]} 到 {trading_days[-1]} 的交割配对数据，共 {len(trading_days)} 个交易日"
            )

            all_dfs = []
            success_count = 0
            failed_dates = []

            # 2. Data Fetching and Processing Loop
            for date_str in trading_days:
                try:
                    self.logger.info(f"正在获取 {date_str} 的交割配对数据")

                    # Fetch data
                    # ak.futures_delivery_match_czce takes date in YYYYMMDD format
                    # df = ak.futures_delivery_match_czce(date=date_str.replace('-', ''))
                    df = self.fetch_ak_data(
                        "futures_delivery_match_czce", date_str.replace("-", "")
                    )

                    if df is None or df.empty:
                        self.logger.warning(f"未获取到 {date_str} 的交割配对数据")
                        continue

                    # Rename columns
                    df.rename(
                        columns={
                            "卖方会员": "SELLER_MEMBER_ID",
                            "卖方会员-会员简称": "SELLER_MEMBER_NAME",
                            "买方会员": "BUYER_MEMBER_ID",
                            "买方会员-会员简称": "BUYER_MEMBER_NAME",
                            "交割量": "DELIVERY_VOLUME",
                            "配对日期": "MATCH_DATE",
                            "合约代码": "CONTRACT_CODE",
                        },
                        inplace=True,
                    )

                    # Add system columns
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = "CZCE_DELIVERY_MATCH"
                    df["REFERENCE_NAME"] = "郑州商品交易所交割配对"
                    # PRODUCT_CATEGORY is a generated column, don't include it in the insert
                    df["UNIT"] = "手"
                    df["CURRENCY"] = "CNY"
                    df["TRADE_DATE"] = date_str  # The date for which data was fetched

                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"

                    # Convert data types
                    df["DELIVERY_VOLUME"] = pd.to_numeric(
                        df["DELIVERY_VOLUME"], errors="coerce"
                    ).fillna(0.0)
                    df["MATCH_DATE"] = pd.to_datetime(df["MATCH_DATE"]).dt.strftime("%Y-%m-%d")

                    # Ensure all required columns exist and are in the correct order
                    # Exclude PRODUCT_CATEGORY as it's a generated column
                    required_columns = [
                        "R_ID",
                        "REFERENCE_CODE",
                        "REFERENCE_NAME",
                        "SELLER_MEMBER_ID",
                        "SELLER_MEMBER_NAME",
                        "BUYER_MEMBER_ID",
                        "BUYER_MEMBER_NAME",
                        "DELIVERY_VOLUME",
                        "MATCH_DATE",
                        "CONTRACT_CODE",
                        "UNIT",
                        "CURRENCY",
                        "TRADE_DATE",
                        "CREATEDATE",
                        "CREATEUSER",
                        "UPDATEDATE",
                        "UPDATEUSER",
                    ]

                    for col in required_columns:
                        if col not in df.columns:
                            df[col] = None

                    # Reorder columns to match DDL (optional)
                    df = df[required_columns]
                    df = df.replace(np.nan, None)
                    # Save to database
                    self.save_data(df, table_name)
                    success_count += 1
                    self.logger.info(f"成功保存 {date_str} 的交割配对数据，共 {len(df)} 条记录")
                    all_dfs.append(df)

                except Exception as e:
                    self.logger.error(f"处理 {date_str} 数据时出错: {str(e)}")
                    failed_dates.append(date_str)
                    continue

            # 3. Summary
            if success_count > 0:
                self.logger.info(f"成功更新 {success_count} 个交易日的交割配对数据")
                final_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            else:
                self.logger.warning("没有成功更新任何数据")
                final_df = pd.DataFrame()

            if failed_dates:
                self.logger.warning(f"以下日期的数据处理失败: {', '.join(failed_dates)}")

            return final_df

        except Exception as e:
            self.logger.error(f"更新郑州商品交易所交割配对数据失败: {str(e)}")
            raise
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesDeliveryMatchCzce()
    data_updater.run()
