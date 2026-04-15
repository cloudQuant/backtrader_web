# 4080_sw_index_components.py
import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class SWIndexComponents(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "SW_INDEX_COMPONENTS"
        self.create_table_sql = """
            CREATE TABLE IF NOT EXISTS `SW_INDEX_COMPONENTS` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `STOCK_CODE` VARCHAR(20) NOT NULL COMMENT '证券代码',
                `STOCK_NAME` VARCHAR(100) COMMENT '证券名称',
                `WEIGHT` DECIMAL(10, 4) COMMENT '最新权重(%)',
                `INCLUSION_DATE` DATE COMMENT '计入日期',
                `RANK` INT COMMENT '序号',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_STOCK` (`INDEX_CODE`, `STOCK_CODE`),
                INDEX `IDX_IS_ACTIVE` (`IS_ACTIVE`),
                INDEX `IDX_INDEX_CODE` (`INDEX_CODE`),
                INDEX `IDX_STOCK_CODE` (`STOCK_CODE`),
                INDEX `IDX_INCLUSION_DATE` (`INCLUSION_DATE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='申万指数成分股';
        """

    def fetch_components_data(self, symbol):
        """Fetch Shenwan Index components data"""
        try:
            self.logger.info(f"Fetching component stocks for Shenwan Index {symbol}")

            df = self.fetch_ak_data("index_component_sw", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No component data found for index {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "序号": "RANK",
                    "证券代码": "STOCK_CODE",
                    "证券名称": "STOCK_NAME",
                    "最新权重": "WEIGHT",
                    "计入日期": "INCLUSION_DATE",
                }
            )

            # Add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["INDEX_CODE"] = symbol
            df["INCLUSION_DATE"] = pd.to_datetime(df["INCLUSION_DATE"]).dt.date
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(
                f"Error fetching component data for {symbol}: {str(e)}", exc_info=True
            )
            return pd.DataFrame()

    def get_symbol_list(self):
        df = self.get_data_by_columns("SW_INDEX_REALTIME", ["INDEX_CODE"])
        return list(df["INDEX_CODE"].unique())

    def run(self, symbol=None):
        """Run the Shenwan Index components update"""
        try:
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")
            symbol_list = self.get_symbol_list() if symbol is None else [symbol]
            for symbol in symbol_list:
                # Fetch and save new components
                df = self.fetch_components_data(symbol)

                if not df.empty:
                    # Save data
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDEX_CODE", "STOCK_CODE"],
                    )
                    self.logger.info(f"Updated {len(df)} component stocks for index {symbol}")

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
    parser = argparse.ArgumentParser(description="Update Shenwan Index Components")
    parser.add_argument(
        "--symbol",
        type=str,
        required=False,
        help="Index code (e.g., 801001 for 申万50)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = SWIndexComponents(logger=logger)
        success = fetcher.run(symbol=args.symbol)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
