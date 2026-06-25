import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import akshare as ak
import numpy as np
import pandas as pd
from akshare.utils.request import request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockZhIndexDailyEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_ZH_INDEX_DAILY_EM"
        self.create_table_sql = """
            CREATE TABLE `STOCK_ZH_INDEX_DAILY_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(20, 4) COMMENT '开盘价',
                `CLOSE` DECIMAL(20, 4) COMMENT '收盘价',
                `HIGH` DECIMAL(20, 4) COMMENT '最高价',
                `LOW` DECIMAL(20, 4) COMMENT '最低价',
                `VOLUME` BIGINT COMMENT '成交量(手)',
                `AMOUNT` DECIMAL(30, 2) COMMENT '成交额(元)',
                `MARKET_TYPE` VARCHAR(10) COMMENT '市场类型: sh/sz/csi',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE_DATE` (`INDEX_CODE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_MARKET_TYPE` (`MARKET_TYPE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指数日线行情表(东方财富)';
        """

    def get_em_index_code(self):
        """Get list of index codes from East Money spot data."""
        table_name = "STOCK_ZH_INDEX_SPOT_EM"
        df = self.get_data_by_columns(table_name, ["INDEX_CODE"])
        return list(df["INDEX_CODE"].unique())

    def normalize_index_symbol(self, symbol):
        symbol = str(symbol)
        if symbol.startswith(("sz", "sh", "csi", "bj")):
            return symbol
        return ak.stock_a_code_to_symbol(symbol)

    @staticmethod
    def _index_secid_candidates(symbol):
        raw_symbol = str(symbol or "").strip()
        normalized = raw_symbol.lower()
        if normalized.startswith("sh"):
            return [f"1.{raw_symbol[2:]}"]
        if normalized.startswith(("sz", "bj")):
            return [f"0.{raw_symbol[2:]}"]
        if normalized.startswith("csi"):
            return [f"2.{raw_symbol[3:]}"]
        if normalized.startswith("399"):
            preferred = "0"
        elif normalized.startswith(("000", "880")):
            preferred = "1"
        else:
            preferred = "1"
        candidates = [
            f"{preferred}.{raw_symbol}",
            f"1.{raw_symbol}",
            f"0.{raw_symbol}",
            f"2.{raw_symbol}",
            f"47.{raw_symbol}",
        ]
        return list(dict.fromkeys(candidates))

    def _fetch_daily_from_trends(self, symbol, start_date=None, end_date=None):
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        for secid in self._index_secid_candidates(symbol):
            params = {
                "secid": secid,
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                "iscr": "0",
                "iscca": "0",
                "ndays": "5",
            }
            try:
                data_json = request_eastmoney(url, params=params, timeout=20).json()
            except Exception as exc:
                self.logger.warning(f"Eastmoney index trends2 fallback failed for {secid}: {exc}")
                continue

            data = data_json.get("data") or {}
            trends = data.get("trends") or []
            if not trends:
                continue
            df = pd.DataFrame([item.split(",") for item in trends])
            if df.empty or df.shape[1] < 7:
                continue
            df = df.iloc[:, :7]
            df.columns = ["time", "open", "close", "high", "low", "volume", "amount"]
            df["time"] = pd.to_datetime(df["time"], errors="coerce")
            df = df.dropna(subset=["time"])
            if df.empty:
                continue
            for column in ("open", "close", "high", "low", "volume", "amount"):
                df[column] = pd.to_numeric(df[column], errors="coerce")
            df["date"] = df["time"].dt.strftime("%Y-%m-%d")
            grouped = (
                df.groupby("date", as_index=False)
                .agg(
                    open=("open", "first"),
                    close=("close", "last"),
                    high=("high", "max"),
                    low=("low", "min"),
                    volume=("volume", "sum"),
                    amount=("amount", "sum"),
                )
                .sort_values("date")
            )
            if start_date:
                start = pd.to_datetime(start_date, errors="coerce")
                if not pd.isna(start):
                    grouped = grouped[pd.to_datetime(grouped["date"]) >= start]
            if end_date:
                end = pd.to_datetime(end_date, errors="coerce")
                if not pd.isna(end):
                    grouped = grouped[pd.to_datetime(grouped["date"]) <= end]
            if not grouped.empty:
                self.logger.warning(
                    "Eastmoney index daily kline returned empty; populated "
                    "STOCK_ZH_INDEX_DAILY_EM from same-source trends2 aggregation"
                )
                return grouped.reset_index(drop=True)
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume", "amount"])

    def normalize_date_arg(self, value):
        if value is None:
            return None
        if isinstance(value, date):
            return value.strftime("%Y%m%d")
        return str(value).replace("-", "").replace("/", "").replace(".", "")

    def get_default_start_date(self, symbol):
        latest_date = self.get_latest_date(
            self.table_name, "TRADE_DATE", {"INDEX_CODE": symbol}
        )
        if latest_date is None:
            return "19900101"
        return self.normalize_date_arg(latest_date)

    def get_default_end_date(self):
        return self.get_current_date().replace("-", "")

    def fetch_index_daily(self, symbol, start_date=None, end_date=None):
        """Fetch daily index data from East Money and process it.

        Args:
            symbol: Index code (e.g., 'sz399812', 'sh000001', 'csi000905')
            start_date: Start date in format 'YYYYMMDD' (optional)
            end_date: End date in format 'YYYYMMDD' (optional)

        Returns:
            pd.DataFrame: Processed DataFrame with daily index data or empty DataFrame on error
        """
        try:
            # 1. Set default date range if not provided
            if start_date is None:
                start_date = "19900101"  # Default start from 1990
            if end_date is None:
                end_date = date.today().strftime("%Y%m%d")
            symbol = self.normalize_index_symbol(symbol)
            # print(f"symbol: {symbol}, start_date: {start_date}, end_date: {end_date}")
            # 2. Fetch data from AKShare
            try:
                df = self.fetch_ak_data(
                    "stock_zh_index_daily_em",
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as fetch_exc:
                self.logger.warning(
                    f"Eastmoney index daily kline fetch failed, trying same-source "
                    f"trends2 aggregation: {fetch_exc}"
                )
                df = pd.DataFrame()

            if df is None or df.empty:
                df = self._fetch_daily_from_trends(symbol, start_date, end_date)
                if df is None or df.empty:
                    self.logger.warning(f"No daily data found for index {symbol}")
                    return pd.DataFrame()

            # 3. Rename and process columns
            df = df.rename(
                columns={
                    "date": "TRADE_DATE",
                    "open": "OPEN",
                    "close": "CLOSE",
                    "high": "HIGH",
                    "low": "LOW",
                    "volume": "VOLUME",
                    "amount": "AMOUNT",
                }
            )

            # 4. Process date and numeric columns
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"]).dt.date

            numeric_columns = ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "AMOUNT"]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 5. Process volume (convert to integer)
            if "VOLUME" in df.columns:
                df["VOLUME"] = df["VOLUME"].fillna(0).astype("int64")

            # 6. Add metadata columns
            df["INDEX_CODE"] = symbol
            df["MARKET_TYPE"] = symbol[:2].lower() if not symbol.startswith("csi") else "csi"
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]  # Generate unique IDs
            df["DATA_SOURCE"] = "东方财富"
            df["IS_ACTIVE"] = 1

            # 7. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "TRADE_DATE",
                "OPEN",
                "CLOSE",
                "HIGH",
                "LOW",
                "VOLUME",
                "AMOUNT",
                "MARKET_TYPE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE", "TRADE_DATE"])

        except Exception as e:
            self.logger.error(
                f"Error fetching daily data for index {symbol}: {str(e)}", exc_info=True
            )
            return pd.DataFrame()

    def save_index_daily(self, symbol, df):
        if not df.empty:
            df = df.replace(np.nan, None)
            success = self.save_data(
                df=df,
                table_name=self.table_name,
                on_duplicate_update=True,
                unique_keys=["INDEX_CODE", "TRADE_DATE"],
            )

            if success:
                self.logger.info(
                    f"Successfully updated {len(df)} records for index {symbol} in {self.table_name}"
                )
                return True

            self.logger.error(f"Failed to save data for index {symbol}")
            return False

        self.logger.warning(f"No data found for index {symbol}")
        return True

    def fetch_jobs(self, jobs, max_workers):
        worker_count = max(1, min(max_workers, len(jobs)))
        if worker_count == 1:
            for symbol, start_date, end_date in jobs:
                yield symbol, self.fetch_index_daily(symbol, start_date, end_date)
            return

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(self.fetch_index_daily, symbol, start_date, end_date): (
                    symbol,
                    start_date,
                    end_date,
                )
                for symbol, start_date, end_date in jobs
            }
            for future in as_completed(future_map):
                symbol, start_date, end_date = future_map[future]
                try:
                    yield symbol, future.result()
                except Exception as exc:
                    self.logger.error(
                        f"Error fetching daily data for index {symbol} from {start_date} to {end_date}: {exc}"
                    )
                    yield symbol, pd.DataFrame()

    def run(
        self,
        symbol=None,
        start_date=None,
        end_date=None,
        max_workers=8,
        max_symbols=None,
        lookback_days=None,
    ):
        """Main method to run the data fetching and saving process.

        Args:
            symbol: Index code (e.g., 'sz399812') or None to process all indices
            start_date: Start date in format 'YYYYMMDD' (optional)
            end_date: End date in format 'YYYYMMDD' (optional)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info("Starting East Money daily index data update")

            # 创建表（如果不存在）
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # 获取要处理的指数代码列表
            if symbol is None:
                symbol_list = self.get_em_index_code()
                self.logger.info(f"Found {len(symbol_list)} indices to process")
            else:
                symbol_list = [symbol]
            max_symbols = int(max_symbols) if max_symbols is not None else None
            lookback_days = int(lookback_days) if lookback_days is not None else None
            if max_symbols is not None and len(symbol_list) > max_symbols:
                symbol_list = symbol_list[:max_symbols]
                self.logger.info(f"Limiting East Money index update to {max_symbols} symbols")

            explicit_start_date = self.normalize_date_arg(start_date)
            resolved_end_date = self.normalize_date_arg(end_date) or self.get_default_end_date()
            jobs = []
            for raw_symbol in symbol_list:
                normalized_symbol = self.normalize_index_symbol(raw_symbol)
                resolved_start_date = explicit_start_date or self.get_default_start_date(
                    normalized_symbol
                )
                if lookback_days is not None:
                    lookback_start = (
                        datetime.strptime(resolved_end_date, "%Y%m%d")
                        - timedelta(days=lookback_days)
                    ).strftime("%Y%m%d")
                    if resolved_start_date < lookback_start:
                        resolved_start_date = lookback_start
                        self.logger.info(
                            f"Index {normalized_symbol}: limiting update to last {lookback_days} days"
                        )
                if resolved_start_date > resolved_end_date:
                    self.logger.info(
                        f"Index {normalized_symbol} is already up to date through {resolved_end_date}"
                    )
                    continue
                jobs.append((normalized_symbol, resolved_start_date, resolved_end_date))

            all_success = True
            for symbol, df in self.fetch_jobs(jobs, int(max_workers or 1)):
                try:
                    all_success = self.save_index_daily(symbol, df) and all_success

                except Exception as e:
                    all_success = False
                    self.logger.error(f"Error processing index {symbol}: {str(e)}", exc_info=True)

            return all_success

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


if __name__ == "__main__":
    import argparse
    import logging
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Fetch historical daily index data from East Money"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        required=False,
        help="指数代码，例如: sz399812, sh000001, csi000905",
    )
    parser.add_argument("--start-date", type=str, help="开始日期，格式: YYYYMMDD，默认: 19900101")
    parser.add_argument("--end-date", type=str, help="结束日期，格式: YYYYMMDD，默认: 当前日期")

    try:
        args = parser.parse_args()
        fetcher = StockZhIndexDailyEm(logger=logger)
        success = fetcher.run(args.symbol, args.start_date, args.end_date)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)
