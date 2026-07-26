"""
Cost Living

数据源: Expatistan
原 AkShare 函数: cost_living
频率: daily
"""

from io import StringIO

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

REGION_PATHS = {
    "europe": "/cost-of-living/index/europe",
    "north-america": "/cost-of-living/index/north-america",
    "latin-america": "/cost-of-living/index/latin-america",
    "asia": "/cost-of-living/index/asia",
    "middle-east": "/cost-of-living/index/middle-east",
    "africa": "/cost-of-living/index/africa",
    "oceania": "/cost-of-living/index/oceania",
    "world": "/cost-of-living/index",
}


class CostLiving(AkshareToMySql):
    """Expatistan world/city cost of living index."""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "COST_LIVING"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `COST_LIVING` (
        `R_ID` BIGINT AUTO_INCREMENT PRIMARY KEY,
        `rank` VARCHAR(20) COMMENT '排名',
        `city` VARCHAR(255) COMMENT '城市',
        `index` DOUBLE COMMENT '生活成本指数',
        `region` VARCHAR(50) COMMENT '区域',
        `data_date` DATE COMMENT '数据日期',
        `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
        `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_city_region_date (`city`, `region`, `data_date`),
        INDEX idx_data_date (`data_date`),
        INDEX idx_region (`region`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Cost Living'
    """

    def _fetch_expatistan(self, symbol: str = "world") -> pd.DataFrame:
        """Fetch cost-of-living ranking from the original Expatistan page."""
        if symbol not in REGION_PATHS:
            raise ValueError(f"Unsupported symbol={symbol!r}; choices={sorted(REGION_PATHS)}")

        url = f"https://www.expatistan.com{REGION_PATHS[symbol]}"
        # Expatistan currently serves the table to the default python-requests UA;
        # browser-like User-Agent headers trigger Cloudflare 403.
        response = requests.get(url, timeout=20)
        response.raise_for_status()

        tables = pd.read_html(StringIO(response.text))
        if not tables:
            return pd.DataFrame(columns=["rank", "city", "index", "region", "data_date"])

        df = tables[0].iloc[:, :3].copy()
        df.columns = ["rank", "city", "index"]
        df["rank"] = df["rank"].astype(str)
        df["city"] = df["city"].astype(str).str.strip()
        df["index"] = pd.to_numeric(df["index"], errors="coerce")
        df["region"] = symbol
        df["data_date"] = pd.Timestamp.now().date()
        df = df.dropna(subset=["city", "index"])
        return df[["rank", "city", "index", "region", "data_date"]]

    def fetch_data(self, symbol: str = "world", **kwargs):
        """Fetch cost living data from Expatistan and save to database."""
        try:
            df = self._fetch_expatistan(symbol=symbol)

            if df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = CostLiving()
    script.fetch_data()


if __name__ == "__main__":
    main()
