"""
Index Zh A Hist

数据源: AkShare
函数: index_zh_a_hist
频率: daily
"""

from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexZhAHist(AkshareToMySql):
    """Index Zh A Hist"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_ZH_A_HIST"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `INDEX_ZH_A_HIST` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Index Zh A Hist'
    """

    def _get_latest_trade_date(self):
        """Return latest market date stored in the legacy Chinese `日期` column."""
        try:
            self.connect_db()
            self.cursor.execute(f"SELECT MAX(`日期`) FROM `{self.table_name}`")  # nosec B608
            row = self.cursor.fetchone()
            if not row or not row[0]:
                return None
            parsed = pd.to_datetime(row[0], errors="coerce")
            if pd.isna(parsed):
                return None
            return parsed.date().isoformat()
        except Exception as exc:
            self.logger.warning(f"Failed to get latest trade date from {self.table_name}: {exc}")
            return None
        finally:
            try:
                self.disconnect_db()
            except Exception:
                pass

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.index_zh_a_hist

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            if not kwargs.get("end_date"):
                kwargs["end_date"] = datetime.now().strftime("%Y%m%d")
            if not kwargs.get("start_date"):
                latest_trade_date = self._get_latest_trade_date()
                if latest_trade_date:
                    start_date = pd.to_datetime(latest_trade_date).date()
                    end_date = datetime.strptime(kwargs["end_date"], "%Y%m%d").date()
                    if start_date > end_date:
                        self.logger.info("INDEX_ZH_A_HIST is already up to date")
                        return pd.DataFrame()
                    kwargs["start_date"] = start_date.strftime("%Y%m%d")

            # Fetch data from AkShare
            df = self.fetch_ak_data("index_zh_a_hist", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            if "日期" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
                df = df.dropna(subset=["日期"]).drop_duplicates(subset=["日期"])
                if "data_date" not in df.columns:
                    df["data_date"] = df["日期"]
            elif "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            if "日期" in df.columns:
                for trade_date in sorted(df["日期"].astype(str).unique()):
                    self.delete_data(self.table_name, {"日期": trade_date})
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = IndexZhAHist()
    script.run()


if __name__ == "__main__":
    main()
