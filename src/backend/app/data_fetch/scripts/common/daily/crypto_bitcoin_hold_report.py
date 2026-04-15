"""
Crypto Bitcoin Hold Report

数据源: AkShare
函数: crypto_bitcoin_hold_report
频率: daily

返回列: 代码, 公司名称-英文, 公司名称-中文, 国家/地区, 市值, 比特币占市值比重, 持仓成本, 持仓占比, 持仓量, 当日持仓市值, 查询日期, 公告链接, 分类, 倍数
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class CryptoBitcoinHoldReport(AkshareToMySql):
    """Crypto Bitcoin Hold Report"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "CRYPTO_BITCOIN_HOLD_REPORT"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `CRYPTO_BITCOIN_HOLD_REPORT` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `代码` VARCHAR(50) COMMENT '代码',
            `公司名称-英文` VARCHAR(200) COMMENT '公司名称-英文',
            `公司名称-中文` VARCHAR(200) COMMENT '公司名称-中文',
            `国家/地区` VARCHAR(100) COMMENT '国家/地区',
            `市值` DOUBLE COMMENT '市值',
            `比特币占市值比重` DOUBLE COMMENT '比特币占市值比重',
            `持仓成本` DOUBLE COMMENT '持仓成本',
            `持仓占比` DOUBLE COMMENT '持仓占比',
            `持仓量` DOUBLE COMMENT '持仓量',
            `当日持仓市值` DOUBLE COMMENT '当日持仓市值',
            `查询日期` VARCHAR(50) COMMENT '查询日期',
            `公告链接` VARCHAR(500) COMMENT '公告链接',
            `分类` VARCHAR(100) COMMENT '分类',
            `倍数` DOUBLE COMMENT '倍数',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_code_date (`代码`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='比特币持仓报告'
    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.crypto_bitcoin_hold_report

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("crypto_bitcoin_hold_report", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Add data_date if not exists
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
    script = CryptoBitcoinHoldReport()
    script.fetch_data()


if __name__ == "__main__":
    main()
