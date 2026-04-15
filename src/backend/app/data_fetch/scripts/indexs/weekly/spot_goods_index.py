import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class SpotGoodsIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "SPOT_GOODS_INDEX"
        self.create_table_sql = """
            CREATE TABLE `SPOT_GOODS_INDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDEX_NAME` VARCHAR(50) NOT NULL COMMENT '指数名称',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `INDEX_VALUE` DECIMAL(20, 4) COMMENT '指数值',
                `CHANGE_AMOUNT` DECIMAL(20, 4) COMMENT '涨跌额',
                `CHANGE_PCT` DECIMAL(10, 4) COMMENT '涨跌幅(%)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_DATE` (`INDEX_NAME`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品现货价格指数';
        """

    def fetch_index_data(self, index_name):
        """
        Fetch spot goods index data

        Args:
            index_name: Name of the index (e.g., "波罗的海干散货指数")

        Returns:
            DataFrame containing index data
        """
        try:
            self.logger.info(f"Fetching {index_name} data")

            # Fetch data using parent class method
            df = self.fetch_ak_data("spot_goods", symbol=index_name)

            if df is None or df.empty:
                self.logger.warning(f"No data found for {index_name}")
                return pd.DataFrame()

            # Rename columns to English
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE",
                    "指数": "INDEX_VALUE",
                    "涨跌额": "CHANGE_AMOUNT",
                    "涨跌幅": "CHANGE_PCT",
                }
            )

            # Convert date format and add metadata
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date
            df["INDEX_NAME"] = index_name
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "INDEX_NAME",
                "TRADE_DATE",
                "INDEX_VALUE",
                "CHANGE_AMOUNT",
                "CHANGE_PCT",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns]

        except Exception as e:
            self.logger.error(f"Error fetching {index_name} data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, index_name=None, update_all=False):
        """
        Main method to run the spot goods index update

        Args:
            index_name: Name of the index (e.g., "波罗的海干散货指数")
            update_all: If True, update all historical data; if False, update only new data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # # Mark old records as inactive for this index if not updating all
            # if not update_all:
            #     self.execute_sql(
            #         f"UPDATE {self.table_name} SET IS_ACTIVE = 0 WHERE INDEX_NAME = %s",
            #         (index_name,)
            #     )
            if index_name is None:
                index_name_list = [
                    "波罗的海干散货指数",
                    "钢坯价格指数",
                    "澳大利亚粉矿价格",
                ]
            else:
                index_name_list = [index_name]
            for index_name in index_name_list:
                # Fetch and save new data
                df = self.fetch_index_data(index_name)
                if not df.empty:
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDEX_NAME", "TRADE_DATE"],
                    )
                    self.logger.info(f"Updated {len(df)} records for {index_name}")

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
    parser = argparse.ArgumentParser(description="Update Spot Goods Index Data")
    parser.add_argument(
        "--index",
        type=str,
        required=False,
        help='Index name (e.g., "波罗的海干散货指数", "钢坯价格指数", "澳大利亚粉矿价格")',
    )
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = SpotGoodsIndex(logger=logger)
        success = fetcher.run(index_name=args.index, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
