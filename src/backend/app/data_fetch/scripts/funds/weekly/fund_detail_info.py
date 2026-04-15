import os
import pickle
import random
import re

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

# from random import shuffle


class FundDetailInfoXq(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_DETAIL_INFO_XQ"
        self.create_table_sql = r"""
                                CREATE TABLE `FUND_DETAIL_INFO_XQ` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_DETAIL_INFO' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金详细信息表(雪球)' COMMENT '参考名称',

                                      -- 基金基础信息
                                      `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                                      `FUND_NAME` VARCHAR(100) COMMENT '基金名称',
                                      `FULL_NAME` VARCHAR(200) COMMENT '基金全称',
                                      `ESTABLISH_DATE` DATE COMMENT '成立日期',
                                      `LATEST_SCALE` DECIMAL(20, 2) COMMENT '最新规模(亿元)',
                                      `FUND_COMPANY` VARCHAR(100) COMMENT '基金公司',
                                      `FUND_MANAGER` VARCHAR(200) COMMENT '基金经理',
                                      `CUSTODIAN_BANK` VARCHAR(100) COMMENT '托管银行',
                                      `FUND_TYPE` VARCHAR(50) COMMENT '基金类型',
                                      `RATING_AGENCY` VARCHAR(50) COMMENT '评级机构',
                                      `FUND_RATING` VARCHAR(50) COMMENT '基金评级',
                                      `INVESTMENT_STRATEGY` TEXT COMMENT '投资策略',
                                      `INVESTMENT_OBJECTIVE` TEXT COMMENT '投资目标',
                                      `BENCHMARK` TEXT COMMENT '业绩比较基准',

                                      -- 系统字段
                                      `BASEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '基础时间',
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '雪球' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_FUND_CODE` (`FUND_CODE`, `BASEDATE`),
                                      KEY `IDX_FUND_NAME` (`FUND_NAME`),
                                      KEY `IDX_FUND_COMPANY` (`FUND_COMPANY`),
                                      KEY `IDX_FUND_TYPE` (`FUND_TYPE`),
                                      KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`),
                                      FULLTEXT KEY `IDX_FULLTEXT_SEARCH` (`FUND_NAME`, `FULL_NAME`, `FUND_COMPANY`, `FUND_MANAGER`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金详细信息表(雪球)';

                                """

    def run(self):
        """
        Fetches and stores detailed information for funds that are not yet in the detail table.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting fund detail information update.")
        table_name = "FUND_DETAIL_INFO_XQ"
        if not os.path.exists("lost_codes.pkl"):
            lost_codes = []
        else:
            with open("lost_codes.pkl", "rb") as f:
                lost_codes = pickle.load(f)
        try:
            # 1. Get lists of funds
            all_codes = self.get_data_by_columns("FUND_BASIC_INFO_EM", ["FUND_CODE"])
            self.logger.info(f"Found {len(all_codes)} existing funds in the database.")
            exists_codes = self.get_data_by_columns(table_name, ["FUND_CODE"])
            self.logger.info(f"Found {len(exists_codes)} existing funds in the database.")
            codes_to_fetch = set(all_codes["FUND_CODE"].to_list()) - set(
                exists_codes["FUND_CODE"].to_list()
            )
            if not codes_to_fetch:
                self.logger.info(
                    "All funds already have their details in the database. No update needed."
                )
                return

            self.logger.info(f"Found {len(codes_to_fetch)} funds that need detail information.")

            # 2. Fetch and process data for each fund
            all_new_details = []
            codes_to_fetch = list(codes_to_fetch)
            count = 0
            random.shuffle(codes_to_fetch)
            for symbol in codes_to_fetch:
                if symbol in lost_codes:
                    self.logger.info(f"Skipping {symbol} as it failed before.")
                    continue
                try:
                    count += 1
                    self.logger.info(f"Fetching {count} details for fund: {symbol}")
                    # df = ak.fund_individual_basic_info_xq(symbol=symbol)
                    df = self.fetch_ak_data("fund_individual_basic_info_xq", symbol)
                    # time.sleep(1) # Be respectful
                    if df.empty or "item" not in df.columns or "value" not in df.columns:
                        self.logger.warning(f"No or invalid data returned for {symbol}.")
                        continue

                    # 3. Pivot and clean data
                    detail_series = df.set_index("item")["value"]
                    detail_df = pd.DataFrame([detail_series])

                    detail_df.rename(
                        columns={
                            "基金代码": "FUND_CODE",
                            "基金名称": "FUND_NAME",
                            "基金全称": "FULL_NAME",
                            "成立时间": "ESTABLISH_DATE",
                            "最新规模": "LATEST_SCALE",
                            "基金公司": "FUND_COMPANY",
                            "基金经理": "FUND_MANAGER",
                            "托管银行": "CUSTODIAN_BANK",
                            "基金类型": "FUND_TYPE",
                            "评级机构": "RATING_AGENCY",
                            "基金评级": "FUND_RATING",
                            "投资策略": "INVESTMENT_STRATEGY",
                            "投资目标": "INVESTMENT_OBJECTIVE",
                            "业绩比较基准": "BENCHMARK",
                        },
                        inplace=True,
                    )

                    # Clean LATEST_SCALE (e.g., "27.30亿" -> 27.30)
                    if "LATEST_SCALE" in detail_df.columns:
                        scale_str = detail_df["LATEST_SCALE"].iloc[0]
                        if isinstance(scale_str, str):
                            scale_match = re.search(r"[\d\.]+", scale_str)
                            if scale_match:
                                detail_df["LATEST_SCALE"] = pd.to_numeric(
                                    scale_match.group(0), errors="coerce"
                                )
                            else:
                                detail_df["LATEST_SCALE"] = None

                    # Add system columns
                    detail_df["R_ID"] = [self.get_uuid() for _ in range(len(detail_df))]
                    detail_df["REFERENCE_CODE"] = "FUND_DETAIL_INFO"
                    detail_df["REFERENCE_NAME"] = "基金详细信息表(雪球)"
                    detail_df["IS_ACTIVE"] = 1
                    detail_df["DATA_SOURCE"] = "雪球"
                    detail_df["CREATEUSER"] = "system"
                    detail_df["UPDATEUSER"] = "system"

                    all_new_details.append(detail_df)

                except Exception as e:
                    self.logger.error(
                        f"Failed to process details for fund {symbol}: {e}",
                        exc_info=True,
                    )
                    lost_codes.append(symbol)
                    continue
            with open("lost_codes.pkl", "wb") as f:
                pickle.dump(lost_codes, f)
            # 4. Combine and save all new records
            if all_new_details:
                final_df = pd.concat(all_new_details, ignore_index=True)
                # final_df = final_df.fillna(None)
                final_df = final_df.replace({pd.NA: None, np.nan: None})
                self.save_data(final_df, table_name)

            self.logger.info("Fund detail information update finished successfully.")

        except Exception as e:
            self.logger.error(
                f"An error occurred during the main update process: {e}", exc_info=True
            )
        finally:
            self.disconnect_db()
            with open("lost_codes.pkl", "wb") as f:
                pickle.dump(lost_codes, f)


if __name__ == "__main__":
    data_updater = FundDetailInfoXq()
    data_updater.run()
