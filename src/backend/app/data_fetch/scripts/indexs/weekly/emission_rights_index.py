# 4052_emission_rights_index.py
import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class EmissionRightsIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "EMISSION_RIGHTS_INDEX"
        self.create_table_sql = """
            CREATE TABLE `EMISSION_RIGHTS_INDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `PERIOD_TYPE` ENUM('MONTHLY', 'QUARTERLY') NOT NULL COMMENT '周期类型',
                `PERIOD_DATE` DATE NOT NULL COMMENT '日期',
                `TRADE_INDEX` DECIMAL(15, 6) COMMENT '交易指数',
                `VOLUME` DECIMAL(15, 4) COMMENT '成交量(吨)',
                `TURNOVER` DECIMAL(20, 4) COMMENT '成交额(元)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_PERIOD` (`PERIOD_TYPE`, `PERIOD_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='浙江省排污权交易指数';
        """

    def fetch_index_data(self, period_type):
        """
        Fetch Emission Rights Index data

        Args:
            period_type: 'MONTHLY' or 'QUARTERLY'

        Returns:
            DataFrame containing index data
        """
        try:
            symbol = "月度" if period_type == "MONTHLY" else "季度"
            self.logger.info(f"Fetching Emission Rights Index data for {symbol}")

            df = self.fetch_ak_data("index_eri", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No data found for Emission Rights Index ({symbol})")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "日期": "PERIOD_DATE",
                    "交易指数": "TRADE_INDEX",
                    "成交量": "VOLUME",
                    "成交额": "TURNOVER",
                }
            )

            # Convert date format and add metadata
            df["PERIOD_DATE"] = pd.to_datetime(df["PERIOD_DATE"]).dt.date
            df["PERIOD_TYPE"] = period_type
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(f"Error fetching Emission Rights Index data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, period_type="MONTHLY", update_all=False):
        """Run the emission rights index update"""
        try:
            if period_type not in ["MONTHLY", "QUARTERLY"]:
                raise ValueError("period_type must be either 'MONTHLY' or 'QUARTERLY'")

            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Mark old records as inactive if not updating all
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
                    unique_keys=["PERIOD_TYPE", "PERIOD_DATE"],
                )
                period_name = "Monthly" if period_type == "MONTHLY" else "Quarterly"
                self.logger.info(f"Updated {len(df)} {period_name} emission rights index records")

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
    parser = argparse.ArgumentParser(description="Update Emission Rights Index Data")
    parser.add_argument(
        "--period",
        type=str,
        default="MONTHLY",
        choices=["MONTHLY", "QUARTERLY"],
        help="Period type: MONTHLY or QUARTERLY",
    )
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = EmissionRightsIndex(logger=logger)
        success = fetcher.run(period_type=args.period, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
