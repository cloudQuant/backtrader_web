import argparse
import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class SWIndustryThirdCons(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "SW_INDUSTRY_THIRD_CONS"
        self.create_table_sql = """
            CREATE TABLE `SW_INDUSTRY_THIRD_CONS` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDUSTRY_CODE` VARCHAR(20) NOT NULL COMMENT '行业代码',
                `STOCK_CODE` VARCHAR(20) NOT NULL COMMENT '股票代码',
                `STOCK_NAME` VARCHAR(100) COMMENT '股票简称',
                `INCLUSION_DATE` VARCHAR(20) COMMENT '纳入时间',
                `SW_LEVEL1` VARCHAR(50) COMMENT '申万1级',
                `SW_LEVEL2` VARCHAR(50) COMMENT '申万2级',
                `SW_LEVEL3` VARCHAR(100) COMMENT '申万3级',
                `PRICE` DECIMAL(10, 4) COMMENT '价格',
                `PE` DECIMAL(15, 4) COMMENT '市盈率',
                `PE_TTM` DECIMAL(15, 4) COMMENT '市盈率TTM',
                `PB` DECIMAL(15, 4) COMMENT '市净率',
                `DIVIDEND_YIELD` DECIMAL(10, 4) COMMENT '股息率(%)',
                `MARKET_CAP` DECIMAL(20, 4) COMMENT '市值(亿元)',
                `NET_PROFIT_YOY_Q3` DECIMAL(15, 4) COMMENT '归母净利润同比增长(09-30)(%)',
                `NET_PROFIT_YOY_H1` DECIMAL(15, 4) COMMENT '归母净利润同比增长(06-30)(%)',
                `REVENUE_YOY_Q3` DECIMAL(15, 4) COMMENT '营业收入同比增长(09-30)(%)',
                `REVENUE_YOY_H1` DECIMAL(15, 4) COMMENT '营业收入同比增长(06-30)(%)',
                `UPDATE_DATE` DATE NOT NULL COMMENT '更新日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDUSTRY_STOCK` (`INDUSTRY_CODE`, `STOCK_CODE`),
                KEY `IDX_STOCK_CODE` (`STOCK_CODE`),
                KEY `IDX_UPDATE_DATE` (`UPDATE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万三级行业成份';
        """

    def fetch_industry_cons(self, industry_code):
        """
        Fetch Shenwan Third-Class Industry Constituents

        Args:
            industry_code: Industry code (e.g., "850111.SI")

        Returns:
            DataFrame containing industry constituents
        """
        try:
            self.logger.info(
                f"Fetching Shenwan Third-Class Industry Constituents for {industry_code}"
            )

            # Fetch data using parent class method
            df = self.fetch_ak_data("sw_index_third_cons", symbol=industry_code)

            if df is None or df.empty:
                self.logger.warning(f"No constituents found for industry {industry_code}")
                return pd.DataFrame()

            # Rename columns to English
            df = df.rename(
                columns={
                    "股票代码": "STOCK_CODE",
                    "股票简称": "STOCK_NAME",
                    "纳入时间": "INCLUSION_DATE",
                    "申万1级": "SW_LEVEL1",
                    "申万2级": "SW_LEVEL2",
                    "申万3级": "SW_LEVEL3",
                    "价格": "PRICE",
                    "市盈率": "PE",
                    "市盈率ttm": "PE_TTM",
                    "市净率": "PB",
                    "股息率": "DIVIDEND_YIELD",
                    "市值": "MARKET_CAP",
                    "归母净利润同比增长(09-30)": "NET_PROFIT_YOY_Q3",
                    "归母净利润同比增长(06-30)": "NET_PROFIT_YOY_H1",
                    "营业收入同比增长(09-30)": "REVENUE_YOY_Q3",
                    "营业收入同比增长(06-30)": "REVENUE_YOY_H1",
                }
            )

            # Add industry code and metadata
            df["INDUSTRY_CODE"] = industry_code
            df["UPDATE_DATE"] = datetime.now().date()
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "INDUSTRY_CODE",
                "STOCK_CODE",
                "STOCK_NAME",
                "INCLUSION_DATE",
                "SW_LEVEL1",
                "SW_LEVEL2",
                "SW_LEVEL3",
                "PRICE",
                "PE",
                "PE_TTM",
                "PB",
                "DIVIDEND_YIELD",
                "MARKET_CAP",
                "NET_PROFIT_YOY_Q3",
                "NET_PROFIT_YOY_H1",
                "REVENUE_YOY_Q3",
                "REVENUE_YOY_H1",
                "UPDATE_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns]

        except Exception as e:
            self.logger.error(
                f"Error fetching constituents for industry {industry_code}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def get_all_industry_code(self):
        df = self.get_data_by_columns("SW_INDUSTRY_THIRD_INFO", ["INDUSTRY_CODE"])
        return df["INDUSTRY_CODE"].tolist()

    def run(self, industry_code=None, update_all=False):
        """
        Main method to run the industry constituents update

        Args:
            industry_code: Industry code (e.g., "850111.SI")
            update_all: If True, update all historical data; if False, update only new data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")
            code_list = self.get_all_industry_code() if industry_code is None else [industry_code]

            # Mark old records as inactive for this industry
            # if not update_all:
            #     self.execute_sql(
            #         f"UPDATE {self.table_name} SET IS_ACTIVE = 0 WHERE INDUSTRY_CODE = %s",
            #         (industry_code,)
            #     )
            for industry_code in code_list:
                # Fetch and save new data
                df = self.fetch_industry_cons(industry_code)
                if not df.empty:
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDUSTRY_CODE", "STOCK_CODE"],
                    )
                    self.logger.info(f"Updated {len(df)} constituents for industry {industry_code}")

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
    parser = argparse.ArgumentParser(description="Update Shenwan Third-Class Industry Constituents")
    parser.add_argument(
        "--industry", type=str, required=False, help="Industry code (e.g., 850111.SI)"
    )
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = SWIndustryThirdCons(logger=logger)
        success = fetcher.run(industry_code=args.industry, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
