import logging
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexAllCNI(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_ALL_CNI_DAILY"
        self.create_table_sql = """
            CREATE TABLE `INDEX_ALL_CNI_DAILY` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `INDEX_NAME` VARCHAR(100) COMMENT '指数简称',
                `SAMPLE_COUNT` INT COMMENT '样本数',
                `CLOSE` DECIMAL(20, 6) COMMENT '收盘点位',
                `CHANGE_PCT` DECIMAL(10, 6) COMMENT '涨跌幅(%)',
                `PE_TTM` DECIMAL(20, 6) COMMENT 'PE滚动',
                `VOLUME` DECIMAL(30, 6) COMMENT '成交量(万手/亿张)',
                `TURNOVER` DECIMAL(30, 6) COMMENT '成交额(亿元)',
                `TOTAL_MARKET_CAP` DECIMAL(30, 6) COMMENT '总市值(亿元)',
                `FREE_FLOAT_MARKET_CAP` DECIMAL(30, 6) COMMENT '自由流通市值(亿元)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '国证指数' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_DATE_INDEX` (`TRADE_DATE`, `INDEX_CODE`),
                KEY `IDX_INDEX_CODE` (`INDEX_CODE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国证指数-全部指数日行情';
        """

    def fetch_index_data(self, trade_date=None):
        """Fetch all indices data from CNI.

        Args:
            trade_date: Trade date in 'YYYY-MM-DD' format, if None, use today

        Returns:
            DataFrame: Processed DataFrame with indices data or empty DataFrame on error
        """
        try:
            trade_date = pd.to_datetime(trade_date or datetime.now()).date()
            self.logger.info(f"Fetching CNI index data for {trade_date}")

            # 1. Fetch data directly (akshare function broken - column count mismatch)
            api_url = "http://www.cnindex.com.cn/index/indexList"
            params = {"channelCode": "-1", "rows": "2000", "pageNum": "1"}
            r = requests.get(api_url, params=params, timeout=30)
            data_json = r.json()
            df = pd.DataFrame(data_json["data"]["rows"])
            df = df.rename(
                columns={
                    "indexcode": "INDEX_CODE",
                    "indexname": "INDEX_NAME",
                    "samplesize": "SAMPLE_COUNT",
                    "closeingPoint": "CLOSE",
                    "percent": "CHANGE_PCT",
                    "peDynamic": "PE_TTM",
                    "volume": "VOLUME",
                    "amount": "TURNOVER",
                    "totalMarketValue": "TOTAL_MARKET_CAP",
                    "freeMarketValue": "FREE_FLOAT_MARKET_CAP",
                }
            )
            # Keep only the columns we need
            keep_cols = [
                "INDEX_CODE",
                "INDEX_NAME",
                "SAMPLE_COUNT",
                "CLOSE",
                "CHANGE_PCT",
                "PE_TTM",
                "VOLUME",
                "TURNOVER",
                "TOTAL_MARKET_CAP",
                "FREE_FLOAT_MARKET_CAP",
            ]
            df = df[[c for c in keep_cols if c in df.columns]]
            # Convert units
            if "VOLUME" in df.columns:
                df["VOLUME"] = pd.to_numeric(df["VOLUME"], errors="coerce") / 100000
            if "TURNOVER" in df.columns:
                df["TURNOVER"] = pd.to_numeric(df["TURNOVER"], errors="coerce") / 100000000
            if "TOTAL_MARKET_CAP" in df.columns:
                df["TOTAL_MARKET_CAP"] = (
                    pd.to_numeric(df["TOTAL_MARKET_CAP"], errors="coerce") / 100000000
                )
            if "FREE_FLOAT_MARKET_CAP" in df.columns:
                df["FREE_FLOAT_MARKET_CAP"] = (
                    pd.to_numeric(df["FREE_FLOAT_MARKET_CAP"], errors="coerce") / 100000000
                )
            if df is None or df.empty:
                self.logger.warning("No index data found from CNI")
                return pd.DataFrame()

            # 2. Process numeric columns
            for col in ["SAMPLE_COUNT", "CLOSE", "CHANGE_PCT", "PE_TTM"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 3. Add metadata columns
            df["TRADE_DATE"] = trade_date
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["DATA_SOURCE"] = "国证指数"
            df["IS_ACTIVE"] = 1

            # 5. Define final column order
            final_columns = [
                "R_ID",
                "TRADE_DATE",
                "INDEX_CODE",
                "INDEX_NAME",
                "SAMPLE_COUNT",
                "CLOSE",
                "CHANGE_PCT",
                "PE_TTM",
                "VOLUME",
                "TURNOVER",
                "TOTAL_MARKET_CAP",
                "FREE_FLOAT_MARKET_CAP",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["TRADE_DATE", "INDEX_CODE"])

        except Exception as e:
            self.logger.error(f"Error fetching index data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, trade_date=None):
        """Main method to run the data fetching and saving process.

        Args:
            trade_date (str, optional): Trade date in 'YYYY-MM-DD' format. Defaults to today.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # 1. Parse trade date
            trade_date = pd.to_datetime(trade_date or datetime.now()).date()
            self.logger.info(f"Starting CNI index data update for {trade_date}")

            # 2. Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # 3. Fetch and process data
            df = self.fetch_index_data(trade_date)
            if df.empty:
                self.logger.warning("No data to save")
                return False

            # 4. Handle NaN values
            df = df.replace(np.nan, None)
            # 5. Save data using INSERT ... ON DUPLICATE KEY UPDATE
            success = self.save_data(
                df=df,
                table_name=self.table_name,
                on_duplicate_update=True,
                unique_keys=["TRADE_DATE", "INDEX_CODE"],
            )

            if success:
                self.logger.info(
                    f"Successfully updated {len(df)} records in {self.table_name} "
                    f"for date {trade_date}"
                )
            return success

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
    parser = argparse.ArgumentParser(description="Fetch all indices data from CNI")
    parser.add_argument(
        "--date",
        type=str,
        required=False,
        help="交易日期，格式: YYYY-MM-DD (可选，默认为今天)",
    )

    try:
        fetcher = IndexAllCNI(logger=logger)
        success = fetcher.run(parser.parse_args().date)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
