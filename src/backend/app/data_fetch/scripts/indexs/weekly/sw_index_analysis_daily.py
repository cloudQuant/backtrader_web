# 4081_sw_index_analysis_daily.py
import argparse
import logging
import sys

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class SWIndexAnalysisDaily(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "SW_INDEX_ANALYSIS_DAILY"
        self.create_table_sql = """
            CREATE TABLE `SW_INDEX_ANALYSIS_DAILY` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `INDEX_NAME` VARCHAR(100) COMMENT '指数名称',
                `TRADE_DATE` DATE NOT NULL COMMENT '发布日期',
                `CLOSE_INDEX` DECIMAL(12, 4) COMMENT '收盘指数',
                `VOLUME` DECIMAL(18, 4) COMMENT '成交量(亿股)',
                `CHANGE_PCT` DECIMAL(10, 4) COMMENT '涨跌幅(%)',
                `TURNOVER_RATE` DECIMAL(10, 4) COMMENT '换手率(%)',
                `PE_RATIO` DECIMAL(12, 4) COMMENT '市盈率(倍)',
                `PB_RATIO` DECIMAL(12, 4) COMMENT '市净率(倍)',
                `AVG_PRICE` DECIMAL(12, 4) COMMENT '均价(元)',
                `TURNOVER_RATIO` DECIMAL(10, 4) COMMENT '成交额占比(%)',
                `FLOAT_MV` DECIMAL(20, 4) COMMENT '流通市值(亿元)',
                `AVG_FLOAT_MV` DECIMAL(20, 4) COMMENT '平均流通市值(亿元)',
                `DIVIDEND_YIELD` DECIMAL(10, 4) COMMENT '股息率(%)',
                `SYMBOL_TYPE` VARCHAR(20) COMMENT '指数类型',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_CODE_DATE_TYPE` (`INDEX_CODE`, `TRADE_DATE`, `SYMBOL_TYPE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_SYMBOL_TYPE` (`SYMBOL_TYPE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万指数分析日报表';
        """
        self.valid_symbols = ["市场表征", "一级行业", "二级行业", "风格指数"]

    def fetch_analysis_data(self, symbol, start_date, end_date):
        """Fetch Shenwan Index daily analysis data"""
        try:
            if symbol not in self.valid_symbols:
                self.logger.error(f"Invalid symbol: {symbol}. Must be one of {self.valid_symbols}")
                return pd.DataFrame()

            self.logger.info(
                f"Fetching Shenwan Index daily analysis for {symbol} from {start_date} to {end_date}"
            )

            df = self.fetch_ak_data(
                "index_analysis_daily_sw",
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )

            if df is None or df.empty:
                self.logger.warning(
                    f"No analysis data found for {symbol} from {start_date} to {end_date}"
                )
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "指数代码": "INDEX_CODE",
                    "指数名称": "INDEX_NAME",
                    "发布日期": "TRADE_DATE",
                    "收盘指数": "CLOSE_INDEX",
                    "成交量": "VOLUME",
                    "涨跌幅": "CHANGE_PCT",
                    "换手率": "TURNOVER_RATE",
                    "市盈率": "PE_RATIO",
                    "市净率": "PB_RATIO",
                    "均价": "AVG_PRICE",
                    "成交额占比": "TURNOVER_RATIO",
                    "流通市值": "FLOAT_MV",
                    "平均流通市值": "AVG_FLOAT_MV",
                    "股息率": "DIVIDEND_YIELD",
                }
            )

            # Add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date
            df["SYMBOL_TYPE"] = symbol
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "akshare"

            return df

        except Exception as e:
            self.logger.error(f"Error fetching analysis data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, symbol=None, start_date=None, end_date=None, update_all=False):
        """Run the Shenwan Index daily analysis update"""
        try:
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Set default dates if not provided
            if not end_date:
                end_date = self.get_previous_date().replace("-", "")
            if not start_date:
                start_date = "20050104"
            symbol_list = self.valid_symbols if symbol is None else [symbol]
            for symbol in symbol_list:
                df = self.fetch_analysis_data(symbol, start_date, end_date)

                if not df.empty:
                    # Save data
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["INDEX_CODE", "TRADE_DATE", "SYMBOL_TYPE"],
                    )
                    self.logger.info(f"Updated {len(df)} daily analysis records for {symbol}")

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
    parser = argparse.ArgumentParser(description="Update Shenwan Index Daily Analysis")
    parser.add_argument(
        "--symbol",
        type=str,
        required=False,
        choices=["市场表征", "一级行业", "二级行业", "风格指数"],
        help="Index type to fetch",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYYMMDD), defaults to end_date if not specified",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (YYYYMMDD), defaults to today if not specified",
    )
    parser.add_argument(
        "--update-all",
        action="store_true",
        help="Update all data, including existing records",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = SWIndexAnalysisDaily(logger=logger)
        success = fetcher.run(
            symbol=args.symbol,
            start_date=args.start_date,
            end_date=args.end_date,
            update_all=args.update_all,
        )
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
