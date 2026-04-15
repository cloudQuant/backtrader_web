import logging
from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexConstituentWeightsCSIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_CONSTITUENT_WEIGHTS_CSINDEX"
        self.create_table_sql = """
            CREATE TABLE `INDEX_CONSTITUENT_WEIGHTS_CSINDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `TRADE_DATE` DATE NOT NULL COMMENT '日期',
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `INDEX_NAME` VARCHAR(100) COMMENT '指数名称',
                `INDEX_NAME_EN` VARCHAR(200) COMMENT '指数英文名称',
                `STOCK_CODE` VARCHAR(20) NOT NULL COMMENT '成分券代码',
                `STOCK_NAME` VARCHAR(100) COMMENT '成分券名称',
                `STOCK_NAME_EN` VARCHAR(200) COMMENT '成分券英文名称',
                `EXCHANGE` VARCHAR(50) COMMENT '交易所',
                `EXCHANGE_EN` VARCHAR(100) COMMENT '交易所英文名称',
                `WEIGHT` DECIMAL(10, 6) COMMENT '权重(%)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '中证指数' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_DATE_INDEX_STOCK` (`TRADE_DATE`, `INDEX_CODE`, `STOCK_CODE`),
                KEY `IDX_INDEX_CODE` (`INDEX_CODE`),
                KEY `IDX_STOCK_CODE` (`STOCK_CODE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中证指数成份股权重信息';
        """

    def parse_date(self, date_str):
        """Parse date string to date object with error handling"""
        try:
            if pd.isna(date_str) or not date_str or not str(date_str).strip():
                return None
            return pd.to_datetime(date_str, errors="coerce").date()
        except Exception as e:
            self.logger.warning(f"Error parsing date {date_str}: {e}")
            return None

    def parse_weight(self, weight):
        """Parse weight to float with error handling"""
        try:
            if pd.isna(weight) or not str(weight).strip():
                return None
            return float(str(weight).strip().replace("%", ""))
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Error parsing weight {weight}: {e}")
            return None

    def fetch_constituent_weights(self, symbol, trade_date=None):
        """
        Fetch index constituent weights from CSIndex

        Args:
            symbol: Index code, e.g., '000300' for CSI 300
            trade_date: Trade date in 'YYYY-MM-DD' format, if None, use today

        Returns:
            DataFrame containing index constituent weights
        """
        try:
            trade_date = pd.to_datetime(trade_date or datetime.now()).date()
            self.logger.info(f"Fetching constituent weights for index {symbol} on {trade_date}")

            # Fetch data using parent class method
            df = self.fetch_ak_data("index_stock_cons_weight_csindex", symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No constituent weight data found for index {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE_STR",
                    "指数代码": "INDEX_CODE",
                    "指数名称": "INDEX_NAME",
                    "指数英文名称": "INDEX_NAME_EN",
                    "成分券代码": "STOCK_CODE",
                    "成分券名称": "STOCK_NAME",
                    "成分券英文名称": "STOCK_NAME_EN",
                    "交易所": "EXCHANGE",
                    "交易所英文名称": "EXCHANGE_EN",
                    "权重": "WEIGHT",
                }
            )

            # Process dates and weights
            df["TRADE_DATE"] = df["TRADE_DATE_STR"].apply(self.parse_date)
            df["TRADE_DATE"] = df["TRADE_DATE"].fillna(trade_date)
            df["WEIGHT"] = df["WEIGHT"].apply(self.parse_weight)

            # Generate unique ID and add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "中证指数"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "TRADE_DATE",
                "INDEX_CODE",
                "INDEX_NAME",
                "INDEX_NAME_EN",
                "STOCK_CODE",
                "STOCK_NAME",
                "STOCK_NAME_EN",
                "EXCHANGE",
                "EXCHANGE_EN",
                "WEIGHT",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates()

        except Exception as e:
            self.logger.error(
                f"Error fetching constituent weights for index {symbol}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, symbol=None, trade_date=None):
        """
        Main method to run the constituent weights update

        Args:
            symbol: Index code (e.g., '000300' for CSI 300)
            trade_date: Trade date in 'YYYY-MM-DD' format

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not symbol:
                self.logger.error("Index symbol is required")
                df = self.fetch_ak_data("index_csindex_all")
                symbol_list = df["指数代码"].to_list()
            else:
                symbol_list = [symbol]

            trade_date = pd.to_datetime(trade_date or datetime.now()).date()
            self.logger.info(
                f"Starting constituent weights update for index {symbol} on {trade_date}"
            )

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Fetch and save data
            for symbol in symbol_list:
                df = self.fetch_constituent_weights(symbol, trade_date)
                if not df.empty:
                    self.save_data(
                        df,
                        self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["TRADE_DATE", "INDEX_CODE", "STOCK_CODE"],
                    )
                else:
                    self.logger.warning(f"No data to process FOR {symbol}")

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
    parser = argparse.ArgumentParser(description="Update CSIndex constituent weights")
    parser.add_argument("--symbol", required=False, help="Index code (e.g., 000300 for CSI 300)")
    parser.add_argument("--date", help="Trade date in YYYY-MM-DD format (default: today)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = IndexConstituentWeightsCSIndex(logger=logger)
        success = fetcher.run(args.symbol, args.date)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
