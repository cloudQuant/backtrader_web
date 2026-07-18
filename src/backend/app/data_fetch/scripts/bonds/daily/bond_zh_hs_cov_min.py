"""
Bond Zh Hs Cov Min

数据源: AkShare
函数: bond_zh_hs_cov_min
频率: daily
"""

import pandas as pd
from akshare.utils.request import request_with_retry as request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class BondZhHsCovMin(AkshareToMySql):
    """Bond Zh Hs Cov Min"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "BOND_ZH_HS_COV_MIN"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `BOND_ZH_HS_COV_MIN` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `时间` DATETIME COMMENT '交易时间',
            `开盘` DOUBLE COMMENT '开盘',
            `收盘` DOUBLE COMMENT '收盘',
            `最高` DOUBLE COMMENT '最高',
            `最低` DOUBLE COMMENT '最低',
            `成交量` BIGINT COMMENT '成交量',
            `成交额` DOUBLE COMMENT '成交额',
            `最新价` DOUBLE COMMENT '最新价',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_time (`symbol`, `时间`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Bond Zh Hs Cov Min'
    """

    @staticmethod
    def _secid(symbol):
        symbol = str(symbol or "").strip()
        market = {"sh": "1", "sz": "0"}.get(symbol[:2])
        if market is None:
            return ""
        return f"{market}.{symbol[2:]}"

    def _fetch_minute_from_trends(self, symbol, start_date=None, end_date=None):
        secid = self._secid(symbol)
        if not secid:
            return pd.DataFrame()
        url = "https://push2.eastmoney.com/api/qt/stock/trends2/get"
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "iscr": "0",
            "iscca": "0",
            "ut": "f057cbcbce2a86e2866ab8877db1d059",
            "ndays": "1",
        }
        try:
            data_json = request_eastmoney(url, params=params, timeout=20).json()
        except Exception as exc:
            self.logger.warning(f"Eastmoney convertible bond trends2 fallback failed: {exc}")
            return pd.DataFrame()
        trends = ((data_json.get("data") or {}).get("trends")) or []
        if not trends:
            return pd.DataFrame()
        df = pd.DataFrame([item.split(",") for item in trends])
        columns = ["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "最新价"]
        if df.empty or df.shape[1] < len(columns):
            return pd.DataFrame()
        df = df.iloc[:, : len(columns)]
        df.columns = columns
        df["时间"] = pd.to_datetime(df["时间"], errors="coerce")
        df = df.dropna(subset=["时间"])
        if start_date or end_date:
            df = df.set_index("时间")
            df = df[start_date:end_date].reset_index()
        for column in ("开盘", "收盘", "最高", "最低", "成交量", "成交额", "最新价"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
        if not df.empty:
            self.logger.warning(
                "Eastmoney convertible bond min wrapper failed; populated "
                "BOND_ZH_HS_COV_MIN from same-source trends2 data"
            )
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.bond_zh_hs_cov_min

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            kwargs.setdefault("symbol", "sh110074")
            kwargs.setdefault("period", "1")
            kwargs.setdefault("_call_timeout", 30)
            # Fetch data from AkShare
            try:
                df = self.fetch_ak_data("bond_zh_hs_cov_min", **kwargs)
            except Exception as fetch_exc:
                self.logger.warning(
                    f"Eastmoney convertible bond min fetch failed, trying same-source "
                    f"trends2 data: {fetch_exc}"
                )
                df = pd.DataFrame()

            if df is None or df.empty:
                df = self._fetch_minute_from_trends(
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
                df["时间"] = pd.to_datetime(df["时间"], errors="coerce")
                df = df.dropna(subset=["时间"]).drop_duplicates(subset=["时间"])
                df["data_date"] = df["时间"].dt.date
            elif "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()
            if "symbol" not in df.columns:
                df["symbol"] = str(kwargs.get("symbol") or "sh110074")
            if "name" not in df.columns:
                df["name"] = str(kwargs.get("symbol") or "sh110074")

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["symbol", "时间"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = BondZhHsCovMin()
    script.run()


if __name__ == "__main__":
    main()
