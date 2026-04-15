"""
Crypto Js Spot

数据源: AkShare
函数: crypto_js_spot
频率: hourly

返回列: 市场, 交易品种, 最近报价, 涨跌额, 涨跌幅, 24小时最高, 24小时最低, 24小时成交量, 更新时间
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class CryptoJsSpot(AkshareToMySql):
    """Crypto Js Spot"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "CRYPTO_JS_SPOT"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `CRYPTO_JS_SPOT` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `市场` VARCHAR(100) COMMENT '市场',
            `交易品种` VARCHAR(100) COMMENT '交易品种',
            `最近报价` DOUBLE COMMENT '最近报价',
            `涨跌额` DOUBLE COMMENT '涨跌额',
            `涨跌幅` DOUBLE COMMENT '涨跌幅',
            `24小时最高` DOUBLE COMMENT '24小时最高',
            `24小时最低` DOUBLE COMMENT '24小时最低',
            `24小时成交量` DOUBLE COMMENT '24小时成交量',
            `更新时间` VARCHAR(50) COMMENT '更新时间',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间戳',
        UNIQUE KEY uk_market_symbol_date (`市场`, `交易品种`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数字货币现货行情'
    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.crypto_js_spot

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("crypto_js_spot", **kwargs)

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
    script = CryptoJsSpot()
    script.fetch_data()


if __name__ == "__main__":
    main()
