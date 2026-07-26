"""
Index Zh A Hist

数据源: AkShare
函数: index_zh_a_hist
频率: daily
"""

from datetime import datetime

import pandas as pd
from akshare.utils.request import request_with_retry as request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexZhAHist(AkshareToMySql):
    """Index Zh A Hist"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_ZH_A_HIST"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `INDEX_ZH_A_HIST` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Index Zh A Hist'
    """

    def _get_latest_trade_date(self):
        """Return latest market date stored in the normalized data_date column."""
        try:
            self.connect_db()
            self.cursor.execute(f"SELECT MAX(`data_date`) FROM `{self.table_name}`")  # nosec B608
            row = self.cursor.fetchone()
            if not row or not row[0]:
                return None
            parsed = pd.to_datetime(row[0], errors="coerce")
            if pd.isna(parsed):
                return None
            return parsed.date().isoformat()
        except Exception as exc:
            self.logger.warning(f"Failed to get latest trade date from {self.table_name}: {exc}")
            return None
        finally:
            try:
                self.disconnect_db()
            except Exception:
                pass

    @staticmethod
    def _index_secid_candidates(symbol: str) -> list[str]:
        symbol = str(symbol or "").strip()
        candidates = [f"{market}.{symbol}" for market in ("1", "0", "2", "47")]
        if symbol == "000300":
            candidates.insert(0, "1.000300")
            candidates.insert(1, "0.399300")
        return list(dict.fromkeys(candidates))

    def _fetch_daily_from_trends(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        """Build a daily index row from Eastmoney trends2 when kline is unavailable."""
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        last_error: Exception | None = None
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
                response = request_eastmoney(url, params=params, timeout=15)
                data_json = response.json()
            except Exception as exc:
                last_error = exc
                continue

            data = data_json.get("data") or {}
            trends = data.get("trends") or []
            if not trends:
                continue

            df = pd.DataFrame([item.split(",") for item in trends])
            if df.empty or df.shape[1] < 7:
                continue
            df = df.iloc[:, :7]
            df.columns = ["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
            df["时间"] = pd.to_datetime(df["时间"], errors="coerce")
            df = df.dropna(subset=["时间"])
            if df.empty:
                continue
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
            change_values: list[float | None] = []
            pct_values: list[float | None] = []
            amplitude_values: list[float | None] = []
            for _, row in grouped.iterrows():
                close = row["收盘"]
                high = row["最高"]
                low = row["最低"]
                if pd.isna(previous_close) or previous_close == 0:
                    change_values.append(None)
                    pct_values.append(None)
                    amplitude_values.append(None)
                else:
                    change = close - previous_close
                    change_values.append(change)
                    pct_values.append(change / previous_close * 100)
                    amplitude_values.append((high - low) / previous_close * 100)
                previous_close = close
            grouped["振幅"] = amplitude_values
            grouped["涨跌幅"] = pct_values
            grouped["涨跌额"] = change_values
            grouped["换手率"] = None
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
                    "Eastmoney kline returned empty; populated INDEX_ZH_A_HIST from same-source trends2 aggregation"
                )
                return grouped.reset_index(drop=True)

        if last_error is not None:
            self.logger.warning(f"Eastmoney trends2 fallback failed: {last_error}")
        return pd.DataFrame()

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.index_zh_a_hist

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            if not kwargs.get("end_date"):
                kwargs["end_date"] = datetime.now().strftime("%Y%m%d")
            if not kwargs.get("start_date"):
                latest_trade_date = self._get_latest_trade_date()
                if latest_trade_date:
                    start_date = pd.to_datetime(latest_trade_date).date()
                    end_date = datetime.strptime(kwargs["end_date"], "%Y%m%d").date()
                    if start_date > end_date:
                        self.logger.info("INDEX_ZH_A_HIST is already up to date")
                        return pd.DataFrame()
                    kwargs["start_date"] = start_date.strftime("%Y%m%d")

            # Fetch data from AkShare
            try:
                df = self.fetch_ak_data("index_zh_a_hist", **kwargs)
            except Exception as fetch_exc:
                self.logger.warning(
                    f"Eastmoney kline fetch failed, trying same-source trends2 aggregation: {fetch_exc}"
                )
                df = pd.DataFrame()

            if df is None or df.empty:
                symbol = str(kwargs.get("symbol") or "000300")
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
                if "data_date" not in df.columns:
                    df["data_date"] = df["日期"]
            elif "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()
            if "symbol" not in df.columns and kwargs.get("symbol") is not None:
                df["symbol"] = str(kwargs["symbol"])
            if "name" not in df.columns and kwargs.get("symbol") is not None:
                df["name"] = str(kwargs["symbol"])

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            if "日期" in df.columns:
                for trade_date in sorted(df["日期"].astype(str).unique()):
                    self.delete_data(self.table_name, {"data_date": trade_date})
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = IndexZhAHist()
    script.run()


if __name__ == "__main__":
    main()
