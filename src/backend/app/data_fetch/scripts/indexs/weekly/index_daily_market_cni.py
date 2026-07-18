import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexDailyMarketCNI(AkshareToMySql):
    DEFAULT_START_DATE = "20050101"

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_DAILY_MARKET_CNI"
        self.create_table_sql = """
            CREATE TABLE `INDEX_DAILY_MARKET_CNI` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `OPEN_PRICE` DECIMAL(18, 4) COMMENT '开盘价',
                `HIGH_PRICE` DECIMAL(18, 4) COMMENT '最高价',
                `LOW_PRICE` DECIMAL(18, 4) COMMENT '最低价',
                `CLOSE_PRICE` DECIMAL(18, 4) COMMENT '收盘价',
                `CHANGE_PCT` DECIMAL(10, 6) COMMENT '涨跌幅(%)',
                `VOLUME` DECIMAL(20, 2) COMMENT '成交量(万手)',
                `TURNOVER` DECIMAL(20, 2) COMMENT '成交额(亿元)',
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
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国证指数日行情数据';
        """

    def fetch_index_market_data(self, symbol, start_date=None, end_date=None):
        """
        Fetch index market data from CNI

        Args:
            symbol: Index code, e.g., '399005' for Small and Medium Enterprise Index
            start_date: Start date in 'YYYYMMDD' format
            end_date: End date in 'YYYYMMDD' format

        Returns:
            DataFrame containing index market data
        """
        try:
            # Set default date range if not provided
            # end_date = end_date or datetime.now().strftime('%Y%m%d')
            # start_date = start_date or (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
            #
            self.logger.info(
                f"Fetching market data for index {symbol} from {start_date} to {end_date}"
            )

            # Fetch data using parent class method
            df = self.fetch_ak_data(
                "index_hist_cni",
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )

            if df is None or df.empty:
                self.logger.warning(f"No market data found for index {symbol}")
                return pd.DataFrame()

            # Rename and process columns
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE_STR",
                    "开盘价": "OPEN_PRICE",
                    "最高价": "HIGH_PRICE",
                    "最低价": "LOW_PRICE",
                    "收盘价": "CLOSE_PRICE",
                    "涨跌幅": "CHANGE_PCT",
                    "成交量": "VOLUME",
                    "成交额": "TURNOVER",
                }
            )

            # Process dates and numeric values
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE_STR"], errors="coerce").dt.date
            df["TRADE_DATE"] = df["TRADE_DATE"].fillna(datetime.now().date())

            numeric_columns = [
                "OPEN_PRICE",
                "HIGH_PRICE",
                "LOW_PRICE",
                "CLOSE_PRICE",
                "CHANGE_PCT",
                "VOLUME",
                "TURNOVER",
            ]
            for col in numeric_columns:
                df[col] = df[col].apply(self.parse_numeric)

            # Generate unique ID and add metadata
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["INDEX_CODE"] = symbol
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "国证指数"

            # Select and return final columns
            final_columns = [
                "R_ID",
                "TRADE_DATE",
                "INDEX_CODE",
                "OPEN_PRICE",
                "HIGH_PRICE",
                "LOW_PRICE",
                "CLOSE_PRICE",
                "CHANGE_PCT",
                "VOLUME",
                "TURNOVER",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates()

        except Exception as e:
            self.logger.error(
                f"Error fetching market data for index {symbol}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def _normalize_date_arg(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.strftime("%Y%m%d")
        if isinstance(value, date):
            return value.strftime("%Y%m%d")

        value_str = str(value).strip()
        if not value_str:
            return None
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(value_str, fmt).strftime("%Y%m%d")
            except ValueError:
                continue
        raise ValueError(f"Unsupported date format: {value}")

    def _get_default_end_date(self) -> str:
        return self.get_current_date().replace("-", "")

    def _get_default_start_date_for_symbol(self, symbol: str) -> str:
        latest_date = self.get_latest_date(self.table_name, "TRADE_DATE", {"INDEX_CODE": symbol})
        if latest_date is None:
            return self.DEFAULT_START_DATE
        return self._normalize_date_arg(latest_date) or self.DEFAULT_START_DATE

    def _get_table_latest_date(self) -> str | None:
        latest_date = self.get_latest_date(self.table_name, "TRADE_DATE")
        return self._normalize_date_arg(latest_date)

    def _get_probe_symbol(self, symbol_list: list[str], latest_date: str) -> str | None:
        try:
            latest_date_sql = datetime.strptime(latest_date, "%Y%m%d").strftime("%Y-%m-%d")
            rows = self.query_data(
                f"SELECT INDEX_CODE FROM {self.table_name} WHERE TRADE_DATE = %s LIMIT 1",
                (latest_date_sql,),
            )
            if rows:
                return str(rows[0][0])
        except Exception as exc:
            self.logger.warning(f"Failed to resolve CNI probe symbol: {exc}")

        return symbol_list[0] if symbol_list else None

    def _resolve_effective_end_date(
        self, symbol_list: list[str], requested_end_date: str, explicit_end_date: bool
    ) -> str:
        if explicit_end_date:
            return requested_end_date

        table_latest_date = self._get_table_latest_date()
        if table_latest_date is None:
            return requested_end_date

        probe_start_date = table_latest_date.replace("-", "")
        if probe_start_date > requested_end_date:
            return requested_end_date
        if not self._range_contains_weekday(probe_start_date, requested_end_date):
            return table_latest_date

        probe_symbol = self._get_probe_symbol(symbol_list, table_latest_date)
        if not probe_symbol:
            return requested_end_date

        probe_df = self.fetch_index_market_data(probe_symbol, probe_start_date, requested_end_date)
        if probe_df.empty:
            self.logger.info(
                f"CNI source has no newer data from {probe_start_date} to "
                f"{requested_end_date}; using {table_latest_date} as effective end date"
            )
            return table_latest_date
        return requested_end_date

    def _range_contains_weekday(self, start_date: str, end_date: str) -> bool:
        start_dt = datetime.strptime(start_date, "%Y%m%d").date()
        end_dt = datetime.strptime(end_date, "%Y%m%d").date()

        current_dt = start_dt
        while current_dt <= end_dt:
            if current_dt.weekday() < 5:
                return True
            current_dt += timedelta(days=1)
        return False

    def _get_symbol_list(self, symbol=None) -> list[str]:
        if symbol:
            return [str(symbol)]

        df = self.get_data_by_columns("INDEX_ALL_CNI_DAILY", ["INDEX_CODE"])
        if df.empty or "INDEX_CODE" not in df.columns:
            self.logger.warning("No CNI index symbols found in INDEX_ALL_CNI_DAILY")
            return []

        return [str(item) for item in df["INDEX_CODE"].dropna().unique()]

    def _save_market_data(self, df: pd.DataFrame) -> None:
        if not df.empty:
            self.save_data(
                df.replace(np.nan, None),
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["TRADE_DATE", "INDEX_CODE"],
            )
        else:
            self.logger.warning("No data to process")

    def _fetch_market_data_jobs(self, jobs: list[tuple[str, str, str]], max_workers: int) -> None:
        if not jobs:
            return

        worker_count = max(1, min(max_workers, len(jobs)))
        if worker_count == 1:
            for symbol, start_date, end_date in jobs:
                df = self.fetch_index_market_data(symbol, start_date, end_date)
                self._save_market_data(df)
            return

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(self.fetch_index_market_data, symbol, start_date, end_date): (
                    symbol,
                    start_date,
                    end_date,
                )
                for symbol, start_date, end_date in jobs
            }
            for future in as_completed(future_map):
                symbol, start_date, end_date = future_map[future]
                try:
                    df = future.result()
                except Exception as exc:
                    self.logger.error(
                        f"Error fetching market data for index {symbol} "
                        f"from {start_date} to {end_date}: {exc}"
                    )
                    df = pd.DataFrame()
                self._save_market_data(df)

    def run(
        self,
        symbol=None,
        start_date=None,
        end_date=None,
        max_workers=8,
        max_symbols=None,
        lookback_days=None,
    ):
        """
        Main method to run the market data update

        Args:
            symbol: Index code (e.g., '399005')
            start_date: Start date in 'YYYYMMDD' format
            end_date: End date in 'YYYYMMDD' format

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            symbol_list = self._get_symbol_list(symbol)
            max_symbols = int(max_symbols) if max_symbols is not None else None
            lookback_days = int(lookback_days) if lookback_days is not None else None
            if max_symbols is not None and len(symbol_list) > max_symbols:
                symbol_list = symbol_list[:max_symbols]
                self.logger.info(f"Limiting CNI market data update to {max_symbols} symbols")
            explicit_start_date = self._normalize_date_arg(start_date)
            requested_end_date = self._normalize_date_arg(end_date) or self._get_default_end_date()
            resolved_end_date = self._resolve_effective_end_date(
                symbol_list, requested_end_date, explicit_end_date=end_date is not None
            )
            self.logger.info(f"Starting market data update for index {symbol}")

            jobs: list[tuple[str, str, str]] = []
            for symbol in symbol_list:
                resolved_start_date = (
                    explicit_start_date or self._get_default_start_date_for_symbol(symbol)
                )
                if lookback_days is not None:
                    lookback_start = (
                        datetime.strptime(resolved_end_date, "%Y%m%d")
                        - timedelta(days=lookback_days)
                    ).strftime("%Y%m%d")
                    if resolved_start_date < lookback_start:
                        resolved_start_date = lookback_start
                        self.logger.info(
                            f"Index {symbol}: limiting market data to last {lookback_days} days"
                        )
                if resolved_start_date > resolved_end_date:
                    self.logger.info(
                        f"Index {symbol} is already up to date through {resolved_end_date}"
                    )
                    continue

                jobs.append((symbol, resolved_start_date, resolved_end_date))

            self.logger.info(f"Prepared {len(jobs)} CNI market data fetch jobs")
            self._fetch_market_data_jobs(jobs, int(max_workers or 1))
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
    parser = argparse.ArgumentParser(description="Update CNI index market data")
    parser.add_argument("--symbol", help="Index code (e.g., 399005)")
    parser.add_argument("--start-date", help="Start date in YYYYMMDD format (default: 1 year ago)")
    parser.add_argument("--end-date", help="End date in YYYYMMDD format (default: today)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = IndexDailyMarketCNI(logger=logger)
        success = fetcher.run(
            symbol=args.symbol, start_date=args.start_date, end_date=args.end_date
        )
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
