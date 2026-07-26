"""
Stock Us Spot Em

数据源: AkShare
函数: stock_us_spot_em
频率: hourly
"""

import pandas as pd
from akshare.utils.request import request_with_retry as request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockUsSpotEm(AkshareToMySql):
    """Stock Us Spot Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_US_SPOT_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_US_SPOT_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Us Spot Em'
    """

    @staticmethod
    def fetch_limited_pages(max_pages: int = 1) -> pd.DataFrame:
        url = "https://72.push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f12",
            "fs": "m:105,m:106,m:107",
            "fields": (
                "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,"
                "f20,f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152"
            ),
        }
        frames = []
        for page in range(1, max(1, int(max_pages)) + 1):
            params["pn"] = str(page)
            response = request_eastmoney(url, params=params, timeout=20)
            data = (response.json().get("data") or {}).get("diff") or []
            if not data:
                break
            frames.append(pd.DataFrame(data))
        if not frames:
            return pd.DataFrame()
        raw = pd.concat(frames, ignore_index=True)
        df = pd.DataFrame(
            {
                "序号": range(1, len(raw) + 1),
                "名称": raw["f14"],
                "最新价": raw["f2"],
                "涨跌额": raw["f4"],
                "涨跌幅": raw["f3"],
                "开盘价": raw["f17"],
                "最高价": raw["f15"],
                "最低价": raw["f16"],
                "昨收价": raw["f18"],
                "总市值": raw["f20"],
                "市盈率": raw["f115"],
                "成交量": raw["f5"],
                "成交额": raw["f6"],
                "振幅": raw["f7"],
                "换手率": raw["f8"],
                "代码": raw["f13"].astype(str) + "." + raw["f12"].astype(str),
            }
        )
        return StockUsSpotEm.normalize_columns(df)

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        for column in (
            "最新价",
            "涨跌额",
            "涨跌幅",
            "开盘价",
            "最高价",
            "最低价",
            "昨收价",
            "总市值",
            "市盈率",
            "成交量",
            "成交额",
            "振幅",
            "换手率",
        ):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        if "代码" in df.columns:
            df["symbol"] = df["代码"].astype(str).str.strip()
        if "名称" in df.columns:
            df["name"] = df["名称"].astype(str).str.strip()
        df["data_date"] = pd.Timestamp.now().date()
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_us_spot_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            max_pages = kwargs.pop("max_pages", None)
            if max_pages is not None:
                df = self.fetch_limited_pages(max_pages=int(max_pages))
            else:
                df = self.fetch_ak_data("stock_us_spot_em", **kwargs)

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
            if "data_date" in df.columns:
                for data_date in sorted(df["data_date"].dropna().astype(str).unique()):
                    self.delete_data(self.table_name, {"data_date": data_date})
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockUsSpotEm()
    script.run()


if __name__ == "__main__":
    main()
