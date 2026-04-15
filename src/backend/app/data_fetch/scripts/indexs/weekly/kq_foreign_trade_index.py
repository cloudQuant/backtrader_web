# 4048_kq_foreign_trade_index.py

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class KQForeignTradeIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "KQ_FOREIGN_TRADE_INDEX"
        self.create_table_sql = """
            CREATE TABLE `KQ_FOREIGN_TRADE_INDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `PERIOD_DATE` VARCHAR(10) NOT NULL COMMENT '期次(年月)',
                `PRICE_INDEX` DECIMAL(10, 4) COMMENT '价格指数',
                `PRICE_INDEX_CHG` DECIMAL(10, 4) COMMENT '价格指数-涨跌幅(%)',
                `PROSPERITY_INDEX` DECIMAL(10, 4) COMMENT '景气指数',
                `PROSPERITY_INDEX_CHG` DECIMAL(10, 4) COMMENT '景气指数-涨跌幅(%)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_PERIOD_DATE` (`PERIOD_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='柯桥纺织品外贸指数';
        """

    def fetch_index_data(self):
        """Fetch Keqiao Textile Foreign Trade Index data"""
        try:
            self.logger.info("Fetching Keqiao Textile Foreign Trade Index data")

            df = self.fetch_ak_data("index_kq_fz", symbol="外贸指数")

            if df is None or df.empty:
                self.logger.warning("No data found for Keqiao Textile Foreign Trade Index")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "期次": "PERIOD_DATE",
                    "价格指数": "PRICE_INDEX",
                    "价格指数-涨跌幅": "PRICE_INDEX_CHG",
                    "景气指数": "PROSPERITY_INDEX",
                    "景气指数-涨跌幅": "PROSPERITY_INDEX_CHG",
                }
            )

            # Add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(
                f"Error fetching Keqiao Textile Foreign Trade Index data: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, update_all=False):
        """Run the foreign trade index update"""
        try:
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # if not update_all:
            #     self.execute_sql(
            #         f"UPDATE {self.table_name} SET IS_ACTIVE = 0"
            #     )

            df = self.fetch_index_data()
            if not df.empty:
                self.save_data(
                    df=df.replace({np.nan: None}),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["PERIOD_DATE"],
                )
                self.logger.info(f"Updated {len(df)} foreign trade index records")

            return True

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():
    ...
    # logging.basicConfig(
    #     level=logging.INFO,
    #     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    #     handlers=[logging.StreamHandler(sys.stdout)]
    # )
    # logger = logging.getLogger(__name__)
    #
    # parser = argparse.ArgumentParser(description='Update Keqiao Textile Foreign Trade Index Data')
    # parser.add_argument('--update-all', action='store_true',
    #                    help='Update all historical data')
    # parser.add_argument('--debug', action='store_true',
    #                    help='Enable debug logging')
    #
    # try:
    #     args = parser.parse_args()
    #     if args.debug:
    #         logger.setLevel(logging.DEBUG)
    #
    #     fetcher = KQForeignTradeIndex(logger=logger)
    #     success = fetcher.run(update_all=args.update_all)
    #     sys.exit(0 if success else 1)
    #
    # except Exception as e:
    #     logger.error(f"Error: {str(e)}", exc_info=args.debug if 'args' in locals() else False)
    #     sys.exit(1)


if __name__ == "__main__":
    main()
