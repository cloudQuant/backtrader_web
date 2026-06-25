"""
Index Bloomberg Billionaires Hist

数据源: AkShare
函数: index_bloomberg_billionaires_hist
频率: weekly
"""

from io import StringIO

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexBloombergBillionairesHist(AkshareToMySql):
    """Index Bloomberg Billionaires Hist"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_BLOOMBERG_BILLIONAIRES_HIST"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `INDEX_BLOOMBERG_BILLIONAIRES_HIST` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `rank` INT COMMENT '排名',
            `year` INT COMMENT '年份',
            `total_net_worth` VARCHAR(50) COMMENT '总净值',
            `last_change` VARCHAR(50) COMMENT '最近变化',
            `ytd_change` VARCHAR(50) COMMENT '年初至今变化',
            `country` VARCHAR(100) COMMENT '国家/地区',
            `industry` VARCHAR(100) COMMENT '行业',
            `age` VARCHAR(50) COMMENT '年龄',
            `source_of_wealth` VARCHAR(255) COMMENT '财富来源',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Index Bloomberg Billionaires Hist'
    """

    @staticmethod
    def _normalise_columns(df: pd.DataFrame, year: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        # Older pages keep the title and header in the first two data rows.
        if "Rank" not in df.columns:
            header_rows = df[df.iloc[:, 0].astype(str).str.strip().eq("Rank")]
            if header_rows.empty:
                return pd.DataFrame()
            header_idx = header_rows.index[0]
            columns = df.loc[header_idx].astype(str).str.strip().tolist()
            df = df.loc[header_idx + 1 :].copy()
            df.columns = columns

        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]
        rename_map = {
            "Rank": "rank",
            "Name": "name",
            "Total net worth $Billion": "total_net_worth",
            "Total net worth ($US Billion)": "total_net_worth",
            "Net Worth ($US billion)": "total_net_worth",
            "$ Last change": "last_change",
            "$ YTD change": "ytd_change",
            "YTD change ($US)": "ytd_change",
            "Country": "country",
            "Citizenship": "country",
            "Industry": "industry",
            "Source of Wealth": "source_of_wealth",
            "Age": "age",
        }
        df = df.rename(columns=rename_map)
        if "rank" not in df.columns or "name" not in df.columns:
            return pd.DataFrame()

        df = df[pd.to_numeric(df["rank"], errors="coerce").notna()].copy()
        if df.empty:
            return pd.DataFrame()

        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").astype("Int64")
        df["year"] = int(year)
        df["symbol"] = df["rank"].astype(str)
        df["data_date"] = pd.to_datetime(f"{year}-12-31").date()

        for col in [
            "total_net_worth",
            "last_change",
            "ytd_change",
            "country",
            "industry",
            "age",
            "source_of_wealth",
        ]:
            if col not in df.columns:
                df[col] = pd.NA

        output_columns = [
            "symbol",
            "name",
            "data_date",
            "rank",
            "year",
            "total_net_worth",
            "last_change",
            "ytd_change",
            "country",
            "industry",
            "age",
            "source_of_wealth",
        ]
        return df[output_columns].reset_index(drop=True)

    def _fetch_hist_year(self, year: str) -> pd.DataFrame:
        url = f"https://stats.areppim.com/listes/list_billionairesx{year[-2:]}xwor.htm"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        if not tables:
            return pd.DataFrame()
        return self._normalise_columns(tables[0], year)

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.index_bloomberg_billionaires_hist

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            year = str(kwargs.pop("year", "2021"))
            df = self._fetch_hist_year(year)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

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

    script = IndexBloombergBillionairesHist()
    script.run()


if __name__ == "__main__":
    main()
