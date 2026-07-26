"""
Stock Hot Follow Xq

数据源: AkShare
函数: stock_hot_follow_xq
频率: daily
"""

import math

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockHotFollowXq(AkshareToMySql):
    """Stock Hot Follow Xq"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HOT_FOLLOW_XQ"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_HOT_FOLLOW_XQ` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Hot Follow Xq'
    """

    @staticmethod
    def fetch_rank(symbol: str = "最热门", max_pages: int | None = 30) -> pd.DataFrame:
        symbol_map = {
            "本周新增": "follow7d",
            "最热门": "follow",
        }
        order_by = symbol_map.get(symbol, symbol_map["最热门"])
        url = "https://xueqiu.com/service/v5/stock/screener/screen"
        params = {
            "category": "CN",
            "size": "200",
            "order": "desc",
            "order_by": order_by,
            "only_count": "0",
            "page": "1",
        }
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Referer": "https://xueqiu.com/hq",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }
        first_response = requests.get(url, params=params, headers=headers, timeout=20)
        first_response.raise_for_status()
        first_json = first_response.json()
        total_num = int((first_json.get("data") or {}).get("count") or 0)
        total_page = max(1, math.ceil(total_num / 200))
        if max_pages is not None:
            total_page = min(total_page, max(1, int(max_pages)))

        frames = []
        for page in range(1, total_page + 1):
            if page == 1:
                data_json = first_json
            else:
                params["page"] = str(page)
                try:
                    response = requests.get(url, params=params, headers=headers, timeout=20)
                    response.raise_for_status()
                    data_json = response.json()
                except requests.RequestException:
                    break
            page_df = pd.DataFrame((data_json.get("data") or {}).get("list") or [])
            if page_df.empty:
                continue
            frames.append(page_df)
        if not frames:
            return pd.DataFrame()
        raw = pd.concat(frames, ignore_index=True)
        value_column = "follow7d" if symbol == "本周新增" else "follow"
        df = raw[["symbol", "name", value_column, "current"]].copy()
        df.columns = ["股票代码", "股票简称", "关注", "最新价"]
        return StockHotFollowXq.normalize_columns(df)

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        for column in ("关注", "最新价"):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        if "股票代码" in df.columns:
            df["symbol"] = df["股票代码"].astype(str).str.strip()
        if "股票简称" in df.columns:
            df["name"] = df["股票简称"].astype(str).str.strip()
        df["data_date"] = pd.Timestamp.now().date()
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_hot_follow_xq

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            symbol = kwargs.pop("symbol", "最热门")
            max_pages = kwargs.pop("max_pages", 30)
            df = self.fetch_rank(symbol=symbol, max_pages=max_pages)

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

    script = StockHotFollowXq()
    script.run()


if __name__ == "__main__":
    main()
