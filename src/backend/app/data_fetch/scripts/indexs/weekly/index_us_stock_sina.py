import logging

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexUsStockSina(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_US_STOCK_SINA"
        self.valid_symbols = [".IXIC", ".DJI", ".INX", ".NDX"]  # 支持的指数代码
        self.create_table_sql = """
            CREATE TABLE `INDEX_US_STOCK_SINA` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(10) NOT NULL COMMENT '指数代码',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(20, 4) COMMENT '开盘价',
                `HIGH` DECIMAL(20, 4) COMMENT '最高价',
                `LOW` DECIMAL(20, 4) COMMENT '最低价',
                `CLOSE` DECIMAL(20, 4) COMMENT '收盘价',
                `VOLUME` BIGINT COMMENT '成交量',
                `AMOUNT` BIGINT COMMENT '成交额',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '新浪财经-美股' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE_DATE` (`INDEX_CODE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='美股指数日线行情表(新浪财经)';
        """

    def validate_symbol(self, symbol):
        """Validate if the provided symbol is supported.

        Args:
            symbol (str): The index symbol to validate

        Returns:
            tuple: (is_valid, error_message)
        """
        if not symbol:
            return False, "Index symbol cannot be empty"
        if symbol.upper() not in [s.upper() for s in self.valid_symbols]:
            return False, f"Invalid symbol. Must be one of {self.valid_symbols}"
        return True, ""

    def fetch_index_data(self, symbol):
        """Fetch US stock index data from Sina Finance.

        Args:
            symbol (str): Index code (e.g., '.IXIC')

        Returns:
            pd.DataFrame: Processed DataFrame with index data or empty DataFrame on error
        """
        try:
            # 1. Fetch data from AKShare
            df = self.fetch_ak_data("index_us_stock_sina", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No data found for US stock index {symbol}")
                return pd.DataFrame()

            # 2. Rename and process columns
            df = df.rename(
                columns={
                    "date": "TRADE_DATE_STR",
                    "open": "OPEN",
                    "high": "HIGH",
                    "low": "LOW",
                    "close": "CLOSE",
                    "volume": "VOLUME",
                    "amount": "AMOUNT",
                }
            )

            # 3. Process date and numeric columns
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE_STR"]).dt.date

            # 4. Process numeric columns
            numeric_columns = ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "AMOUNT"]
            for col in numeric_columns:
                if col in df.columns:
                    # Remove commas and convert to numeric
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 5. Convert volume and amount to integers
            for col in ["VOLUME", "AMOUNT"]:
                if col in df.columns:
                    df[col] = df[col].fillna(0).astype("int64")

            # 6. Add metadata columns
            df["INDEX_CODE"] = symbol.upper()
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["DATA_SOURCE"] = "新浪财经-美股"
            df["IS_ACTIVE"] = 1

            # 7. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "TRADE_DATE",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "VOLUME",
                "AMOUNT",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE", "TRADE_DATE"])

        except Exception as e:
            self.logger.error(
                f"Error fetching data for US stock index {symbol}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, symbol=None):
        """Main method to run the data fetching and saving process.

        Args:
            symbol (str, optional): Index code (e.g., '.IXIC'). If None, processes all valid symbols.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info("Starting US stock index data update from Sina Finance")

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Determine which symbols to process
            if symbol is None:
                symbol_list = self.valid_symbols
                self.logger.info(f"Processing all {len(symbol_list)} US stock indices")
            else:
                is_valid, error_msg = self.validate_symbol(symbol)
                if not is_valid:
                    self.logger.error(error_msg)
                    return False
                symbol_list = [symbol.upper()]

            all_success = True
            for symbol in symbol_list:
                try:
                    # Fetch data
                    df = self.fetch_index_data(symbol)

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
    parser = argparse.ArgumentParser(description="Fetch US stock index data from Sina Finance")
    parser.add_argument(
        "--symbol",
        type=str,
        required=False,
        help="美股指数代码，支持: .IXIC(纳斯达克), .DJI(道琼斯), .INX(标普500), .NDX(纳斯达克100)。如果不指定，将处理所有指数",
    )

    try:
        args = parser.parse_args()
        fetcher = IndexUsStockSina(logger=logger)
        success = fetcher.run(args.symbol)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
