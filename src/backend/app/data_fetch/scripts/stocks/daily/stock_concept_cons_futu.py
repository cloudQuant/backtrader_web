"""
Stock Concept Cons Futu

数据源: AkShare
函数: stock_concept_cons_futu
频率: daily
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockConceptConsFutu(AkshareToMySql):
    """Stock Concept Cons Futu"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_CONCEPT_CONS_FUTU"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_CONCEPT_CONS_FUTU` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Concept Cons Futu'
    """

    @staticmethod
    def _fetch_futu_html(symbol: str) -> pd.DataFrame:
        url_map = {
            "特朗普概念股": "https://www.futunn.com/sectors/Donald-Trump-BK22962",
            "巴菲特持仓": "https://www.futunn.com/stock/BK2999",
            "佩洛西持仓": "https://www.futunn.com/stock/BK20883",
        }
        url = url_map.get(symbol)
        if not url:
            return pd.DataFrame()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.futunn.com/quote/sparks-us",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        response = requests.get(url, headers=headers, timeout=(5, 15))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, features="lxml")
        rows = []
        for item in soup.select("div.content-main a.list-item"):
            code = item.select_one(".fix-left .code")
            name = item.select_one(".fix-left .name")
            values = [
                span.get("title") or span.get_text(strip=True)
                for span in item.select(".middle .value")
            ]
            if code is None or name is None or len(values) < 5:
                continue
            rows.append(
                [
                    code.get("title") or code.get_text(strip=True),
                    name.get("title") or name.get_text(strip=True),
                    *values[:5],
                ]
            )

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(
            rows,
            columns=["代码", "股票名称", "最新价", "涨跌额", "涨跌幅", "成交量", "成交额"],
        )
        df["最新价"] = pd.to_numeric(df["最新价"], errors="coerce")
        df["涨跌额"] = pd.to_numeric(df["涨跌额"], errors="coerce")
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_concept_cons_futu

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            kwargs.pop("_call_timeout", None)
            symbol = kwargs.get("symbol", "特朗普概念股")
            df = self._fetch_futu_html(symbol)
            if df.empty:
                try:
                    df = self.fetch_ak_data("stock_concept_cons_futu", **kwargs)
                except Exception as exc:
                    self.logger.warning(
                        "AkShare Futunn API fetch failed after same-source HTML: %s", exc
                    )
                    df = pd.DataFrame()

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = df.copy()
            df["symbol"] = df["代码"].astype(str).str.strip()
            df["name"] = df["股票名称"]
            df["concept_name"] = symbol
            df["data_date"] = pd.Timestamp.now().date()

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

    script = StockConceptConsFutu()
    script.run()


if __name__ == "__main__":
    main()
