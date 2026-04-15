import time

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundPurchaseStatusEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_PURCHASE_STATUS_EM"
        self.create_table_sql = r"""
                                CREATE TABLE `FUND_PURCHASE_STATUS_EM` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_PURCHASE_STATUS' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金申购状态表(东方财富)' COMMENT '参考名称',

                                      -- 基金基础信息
                                      `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                                      `FUND_NAME` VARCHAR(200) COMMENT '基金简称',
                                      `FUND_TYPE` VARCHAR(50) COMMENT '基金类型',

                                      -- 净值信息
                                      `NAV` DECIMAL(10, 6) COMMENT '最新净值/万份收益',
                                      `NAV_DATE` DATE COMMENT '最新净值/万份收益-报告时间',

                                      -- 申赎状态
                                      `PURCHASE_STATUS` VARCHAR(20) COMMENT '申购状态',
                                      `REDEMPTION_STATUS` VARCHAR(20) COMMENT '赎回状态',
                                      `NEXT_OPEN_DATE` DATE COMMENT '下一开放日',

                                      -- 交易限制
                                      `MIN_PURCHASE_AMOUNT` DECIMAL(18, 2) COMMENT '购买起点(元)',
                                      `DAILY_PURCHASE_LIMIT` DECIMAL(20, 2) COMMENT '日累计限定金额(元)',
                                      `FEE_RATE` DECIMAL(8, 4) COMMENT '手续费(%)',

                                      -- 系统字段
                                      `BASEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '基础时间',
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_FUND_CODE_DATE` (`FUND_CODE`, `NAV_DATE`, `BASEDATE`),
                                      KEY `IDX_FUND_NAME` (`FUND_NAME`),
                                      KEY `IDX_FUND_TYPE` (`FUND_TYPE`),
                                      KEY `IDX_PURCHASE_STATUS` (`PURCHASE_STATUS`),
                                      KEY `IDX_REDEMPTION_STATUS` (`REDEMPTION_STATUS`),
                                      KEY `IDX_NAV_DATE` (`NAV_DATE`),
                                      KEY `IDX_BASEDATE` (`BASEDATE`),
                                      KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`),
                                      FULLTEXT KEY `IDX_FULLTEXT_SEARCH` (`FUND_NAME`, `FUND_CODE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金申购状态表(东方财富)';

                                """

    def run(self):
        """
        Fetches and stores the current purchase and redemption status for all funds.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting fund purchase status update.")
        table_name = "FUND_PURCHASE_STATUS_EM"

        try:
            # 1. Fetch Data
            self.logger.info("Fetching all fund purchase status data from Eastmoney.")
            # df = ak.fund_purchase_em()
            df = self.fetch_ak_data("fund_purchase_em")
            time.sleep(2)  # Be respectful

            if df.empty:
                self.logger.warning("No fund status data returned from Eastmoney.")
                return

            # 2. Data Transformation
            df.rename(
                columns={
                    "基金代码": "FUND_CODE",
                    "基金简称": "FUND_NAME",
                    "基金类型": "FUND_TYPE",
                    "最新净值/万份收益": "NAV",
                    "最新净值/万份收益-报告时间": "NAV_DATE",
                    "申购状态": "PURCHASE_STATUS",
                    "赎回状态": "REDEMPTION_STATUS",
                    "下一开放日": "NEXT_OPEN_DATE",
                    "购买起点": "MIN_PURCHASE_AMOUNT",
                    "日累计限定金额": "DAILY_PURCHASE_LIMIT",
                    "手续费": "FEE_RATE",
                },
                inplace=True,
            )

            # Drop the original index column if it exists
            df.drop(columns=["序号"], inplace=True, errors="ignore")

            # Add system columns
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["REFERENCE_CODE"] = "FUND_PURCHASE_STATUS"
            df["REFERENCE_NAME"] = "基金申购状态表(东方财富)"
            df["BASEDATE"] = self.get_current_date()
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"
            df["CREATEUSER"] = "system"
            df["UPDATEUSER"] = "system"

            # Clean and format data
            df["FEE_RATE"] = pd.to_numeric(df["FEE_RATE"], errors="coerce") / 100
            date_cols = ["NAV_DATE", "NEXT_OPEN_DATE"]
            for col in date_cols:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")
            df = df.replace(np.nan, None)
            # 3. Save to DB
            self.save_data(
                df,
                table_name,
                on_duplicate_update=True,
                unique_keys=["FUND_CODE", "NAV_DATE", "BASEDATE"],
            )

            self.logger.info("Fund purchase status update finished successfully.")

        except Exception as e:
            self.logger.error(f"An error occurred during the update process: {e}", exc_info=True)
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FundPurchaseStatusEm()
    data_updater.run()
