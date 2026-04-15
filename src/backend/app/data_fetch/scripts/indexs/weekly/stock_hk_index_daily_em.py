import logging

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockHkIndexDailyEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HK_INDEX_DAILY_EM"
        self.create_table_sql = """
            CREATE TABLE `STOCK_HK_INDEX_DAILY_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(20, 4) COMMENT '开盘价',
                `HIGH` DECIMAL(20, 4) COMMENT '最高价',
                `LOW` DECIMAL(20, 4) COMMENT '最低价',
                `CLOSE` DECIMAL(20, 4) COMMENT '收盘价',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富-港股' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE_DATE` (`INDEX_CODE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股指数日线行情表(东方财富)';
        """

    def get_hk_index_codes(self):
        """Get list of Hong Kong index codes from the spot table.

        Returns:
            list: List of index codes
        """
        table_name = "STOCK_HK_INDEX_SPOT_EM"
        df = self.get_data_by_columns(table_name, ["INDEX_CODE"])
        return list(df["INDEX_CODE"].unique()) if not df.empty else []

    def fetch_index_daily(self, symbol):
        """Fetch daily historical data for a Hong Kong index from East Money.

        Args:
            symbol (str): Index code (e.g., 'HSTECF2L')

        Returns:
            pd.DataFrame: Processed DataFrame with daily data or empty DataFrame on error
        """
        try:
            # 1. Fetch data from AKShare
            df = self.fetch_ak_data("stock_hk_index_daily_em", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No daily data found for Hong Kong index {symbol}")
                return pd.DataFrame()

            # 2. Rename and process columns
            df = df.rename(
                columns={
                    "date": "TRADE_DATE_STR",
                    "open": "OPEN",
                    "high": "HIGH",
                    "low": "LOW",
                    "latest": "CLOSE",
                }
            )

            # 3. Process date and numeric columns
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE_STR"]).dt.date

            numeric_columns = ["OPEN", "HIGH", "LOW", "CLOSE"]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 4. Add metadata columns
            df["INDEX_CODE"] = symbol
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["DATA_SOURCE"] = "东方财富-港股"
            df["IS_ACTIVE"] = 1

            # 5. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "TRADE_DATE",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE", "TRADE_DATE"])

        except Exception as e:
            self.logger.error(
                f"Error fetching daily data for Hong Kong index {symbol}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, symbol=None):
        """Main method to run the data fetching and saving process.

        Args:
            symbol (str, optional): Index code (e.g., 'HSTECF2L'). If None, fetches all indices.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info("Starting Hong Kong index daily data update from East Money")

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Get list of indices to process
            if symbol is None:
                symbol_list = self.get_hk_index_codes()
                if not symbol_list:
                    self.logger.error("No index codes found in the spot table")
                    return False
                self.logger.info(f"Found {len(symbol_list)} indices to process")
            else:
                symbol_list = [symbol]

            all_success = True
            for symbol in symbol_list:
                try:
                    # Fetch data
                    df = self.fetch_index_daily(symbol)

                    if not df.empty:
                        # Handle NaN values
                        df = df.replace(np.nan, None)

                        # Save data using INSERT ... ON DUPLICATE KEY UPDATE
                        success = self.save_data(
                            df=df,
                            table_name=self.table_name,
                            on_duplicate_update=True,
                            unique_keys=["INDEX_CODE", "TRADE_DATE"],
                        )

                        if success:
                            self.logger.info(
                                f"Successfully updated {len(df)} records for index {symbol} "
                                f"in {self.table_name}"
                            )
                        else:
                            all_success = False
                            self.logger.error(f"Failed to save data for index {symbol}")
                    else:
                        self.logger.warning(f"No data found for index {symbol}")

                except Exception as e:
                    all_success = False
                    self.logger.error(f"Error processing index {symbol}: {str(e)}", exc_info=True)

            return all_success

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():
    import argparse
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Fetch historical daily Hong Kong index data from East Money"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        required=False,
        help="港股指数代码，例如: HSTECF2L。如果不指定，将处理所有指数",
    )

    try:
        args = parser.parse_args()
        fetcher = StockHkIndexDailyEm(logger=logger)
        success = fetcher.run(args.symbol)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
