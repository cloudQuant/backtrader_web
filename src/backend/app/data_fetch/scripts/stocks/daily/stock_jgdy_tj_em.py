"""
Stock Jgdy Tj Em

数据源: AkShare
函数: stock_jgdy_tj_em
频率: daily
"""

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockJgdyTjEm(AkshareToMySql):
    """Stock Jgdy Tj Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_JGDY_TJ_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_JGDY_TJ_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Jgdy Tj Em'
    """

    @staticmethod
    def fetch_limited_pages(date: str = "20240601", max_pages: int = 3) -> pd.DataFrame:
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "sortColumns": "NOTICE_DATE,SUM,RECEIVE_START_DATE,SECURITY_CODE",
            "sortTypes": "-1,-1,-1,1",
            "pageSize": "500",
            "pageNumber": "1",
            "reportName": "RPT_ORG_SURVEYNEW",
            "columns": "ALL",
            "quoteColumns": "f2~01~SECURITY_CODE~CLOSE_PRICE,f3~01~SECURITY_CODE~CHANGE_RATE",
            "source": "WEB",
            "client": "WEB",
            "filter": f"""(NUMBERNEW="1")(IS_SOURCE="1")(NOTICE_DATE>'{"-".join([date[:4], date[4:6], date[6:]])}')""",
        }
        response = requests.get(url, params=params, timeout=30)
        data_json = response.json()
        total_page = int(data_json["result"]["pages"])
        page_count = min(total_page, max(1, int(max_pages)))
        frames = []
        for page in range(1, page_count + 1):
            params.update({"pageNumber": page})
            response = requests.get(url, params=params, timeout=30)
            data_json = response.json()
            temp_df = pd.DataFrame(data_json["result"]["data"])
            if not temp_df.empty:
                frames.append(temp_df)
        if not frames:
            return pd.DataFrame()

        big_df = pd.concat(frames, ignore_index=True)
        big_df.reset_index(inplace=True)
        big_df["index"] = list(range(1, len(big_df) + 1))
        big_df.columns = [
            "序号",
            "_",
            "代码",
            "名称",
            "_",
            "公告日期",
            "接待日期",
            "_",
            "_",
            "_",
            "_",
            "_",
            "_",
            "_",
            "接待地点",
            "_",
            "接待方式",
            "_",
            "接待人员",
            "_",
            "_",
            "_",
            "_",
            "_",
            "接待机构数量",
            "_",
            "_",
            "_",
            "_",
            "_",
            "_",
            "最新价",
            "涨跌幅",
        ]
        big_df = big_df[
            [
                "序号",
                "代码",
                "名称",
                "最新价",
                "涨跌幅",
                "接待机构数量",
                "接待方式",
                "接待人员",
                "接待地点",
                "接待日期",
                "公告日期",
            ]
        ]
        big_df["最新价"] = pd.to_numeric(big_df["最新价"], errors="coerce")
        big_df["涨跌幅"] = pd.to_numeric(big_df["涨跌幅"], errors="coerce")
        big_df["接待机构数量"] = pd.to_numeric(big_df["接待机构数量"], errors="coerce")
        big_df["接待日期"] = pd.to_datetime(big_df["接待日期"], errors="coerce").dt.date
        big_df["公告日期"] = pd.to_datetime(big_df["公告日期"], errors="coerce").dt.date
        return big_df

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df = df.copy()
        if "代码" in df.columns:
            symbol = df["代码"].astype(str).str.strip()
            numeric_symbol = symbol.str.fullmatch(r"\d+")
            symbol.loc[numeric_symbol] = symbol.loc[numeric_symbol].str.zfill(6)
            df["symbol"] = symbol
        if "名称" in df.columns:
            df["name"] = df["名称"].astype(str).str.strip()
        if "接待日期" in df.columns:
            df["data_date"] = pd.to_datetime(df["接待日期"], errors="coerce").dt.date
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_jgdy_tj_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            max_pages = kwargs.pop("max_pages", None)
            if max_pages is not None:
                df = self.fetch_limited_pages(
                    date=kwargs.get("date", "20240601"),
                    max_pages=int(max_pages),
                )
            else:
                df = self.fetch_ak_data("stock_jgdy_tj_em", **kwargs)

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

    script = StockJgdyTjEm()
    script.run()


if __name__ == "__main__":
    main()
