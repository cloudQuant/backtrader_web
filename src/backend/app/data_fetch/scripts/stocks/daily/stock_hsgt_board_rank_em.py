"""
Stock Hsgt Board Rank Em

数据源: AkShare
函数: stock_hsgt_board_rank_em
频率: daily
"""

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockHsgtBoardRankEm(AkshareToMySql):
    """Stock Hsgt Board Rank Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HSGT_BOARD_RANK_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_HSGT_BOARD_RANK_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `board_rank_type` VARCHAR(50) COMMENT '排行类型',
            `indicator` VARCHAR(20) COMMENT '统计周期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_type_indicator_date (`board_rank_type`, `indicator`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Hsgt Board Rank Em'
    """

    SYMBOL_MAP = {
        "北向资金增持行业板块排行": "5",
        "北向资金增持概念板块排行": "4",
        "北向资金增持地域板块排行": "3",
    }
    INDICATOR_MAP = {
        "今日": "1",
        "3日": "3",
        "5日": "5",
        "10日": "10",
        "1月": "M",
        "1季": "Q",
        "1年": "Y",
    }

    @classmethod
    def fetch_board_rank(
        cls,
        *,
        symbol: str = "北向资金增持行业板块排行",
        indicator: str = "今日",
        page_size: int = 500,
        max_pages: int = 1,
        timeout: int = 15,
    ) -> pd.DataFrame:
        board_type = cls.SYMBOL_MAP.get(symbol, cls.SYMBOL_MAP["北向资金增持行业板块排行"])
        interval_type = cls.INDICATOR_MAP.get(indicator, cls.INDICATOR_MAP["今日"])
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com/hsgtcg/hy.html",
        }
        frames = []
        for page in range(1, max(1, int(max_pages)) + 1):
            params = {
                "sortColumns": "TRADE_DATE",
                "sortTypes": "-1",
                "pageSize": str(page_size),
                "pageNumber": str(page),
                "reportName": "RPT_MUTUAL_BOARD_HOLDRANK_WEB",
                "columns": "ALL",
                "quoteColumns": "f3~05~SECURITY_CODE~INDEX_CHANGE_RATIO",
                "source": "WEB",
                "client": "WEB",
                "filter": f'(BOARD_TYPE="{board_type}")(INTERVAL_TYPE="{interval_type}")',
            }
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            data_json = response.json()
            result = data_json.get("result") or {}
            records = result.get("data") or []
            if not records:
                break
            frames.append(pd.DataFrame(records))
            if page >= int(result.get("pages") or 1):
                break
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def normalize_columns(
        df: pd.DataFrame,
        *,
        board_rank_type: str,
        indicator: str,
    ) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        if "BOARD_CODE" in df.columns:
            df["symbol"] = df["BOARD_CODE"].astype(str).str.strip()
        elif "BOARD_NAME" in df.columns:
            df["symbol"] = df["BOARD_NAME"].astype(str).str.strip()
        if "BOARD_NAME" in df.columns:
            df["name"] = df["BOARD_NAME"].astype(str).str.strip()
        elif "symbol" in df.columns:
            df["name"] = df["symbol"]
        if "TRADE_DATE" in df.columns:
            df["data_date"] = pd.to_datetime(df["TRADE_DATE"], errors="coerce").dt.date
        elif "报告时间" in df.columns:
            df["data_date"] = pd.to_datetime(df["报告时间"], errors="coerce").dt.date
        elif "data_date" not in df.columns:
            df["data_date"] = pd.Timestamp.now().date()
        df["board_rank_type"] = str(board_rank_type)
        df["indicator"] = str(indicator)
        front_columns = ["symbol", "name", "data_date", "board_rank_type", "indicator"]
        ordered = [col for col in front_columns if col in df.columns]
        ordered.extend(col for col in df.columns if col not in ordered)
        return df[ordered]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_hsgt_board_rank_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            symbol = kwargs.pop("symbol", "北向资金增持行业板块排行")
            indicator = kwargs.pop("indicator", "今日")
            page_size = int(kwargs.pop("page_size", 500))
            max_pages = int(kwargs.pop("max_pages", 1))
            timeout = int(kwargs.pop("_call_timeout", kwargs.pop("timeout", 15)))
            df = self.fetch_board_rank(
                symbol=symbol,
                indicator=indicator,
                page_size=page_size,
                max_pages=max_pages,
                timeout=timeout,
            )

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = self.normalize_columns(
                df,
                board_rank_type=symbol,
                indicator=indicator,
            )

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            for data_date in sorted(df["data_date"].dropna().astype(str).unique()):
                self.delete_data(
                    self.table_name,
                    {
                        "board_rank_type": str(symbol),
                        "indicator": str(indicator),
                        "data_date": data_date,
                    },
                )
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockHsgtBoardRankEm()
    script.run()


if __name__ == "__main__":
    main()
