"""
Stock Dxsyl Em

数据源: AkShare
函数: stock_dxsyl_em
频率: daily
"""

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


OUTPUT_COLUMNS = [
    "序号",
    "股票代码",
    "股票简称",
    "发行价",
    "最新价",
    "网上-发行中签率",
    "网上-有效申购股数",
    "网上-有效申购户数",
    "网上-超额认购倍数",
    "网下-配售中签率",
    "网下-有效申购股数",
    "网下-有效申购户数",
    "网下-配售认购倍数",
    "总发行数量",
    "开盘溢价",
    "首日涨幅",
    "上市日期",
]


class StockDxsylEm(AkshareToMySql):
    """Stock Dxsyl Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_DXSYL_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_DXSYL_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Dxsyl Em'
    """

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    def _fetch_eastmoney_data(
        self, *, page_size: int = 400, max_pages: int | None = None
    ) -> pd.DataFrame:
        """Fetch from the same Eastmoney endpoint using stable page sizes."""

        page_size = max(1, min(int(page_size or 400), 400))
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "sortColumns": "LISTING_DATE,SECURITY_CODE",
            "sortTypes": "-1,-1",
            "pageSize": str(page_size),
            "pageNumber": "1",
            "reportName": "RPTA_APP_IPOAPPLY",
            "quoteColumns": "f2~01~SECURITY_CODE,f14~01~SECURITY_CODE",
            "quoteType": "0",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
            "filter": """((APPLY_DATE>'2010-01-01')(|@APPLY_DATE="NULL"))((LISTING_DATE>'2010-01-01')(|@LISTING_DATE="NULL"))(TRADE_MARKET_CODE!="069001017")""",
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://data.eastmoney.com/xg/xg/dxsyl.html",
        }
        session = requests.Session()
        frames: list[pd.DataFrame] = []
        total_pages: int | None = None

        page = 1
        while True:
            params["pageNumber"] = str(page)
            response = session.get(url, params=params, headers=headers, timeout=(5, 25))
            response.raise_for_status()
            data_json = response.json()
            result = data_json.get("result") or {}
            if total_pages is None:
                total_pages = int(result.get("pages") or 0)
                if max_pages is not None:
                    total_pages = min(total_pages, int(max_pages))
            records = result.get("data") or []
            if records:
                frames.append(pd.DataFrame(records))
            if total_pages is None or page >= total_pages:
                break
            page += 1

        if not frames:
            return self._empty_frame()

        big_df = pd.concat(frames, ignore_index=True)
        big_df.reset_index(inplace=True)
        big_df["index"] = big_df.index + 1
        big_df.rename(
            columns={
                "index": "序号",
                "SECURITY_CODE": "股票代码",
                "f14": "股票简称",
                "ISSUE_PRICE": "发行价",
                "LATELY_PRICE": "最新价",
                "ONLINE_ISSUE_LWR": "网上-发行中签率",
                "ONLINE_VA_SHARES": "网上-有效申购股数",
                "ONLINE_VA_NUM": "网上-有效申购户数",
                "ONLINE_ES_MULTIPLE": "网上-超额认购倍数",
                "OFFLINE_VAP_RATIO": "网下-配售中签率",
                "OFFLINE_VATS": "网下-有效申购股数",
                "OFFLINE_VAP_OBJECT": "网下-有效申购户数",
                "OFFLINE_VAS_MULTIPLE": "网下-配售认购倍数",
                "ISSUE_NUM": "总发行数量",
                "LD_OPEN_PREMIUM": "开盘溢价",
                "LD_CLOSE_CHANGE": "首日涨幅",
                "LISTING_DATE": "上市日期",
            },
            inplace=True,
        )
        for column in OUTPUT_COLUMNS:
            if column not in big_df.columns:
                big_df[column] = None
        big_df = big_df[OUTPUT_COLUMNS].copy()

        numeric_columns = [
            "发行价",
            "最新价",
            "网上-发行中签率",
            "网上-有效申购股数",
            "网上-有效申购户数",
            "网上-超额认购倍数",
            "网下-配售中签率",
            "网下-有效申购股数",
            "网下-有效申购户数",
            "网下-配售认购倍数",
            "总发行数量",
            "开盘溢价",
            "首日涨幅",
        ]
        for column in numeric_columns:
            big_df[column] = pd.to_numeric(big_df[column], errors="coerce")
        big_df["上市日期"] = pd.to_datetime(big_df["上市日期"], errors="coerce").dt.date
        return big_df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_dxsyl_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            kwargs.pop("_call_timeout", None)
            page_size = int(kwargs.pop("page_size", 400))
            max_pages = kwargs.pop("max_pages", None)
            df = self._fetch_eastmoney_data(page_size=page_size, max_pages=max_pages)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = df.copy()
            df["symbol"] = df["股票代码"].astype(str).str.zfill(6)
            df["name"] = df["股票简称"]
            df["data_date"] = pd.to_datetime(df["上市日期"], errors="coerce").dt.date
            df["data_date"] = df["data_date"].fillna(pd.Timestamp.now().date())

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

    script = StockDxsylEm()
    script.run()


if __name__ == "__main__":
    main()
