import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesDailyMarket(AkshareToMySql):
    DCE_SINA_MAIN_SYMBOLS = (
        "A0",
        "B0",
        "C0",
        "CS0",
        "EB0",
        "EG0",
        "FB0",
        "I0",
        "J0",
        "JD0",
        "JM0",
        "L0",
        "LH0",
        "M0",
        "P0",
        "PG0",
        "PP0",
        "RR0",
        "V0",
        "Y0",
    )

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_DAILY_MARKET"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_DAILY_MARKET` (
                                  `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                  `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUTURES_DAILY' COMMENT '参考编码',
                                  `REFERENCE_NAME` VARCHAR(100) DEFAULT '期货历史行情数据' COMMENT '参考名称',

                                  -- 合约信息
                                  `SYMBOL` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                  `VARIETY` VARCHAR(20) COMMENT '品种代码',
                                  `MARKET` VARCHAR(10) NOT NULL COMMENT '交易所(CFFEX/INE/CZCE/DCE/SHFE/GFEX)',

                                  -- 交易日期
                                  `TRADE_DATE` DATE NOT NULL COMMENT '交易日',

                                  -- 价格数据
                                  `OPEN_PRICE` DECIMAL(20, 4) COMMENT '开盘价',
                                  `HIGH_PRICE` DECIMAL(20, 4) COMMENT '最高价',
                                  `LOW_PRICE` DECIMAL(20, 4) COMMENT '最低价',
                                  `CLOSE_PRICE` DECIMAL(20, 4) COMMENT '收盘价',
                                  `SETTLE_PRICE` DECIMAL(20, 4) COMMENT '结算价',
                                  `PREV_SETTLE` DECIMAL(20, 4) COMMENT '前结算价',

                                  -- 成交量持仓量
                                  `VOLUME` BIGINT COMMENT '成交量(手)',
                                  `OPEN_INTEREST` BIGINT COMMENT '持仓量(手)',
                                  `TURNOVER` DECIMAL(30, 4) COMMENT '成交额(元)',

                                  -- 系统字段
                                  `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                  `DATA_SOURCE` VARCHAR(50) DEFAULT '交易所' COMMENT '数据来源',
                                  `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                  `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                  `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                  `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                  PRIMARY KEY (`R_ID`),
                                  UNIQUE KEY `IDX_DAILY_MARKET_UNIQUE` (`MARKET`, `SYMBOL`, `TRADE_DATE`),
                                  KEY `IDX_MARKET_SYMBOL` (`MARKET`, `SYMBOL`),
                                  KEY `IDX_MARKET_VARIETY` (`MARKET`, `VARIETY`),
                                  KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                                  KEY `IDX_VARIETY` (`VARIETY`),
                                  KEY `IDX_MARKET` (`MARKET`),
                                  KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国内期货交易所历史行情数据表';

                                """

    def _ensure_market_scoped_unique_key(self):
        self.connect_db()
        try:
            self.cursor.execute(
                "SHOW INDEX FROM `FUTURES_DAILY_MARKET` WHERE Key_name = 'IDX_DAILY_MARKET_UNIQUE'"
            )
            columns = [
                row[4]
                for row in sorted(
                    self.cursor.fetchall(),
                    key=lambda item: item[3],
                )
            ]
            if columns == ["MARKET", "SYMBOL", "TRADE_DATE"]:
                return
            self.logger.info("Updating FUTURES_DAILY_MARKET unique key to include MARKET")
            self.cursor.execute(
                "ALTER TABLE `FUTURES_DAILY_MARKET` DROP INDEX `IDX_DAILY_MARKET_UNIQUE`"
            )
            self.cursor.execute(
                "ALTER TABLE `FUTURES_DAILY_MARKET` "
                "ADD UNIQUE KEY `IDX_DAILY_MARKET_UNIQUE` (`MARKET`, `SYMBOL`, `TRADE_DATE`)"
            )
            self.connection.commit()
        finally:
            self.disconnect_db()

    def _prepare_daily_market_frame(
        self,
        df: pd.DataFrame,
        *,
        market: str,
        data_source: str,
    ) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        # Drop the 'index' column if it exists to avoid SQL syntax errors
        if "index" in df.columns:
            df = df.drop(columns=["index"])

        df = df.copy()
        expected_columns = {
            "symbol": "SYMBOL",
            "date": "TRADE_DATE",
            "open": "OPEN_PRICE",
            "high": "HIGH_PRICE",
            "low": "LOW_PRICE",
            "close": "CLOSE_PRICE",
            "volume": "VOLUME",
            "open_interest": "OPEN_INTEREST",
            "hold": "OPEN_INTEREST",
            "turnover": "TURNOVER",
            "settle": "SETTLE_PRICE",
            "pre_settle": "PREV_SETTLE",
            "variety": "VARIETY",
        }
        rename_dict = {k: v for k, v in expected_columns.items() if k in df.columns}
        df.rename(columns=rename_dict, inplace=True)

        for old_col, new_col in expected_columns.items():
            if new_col not in df.columns:
                self.logger.warning(
                    f"Column {old_col} missing in data, adding {new_col} with NaN values"
                )
                df[new_col] = None

        df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
        df["REFERENCE_CODE"] = "FUTURES_DAILY"
        df["REFERENCE_NAME"] = "期货历史行情数据"
        df["MARKET"] = market
        if market == "SHFE" and "VARIETY" in df.columns:
            ine_varieties = {"BC", "EC", "LU", "NR", "SC"}
            ine_mask = df["VARIETY"].astype(str).str.upper().isin(ine_varieties)
            if ine_mask.any():
                df.loc[ine_mask, "MARKET"] = "INE"
        df["IS_ACTIVE"] = 1
        df["DATA_SOURCE"] = data_source
        df["CREATEUSER"] = "system"
        df["UPDATEUSER"] = "system"

        try:
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"], errors="coerce").dt.strftime(
                "%Y-%m-%d"
            )
        except Exception as e:
            self.logger.warning(f"Error formatting TRADE_DATE: {e}")

        numeric_cols = [
            "OPEN_PRICE",
            "HIGH_PRICE",
            "LOW_PRICE",
            "CLOSE_PRICE",
            "SETTLE_PRICE",
            "PREV_SETTLE",
            "VOLUME",
            "OPEN_INTEREST",
            "TURNOVER",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "VARIETY" in df.columns and df["VARIETY"].isna().any():
            df.loc[df["VARIETY"].isna(), "VARIETY"] = df.loc[
                df["VARIETY"].isna(), "SYMBOL"
            ].str.extract(r"([A-Za-z]+)", expand=False)
            self.logger.info(f"Filled {df['VARIETY'].isna().sum()} missing VARIETY values")

        if "SYMBOL" in df.columns and "TRADE_DATE" in df.columns:
            before_count = len(df)
            df = df.dropna(subset=["SYMBOL", "TRADE_DATE"])
            dropped_count = before_count - len(df)
            if dropped_count > 0:
                self.logger.warning(
                    f"Dropped {dropped_count} rows with missing SYMBOL or TRADE_DATE"
                )

        if len(df) == 0:
            return df

        before_dedup = len(df)
        df = df.drop_duplicates(subset=["MARKET", "SYMBOL", "TRADE_DATE"])
        dupes_removed = before_dedup - len(df)
        if dupes_removed > 0:
            self.logger.info(f"Removed {dupes_removed} duplicate records")

        return df

    def _save_daily_market_frame(self, df: pd.DataFrame, *, table_name: str) -> bool:
        if df.empty:
            self.logger.warning("No valid data to save after filtering")
            return False

        self.logger.info(f"Saving {len(df)} records to database")
        df = df.replace(np.nan, None)
        self.save_data(
            df,
            table_name,
            on_duplicate_update=True,
            unique_keys=["MARKET", "SYMBOL", "TRADE_DATE"],
        )
        self.logger.info("Data saved successfully")
        return True

    def _fetch_dce_sina_main_contracts(
        self,
        *,
        start_date: str,
        end_date: str,
        _call_timeout: int | None = None,
    ) -> pd.DataFrame:
        start_ts = pd.to_datetime(start_date, errors="coerce")
        end_ts = pd.to_datetime(end_date, errors="coerce")
        if pd.isna(start_ts) or pd.isna(end_ts):
            self.logger.warning(
                "Invalid DCE Sina fallback range: start_date=%s end_date=%s",
                start_date,
                end_date,
            )
            return pd.DataFrame()

        frames: list[pd.DataFrame] = []
        for symbol in self.DCE_SINA_MAIN_SYMBOLS:
            try:
                kwargs = {"symbol": symbol}
                if _call_timeout is not None:
                    kwargs["_call_timeout"] = _call_timeout
                symbol_df = self.fetch_ak_data("futures_zh_daily_sina", **kwargs)
            except Exception as e:
                self.logger.warning("DCE Sina fallback failed for %s: %s", symbol, e)
                continue

            if symbol_df is None or symbol_df.empty or "date" not in symbol_df.columns:
                self.logger.warning("DCE Sina fallback returned no data for %s", symbol)
                continue

            symbol_df = symbol_df.copy()
            symbol_df["date"] = pd.to_datetime(symbol_df["date"], errors="coerce")
            symbol_df = symbol_df[(symbol_df["date"] >= start_ts) & (symbol_df["date"] <= end_ts)]
            if symbol_df.empty:
                continue

            symbol_df["date"] = symbol_df["date"].dt.strftime("%Y-%m-%d")
            symbol_df["symbol"] = symbol
            symbol_df["variety"] = symbol.rstrip("0123456789").upper()
            frames.append(symbol_df)
            time.sleep(0.1)

        if not frames:
            return pd.DataFrame()

        return pd.concat(frames, ignore_index=True)

    def _backfill_dce_sina_main_contracts(
        self,
        *,
        start_date: str,
        end_date: str,
        table_name: str,
        _call_timeout: int | None = None,
    ) -> bool:
        self.logger.warning(
            "Falling back to Sina main-contract daily data for DCE from %s to %s.",
            start_date,
            end_date,
        )
        df = self._fetch_dce_sina_main_contracts(
            start_date=start_date,
            end_date=end_date,
            _call_timeout=_call_timeout,
        )
        if df.empty:
            self.logger.warning("DCE Sina fallback produced no data.")
            return False
        prepared_df = self._prepare_daily_market_frame(df, market="DCE", data_source="新浪期货兜底")
        return self._save_daily_market_frame(prepared_df, table_name=table_name)

    def run(self, markets=None, lookback_days=None, max_windows=None, _call_timeout=None):
        """
        Fetches and stores historical daily market data for all domestic futures exchanges.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self._ensure_market_scoped_unique_key()

        self.logger.info("Starting futures daily market data update for all exchanges.")
        table_name = "FUTURES_DAILY_MARKET"
        if markets is None:
            exchanges = ["CFFEX", "INE", "CZCE", "DCE", "SHFE", "GFEX"]
        elif isinstance(markets, str):
            exchanges = [item.strip().upper() for item in markets.split(",") if item.strip()]
        else:
            exchanges = [str(item).strip().upper() for item in markets if str(item).strip()]
        max_windows = int(max_windows) if max_windows is not None else None
        lookback_days = int(lookback_days) if lookback_days is not None else None

        for market in exchanges:
            try:
                self.logger.info(f"--- Processing market: {market} ---")

                # 1. Determine date range for the current market
                latest_date_in_db = self.get_latest_date(
                    self.table_name, "TRADE_DATE", conditions={"MARKET": market}
                )

                if latest_date_in_db:
                    start_date = latest_date_in_db
                    self.logger.info(
                        f"Latest data for {market} is from {latest_date_in_db}. Starting update from {start_date}."
                    )
                else:
                    start_date = "2010-01-01"
                    self.logger.info(
                        f"No existing data for {market} found. Starting update from {start_date}."
                    )
                if lookback_days is not None:
                    lookback_start = (datetime.now() - timedelta(days=lookback_days)).strftime(
                        "%Y-%m-%d"
                    )
                    if datetime.strptime(start_date, "%Y-%m-%d") < datetime.strptime(
                        lookback_start, "%Y-%m-%d"
                    ):
                        start_date = lookback_start
                        self.logger.info(
                            f"Limiting {market} update to last {lookback_days} days from {start_date}."
                        )

                end_date = datetime.now().strftime("%Y-%m-%d")

                if datetime.strptime(start_date, "%Y-%m-%d") > datetime.strptime(
                    end_date, "%Y-%m-%d"
                ):
                    self.logger.info(f"Data for {market} is already up to date. Skipping.")
                    continue

                # 2. Fetch data in monthly intervals
                current_start = datetime.strptime(start_date, "%Y-%m-%d")
                final_end = datetime.strptime(end_date, "%Y-%m-%d")
                windows_processed = 0

                while current_start <= final_end:
                    if max_windows is not None and windows_processed >= max_windows:
                        self.logger.info(
                            f"Reached max_windows={max_windows} for {market}; stopping this market."
                        )
                        break
                    current_end = current_start + relativedelta(days=7) - timedelta(days=1)
                    if current_end > final_end:
                        current_end = final_end

                    start_str = current_start.strftime("%Y%m%d")
                    end_str = current_end.strftime("%Y%m%d")

                    self.logger.info(f"Fetching {market} data from {start_str} to {end_str}")

                    try:
                        kwargs = {
                            "start_date": start_str,
                            "end_date": end_str,
                            "market": market,
                        }
                        if _call_timeout is not None:
                            kwargs["_call_timeout"] = _call_timeout
                        df = self.fetch_ak_data("get_futures_daily", **kwargs)
                        # df = ak.get_futures_daily(start_date=start_str, end_date=end_str, market=market)
                        # print(df)
                        time.sleep(2)  # Be respectful
                        if df.empty:
                            self.logger.warning(
                                f"No data returned for {market} in range {start_str}-{end_str}."
                            )
                            if market == "DCE":
                                self._backfill_dce_sina_main_contracts(
                                    start_date=start_date,
                                    end_date=end_date,
                                    table_name=table_name,
                                    _call_timeout=_call_timeout,
                                )
                                break
                            continue

                        prepared_df = self._prepare_daily_market_frame(
                            df,
                            market=market,
                            data_source="交易所",
                        )
                        try:
                            self._save_daily_market_frame(prepared_df, table_name=table_name)
                        except Exception as e:
                            self.logger.error(f"Error saving data to database: {e}", exc_info=True)
                            raise
                    except Exception as e:
                        self.logger.error(
                            f"Failed to process data for {market} in range {start_str}-{end_str}: {e}",
                            exc_info=True,
                        )
                        if market == "DCE":
                            self._backfill_dce_sina_main_contracts(
                                start_date=start_date,
                                end_date=end_date,
                                table_name=table_name,
                                _call_timeout=_call_timeout,
                            )
                            break
                    finally:
                        # Move to next period even if the exchange endpoint returns an error.
                        current_start += relativedelta(days=7)
                        windows_processed += 1

            except Exception as e:
                self.logger.error(
                    f"An error occurred while processing market {market}: {e}",
                    exc_info=True,
                )
                continue

        self.logger.info("Futures daily market data update for all exchanges finished.")


if __name__ == "__main__":
    data_updater = FuturesDailyMarket()
    data_updater.run()
