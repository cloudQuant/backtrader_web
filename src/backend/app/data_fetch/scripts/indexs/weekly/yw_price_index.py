import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class YWPriceIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "YW_PRICE_INDEX"
        self.create_table_sql = """
            CREATE TABLE `YW_PRICE_INDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `PERIOD_TYPE` ENUM('WEEKLY', 'MONTHLY') NOT NULL COMMENT '周期类型',
                `PERIOD_DATE` DATE NOT NULL COMMENT '期数日期',
                `PRICE_INDEX` DECIMAL(10, 2) COMMENT '价格指数',
                `ONSITE_PRICE_INDEX` DECIMAL(10, 2) COMMENT '场内价格指数',
                `ONLINE_PRICE_INDEX` DECIMAL(10, 2) COMMENT '网上价格指数',
                `ORDER_PRICE_INDEX` DECIMAL(10, 2) COMMENT '订单价格指数',
                `EXPORT_PRICE_INDEX` DECIMAL(10, 2) COMMENT '出口价格指数',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_PERIOD` (`PERIOD_TYPE`, `PERIOD_DATE`),
                KEY `IDX_PERIOD_DATE` (`PERIOD_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='义乌小商品价格指数';
        """

    def fetch_index_data(self, period_type):
        """
        Fetch Yiwu price index data

        Args:
            period_type: 'WEEKLY' or 'MONTHLY'

        Returns:
            DataFrame containing index data
        """
        try:
            symbol = "周价格指数" if period_type == "WEEKLY" else "月价格指数"
            self.logger.info(f"Fetching Yiwu {symbol} data")

            # Fetch data using parent class method
            df = self.fetch_ak_data("index_yw", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No data found for Yiwu {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "期数": "PERIOD_DATE",
                    "价格指数": "PRICE_INDEX",
                    "场内价格指数": "ONSITE_PRICE_INDEX",
                    "网上价格指数": "ONLINE_PRICE_INDEX",
                    "订单价格指数": "ORDER_PRICE_INDEX",
                    "出口价格指数": "EXPORT_PRICE_INDEX",
                }
            )

            # Add metadata
            df["PERIOD_DATE"] = pd.to_datetime(df["PERIOD_DATE"]).dt.date
            df["PERIOD_TYPE"] = period_type
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(f"Error fetching Yiwu price index data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, period_type="WEEKLY", update_all=False):
        """
        Main method to run the Yiwu price index update

        Args:
            period_type: 'WEEKLY' or 'MONTHLY'
            update_all: If True, update all historical data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if period_type is None:
                period_type = "WEEKLY"
            if period_type not in ["WEEKLY", "MONTHLY"]:
                raise ValueError("period_type must be either 'WEEKLY' or 'MONTHLY'")

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # # Mark old records as inactive if not updating all
            # if not update_all:
            #     self.execute_sql(
            #         f"UPDATE {self.table_name} SET IS_ACTIVE = 0 WHERE PERIOD_TYPE = %s",
            #         (period_type,)
            #     )
            #
            # Fetch and save data
            df = self.fetch_index_data(period_type)
            if not df.empty:
                self.save_data(
                    df=df.replace({np.nan: None}),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["PERIOD_TYPE", "PERIOD_DATE"],
                )
                self.logger.info(f"Updated {len(df)} records for {period_type} price index")

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
    parser = argparse.ArgumentParser(description="Update Yiwu Price Index Data")
    parser.add_argument(
        "--period",
        type=str,
        required=False,
        choices=["WEEKLY", "MONTHLY"],
        help="Period type: WEEKLY or MONTHLY",
    )
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = YWPriceIndex(logger=logger)
        success = fetcher.run(period_type=args.period, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
