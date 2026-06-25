"""
Futures Spot Sys

数据源: AkShare
函数: futures_spot_sys
频率: hourly
"""

import re
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get_100ppi(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, headers=_HEADERS, timeout=20)
    if "HW_CHECK" in response.text and "安全检查" in response.text:
        match = re.search(r'var _0x2 = "([^"]+)"', response.text)
        if match:
            session.cookies.set("HW_CHECK", match.group(1), domain="www.100ppi.com", path="/")
            response = session.get(url, headers=_HEADERS, timeout=20)
    response.raise_for_status()
    return response


def _get_sys_spot_futures_dict(session: requests.Session) -> dict[str, str]:
    response = _get_100ppi(session, "https://www.100ppi.com/sf/792.html")
    soup = BeautifulSoup(response.text, features="lxml")
    item_container = soup.find(name="div", attrs={"class": "q8"})
    if item_container is None:
        return {}
    result: dict[str, str] = {}
    for item in item_container.find_all("li"):
        link = item.find("a")
        if link is None or not link.get("href"):
            continue
        result[link.get_text().strip()] = link["href"]
    return result


def _fetch_futures_spot_sys(symbol: str, indicator: str) -> pd.DataFrame:
    session = requests.Session()
    name_url_dict = _get_sys_spot_futures_dict(session)
    if symbol not in name_url_dict:
        return pd.DataFrame()
    url = name_url_dict[symbol]
    if url.startswith("http"):
        full_url = url
    else:
        full_url = "https://www.100ppi.com" + url
    response = _get_100ppi(session, full_url)
    try:
        tables = pd.read_html(StringIO(response.text), header=0, index_col=0)
    except ValueError:
        return pd.DataFrame()

    if indicator == "市场价格":
        if len(tables) <= 1:
            return pd.DataFrame()
        result = tables[1].T
        for column in ("现货价格", "主力合约", "最近合约"):
            if column in result.columns:
                result[column] = pd.to_numeric(result[column], errors="coerce")
    elif indicator == "基差率":
        if len(tables) <= 2:
            return pd.DataFrame()
        result = tables[2].T
        if "基差率" in result.columns:
            result["基差率"] = result["基差率"].astype(str).str.replace("%", "", regex=False)
            result["基差率"] = pd.to_numeric(result["基差率"], errors="coerce")
    else:
        if len(tables) <= 3:
            return pd.DataFrame()
        result = tables[3].T
        if "主力基差" in result.columns:
            result["主力基差"] = pd.to_numeric(result["主力基差"], errors="coerce")

    result.reset_index(inplace=True)
    result.columns.name = None
    result.rename(columns={"index": "日期"}, inplace=True)
    return result


class FuturesSpotSys(AkshareToMySql):
    """Futures Spot Sys"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_SPOT_SYS"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `FUTURES_SPOT_SYS` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Futures Spot Sys'
    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.futures_spot_sys

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            symbol = str(kwargs.get("symbol") or "铜")
            indicator = str(kwargs.get("indicator") or "市场价格")
            df = _fetch_futures_spot_sys(symbol=symbol, indicator=indicator)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            if "日期" in df.columns:
                current_year = pd.Timestamp.now().year
                df["data_date"] = pd.to_datetime(
                    str(current_year) + "-" + df["日期"].astype(str), errors="coerce"
                ).dt.date
                df = df.dropna(subset=["data_date"])
            elif "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()
            if "symbol" not in df.columns:
                df["symbol"] = symbol
            if "name" not in df.columns:
                df["name"] = f"{symbol}-{indicator}"

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

    script = FuturesSpotSys()
    script.run()


if __name__ == "__main__":
    main()
