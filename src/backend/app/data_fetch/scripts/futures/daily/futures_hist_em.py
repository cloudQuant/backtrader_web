"""
Futures Hist Em

数据源: AkShare
函数: futures_hist_em
频率: daily
"""

import akshare.futures.futures_hist_em as futures_hist_module
import pandas as pd
from akshare.utils.request import request_with_retry as request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesHistEm(AkshareToMySql):
    """Futures Hist Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_HIST_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `FUTURES_HIST_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `时间` DATE COMMENT '交易日期',
            `开盘` DOUBLE COMMENT '开盘',
            `最高` DOUBLE COMMENT '最高',
            `最低` DOUBLE COMMENT '最低',
            `收盘` DOUBLE COMMENT '收盘',
            `涨跌` DOUBLE COMMENT '涨跌',
            `涨跌幅` DOUBLE COMMENT '涨跌幅',
            `成交量` BIGINT COMMENT '成交量',
            `成交额` DOUBLE COMMENT '成交额',
            `持仓量` BIGINT COMMENT '持仓量',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Futures Hist Em'
    """

    @staticmethod
    def _secid_for_symbol(symbol):
        get_exchange_symbol_map = getattr(futures_hist_module, "__get_exchange_symbol_map")
        separate_symbol = getattr(
            futures_hist_module, "__futures_hist_separate_char_and_numbers_em"
        )
        c_contract_mkt, c_contract_to_e_contract, e_symbol_mkt, c_symbol_mkt = (
            get_exchange_symbol_map()
        )
        try:
            return f"{c_contract_mkt[symbol]}.{c_contract_to_e_contract[symbol]}"
        except KeyError:
            symbol_char, _numbers = separate_symbol(symbol)
            if symbol_char in c_symbol_mkt:
                return f"{c_symbol_mkt[symbol_char]}.{symbol}"
            if symbol_char in e_symbol_mkt:
                return f"{e_symbol_mkt[symbol_char]}.{symbol}"
            raise

    def _fetch_daily_from_trends(self, symbol, start_date=None, end_date=None):
        try:
            secid = self._secid_for_symbol(symbol)
        except Exception as exc:
            self.logger.warning(f"Resolve Eastmoney futures symbol failed: {exc}")
            return pd.DataFrame()

        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
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
            self.logger.warning(f"Eastmoney futures trends2 fallback failed: {exc}")
            return pd.DataFrame()

        data = data_json.get("data") or {}
        trends = data.get("trends") or []
        if not trends:
            return pd.DataFrame()
        df = pd.DataFrame([item.split(",") for item in trends])
        if df.empty or df.shape[1] < 7:
            return pd.DataFrame()
        df = df.iloc[:, :7]
        df.columns = ["datetime", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["datetime"])
        if df.empty:
            return pd.DataFrame()
        for column in ("开盘", "收盘", "最高", "最低", "成交量", "成交额"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df["时间"] = df["datetime"].dt.strftime("%Y-%m-%d")
        grouped = (
            df.groupby("时间", as_index=False)
            .agg(
                开盘=("开盘", "first"),
                最高=("最高", "max"),
                最低=("最低", "min"),
                收盘=("收盘", "last"),
                成交量=("成交量", "sum"),
                成交额=("成交额", "sum"),
            )
            .sort_values("时间")
        )
        previous_close = pd.to_numeric(data.get("preClose"), errors="coerce")
        changes = []
        pct_changes = []
        for _, row in grouped.iterrows():
            close = row["收盘"]
            if pd.isna(previous_close) or previous_close == 0:
                changes.append(None)
                pct_changes.append(None)
            else:
                change = close - previous_close
                changes.append(change)
                pct_changes.append(change / previous_close * 100)
            previous_close = close
        grouped["涨跌"] = changes
        grouped["涨跌幅"] = pct_changes
        grouped["持仓量"] = None
        grouped["symbol"] = symbol
        grouped["name"] = data.get("name") or symbol
        grouped["data_date"] = grouped["时间"]
        if start_date:
            start = pd.to_datetime(start_date, errors="coerce")
            if not pd.isna(start):
                grouped = grouped[pd.to_datetime(grouped["时间"]) >= start]
        if end_date:
            end = pd.to_datetime(end_date, errors="coerce")
            if not pd.isna(end):
                grouped = grouped[pd.to_datetime(grouped["时间"]) <= end]
        if not grouped.empty:
            self.logger.warning(
                "Eastmoney futures kline returned empty; populated FUTURES_HIST_EM "
                "from same-source trends2 aggregation"
            )
        return grouped.reset_index(drop=True)

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.futures_hist_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            kwargs.setdefault("symbol", "热卷主连")
            kwargs.setdefault("period", "daily")
            kwargs.setdefault("_call_timeout", 8)
            # Fetch data from AkShare
            try:
                df = self.fetch_ak_data("futures_hist_em", **kwargs)
            except Exception as fetch_exc:
                self.logger.warning(
                    f"Eastmoney futures kline fetch failed, trying same-source trends2 "
                    f"aggregation: {fetch_exc}"
                )
                df = pd.DataFrame()

            if df is None or df.empty:
                df = self._fetch_daily_from_trends(
                    kwargs.get("symbol"),
                    kwargs.get("start_date"),
                    kwargs.get("end_date"),
                )
                if df is None or df.empty:
                    self.logger.warning("No data found")
                    return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            if "时间" in df.columns:
                df["时间"] = pd.to_datetime(df["时间"], errors="coerce").dt.strftime("%Y-%m-%d")
                df = df.dropna(subset=["时间"]).drop_duplicates(subset=["时间"])
                df["data_date"] = df["时间"]
            elif "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()
            if "symbol" not in df.columns:
                df["symbol"] = str(kwargs.get("symbol") or "热卷主连")
            if "name" not in df.columns:
                df["name"] = str(kwargs.get("symbol") or "热卷主连")

            # Save to database
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

    script = FuturesHistEm()
    script.run()


if __name__ == "__main__":
    main()
