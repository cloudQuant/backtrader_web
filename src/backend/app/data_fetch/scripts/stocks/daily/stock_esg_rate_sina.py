"""
Stock Esg Rate Sina

数据源: AkShare
函数: stock_esg_rate_sina
频率: daily
"""

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockEsgRateSina(AkshareToMySql):
    """Stock Esg Rate Sina"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_ESG_RATE_SINA"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_ESG_RATE_SINA` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Esg Rate Sina'
    """

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Populate standard stock columns from Sina ESG agency-rating rows."""
        if df.empty:
            return df

        df = df.copy()
        if "成分股代码" in df.columns:
            symbol = df["成分股代码"].astype(str).str.strip()
            numeric_symbol = symbol.str.fullmatch(r"\d+")
            symbol.loc[numeric_symbol] = symbol.loc[numeric_symbol].str.zfill(6)
            df["symbol"] = symbol
        if "评级机构" in df.columns:
            df["name"] = df["评级机构"].astype(str).str.strip()
        df["data_date"] = pd.Timestamp.now().date()
        return df

    @staticmethod
    def fetch_limited_pages(max_pages: int = 3) -> pd.DataFrame:
        """Fetch a bounded subset of Sina ESG agency rating pages."""
        first_url = (
            "https://global.finance.sina.com.cn/api/openapi.php/"
            "EsgService.getEsgStocks?page=1&num=200"
        )
        first_json = requests.get(first_url, timeout=30).json()
        total = int(first_json["result"]["data"]["info"]["total"])
        page_count = (total + 199) // 200
        page_count = min(page_count, max(1, int(max_pages)))

        rows = []
        for page in range(1, page_count + 1):
            url = (
                "https://global.finance.sina.com.cn/api/openapi.php/"
                f"EsgService.getEsgStocks?page={page}&num=200"
            )
            data_json = requests.get(url, timeout=30).json()
            for stock in data_json["result"]["data"]["info"]["stocks"]:
                esg_info = stock.get("esg_info") or []
                if not esg_info:
                    continue
                temp_df = pd.DataFrame(esg_info)
                temp_df["symbol"] = stock.get("symbol")
                temp_df["market"] = stock.get("market")
                rows.append(temp_df)

        if not rows:
            return pd.DataFrame()

        big_df = pd.concat(rows, ignore_index=True)
        big_df.rename(
            columns={
                "symbol": "成分股代码",
                "agency_name": "评级机构",
                "esg_score": "评级",
                "esg_dt": "评级季度",
                "remark": "标识",
                "market": "交易市场",
            },
            inplace=True,
        )
        return big_df[
            [
                "成分股代码",
                "评级机构",
                "评级",
                "评级季度",
                "标识",
                "交易市场",
            ]
        ]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_esg_rate_sina

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            max_pages = kwargs.pop("max_pages", None)
            if max_pages is not None:
                df = self.fetch_limited_pages(max_pages=int(max_pages))
            else:
                df = self.fetch_ak_data("stock_esg_rate_sina", **kwargs)

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
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockEsgRateSina()
    script.run()


if __name__ == "__main__":
    main()
