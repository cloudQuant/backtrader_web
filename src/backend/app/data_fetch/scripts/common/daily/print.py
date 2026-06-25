"""
print

数据源: AkShare
文档: https://akshare.akfamily.xyz/_sources/data/qhkc/fund.md.txt
描述:
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class Print(AkshareToMySql):
    """print"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "PRINT"
        self.create_table_sql = self._get_create_table_sql()

    def _get_create_table_sql(self) -> str:
        """Generate CREATE TABLE SQL based on the data structure."""
        return (
            "CREATE TABLE IF NOT EXISTS `PRINT` ("
            "`R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',"
            "`DATA_DATE` DATE COMMENT '数据日期',"
            "`CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',"
            "`CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',"
            "`UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',"
            "`UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',"
            "PRIMARY KEY (`R_ID`),"
            "KEY `IDX_DATA_DATE` (`DATA_DATE`)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='print';"
        )

    def run(self, **kwargs):
        """
        Persist an audit row for this scanner-generated placeholder.

        Returns:
            pd.DataFrame: 数据
        """
        self.logger.info("记录 print 占位任务")

        data_date = pd.Timestamp.now().date()
        df = pd.DataFrame(
            [
                {
                    "R_ID": "PRINT_PLACEHOLDER",
                    "DATA_DATE": data_date,
                    "NOTE": "Scanner-generated placeholder; akshare has no callable named print.",
                }
            ]
        )
        self.save_data(df, self.table_name, on_duplicate_update=True, unique_keys=["R_ID"])
        self.logger.info("print 占位任务记录完成")
        return df
