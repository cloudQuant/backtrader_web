import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesMinuteMarket(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_MINUTE_MARKET"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_MINUTE_MARKET` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUTURES_MINUTE' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '期货分时行情数据' COMMENT '参考名称',

                                      -- 合约信息
                                      `SYMBOL` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                      `PERIOD` VARCHAR(10) NOT NULL COMMENT '周期(1/5/15/30/60分钟)',
                                      `VARIETY` VARCHAR(10) COMMENT '品种代码',

                                      -- 时间信息
                                      `TRADE_DATETIME` DATETIME NOT NULL COMMENT '交易时间',
                                      `TRADE_DATE` DATE GENERATED ALWAYS AS (DATE(TRADE_DATETIME)) STORED COMMENT '交易日期',

                                      -- 价格数据
                                      `OPEN_PRICE` DECIMAL(20, 4) COMMENT '开盘价',
                                      `HIGH_PRICE` DECIMAL(20, 4) COMMENT '最高价',
                                      `LOW_PRICE` DECIMAL(20, 4) COMMENT '最低价',
                                      `CLOSE_PRICE` DECIMAL(20, 4) COMMENT '收盘价',

                                      -- 成交量持仓量
                                      `VOLUME` BIGINT COMMENT '成交量(手)',
                                      `OPEN_INTEREST` BIGINT COMMENT '持仓量(手)',

                                      -- 系统字段
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '新浪财经' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_MINUTE_MARKET_UNIQUE` (`SYMBOL`, `PERIOD`, `TRADE_DATETIME`),
                                      KEY `IDX_SYMBOL_PERIOD` (`SYMBOL`, `PERIOD`),
                                      KEY `IDX_TRADE_DATETIME` (`TRADE_DATETIME`),
                                      KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                                      KEY `IDX_VARIETY` (`VARIETY`),
                                      KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国内期货分时行情数据表';

                                """

    @staticmethod
    def _format_latest_datetime(value) -> str | None:
        if value is None:
            return None
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    def _get_latest_trade_datetime(self, symbol: str, period: str) -> str | None:
        try:
            self.connect_db()
            self.cursor.execute(
                f"SELECT MAX(TRADE_DATETIME) FROM {self.table_name} WHERE SYMBOL = %s AND PERIOD = %s",
                (symbol, period),
            )
            row = self.cursor.fetchone()
            return self._format_latest_datetime(row[0] if row else None)
        except Exception as exc:
            self.logger.warning(f"Failed to resolve latest minute datetime for {symbol}: {exc}")
            return None

    def _fetch_symbol_minute_data(self, symbol: str, period: str, sleep_seconds: float):
        df = self.fetch_ak_data(
            "futures_zh_minute_sina", **{"symbol": symbol, "period": period}
        )
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        return symbol, df

    @staticmethod
    def _coerce_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _is_main_continuous_symbol(symbol: str) -> bool:
        return bool(re.fullmatch(r"[A-Z]+0", str(symbol).strip()))

    @classmethod
    def _select_main_continuous_symbols(cls, symbols) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized = str(symbol).strip().upper()
            if not normalized or normalized in seen:
                continue
            if cls._is_main_continuous_symbol(normalized):
                selected.append(normalized)
                seen.add(normalized)
        return selected

    def _save_symbol_minute_data(
        self, symbol: str, period: str, df: pd.DataFrame, table_name: str
    ) -> None:
        latest_dt_str = self._get_latest_trade_datetime(symbol, period)
        if latest_dt_str:
            self.logger.info(
                f"Latest data for {symbol} is from {latest_dt_str}. Re-fetching overlap minute."
            )
        else:
            self.logger.info(f"No existing data for {symbol}. Performing full fetch.")

        if df is None or df.empty:
            self.logger.warning(f"No data returned for {symbol}.")
            return

        df = df.copy()
        df.rename(
            columns={
                "datetime": "TRADE_DATETIME",
                "open": "OPEN_PRICE",
                "high": "HIGH_PRICE",
                "low": "LOW_PRICE",
                "close": "CLOSE_PRICE",
                "volume": "VOLUME",
                "hold": "OPEN_INTEREST",
            },
            inplace=True,
        )

        df["TRADE_DATETIME"] = pd.to_datetime(df["TRADE_DATETIME"], errors="coerce")
        df = df.dropna(subset=["TRADE_DATETIME"])
        df["TRADE_DATETIME"] = df["TRADE_DATETIME"].dt.strftime("%Y-%m-%d %H:%M:%S")

        if latest_dt_str:
            df = df[df["TRADE_DATETIME"] >= latest_dt_str]

        if df.empty:
            self.logger.info(f"No new 1-minute data to update for {symbol}.")
            return

        self.logger.info(f"Found {len(df)} new/overlap 1-minute records for {symbol}.")

        df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
        df["REFERENCE_CODE"] = "FUTURES_MINUTE"
        df["REFERENCE_NAME"] = "期货分时行情数据"
        df["SYMBOL"] = symbol
        df["PERIOD"] = period
        df["VARIETY"] = (
            re.match(r"([A-Z]+)", symbol, re.IGNORECASE).group(1).upper()
            if re.match(r"([A-Z]+)", symbol, re.IGNORECASE)
            else ""
        )
        df["IS_ACTIVE"] = 1
        df["DATA_SOURCE"] = "新浪财经"
        df["CREATEUSER"] = "system"
        df["UPDATEUSER"] = "system"

        self.save_data(
            df,
            table_name,
            on_duplicate_update=True,
            unique_keys=["SYMBOL", "PERIOD", "TRADE_DATETIME"],
        )

    def run(
        self,
        symbols=None,
        period="1",
        sleep_seconds=0,
        max_symbols=None,
        max_workers=4,
        include_all_contracts=False,
    ):
        """
        Fetches and stores minute futures data for current main continuous contracts.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting 1-minute futures market data update.")
        table_name = "FUTURES_MINUTE_MARKET"
        period = str(period or "1")
        sleep_seconds = float(sleep_seconds or 0)
        max_symbols = int(max_symbols) if max_symbols is not None else None
        max_workers = max(1, int(max_workers or 1))
        include_all_contracts = self._coerce_bool(include_all_contracts)

        if symbols is None:
            raw_symbol_list = self.get_current_futures_contract_list()
            if include_all_contracts:
                symbol_list = [str(item).strip().upper() for item in raw_symbol_list if str(item).strip()]
            else:
                symbol_list = self._select_main_continuous_symbols(raw_symbol_list)
                self.logger.info(
                    "Selected %s main continuous contracts from %s listed contracts.",
                    len(symbol_list),
                    len(raw_symbol_list),
                )
        elif isinstance(symbols, str):
            symbol_list = [item.strip().upper() for item in symbols.split(",") if item.strip()]
        else:
            symbol_list = [str(item).strip().upper() for item in symbols if str(item).strip()]
        if max_symbols is not None:
            symbol_list = symbol_list[:max_symbols]

        if not symbol_list:
            self.logger.error("No symbols found to update. Exiting.")
            return

        worker_count = min(max_workers, len(symbol_list))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(
                    self._fetch_symbol_minute_data, symbol, period, sleep_seconds
                ): symbol
                for symbol in symbol_list
            }
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    _, df = future.result()
                    self._save_symbol_minute_data(symbol, period, df, table_name)
                except Exception as e:
                    self.logger.error(f"Failed to process symbol {symbol}: {e}", exc_info=True)
                    continue

        self.logger.info("Futures 1-minute market data update finished.")


if __name__ == "__main__":
    data_updater = FuturesMinuteMarket()
    data_updater.run()
