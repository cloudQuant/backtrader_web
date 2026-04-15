# 4053_container_index.py
import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class ContainerIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "CONTAINER_INDEX"
        self.create_table_sql = """
            CREATE TABLE `CONTAINER_INDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `ROUTE_TYPE` VARCHAR(50) NOT NULL COMMENT '航线类型',
                `TRADE_DATE` DATE NOT NULL COMMENT '日期',
                `WCI_INDEX` DECIMAL(10, 2) COMMENT '集装箱指数(WCI)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_ROUTE_DATE` (`ROUTE_TYPE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='德鲁里世界集装箱指数';
        """
        self.route_mapping = {
            "composite": "综合指数",
            "shanghai-rotterdam": "上海-鹿特丹",
            "rotterdam-shanghai": "鹿特丹-上海",
            "shanghai-los angeles": "上海-洛杉矶",
            "los angeles-shanghai": "洛杉矶-上海",
            "shanghai-genoa": "上海-热那亚",
            "new york-rotterdam": "纽约-鹿特丹",
            "rotterdam-new york": "鹿特丹-纽约",
        }

    def fetch_index_data(self, route_type):
        """
        Fetch Drewry World Container Index data

        Args:
            route_type: Route type (e.g., 'composite', 'shanghai-rotterdam', etc.)

        Returns:
            DataFrame containing index data
        """
        try:
            self.logger.info(f"Fetching Drewry WCI data for route: {route_type}")

            df = self.fetch_ak_data("drewry_wci_index", symbol=route_type)

            if df is None or df.empty:
                self.logger.warning(f"No data found for route: {route_type}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(columns={"date": "TRADE_DATE", "wci": "WCI_INDEX"})
            # print(df)
            df = df.dropna()
            # Convert date format and add metadata
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date
            df["ROUTE_TYPE"] = route_type
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(f"Error fetching WCI data for {route_type}: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, route_type=None, update_all=False):
        """Run the container index update"""
        try:
            valid_routes = list(self.route_mapping.keys())
            total_valid_routes = valid_routes if route_type is None else [route_type]

            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Mark old records as inactive for this route if not updating all
            # if not update_all:
            #     self.execute_sql(
            #         f"UPDATE {self.table_name} SET IS_ACTIVE = 0 WHERE ROUTE_TYPE = %s",
            #         (route_type,)
            #     )
            for route_type in total_valid_routes:
                # Fetch and save data
                df = self.fetch_index_data(route_type)
                if not df.empty:
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["ROUTE_TYPE", "TRADE_DATE"],
                    )
                    route_name = self.route_mapping.get(route_type, route_type)
                    self.logger.info(
                        f"Updated {len(df)} records for {route_name} (route: {route_type})"
                    )

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
    parser = argparse.ArgumentParser(description="Update Drewry World Container Index Data")
    parser.add_argument(
        "--route",
        type=str,
        default=None,
        help="Route type (e.g., composite, shanghai-rotterdam, etc.)",
    )
    parser.add_argument(
        "--list-routes",
        action="store_true",
        help="List all available route types and exit",
    )
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = ContainerIndex(logger=logger)

        if args.list_routes:
            logger.info("Available route types:")
            for route_id, route_name in fetcher.route_mapping.items():
                logger.info("  %s: %s", route_id, route_name)
            sys.exit(0)

        success = fetcher.run(route_type=args.route, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
