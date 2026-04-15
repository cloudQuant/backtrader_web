import time

import numpy as np

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundBasicInfoEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_BASIC_INFO_EM"
        self.create_table_sql = r"""
                                CREATE TABLE `FUND_BASIC_INFO_EM` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_BASIC_INFO' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金基本信息(东方财富)' COMMENT '参考名称',

                                      -- 基金基础信息
                                      `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                                      `FUND_SHORT_NAME` VARCHAR(100) COMMENT '基金简称',
                                      `FUND_TYPE` VARCHAR(50) COMMENT '基金类型',
                                      `PINYIN_ABBR` VARCHAR(50) COMMENT '拼音缩写',
                                      `PINYIN_FULL` VARCHAR(200) COMMENT '拼音全称',

                                      -- 系统字段
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_FUND_CODE` (`FUND_CODE`),
                                      KEY `IDX_FUND_TYPE` (`FUND_TYPE`),
                                      KEY `IDX_PINYIN_ABBR` (`PINYIN_ABBR`),
                                      KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金基本信息表(东方财富)';

                                """

    def run(self):
        """
        Fetches and stores only new fund basic information from Eastmoney.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting fund basic information update (new funds only).")
        table_name = "FUND_BASIC_INFO_EM"

        try:
            # 1. Fetch all fund data from the source
            self.logger.info("Fetching all fund basic info from Eastmoney.")
            # source_df = ak.fund_name_em()
            source_df = self.fetch_ak_data("fund_name_em")
            time.sleep(2)  # Be respectful

            if source_df.empty:
                self.logger.warning("No fund data returned from Eastmoney.")
                return

            source_df.rename(
                columns={
                    "基金代码": "FUND_CODE",
                    "拼音缩写": "PINYIN_ABBR",
                    "基金简称": "FUND_SHORT_NAME",
                    "基金类型": "FUND_TYPE",
                    "拼音全称": "PINYIN_FULL",
                },
                inplace=True,
            )

            # 2. Get existing fund codes from the database
            existing_codes = self.get_data_by_columns(table_name, ["FUND_CODE"])
            self.logger.info(f"Found {len(existing_codes)} existing funds in the database.")

            # 3. Filter for new funds only
            new_funds_df = source_df[
                ~source_df["FUND_CODE"].isin(existing_codes["FUND_CODE"])
            ].copy()

            if new_funds_df.empty:
                self.logger.info("No new funds found to add to the database.")
                return

            self.logger.info(f"Found {len(new_funds_df)} new funds to be inserted.")

            # 4. Prepare and save the new data
            new_funds_df["R_ID"] = [self.get_uuid() for _ in range(len(new_funds_df))]
            new_funds_df["REFERENCE_CODE"] = "FUND_BASIC_INFO"
            new_funds_df["REFERENCE_NAME"] = "基金基本信息(东方财富)"
            new_funds_df["IS_ACTIVE"] = 1
            new_funds_df["DATA_SOURCE"] = "东方财富"
            new_funds_df["CREATEUSER"] = "system"
            new_funds_df["UPDATEUSER"] = "system"
            new_funds_df = new_funds_df.replace(np.nan, None)
            self.save_data(new_funds_df, table_name)

            self.logger.info("Fund basic information update finished successfully.")

        except Exception as e:
            self.logger.error(f"An error occurred during the update process: {e}", exc_info=True)
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FundBasicInfoEm()
    data_updater.run()
