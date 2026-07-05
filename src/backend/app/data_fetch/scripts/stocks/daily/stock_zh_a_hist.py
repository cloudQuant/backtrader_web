"""
Stock Zh A Hist

数据源: AkShare
函数: stock_zh_a_hist
频率: daily
"""

import pandas as pd
from akshare.utils.request import request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockZhAHist(AkshareToMySql):
    """Stock Zh A Hist"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_ZH_A_HIST"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_ZH_A_HIST` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Zh A Hist'
    """

    @staticmethod
    def _trend_secid(symbol: str) -> str:
        symbol = str(symbol or "").strip()
        market = "1" if symbol.startswith("6") else "0"
        return f"{market}.{symbol}"

    @staticmethod
    def _tx_symbol(symbol: str) -> str:
        symbol = str(symbol or "").strip()
        if symbol.startswith(("sh", "sz", "bj")):
            return symbol
        if symbol.startswith("6"):
            return f"sh{symbol}"
        if symbol.startswith(("4", "8")):
            return f"bj{symbol}"
        return f"sz{symbol}"

    def _fetch_daily_from_tencent(self, **kwargs) -> pd.DataFrame:
        symbol = str(kwargs.get("symbol") or "000001").strip()
        tx_kwargs = {
            "symbol": self._tx_symbol(symbol),
            "start_date": kwargs.get("start_date", "19700101"),
            "end_date": kwargs.get("end_date", "20500101"),
            "adjust": kwargs.get("adjust", "qfq"),
        }
        if kwargs.get("_call_timeout") is not None:
            tx_kwargs["_call_timeout"] = kwargs["_call_timeout"]
        try:
            df = self.fetch_ak_data("stock_zh_a_hist_tx", **tx_kwargs)
        except Exception as exc:
            self.logger.warning(f"Tencent stock history fallback failed: {exc}")
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(
            columns={
                "date": "日期",
                "open": "开盘",
                "close": "收盘",
                "high": "最高",
                "low": "最低",
                "amount": "成交量",
            }
        )
        df["股票代码"] = symbol
        df["symbol"] = symbol
        df["name"] = symbol
        if "成交额" not in df.columns:
            df["成交额"] = None
        for column in ("振幅", "涨跌幅", "涨跌额", "换手率"):
            if column not in df.columns:
                df[column] = None
        self.logger.warning(
            "Eastmoney kline returned empty; populated STOCK_ZH_A_HIST from Tencent daily history"
        )
        return df

    def _fetch_daily_from_trends(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        params = {
            "secid": self._trend_secid(symbol),
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
            self.logger.warning(f"Eastmoney trends2 fallback failed: {exc}")
            return pd.DataFrame()

        data = data_json.get("data") or {}
        trends = data.get("trends") or []
        if not trends:
            return pd.DataFrame()
        df = pd.DataFrame([item.split(",") for item in trends])
        if df.empty or df.shape[1] < 7:
            return pd.DataFrame()
        df = df.iloc[:, :7]
        df.columns = ["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
        df["时间"] = pd.to_datetime(df["时间"], errors="coerce")
        df = df.dropna(subset=["时间"])
        if df.empty:
            return pd.DataFrame()
        for column in ("开盘", "收盘", "最高", "最低", "成交量", "成交额"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df["日期"] = df["时间"].dt.strftime("%Y-%m-%d")
        grouped = (
            df.groupby("日期", as_index=False)
            .agg(
                开盘=("开盘", "first"),
                收盘=("收盘", "last"),
                最高=("最高", "max"),
                最低=("最低", "min"),
                成交量=("成交量", "sum"),
                成交额=("成交额", "sum"),
            )
            .sort_values("日期")
        )
        previous_close = pd.to_numeric(data.get("preClose"), errors="coerce")
        changes: list[float | None] = []
        pct_changes: list[float | None] = []
        amplitudes: list[float | None] = []
        for _, row in grouped.iterrows():
            close = row["收盘"]
            high = row["最高"]
            low = row["最低"]
            if pd.isna(previous_close) or previous_close == 0:
                changes.append(None)
                pct_changes.append(None)
                amplitudes.append(None)
            else:
                change = close - previous_close
                changes.append(change)
                pct_changes.append(change / previous_close * 100)
                amplitudes.append((high - low) / previous_close * 100)
            previous_close = close
        grouped["涨跌额"] = changes
        grouped["涨跌幅"] = pct_changes
        grouped["振幅"] = amplitudes
        grouped["换手率"] = None
        grouped["股票代码"] = symbol
        grouped["symbol"] = symbol
        grouped["name"] = data.get("name") or symbol
        grouped["data_date"] = grouped["日期"]
        if start_date:
            start = pd.to_datetime(start_date, errors="coerce")
            if not pd.isna(start):
                grouped = grouped[pd.to_datetime(grouped["日期"]) >= start]
        if end_date:
            end = pd.to_datetime(end_date, errors="coerce")
            if not pd.isna(end):
                grouped = grouped[pd.to_datetime(grouped["日期"]) <= end]
        if not grouped.empty:
            self.logger.warning(
                "Eastmoney kline returned empty; populated STOCK_ZH_A_HIST from same-source trends2 aggregation"
            )
        return grouped.reset_index(drop=True)

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_zh_a_hist

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            source = str(kwargs.pop("source", "auto") or "auto").lower()
            source_aliases = {
                "tx": "tencent",
                "qq": "tencent",
                "em": "eastmoney",
                "east_money": "eastmoney",
            }
            source = source_aliases.get(source, source)
            if source not in {"auto", "eastmoney", "tencent"}:
                self.logger.warning(f"Unknown stock history source {source!r}; using auto")
                source = "auto"

            # Fetch data from AkShare
            if source == "tencent":
                df = self._fetch_daily_from_tencent(**kwargs)
            else:
                try:
                    df = self.fetch_ak_data("stock_zh_a_hist", **kwargs)
                except Exception as fetch_exc:
                    self.logger.warning(
                        f"Eastmoney kline fetch failed, trying Tencent daily history: {fetch_exc}"
                    )
                    df = pd.DataFrame()

            if df is None or df.empty:
                symbol = str(kwargs.get("symbol") or "000001")
                if source in {"auto", "tencent"}:
                    df = self._fetch_daily_from_tencent(**kwargs)
                if df is None or df.empty:
                    df = self._fetch_daily_from_trends(
                        symbol=symbol,
                        start_date=kwargs.get("start_date"),
                        end_date=kwargs.get("end_date"),
                    )
                if df is None or df.empty:
                    self.logger.warning("No data found")
                    return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            if "日期" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
                df = df.dropna(subset=["日期"]).drop_duplicates(subset=["日期"])
                df["data_date"] = df["日期"]
            elif "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()
            if "symbol" not in df.columns:
                if "股票代码" in df.columns:
                    df["symbol"] = df["股票代码"].astype(str)
                elif kwargs.get("symbol") is not None:
                    df["symbol"] = str(kwargs["symbol"])
            if "name" not in df.columns and kwargs.get("symbol") is not None:
                df["name"] = str(kwargs["symbol"])

            # Save to database. STOCK_ZH_A_HIST is keyed by (symbol, data_date);
            # deleting by data_date alone would remove the same day's rows for
            # other symbols during batch backfills.
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["symbol", "data_date"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockZhAHist()
    script.run()


if __name__ == "__main__":
    main()
