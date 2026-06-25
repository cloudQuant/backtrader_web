"""
Option Minute Em

数据源: AkShare
函数: option_minute_em
频率: hourly
"""

import json

import pandas as pd
from akshare.stock_feature.stock_hist_em import request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.scripts.funds.daily.option_current_em import OptionCurrentEm
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class OptionMinuteEm(AkshareToMySql):
    """Option Minute Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "OPTION_MINUTE_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `OPTION_MINUTE_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Option Minute Em'
    """

    @staticmethod
    def _resolve_contract(
        symbol: str | None = None,
        max_current_pages: int = 1,
        include_cffex: bool = True,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        current_df = OptionCurrentEm.fetch_limited_pages(
            max_pages=max_current_pages,
            include_cffex=include_cffex,
        )
        if current_df.empty:
            return symbol, None, None, None
        if symbol:
            symbol_text = str(symbol)
            matched_df = current_df[
                (current_df["symbol"].astype(str) == symbol_text)
                | (current_df["代码"].astype(str) == symbol_text)
            ]
            if matched_df.empty and "." in symbol_text:
                market, code = symbol_text.split(".", 1)
                return symbol_text, code, code, market
        else:
            matched_df = current_df[current_df["代码"].notna()]

        if matched_df.empty:
            return symbol, None, None, None
        row = matched_df.iloc[0]
        return (
            str(row.get("symbol")),
            str(row.get("代码")),
            str(row.get("name") or row.get("名称") or row.get("代码")),
            str(row.get("市场标识")),
        )

    @staticmethod
    def fetch_minute_data(
        symbol: str | None = None,
        max_current_pages: int = 1,
        include_cffex: bool = True,
    ) -> pd.DataFrame:
        secid, code, name, market = OptionMinuteEm._resolve_contract(
            symbol=symbol,
            max_current_pages=max_current_pages,
            include_cffex=include_cffex,
        )
        if not secid:
            return pd.DataFrame(columns=["time", "close", "high", "low", "volume", "amount"])
        url = "https://push2.eastmoney.com/api/qt/stock/trends2/get"
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f17",
            "fields2": "f51,f53,f54,f55,f56,f57,f58",
            "iscr": "0",
            "iscca": "0",
            "ut": "f057cbcbce2a86e2866ab8877db1d059",
            "ndays": "1",
            "cb": "quotepushdata1",
        }
        response = request_eastmoney(url, params=params, timeout=20)
        data_text = response.text
        data_json = json.loads(data_text[data_text.find("(") + 1 : data_text.rfind(")")])
        trends = (data_json.get("data") or {}).get("trends") or []
        if not trends:
            return pd.DataFrame(columns=["time", "close", "high", "low", "volume", "amount"])
        df = pd.DataFrame([item.split(",") for item in trends])
        df.columns = ["time", "close", "high", "low", "volume", "amount", "-"]
        df = df[["time", "close", "high", "low", "volume", "amount"]]
        df["symbol"] = secid
        df["name"] = name or code or secid
        df["代码"] = code
        df["市场标识"] = market
        return OptionMinuteEm.normalize_columns(df)

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        for column in ("close", "high", "low", "volume", "amount"):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        if "symbol" in df.columns:
            df["symbol"] = df["symbol"].astype(str).str.strip()
        if "name" in df.columns:
            df["name"] = df["name"].astype(str).str.strip()
        if "time" in df.columns:
            df["data_date"] = pd.to_datetime(df["time"], errors="coerce").dt.date
        if "data_date" not in df.columns:
            df["data_date"] = pd.Timestamp.now().date()
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.option_minute_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            symbol = kwargs.pop("symbol", None)
            max_current_pages = int(kwargs.pop("max_current_pages", 1))
            include_cffex = bool(kwargs.pop("include_cffex", True))
            df = self.fetch_minute_data(
                symbol=symbol,
                max_current_pages=max_current_pages,
                include_cffex=include_cffex,
            )

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            df = self.normalize_columns(df)
            if "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            if {"symbol", "data_date"}.issubset(df.columns):
                for symbol_value in sorted(df["symbol"].dropna().astype(str).unique()):
                    symbol_df = df[df["symbol"].astype(str) == symbol_value]
                    for data_date in sorted(symbol_df["data_date"].dropna().astype(str).unique()):
                        self.delete_data(
                            self.table_name,
                            {"symbol": symbol_value, "data_date": data_date},
                        )
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = OptionMinuteEm()
    script.run()


if __name__ == "__main__":
    main()
