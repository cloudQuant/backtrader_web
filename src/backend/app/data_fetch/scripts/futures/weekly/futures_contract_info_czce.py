import re
import time
from datetime import datetime, timedelta

import numpy as np

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesContractInfoCzce(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_CONTRACT_INFO_CZCE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_CONTRACT_INFO_CZCE` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'CZCE_CONTRACT_INFO' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '郑州商品交易所合约信息' COMMENT '参考名称',

                                      -- 基本信息
                                      `PRODUCT_NAME` VARCHAR(50) COMMENT '产品名称',
                                      `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                      `PRODUCT_CODE` VARCHAR(20) COMMENT '产品代码',
                                      `PRODUCT_TYPE` VARCHAR(20) COMMENT '产品类型',
                                      `EXCHANGE_MIC` VARCHAR(20) COMMENT '交易所MIC编码',
                                      `TRADING_VENUE` VARCHAR(100) COMMENT '交易场所',

                                      -- 交易时间信息
                                      `TRADING_HOURS` VARCHAR(200) COMMENT '交易时间(节假日除外)',
                                      `TRADE_DATE` DATE NOT NULL COMMENT '数据日期',

                                      -- 国家/货币信息
                                      `COUNTRY_ISO` VARCHAR(10) COMMENT '交易国家ISO编码',
                                      `TRADE_CURRENCY` VARCHAR(10) COMMENT '交易币种ISO编码',
                                      `SETTLEMENT_CURRENCY` VARCHAR(10) COMMENT '结算币种ISO编码',
                                      `FEE_CURRENCY` VARCHAR(10) COMMENT '费用币种ISO编码',

                                      -- 交易参数
                                      `TRADING_UNIT` VARCHAR(50) COMMENT '交易单位',
                                      `PRICE_TICK` VARCHAR(50) COMMENT '最小变动价位',
                                      `TICK_VALUE` VARCHAR(50) COMMENT '最小变动价值',
                                      `UNIT` VARCHAR(20) COMMENT '计量单位',
                                      `MAX_ORDER_VOLUME` VARCHAR(50) COMMENT '最大下单量',
                                      `DAILY_POSITION_LIMIT` VARCHAR(100) COMMENT '日持仓限额',
                                      `BLOCK_TRADE_MIN_VOLUME` VARCHAR(50) COMMENT '大宗交易最小规模',

                                      -- 合约状态
                                      `IS_CESR_REGULATED` VARCHAR(10) COMMENT '是否受CESR监管',
                                      `IS_FLEX_CONTRACT` VARCHAR(10) COMMENT '是否为灵活合约',
                                      `LISTING_CYCLE` TEXT COMMENT '上市周期(该产品的所有合约月份)',

                                      -- 日期信息
                                      `FIRST_TRADE_DATE` DATE COMMENT '第一交易日',
                                      `EXPIRY_DATE` DATE COMMENT '最后交易日',
                                      `DELIVERY_NOTICE_DAY` VARCHAR(50) COMMENT '交割通知日',
                                      `SETTLEMENT_DAY` DATE COMMENT '交割结算日',
                                      `MONTH_CODE` VARCHAR(10) COMMENT '月份代码',
                                      `YEAR_CODE` VARCHAR(10) COMMENT '年份代码',
                                      `DELIVERY_END_DATE` DATE COMMENT '最后交割日',
                                      `BOARD_LOT_END_DATE` DATE COMMENT '车(船)板最后交割日',
                                      `DELIVERY_MONTH` VARCHAR(10) COMMENT '合约交割月份',

                                      -- 费用信息
                                      `TRADING_FEE` DECIMAL(18, 4) COMMENT '交易手续费',
                                      `FEE_TYPE` VARCHAR(20) COMMENT '手续费收取方式',
                                      `DELIVERY_FEE` DECIMAL(18, 4) COMMENT '交割手续费',
                                      `INTRA_DAY_FEE` DECIMAL(18, 4) COMMENT '平今仓手续费',
                                      `TRADING_LIMIT` DECIMAL(18, 4) COMMENT '交易限额',

                                      -- 风险控制
                                      `MARGIN_RATE` VARCHAR(20) COMMENT '交易保证金率',
                                      `PRICE_LIMIT` VARCHAR(20) COMMENT '涨跌停板',

                                      -- 系统字段
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效合约(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '郑州商品交易所' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_CZCE_CONTRACT_UNIQUE` (`CONTRACT_CODE`, `TRADE_DATE`),
                                      KEY `IDX_CZCE_CONTRACT_CODE` (`CONTRACT_CODE`),
                                      KEY `IDX_CZCE_TRADE_DATE` (`TRADE_DATE`),
                                      KEY `IDX_CZCE_PRODUCT_CODE` (`PRODUCT_CODE`),
                                      KEY `IDX_CZCE_PRODUCT_NAME` (`PRODUCT_NAME`),
                                      KEY `IDX_CZCE_DELIVERY_MONTH` (`DELIVERY_MONTH`),
                                      KEY `IDX_CZCE_IS_ACTIVE` (`IS_ACTIVE`),
                                      KEY `IDX_CZCE_EXPIRY_DATE` (`EXPIRY_DATE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='郑州商品交易所合约信息表';

                                """

    def run(self, start_date=None, end_date=None):
        """
        Fetches and stores daily contract information from the Zhengzhou Commodity Exchange (CZCE).
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting CZCE contract info update.")
        table_name = "FUTURES_CONTRACT_INFO_CZCE"

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
                    start_date = "2023-01-03"  # Default start date
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
                    df = self.fetch_ak_data(
                        "futures_contract_info_czce", trade_date.replace("-", "")
                    )
                    time.sleep(2)  # Be respectful

                    if df.empty:
                        self.logger.warning(f"No data returned for {trade_date}.")
                        continue

                    # 3. Data Transformation
                    # Clean up column names that have extra descriptions
                    df.columns = [
                        re.sub(
                            r"(.*?)(待国家公布|节假日除外|期货公司会员不限仓|本合约交割月份).*$",
                            r"\1",
                            col,
                        )
                        for col in df.columns
                    ]
                    # print(df[["到期时间", "最后交易日", "第一交易日"]])
                    # print(df["结算方式"])
                    # print(df.columns)
                    # if "到期时间" in df.columns:
                    #     df.drop(columns=["到期时间"], inplace=True)
                    # if "结算方式" in df.columns:
                    #     df.drop(columns=["结算方式"], inplace=True)
                    df.rename(
                        columns={
                            "产品名称": "PRODUCT_NAME",
                            "合约代码": "CONTRACT_CODE",
                            "产品代码": "PRODUCT_CODE",
                            "产品类型": "PRODUCT_TYPE",
                            "交易所MIC编码": "EXCHANGE_MIC",
                            "交易场所": "TRADING_VENUE",
                            "交易时间": "TRADING_HOURS",
                            "交易国家ISO编码": "COUNTRY_ISO",
                            "交易币种ISO编码": "TRADE_CURRENCY",
                            "结算币种ISO编码": "SETTLEMENT_CURRENCY",
                            "费用币种ISO编码": "FEE_CURRENCY",
                            "交易单位": "TRADING_UNIT",
                            "最小变动价位": "PRICE_TICK",
                            "最小变动价值": "TICK_VALUE",
                            "计量单位": "UNIT",
                            "最大下单量": "MAX_ORDER_VOLUME",
                            "日持仓限额": "DAILY_POSITION_LIMIT",
                            "大宗交易最小规模": "BLOCK_TRADE_MIN_VOLUME",
                            "是否受CESR监管": "IS_CESR_REGULATED",
                            "是否为灵活合约": "IS_FLEX_CONTRACT",
                            "上市周期": "LISTING_CYCLE",
                            "第一交易日": "FIRST_TRADE_DATE",
                            "最后交易日": "EXPIRY_DATE",
                            "交割通知日": "DELIVERY_NOTICE_DAY",
                            "交割结算日": "SETTLEMENT_DAY",
                            "月份代码": "MONTH_CODE",
                            "年份代码": "YEAR_CODE",
                            "最后交割日": "DELIVERY_END_DATE",
                            "车（船）板最后交割日": "BOARD_LOT_END_DATE",
                            "合约交割月份": "DELIVERY_MONTH",
                            "交易手续费": "TRADING_FEE",
                            "手续费收取方式": "FEE_TYPE",
                            "交割手续费": "DELIVERY_FEE",
                            "平今仓手续费": "INTRA_DAY_FEE",
                            "交易限额": "TRADING_LIMIT",
                            "交易保证金率": "MARGIN_RATE",
                            "涨跌停板": "PRICE_LIMIT",
                        },
                        inplace=True,
                    )

                    # Add custom and default columns
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["TRADE_DATE"] = trade_date
                    df["REFERENCE_CODE"] = "CZCE_CONTRACT_INFO"
                    df["REFERENCE_NAME"] = "郑州商品交易所合约信息"
                    df["IS_ACTIVE"] = 1
                    df["DATA_SOURCE"] = "郑州商品交易所"
                    df["CREATEUSER"] = "system"
                    df["UPDATEUSER"] = "system"

                    # Format date columns
                    date_cols = [
                        "FIRST_TRADE_DATE",
                        "EXPIRY_DATE",
                        "SETTLEMENT_DAY",
                        "DELIVERY_END_DATE",
                        "BOARD_LOT_END_DATE",
                    ]
                    for col in date_cols:
                        df[col] = self.safe_date_format(df[col])
                    if "LISTING_CYCLE" not in df.columns:
                        df["LISTING_CYCLE"] = None
                    # 根据数据表，填写需要的列
                    required_columns = [
                        # 主键和参考信息
                        "R_ID",
                        "REFERENCE_CODE",
                        "REFERENCE_NAME",
                        # 基本信息
                        "PRODUCT_NAME",
                        "CONTRACT_CODE",
                        "PRODUCT_CODE",
                        "PRODUCT_TYPE",
                        "EXCHANGE_MIC",
                        "TRADING_VENUE",
                        # 交易时间信息
                        "TRADING_HOURS",
                        "TRADE_DATE",
                        # 国家/货币信息
                        "COUNTRY_ISO",
                        "TRADE_CURRENCY",
                        "SETTLEMENT_CURRENCY",
                        "FEE_CURRENCY",
                        # 交易参数
                        "TRADING_UNIT",
                        "PRICE_TICK",
                        "TICK_VALUE",
                        "UNIT",
                        "MAX_ORDER_VOLUME",
                        "DAILY_POSITION_LIMIT",
                        "BLOCK_TRADE_MIN_VOLUME",
                        # 合约状态
                        "IS_CESR_REGULATED",
                        "IS_FLEX_CONTRACT",
                        "LISTING_CYCLE",
                        # 日期信息
                        "FIRST_TRADE_DATE",
                        "EXPIRY_DATE",
                        "DELIVERY_NOTICE_DAY",
                        "SETTLEMENT_DAY",
                        "MONTH_CODE",
                        "YEAR_CODE",
                        "DELIVERY_END_DATE",
                        "BOARD_LOT_END_DATE",
                        "DELIVERY_MONTH",
                        # 费用信息
                        "TRADING_FEE",
                        "FEE_TYPE",
                        "DELIVERY_FEE",
                        "INTRA_DAY_FEE",
                        "TRADING_LIMIT",
                        # 风险控制
                        "MARGIN_RATE",
                        "PRICE_LIMIT",
                        # 系统字段
                        "IS_ACTIVE",
                        "DATA_SOURCE",
                        "CREATEUSER",
                        "UPDATEUSER",
                    ]
                    df = df[required_columns]
                    df = df.replace(np.nan, None)
                    # 4. Save to DB
                    self.save_data(df, table_name, unique_keys=["CONTRACT_CODE", "TRADE_DATE"])

                except Exception as e:
                    self.logger.error(
                        f"Failed to process data for {trade_date}: {e}", exc_info=True
                    )
                    continue

            self.logger.info("CZCE contract info update finished.")

        except Exception as e:
            self.logger.error(
                f"An error occurred during the main CZCE update process: {e}",
                exc_info=True,
            )
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesContractInfoCzce()
    data_updater.run()
