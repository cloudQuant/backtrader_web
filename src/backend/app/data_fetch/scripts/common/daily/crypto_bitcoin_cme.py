"""
Crypto Bitcoin Cme

数据源: AkShare
函数: crypto_bitcoin_cme
频率: daily

返回列: 商品, 类型, 电子交易合约, 场内成交合约, 场外成交合约, 成交量, 未平仓合约, 持仓变化
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class CryptoBitcoinCme(AkshareToMySql):
    """Crypto Bitcoin Cme"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "CRYPTO_BITCOIN_CME"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `CRYPTO_BITCOIN_CME` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `商品` VARCHAR(100) COMMENT '商品',
            `类型` VARCHAR(100) COMMENT '类型',
            `电子交易合约` DOUBLE COMMENT '电子交易合约',
            `场内成交合约` DOUBLE COMMENT '场内成交合约',
            `场外成交合约` DOUBLE COMMENT '场外成交合约',
            `成交量` DOUBLE COMMENT '成交量',
            `未平仓合约` DOUBLE COMMENT '未平仓合约',
            `持仓变化` DOUBLE COMMENT '持仓变化',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_product_type_date (`商品`, `类型`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='比特币CME持仓数据'
    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.crypto_bitcoin_cme

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("crypto_bitcoin_cme", **kwargs)

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
    script = CryptoBitcoinCme()
    script.fetch_data()


if __name__ == "__main__":
    main()
