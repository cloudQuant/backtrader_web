# 4059_caixin_digital_economy_index.py
import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class CaixinDigitalEconomyIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "CAIXIN_DIGITAL_ECONOMY_INDEX"
        self.create_table_sql = """
            CREATE TABLE `CAIXIN_DIGITAL_ECONOMY_INDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `TRADE_DATE` DATE NOT NULL COMMENT '日期',
                `DIGITAL_ECONOMY_INDEX` DECIMAL(10, 2) COMMENT '数字经济指数',
                `CHANGE_VALUE` DECIMAL(10, 2) COMMENT '变化值',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='财新数字经济指数';
        """

    def fetch_index_data(self):
        """Fetch Caixin Digital Economy Index data"""
        try:
            self.logger.info("Fetching Caixin Digital Economy Index data")

            df = self.fetch_ak_data("index_dei_cx")

            if df is None or df.empty:
                self.logger.warning("No data found for Caixin Digital Economy Index")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE",
                    "数字经济指数": "DIGITAL_ECONOMY_INDEX",
                    "变化值": "CHANGE_VALUE",
                }
            )

            # Convert date format and add metadata
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(
                f"Error fetching Caixin Digital Economy Index data: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, update_all=False):
        """Run the Caixin Digital Economy Index update"""
        try:
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # if not update_all:
            #     # Get the latest date from database
            #     latest_date = self.get_latest_date()
            #     if latest_date:
            #         self.logger.info(f"Latest date in database: {latest_date}")

            df = self.fetch_index_data()

            if not df.empty:
                # if not update_all and 'latest_date' in locals() and latest_date:
                #     # Filter for new records only
                #     df = df[df['TRADE_DATE'] > latest_date]
                #     if df.empty:
                #         self.logger.info("No new data to update")
                #         return True

                self.save_data(
                    df=df.replace({np.nan: None}),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["TRADE_DATE"],
                )
                self.logger.info(f"Updated {len(df)} Caixin Digital Economy Index records")

            return True

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False

    # def get_latest_date(self):
    #     """Get the latest trade date from database"""
    #     try:
    #         sql = f"SELECT MAX(TRADE_DATE) as latest_date FROM {self.table_name}"
    #         result = self.execute_sql(sql, fetch_one=True)
    #         return result[0] if result and result[0] else None
    #     except Exception as e:
    #         self.logger.warning(f"Error getting latest date: {str(e)}")
    #         return None


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Update Caixin Digital Economy Index Data")
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = CaixinDigitalEconomyIndex(logger=logger)
        success = fetcher.run(update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
