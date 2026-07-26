"""
Migration Area Baidu

数据源: AkShare
函数: migration_area_baidu
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class MigrationAreaBaidu(AkshareToMySql):
    """Migration Area Baidu"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MIGRATION_AREA_BAIDU"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `MIGRATION_AREA_BAIDU` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `area` VARCHAR(100) COMMENT '查询区域',
            `indicator` VARCHAR(20) COMMENT '迁徙方向',
            `city_name` VARCHAR(100) COMMENT '城市名称',
            `province_name` VARCHAR(100) COMMENT '省份名称',
            `value` DOUBLE COMMENT '迁徙比例',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_area_indicator_date (`area`, `indicator`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Migration Area Baidu'
    """

    @staticmethod
    def _parse_data_date(date_value=None):
        if date_value is None:
            return pd.Timestamp.now().date()
        parsed = pd.to_datetime(str(date_value), format="%Y%m%d", errors="coerce")
        if pd.isna(parsed):
            parsed = pd.to_datetime(date_value, errors="coerce")
        if pd.isna(parsed):
            return pd.Timestamp.now().date()
        return parsed.date()

    @staticmethod
    def normalize_columns(
        df: pd.DataFrame,
        *,
        area: str = "重庆市",
        indicator: str = "move_in",
        date=None,
    ) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()

        row_count = len(df)
        province = (
            df["province_name"].fillna("").astype(str).str.strip()
            if "province_name" in df.columns
            else pd.Series([""] * row_count, index=df.index)
        )
        city = (
            df["city_name"].fillna("").astype(str).str.strip()
            if "city_name" in df.columns
            else pd.Series([""] * row_count, index=df.index)
        )
        symbol = (province + "/" + city).str.strip("/")
        fallback = pd.Series(df.index.astype(str), index=df.index)
        df["symbol"] = symbol.where(symbol != "", fallback)
        df["name"] = city.where(city != "", df["symbol"])
        df["area"] = str(area)
        df["indicator"] = str(indicator)
        df["data_date"] = MigrationAreaBaidu._parse_data_date(date)
        if "value" in df.columns:
            df["value"] = pd.to_numeric(df["value"], errors="coerce")

        front_columns = [
            "symbol",
            "name",
            "data_date",
            "area",
            "indicator",
            "city_name",
            "province_name",
            "value",
        ]
        ordered = [col for col in front_columns if col in df.columns]
        ordered.extend(col for col in df.columns if col not in ordered)
        return df[ordered]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.migration_area_baidu

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("migration_area_baidu", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = self.normalize_columns(
                df,
                area=kwargs.get("area", "重庆市"),
                indicator=kwargs.get("indicator", "move_in"),
                date=kwargs.get("date"),
            )

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            for data_date in sorted(df["data_date"].dropna().astype(str).unique()):
                self.delete_data(
                    self.table_name,
                    {
                        "area": str(kwargs.get("area", "重庆市")),
                        "indicator": str(kwargs.get("indicator", "move_in")),
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

    script = MigrationAreaBaidu()
    script.run()


if __name__ == "__main__":
    main()
