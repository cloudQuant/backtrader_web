"""
Macro China Bond Public

数据源: AkShare
函数: macro_china_bond_public
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class MacroChinaBondPublic(AkshareToMySql):
    """Macro China Bond Public"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MACRO_CHINA_BOND_PUBLIC"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `MACRO_CHINA_BOND_PUBLIC` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(191) COMMENT '品种代码',
            `name` VARCHAR(255) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Macro China Bond Public'
    """

    def _ensure_identity_columns_wide_enough(self) -> None:
        try:
            self.connect_db()
            self.cursor.execute(
                f"ALTER TABLE `{self.table_name}` "
                "MODIFY COLUMN `symbol` VARCHAR(191) NULL COMMENT '品种代码'"
            )
            self.cursor.execute(
                f"ALTER TABLE `{self.table_name}` "
                "MODIFY COLUMN `name` VARCHAR(255) NULL COMMENT '品种名称'"
            )
            self.connection.commit()
        except Exception as exc:
            self.logger.warning(f"Expand identity columns failed: {exc}")
            if self.connection:
                self.connection.rollback()
        finally:
            self.disconnect_db()

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.macro_china_bond_public

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("macro_china_bond_public", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = df.copy()
            bond_name = df["债券全称"].astype(str)
            df["symbol"] = bond_name.str.slice(0, 191)
            df["name"] = bond_name.str.slice(0, 255)
            current_year = pd.Timestamp.now().year
            df["data_date"] = pd.to_datetime(
                str(current_year) + "-" + df["发行日期"].astype(str),
                format="%Y-%m-%d",
                errors="coerce",
            ).dt.date
            df["data_date"] = df["data_date"].fillna(pd.Timestamp.now().date())

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self._ensure_identity_columns_wide_enough()
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

    script = MacroChinaBondPublic()
    script.run()


if __name__ == "__main__":
    main()
