"""
Stock Hk Hot Rank Em

数据源: AkShare
函数: stock_hk_hot_rank_em
频率: daily
"""

import pandas as pd
import requests
from akshare.utils.request import request_with_retry as request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockHkHotRankEm(AkshareToMySql):
    """Stock Hk Hot Rank Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HK_HOT_RANK_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_HK_HOT_RANK_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Hk Hot Rank Em'
    """

    @staticmethod
    def fetch_rank(page_size: int = 100) -> pd.DataFrame:
        rank_url = "https://emappdata.eastmoney.com/stockrank/getAllCurrHkUsList"
        payload = {
            "appId": "appId01",
            "globalId": "786e4c21-70dc-435a-93bb-38",
            "marketType": "000003",
            "pageNo": 1,
            "pageSize": int(page_size),
        }
        response = requests.post(rank_url, json=payload, timeout=20)
        response.raise_for_status()
        rank_df = pd.DataFrame(response.json().get("data") or [])
        if rank_df.empty:
            return pd.DataFrame()
        rank_df["代码"] = rank_df["sc"].astype(str).str.split("|").str[-1]
        rank_df["mark"] = "116." + rank_df["代码"]
        quote_params = {
            "ut": "f057cbcbce2a86e2866ab8877db1d059",
            "fltt": "2",
            "invt": "2",
            "fields": "f14,f3,f12,f2",
            "secids": ",".join(rank_df["mark"]) + ",?v=08926209912590994",
        }
        quote_response = request_eastmoney(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params=quote_params,
            timeout=20,
        )
        quote_df = pd.DataFrame((quote_response.json().get("data") or {}).get("diff") or [])
        result = rank_df.rename(columns={"rk": "当前排名"})
        if not quote_df.empty:
            quote_df = quote_df.rename(
                columns={
                    "f2": "最新价",
                    "f3": "涨跌幅",
                    "f12": "代码",
                    "f14": "股票名称",
                }
            )
            result = result.merge(
                quote_df[["代码", "股票名称", "最新价", "涨跌幅"]],
                on="代码",
                how="left",
            )
        result = result[
            [
                column
                for column in ("当前排名", "代码", "股票名称", "最新价", "涨跌幅")
                if column in result.columns
            ]
        ]
        return StockHkHotRankEm.normalize_columns(result)

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        for column in ("当前排名", "最新价", "涨跌幅"):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        if "代码" in df.columns:
            df["symbol"] = df["代码"].astype(str).str.strip()
        if "股票名称" in df.columns:
            df["name"] = df["股票名称"].astype(str).str.strip()
        df["data_date"] = pd.Timestamp.now().date()
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_hk_hot_rank_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            page_size = kwargs.pop("page_size", 100)
            df = self.fetch_rank(page_size=int(page_size))

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

    script = StockHkHotRankEm()
    script.run()


if __name__ == "__main__":
    main()
