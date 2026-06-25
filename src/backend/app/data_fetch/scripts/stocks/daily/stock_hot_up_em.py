"""
Stock Hot Up Em

数据源: AkShare
函数: stock_hot_up_em
频率: daily
"""

import pandas as pd
import requests
from akshare.stock_feature.stock_hist_em import request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockHotUpEm(AkshareToMySql):
    """Stock Hot Up Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HOT_UP_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_HOT_UP_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Hot Up Em'
    """

    @staticmethod
    def fetch_rank(page_size: int = 100) -> pd.DataFrame:
        rank_url = "https://emappdata.eastmoney.com/stockrank/getAllHisRcList"
        payload = {
            "appId": "appId01",
            "globalId": "786e4c21-70dc-435a-93bb-38",
            "marketType": "",
            "pageNo": 1,
            "pageSize": int(page_size),
        }
        response = requests.post(rank_url, json=payload, timeout=20)
        response.raise_for_status()
        rank_df = pd.DataFrame(response.json().get("data") or [])
        if rank_df.empty:
            return pd.DataFrame()
        rank_df["market"] = rank_df["sc"].str[:2]
        rank_df["code6"] = rank_df["sc"].str[2:]
        rank_df["mark"] = rank_df.apply(
            lambda row: ("0." if row["market"] == "SZ" else "1.") + row["code6"],
            axis=1,
        )
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
        result = rank_df.rename(
            columns={"rk": "当前排名", "sc": "代码", "hrc": "排名较昨日变动"}
        )
        if not quote_df.empty:
            quote_df = quote_df.rename(
                columns={
                    "f2": "最新价",
                    "f3": "涨跌幅",
                    "f12": "code6",
                    "f14": "股票名称",
                }
            )
            result = result.merge(
                quote_df[["code6", "股票名称", "最新价", "涨跌幅"]],
                on="code6",
                how="left",
            )
            result["涨跌额"] = result["最新价"] * result["涨跌幅"] / 100
        result = result[
            [
                column
                for column in (
                    "排名较昨日变动",
                    "当前排名",
                    "代码",
                    "股票名称",
                    "最新价",
                    "涨跌额",
                    "涨跌幅",
                )
                if column in result.columns
            ]
        ]
        return StockHotUpEm.normalize_columns(result)

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        for column in ("排名较昨日变动", "当前排名", "最新价", "涨跌额", "涨跌幅"):
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
            **kwargs: Parameters to pass to ak.stock_hot_up_em

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

    script = StockHotUpEm()
    script.run()


if __name__ == "__main__":
    main()
