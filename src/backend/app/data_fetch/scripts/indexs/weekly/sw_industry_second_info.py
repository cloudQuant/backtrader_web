import argparse
import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class SWIndustrySecondInfo(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "SW_INDUSTRY_SECOND_INFO"
        self.create_table_sql = """
            CREATE TABLE `SW_INDUSTRY_SECOND_INFO` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDUSTRY_CODE` VARCHAR(20) NOT NULL COMMENT '行业代码',
                `INDUSTRY_NAME` VARCHAR(50) NOT NULL COMMENT '行业名称',
                `PARENT_INDUSTRY` VARCHAR(50) COMMENT '上级行业',
                `COMPONENT_COUNT` INT COMMENT '成份个数',
                `PE_STATIC` DECIMAL(10, 2) COMMENT '静态市盈率',
                `PE_TTM` DECIMAL(10, 2) COMMENT 'TTM(滚动)市盈率',
                `PB` DECIMAL(10, 2) COMMENT '市净率',
                `DIVIDEND_YIELD` DECIMAL(10, 2) COMMENT '静态股息率',
                `UPDATE_DATE` DATE NOT NULL COMMENT '更新日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDUSTRY_CODE` (`INDUSTRY_CODE`),
                KEY `IDX_PARENT_INDUSTRY` (`PARENT_INDUSTRY`),
                KEY `IDX_UPDATE_DATE` (`UPDATE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万二级行业信息';
        """

    def fetch_industry_info(self):
        """
        Fetch Shenwan Second-Class Industry Information

        Returns:
            DataFrame containing industry information
        """
        try:
            self.logger.info("Fetching Shenwan Second-Class Industry Information")

            # Fetch data using parent class method
            df = self.fetch_ak_data("sw_index_second_info")

            if df is None or df.empty:
                self.logger.warning("No Shenwan second-class industry data found")
                return pd.DataFrame()

            # Rename columns to English
            df = df.rename(
                columns={
                    "行业代码": "INDUSTRY_CODE",
                    "行业名称": "INDUSTRY_NAME",
                    "上级行业": "PARENT_INDUSTRY",
                    "成份个数": "COMPONENT_COUNT",
                    "静态市盈率": "PE_STATIC",
                    "TTM(滚动)市盈率": "PE_TTM",
                    "市净率": "PB",
                    "静态股息率": "DIVIDEND_YIELD",
                }
            )

            # Add update date and metadata
            df["UPDATE_DATE"] = datetime.now().date()
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "INDUSTRY_CODE",
                "INDUSTRY_NAME",
                "PARENT_INDUSTRY",
                "COMPONENT_COUNT",
                "PE_STATIC",
                "PE_TTM",
                "PB",
                "DIVIDEND_YIELD",
                "UPDATE_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns]

        except Exception as e:
            self.logger.error(
                f"Error fetching Shenwan second-class industry data: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self):
        """
        Main method to run the Shenwan second-class industry info update

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # # Mark old records as inactive
            # self.execute_sql(
            #     f"UPDATE {self.table_name} SET IS_ACTIVE = 0 WHERE IS_ACTIVE = 1"
            # )

            # Fetch and save new data
            df = self.fetch_industry_info()
            if not df.empty:
                self.save_data(
                    df=df.replace({np.nan: None}),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["INDUSTRY_CODE"],
                )
                self.logger.info(f"Updated {len(df)} Shenwan second-class industry records")

            return True

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Update Shenwan Second-Class Industry Information")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = SWIndustrySecondInfo(logger=logger)
        success = fetcher.run()
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
