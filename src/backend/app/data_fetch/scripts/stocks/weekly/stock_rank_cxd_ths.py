"""
Stock Rank Cxd Ths

数据源: AkShare
函数: stock_rank_cxd_ths
频率: weekly
"""

from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup
from py_mini_racer import py_mini_racer
from akshare.stock_feature.stock_technology_ths import _get_file_content_ths

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockRankCxdThs(AkshareToMySql):
    """Stock Rank Cxd Ths"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_RANK_CXD_THS"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_RANK_CXD_THS` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Rank Cxd Ths'
    """

    @staticmethod
    def fetch_limited_pages(symbol: str = "创月新低", max_pages: int = 1) -> pd.DataFrame:
        symbol_map = {
            "创月新低": "4",
            "半年新低": "3",
            "一年新低": "2",
            "历史新低": "1",
        }
        js_code = py_mini_racer.MiniRacer()
        js_code.eval(_get_file_content_ths("ths.js"))
        frames = []
        page_count = max(1, int(max_pages))
        for page in range(1, page_count + 1):
            v_code = js_code.call("v")
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/89.0.4389.90 Safari/537.36"
                ),
                "Cookie": f"v={v_code}",
            }
            url = (
                f"http://data.10jqka.com.cn/rank/cxd/board/{symbol_map[symbol]}/field/"
                f"stockcode/order/asc/page/{page}/ajax/1/free/1/"
            )
            response = requests.get(url, headers=headers, timeout=20)
            soup = BeautifulSoup(response.text, features="lxml")
            if page == 1:
                page_info = soup.find(name="span", attrs={"class": "page_info"})
                if page_info is not None:
                    total_page = int(page_info.text.split("/")[1])
                    page_count = min(page_count, total_page)
            temp_df = pd.read_html(StringIO(response.text))[0]
            if isinstance(temp_df.columns, pd.MultiIndex):
                temp_df.columns = [column[0] for column in temp_df.columns]
            temp_df = temp_df.iloc[:, :8]
            temp_df.columns = [
                "序号",
                "股票代码",
                "股票简称",
                "涨跌幅",
                "换手率",
                "最新价",
                "前期低点",
                "前期低点日期",
            ]
            temp_df = temp_df[temp_df["序号"].astype(str) != "序号"]
            if not temp_df.empty:
                frames.append(temp_df)
        if not frames:
            return pd.DataFrame()
        return StockRankCxdThs.normalize_columns(pd.concat(frames, ignore_index=True))

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        df["股票代码"] = df["股票代码"].astype(str).str.strip().str.zfill(6)
        df["股票简称"] = df["股票简称"].astype(str).str.strip()
        for column in ("涨跌幅", "换手率"):
            if column in df.columns:
                df[column] = df[column].astype(str).str.strip("%")
                df[column] = pd.to_numeric(df[column], errors="coerce")
        for column in ("最新价", "前期低点"):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        df["前期低点日期"] = pd.to_datetime(df["前期低点日期"], errors="coerce").dt.date
        df["symbol"] = df["股票代码"]
        df["name"] = df["股票简称"]
        df["data_date"] = df["前期低点日期"]
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_rank_cxd_ths

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            max_pages = kwargs.pop("max_pages", None)
            if max_pages is not None:
                df = self.fetch_limited_pages(
                    symbol=kwargs.get("symbol", "创月新低"),
                    max_pages=int(max_pages),
                )
            else:
                df = self.fetch_ak_data("stock_rank_cxd_ths", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
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

    script = StockRankCxdThs()
    script.run()


if __name__ == "__main__":
    main()
