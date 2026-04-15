import time

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundIndexInfoEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_INDEX_INFO_EM"
        self.create_table_sql = r"""
                                CREATE TABLE `FUND_INDEX_INFO_EM` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_INDEX_INFO' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '指数型基金信息表(东方财富)' COMMENT '参考名称',

                                      -- 基金基础信息
                                      `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                                      `FUND_NAME` VARCHAR(200) COMMENT '基金名称',
                                      `NAV` DECIMAL(10, 4) COMMENT '单位净值',
                                      `NAV_DATE` DATE COMMENT '净值日期',

                                      -- 收益率数据
                                      `DAILY_RETURN` DECIMAL(8, 4) COMMENT '日增长率(%)',
                                      `WEEKLY_RETURN` DECIMAL(8, 4) COMMENT '近1周(%)',
                                      `MONTHLY_RETURN` DECIMAL(8, 4) COMMENT '近1月(%)',
                                      `THREE_MONTH_RETURN` DECIMAL(8, 4) COMMENT '近3月(%)',
                                      `SIX_MONTH_RETURN` DECIMAL(8, 4) COMMENT '近6月(%)',
                                      `YEARLY_RETURN` DECIMAL(8, 4) COMMENT '近1年(%)',
                                      `TWO_YEAR_RETURN` DECIMAL(8, 4) COMMENT '近2年(%)',
                                      `THREE_YEAR_RETURN` DECIMAL(8, 4) COMMENT '近3年(%)',
                                      `YTD_RETURN` DECIMAL(8, 4) COMMENT '今年来(%)',
                                      `SINCE_INCEPTION_RETURN` DECIMAL(8, 4) COMMENT '成立来(%)',

                                      -- 费用和投资信息
                                      `FEE_RATE` DECIMAL(6, 4) COMMENT '手续费(%)',
                                      `MIN_INVESTMENT` VARCHAR(20) COMMENT '起购金额',
                                      `TARGET_INDEX` VARCHAR(100) COMMENT '跟踪标的',
                                      `TRACKING_METHOD` VARCHAR(50) COMMENT '跟踪方式',

                                      -- 查询参数
                                      `INDEX_CATEGORY` VARCHAR(50) COMMENT '指数类别',
                                      `FUND_TYPE` VARCHAR(50) COMMENT '基金类型',

                                      -- 系统字段
                                      `BASEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '基础时间',
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_FUND_CODE_DATE` (`FUND_CODE`, `NAV_DATE`),
                                      KEY `IDX_FUND_NAME` (`FUND_NAME`),
                                      KEY `IDX_TARGET_INDEX` (`TARGET_INDEX`),
                                      KEY `IDX_TRACKING_METHOD` (`TRACKING_METHOD`),
                                      KEY `IDX_INDEX_CATEGORY` (`INDEX_CATEGORY`),
                                      KEY `IDX_NAV_DATE` (`NAV_DATE`),
                                      KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`),
                                      FULLTEXT KEY `IDX_FULLTEXT_SEARCH` (`FUND_NAME`, `TARGET_INDEX`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指数型基金信息表(东方财富)';

                                """

    def run(self):
        """
        Fetches and stores information for all index funds from Eastmoney by iterating through all categories.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("Starting index fund information update.")
        table_name = "FUND_INDEX_INFO_EM"

        index_categories = ["全部"]
        fund_types = ["全部"]
        all_funds_list = []

        try:
            # 1. Fetch data for all combinations
            for category in index_categories:
                for f_type in fund_types:
                    self.logger.info(
                        f"Fetching data for Index Category: '{category}', Fund Type: '{f_type}'"
                    )
                    try:
                        # df = ak.fund_info_index_em(symbol=category, indicator=f_type)
                        df = self.fetch_ak_data(
                            "fund_info_index_em",
                            **{"symbol": category, "indicator": f_type},
                        )
                        time.sleep(2)  # Be respectful

                        if not df.empty:
                            df["INDEX_CATEGORY"] = category
                            df["FUND_TYPE_QUERY"] = f_type
                            all_funds_list.append(df)
                        else:
                            self.logger.warning(
                                f"No data returned for Category: '{category}', Type: '{f_type}'"
                            )
                    except Exception as e:
                        self.logger.error(
                            f"Failed to fetch data for Category: '{category}', Type: '{f_type}'. Error: {e}"
                        )
                        continue

            if not all_funds_list:
                self.logger.error("No data was fetched from any category. Exiting.")
                return

            # 2. Combine and process data
            final_df = pd.concat(all_funds_list, ignore_index=True).drop_duplicates(
                subset=["基金代码", "日期"]
            )
            self.logger.info(f"Total unique fund records fetched: {len(final_df)}")

            # 3. Data Transformation
            final_df.rename(
                columns={
                    "基金代码": "FUND_CODE",
                    "基金名称": "FUND_NAME",
                    "单位净值": "NAV",
                    "日期": "NAV_DATE",
                    "日增长率": "DAILY_RETURN",
                    "近1周": "WEEKLY_RETURN",
                    "近1月": "MONTHLY_RETURN",
                    "近3月": "THREE_MONTH_RETURN",
                    "近6月": "SIX_MONTH_RETURN",
                    "近1年": "YEARLY_RETURN",
                    "近2年": "TWO_YEAR_RETURN",
                    "近3年": "THREE_YEAR_RETURN",
                    "今年来": "YTD_RETURN",
                    "成立来": "SINCE_INCEPTION_RETURN",
                    "手续费": "FEE_RATE",
                    "起购金额": "MIN_INVESTMENT",
                    "跟踪标的": "TARGET_INDEX",
                    "跟踪方式": "TRACKING_METHOD",
                    "FUND_TYPE_QUERY": "FUND_TYPE",
                },
                inplace=True,
            )

            # Convert percentage columns to decimals
            percent_cols = [
                "DAILY_RETURN",
                "WEEKLY_RETURN",
                "MONTHLY_RETURN",
                "THREE_MONTH_RETURN",
                "SIX_MONTH_RETURN",
                "YEARLY_RETURN",
                "TWO_YEAR_RETURN",
                "THREE_YEAR_RETURN",
                "YTD_RETURN",
                "SINCE_INCEPTION_RETURN",
                "FEE_RATE",
            ]
            for col in percent_cols:
                if col in final_df.columns:
                    final_df[col] = pd.to_numeric(final_df[col], errors="coerce") / 100

            # Add system columns
            final_df["R_ID"] = [self.get_uuid() for _ in range(len(final_df))]
            final_df["REFERENCE_CODE"] = "FUND_INDEX_INFO"
            final_df["REFERENCE_NAME"] = "指数型基金信息表(东方财富)"
            final_df["IS_ACTIVE"] = 1
            final_df["DATA_SOURCE"] = "东方财富"
            final_df["CREATEUSER"] = "system"
            final_df["UPDATEUSER"] = "system"
            final_df["BASEDATE"] = self.get_current_date()

            # Format date
            final_df["NAV_DATE"] = pd.to_datetime(
                final_df["NAV_DATE"], errors="coerce"
            ).dt.strftime("%Y-%m-%d")
            final_df = final_df.replace(np.nan, None)
            # 4. Save to DB
            self.save_data(
                final_df,
                table_name,
                on_duplicate_update=True,
                unique_keys=["FUND_CODE", "NAV_DATE"],
            )

            self.logger.info("Index fund information update finished successfully.")

        except Exception as e:
            self.logger.error(
                f"An error occurred during the main update process: {e}", exc_info=True
            )
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FundIndexInfoEm()
    data_updater.run()
