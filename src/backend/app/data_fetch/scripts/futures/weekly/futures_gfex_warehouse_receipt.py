"""
Futures Gfex Warehouse Receipt

数据源: AkShare
函数: futures_gfex_warehouse_receipt
频率: weekly
"""

import hashlib

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql
from app.data_fetch.scripts.futures.weekly._dict_result import flatten_dict_result


class FuturesGfexWarehouseReceipt(AkshareToMySql):
    """Futures Gfex Warehouse Receipt"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_GFEX_WAREHOUSE_RECEIPT"
        self.create_table_sql = """
            CREATE TABLE IF NOT EXISTS `FUTURES_GFEX_WAREHOUSE_RECEIPT` (
              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'GFEX_WAREHOUSE' COMMENT '参考编码',
              `REFERENCE_NAME` VARCHAR(100) DEFAULT '广州期货交易所仓单日报' COMMENT '参考名称',
              `BASEDATE` DATE NOT NULL COMMENT '数据日期',
              `PRODUCT_CODE` VARCHAR(20) NOT NULL COMMENT '品种代码',
              `PRODUCT_NAME` VARCHAR(50) DEFAULT NULL COMMENT '品种名称',
              `WAREHOUSE_ID` VARCHAR(50) DEFAULT NULL COMMENT '仓库ID',
              `WAREHOUSE_NAME` VARCHAR(200) DEFAULT NULL COMMENT '仓库名称',
              `PREVIOUS_VOLUME` INT DEFAULT 0 COMMENT '昨日仓单量',
              `CURRENT_VOLUME` INT DEFAULT 0 COMMENT '今日仓单量',
              `DAILY_CHANGE` INT DEFAULT 0 COMMENT '日增减量',
              `IS_SUBTOTAL` TINYINT(1) DEFAULT 0 COMMENT '是否小计行(1:是,0:否)',
              `IS_TOTAL` TINYINT(1) DEFAULT 0 COMMENT '是否总计行(1:是,0:否)',
              `symbol` VARCHAR(50) COMMENT '品种代码',
              `name` VARCHAR(100) COMMENT '品种名称',
              `data_date` DATE COMMENT '数据日期',
              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
              PRIMARY KEY (`R_ID`),
              KEY `IDX_GFEX_WAREHOUSE_DATE` (`BASEDATE`),
              KEY `IDX_GFEX_WAREHOUSE_PRODUCT` (`PRODUCT_CODE`),
              KEY `IDX_GFEX_WAREHOUSE_NAME` (`WAREHOUSE_NAME`(50)),
              KEY `idx_symbol_date` (`symbol`, `data_date`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='广州期货交易所仓单日报'
            """

    @staticmethod
    def _stable_row_id(row: pd.Series) -> str:
        parsed_date = pd.to_datetime(row["data_date"], errors="coerce")
        date_part = "unknown" if pd.isna(parsed_date) else parsed_date.strftime("%Y%m%d")
        key = f"{row.get('symbol', '')}|{row.get('仓库/分库', '')}|{date_part}"
        digest = hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
        return f"GFEX_{date_part}_{row.get('symbol', '')}_{digest}"[:64]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.futures_gfex_warehouse_receipt

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            result = self.fetch_ak_data("futures_gfex_warehouse_receipt", **kwargs)
            df = flatten_dict_result(result, data_date=kwargs.get("date"))

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = df.copy()
            df["data_date"] = pd.to_datetime(df["data_date"], errors="coerce").dt.date
            df["R_ID"] = df.apply(self._stable_row_id, axis=1)
            df["REFERENCE_CODE"] = "GFEX_WAREHOUSE"
            df["REFERENCE_NAME"] = "广州期货交易所仓单日报"
            df["BASEDATE"] = df["data_date"]
            df["PRODUCT_CODE"] = df["symbol"].astype(str)
            if "品种" in df.columns:
                df["PRODUCT_NAME"] = df["品种"].astype(str).str.slice(0, 50)
                df["name"] = df["品种"].astype(str).str.slice(0, 100)
            if "仓库/分库" in df.columns:
                df["WAREHOUSE_NAME"] = df["仓库/分库"].astype(str).str.slice(0, 200)
                df["WAREHOUSE_ID"] = (
                    df["WAREHOUSE_NAME"]
                    .astype(str)
                    .map(
                        lambda value: hashlib.md5(
                            value.encode("utf-8"), usedforsecurity=False
                        ).hexdigest()[:16]
                    )
                )
                df["IS_SUBTOTAL"] = df["WAREHOUSE_NAME"].str.contains("小计", na=False).astype(int)
                df["IS_TOTAL"] = df["WAREHOUSE_NAME"].str.contains("总计", na=False).astype(int)
            if "昨日仓单量" in df.columns:
                df["PREVIOUS_VOLUME"] = pd.to_numeric(df["昨日仓单量"], errors="coerce")
            if "今日仓单量" in df.columns:
                df["CURRENT_VOLUME"] = pd.to_numeric(df["今日仓单量"], errors="coerce")
            if "增减" in df.columns:
                df["DAILY_CHANGE"] = pd.to_numeric(df["增减"], errors="coerce")

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = FuturesGfexWarehouseReceipt()
    script.run()


if __name__ == "__main__":
    main()
