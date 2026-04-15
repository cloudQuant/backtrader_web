import re
import time
from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesContractInfoDce(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_CONTRACT_INFO_DCE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_CONTRACT_INFO_DCE` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'DCE_CONTRACT_INFO' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '大连商品交易所合约信息' COMMENT '参考名称',
                                      `PRODUCT_NAME` VARCHAR(20) NOT NULL COMMENT '品种名称',
                                      `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                      `TRADING_UNIT` INT COMMENT '交易单位(吨/手)',
                                      `PRICE_TICK` DECIMAL(10, 4) COMMENT '最小变动价位',
                                      `START_TRADE_DATE` DATE COMMENT '开始交易日',
                                      `EXPIRY_DATE` DATE COMMENT '最后交易日',
                                      `DELIVERY_END_DATE` DATE COMMENT '最后交割日',
                                      `TRADE_DATE` DATE NOT NULL COMMENT '数据日期',
                                      `UPDATE_TIME` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `PRODUCT_CATEGORY` VARCHAR(10) COMMENT '品种代码',
                                      `DELIVERY_MONTH` VARCHAR(6) COMMENT '交割月份(YYYYMM)',
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效合约(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '大连商品交易所' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_DCE_CONTRACT_UNIQUE` (`CONTRACT_CODE`, `TRADE_DATE`),
                                      KEY `IDX_DCE_CONTRACT_CODE` (`CONTRACT_CODE`),
                                      KEY `IDX_DCE_TRADE_DATE` (`TRADE_DATE`),
                                      KEY `IDX_DCE_PRODUCT_CATEGORY` (`PRODUCT_CATEGORY`),
                                      KEY `IDX_DCE_DELIVERY_MONTH` (`DELIVERY_MONTH`),
                                      KEY `IDX_DCE_IS_ACTIVE` (`IS_ACTIVE`),
                                      KEY `IDX_DCE_EXPIRY_DATE` (`EXPIRY_DATE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大连商品交易所合约信息表';

                                """

    def run(self):
        """
        Fetches and stores the latest daily contract information from the Dalian Commodity Exchange (DCE).
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("Starting DCE contract info update.")
        table_name = "FUTURES_CONTRACT_INFO_DCE"
        today_str = datetime.now().strftime("%Y-%m-%d")

        try:
            # 1. Check if data for today has already been fetched
            latest_date_in_db = self.get_latest_date(table_name, "TRADE_DATE")
            if latest_date_in_db == today_str:
                self.logger.info(
                    f"DCE contract data for {today_str} has already been updated. Skipping."
                )
                return

            # 2. Fetch Data
            self.logger.info("Fetching latest contract info from DCE.")
            # df = ak.futures_contract_info_dce()
            df = self.fetch_ak_data("futures_contract_info_dce")
            time.sleep(2)  # Be respectful to the server

            if df.empty:
                self.logger.warning("No data returned from DCE.")
                return

            # 3. Data Transformation
            df.rename(
                columns={
                    "品种": "PRODUCT_NAME",
                    "合约代码": "CONTRACT_CODE",
                    "交易单位": "TRADING_UNIT",
                    "最小变动价位": "PRICE_TICK",
                    "开始交易日": "START_TRADE_DATE",
                    "最后交易日": "EXPIRY_DATE",
                    "最后交割日": "DELIVERY_END_DATE",
                },
                inplace=True,
            )

            # Add custom and default columns
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["TRADE_DATE"] = today_str
            df["REFERENCE_CODE"] = "DCE_CONTRACT_INFO"
            df["REFERENCE_NAME"] = "大连商品交易所合约信息"
            df["PRODUCT_CATEGORY"] = df["CONTRACT_CODE"].str.extract(r"(^\D+)")[0].str.lower()

            def get_delivery_month(code):
                match = re.search(r"(\d{4})", str(code))
                if not match:
                    return None
                num_part = match.group(1)
                year_prefix = "20"  # Assuming all years are 20xx
                year = f"{year_prefix}{num_part[:2]}"
                month = num_part[2:]
                return f"{year}{month}"

            df["DELIVERY_MONTH"] = df["CONTRACT_CODE"].apply(get_delivery_month)
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "大连商品交易所"
            df["CREATEUSER"] = "system"
            df["UPDATEUSER"] = "system"
            df["UPDATE_TIME"] = self.get_current_datetime()

            # Format date columns
            date_cols = [
                "START_TRADE_DATE",
                "EXPIRY_DATE",
                "DELIVERY_END_DATE",
                "TRADE_DATE",
            ]
            for col in date_cols:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

            # 4. Save to DB
            self.save_data(df, table_name, unique_keys=["CONTRACT_CODE", "TRADE_DATE"])

            self.logger.info("DCE contract info update finished successfully.")

        except Exception as e:
            self.logger.error(
                f"An error occurred during the DCE update process: {e}", exc_info=True
            )
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesContractInfoDce()
    data_updater.run()
