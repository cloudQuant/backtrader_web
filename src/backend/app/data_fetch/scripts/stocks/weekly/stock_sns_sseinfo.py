"""
Stock Sns Sseinfo

数据源: AkShare
函数: stock_sns_sseinfo
频率: weekly
"""

import pandas as pd
import requests
from akshare.stock_feature.stock_sns_sseinfo import _fetch_stock_uid
from bs4 import BeautifulSoup

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockSnsSseinfo(AkshareToMySql):
    """Stock Sns Sseinfo"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_SNS_SSEINFO"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_SNS_SSEINFO` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Sns Sseinfo'
    """

    @staticmethod
    def _parse_page(html: str) -> pd.DataFrame:
        soup = BeautifulSoup(html, features="lxml")
        content_list = [
            item.get_text().strip()
            for item in soup.find_all(name="div", attrs={"class": "m_feed_txt"})
        ]
        date_list = [
            item.get_text().strip().split("\n")[0]
            for item in soup.find_all(name="div", attrs={"class": "m_feed_from"})
        ]
        source_list = [
            item.get_text().strip().split("\n")[2]
            for item in soup.find_all(name="div", attrs={"class": "m_feed_from"})
        ]
        if not content_list:
            return pd.DataFrame()

        q_list = [item.split(")")[1] for index, item in enumerate(content_list) if index % 2 == 0]
        stock_name = [
            item.split("(")[0].strip(":")
            for index, item in enumerate(content_list)
            if index % 2 == 0
        ]
        stock_code = [
            item.split("(")[1].split(")")[0]
            for index, item in enumerate(content_list)
            if index % 2 == 0
        ]
        a_list = [item for index, item in enumerate(content_list) if index % 2 != 0]
        d_q_list = [item for index, item in enumerate(date_list) if index % 2 == 0]
        d_a_list = [item for index, item in enumerate(date_list) if index % 2 != 0]
        s_q_list = [item for index, item in enumerate(source_list) if index % 2 == 0]
        s_a_list = [item for index, item in enumerate(source_list) if index % 2 != 0]
        author_name = [item["title"] for item in soup.find_all(name="a", attrs={"rel": "face"})]
        row_count = min(
            len(stock_code),
            len(stock_name),
            len(q_list),
            len(a_list),
            len(d_q_list),
            len(d_a_list),
            len(s_q_list),
            len(s_a_list),
            len(author_name),
        )
        temp_df = pd.DataFrame(
            {
                "股票代码": stock_code[:row_count],
                "公司简称": stock_name[:row_count],
                "问题": q_list[:row_count],
                "回答": a_list[:row_count],
                "问题时间": d_q_list[:row_count],
                "回答时间": d_a_list[:row_count],
                "问题来源": s_q_list[:row_count],
                "回答来源": s_a_list[:row_count],
                "用户名": author_name[:row_count],
            }
        )
        return temp_df

    @staticmethod
    def fetch_limited_pages(
        symbol: str = "600000",
        max_pages: int = 3,
        uid: str | None = None,
    ) -> pd.DataFrame:
        if uid is None:
            code_uid_map = _fetch_stock_uid()
            uid = code_uid_map[symbol]
        url = "https://sns.sseinfo.com/ajax/userfeeds.do"
        params = {
            "typeCode": "company",
            "type": "11",
            "pageSize": "100",
            "uid": uid,
        }
        frames = []
        for page in range(1, max(1, int(max_pages)) + 1):
            params["page"] = str(page)
            response = requests.post(url, params=params, timeout=30)
            if len(response.text) < 300:
                break
            page_df = StockSnsSseinfo._parse_page(response.text)
            if not page_df.empty:
                frames.append(page_df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df = df.copy()
        if "股票代码" in df.columns:
            symbol = df["股票代码"].astype(str).str.strip()
            numeric_symbol = symbol.str.fullmatch(r"\d+")
            symbol.loc[numeric_symbol] = symbol.loc[numeric_symbol].str.zfill(6)
            df["symbol"] = symbol
        if "公司简称" in df.columns:
            df["name"] = df["公司简称"].astype(str).str.strip()
        if "问题时间" in df.columns:
            question_time = (
                df["问题时间"]
                .astype(str)
                .str.replace("年", "-", regex=False)
                .str.replace("月", "-", regex=False)
                .str.replace("日", "", regex=False)
            )
            df["data_date"] = pd.to_datetime(question_time, errors="coerce").dt.date
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_sns_sseinfo

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            max_pages = kwargs.pop("max_pages", None)
            if max_pages is not None:
                df = self.fetch_limited_pages(
                    symbol=kwargs.get("symbol", "600000"),
                    max_pages=int(max_pages),
                    uid=kwargs.get("uid"),
                )
            else:
                df = self.fetch_ak_data("stock_sns_sseinfo", **kwargs)

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
            if "symbol" in df.columns:
                for symbol in sorted(df["symbol"].dropna().astype(str).unique()):
                    self.delete_data(self.table_name, {"symbol": symbol})
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockSnsSseinfo()
    script.run()


if __name__ == "__main__":
    main()
