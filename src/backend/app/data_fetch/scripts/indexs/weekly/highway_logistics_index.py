# 4054_highway_logistics_index.py
import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class HighwayLogisticsIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "HIGHWAY_LOGISTICS_INDEX"
        self.create_table_sql = """
            CREATE TABLE `HIGHWAY_LOGISTICS_INDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `PERIOD_TYPE` ENUM('WEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY') NOT NULL COMMENT '周期类型',
                `TRADE_DATE` DATE NOT NULL COMMENT '日期',
                `BASE_INDEX` DECIMAL(10, 2) COMMENT '定基指数',
                `MOM_INDEX` DECIMAL(10, 2) COMMENT '环比指数',
                `YOY_INDEX` DECIMAL(10, 2) COMMENT '同比指数',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_PERIOD_DATE` (`PERIOD_TYPE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中国公路物流运价指数';
        """
        self.period_mapping = {
            "WEEKLY": "周指数",
            "MONTHLY": "月指数",
            "QUARTERLY": "季度指数",
            "YEARLY": "年度指数",
        }
        self.reverse_period_mapping = {v: k for k, v in self.period_mapping.items()}

    def fetch_index_data(self, period_type):
        """
        Fetch China Highway Logistics Price Index data

        Args:
            period_type: Period type ('WEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY')

        Returns:
            DataFrame containing index data
        """
        try:
            symbol = self.period_mapping.get(period_type)
            if not symbol:
                raise ValueError(f"Invalid period type: {period_type}")

            self.logger.info(f"Fetching China Highway Logistics Price Index for {symbol}")

            df = self.fetch_ak_data("index_price_cflp", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No data found for {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE",
                    "定基指数": "BASE_INDEX",
                    "环比指数": "MOM_INDEX",
                    "同比指数": "YOY_INDEX",
                }
            )

            # Convert date format and add metadata
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date
            df["PERIOD_TYPE"] = period_type
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(
                f"Error fetching Highway Logistics Index data: {str(e)}", exc_info=True
            )
            return pd.DataFrame()

    def run(self, period_type="WEEKLY", update_all=False):
        """Run the highway logistics index update"""
        try:
            valid_periods = list(self.period_mapping.keys())
            if period_type not in valid_periods:
                raise ValueError(f"Invalid period_type. Must be one of: {', '.join(valid_periods)}")

            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # # Mark old records as inactive for this period type if not updating all
            # if not update_all:
            #     self.execute_sql(
            #         f"UPDATE {self.table_name} SET IS_ACTIVE = 0 WHERE PERIOD_TYPE = %s",
            #         (period_type,)
            #     )

            # Fetch and save data
            df = self.fetch_index_data(period_type)
            if not df.empty:
                self.save_data(
                    df=df.replace({np.nan: None}),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["PERIOD_TYPE", "TRADE_DATE"],
                )
                period_name = self.period_mapping.get(period_type, period_type)
                self.logger.info(f"Updated {len(df)} {period_name} records")

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
    parser = argparse.ArgumentParser(description="Update China Highway Logistics Price Index Data")
    parser.add_argument(
        "--period",
        type=str,
        default="WEEKLY",
        choices=["WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"],
        help="Period type: WEEKLY, MONTHLY, QUARTERLY, or YEARLY",
    )
    parser.add_argument(
        "--list-periods",
        action="store_true",
        help="List all available period types and exit",
    )
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = HighwayLogisticsIndex(logger=logger)

        if args.list_periods:
            logger.info("Available period types:")
            for period_id, period_name in fetcher.period_mapping.items():
                logger.info("  %s: %s", period_id, period_name)
            sys.exit(0)

        success = fetcher.run(period_type=args.period, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
