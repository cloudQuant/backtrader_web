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
        print

        Returns:
            pd.DataFrame: 数据
        """
        self.logger.info("正在获取print")

        try:
            import akshare as ak

            # Call akshare function dynamically
            ak_func = getattr(ak, "print", None)
            if ak_func is None:
                raise AttributeError("AkShare module does not have function 'print'")

            df = ak_func(**kwargs)

            if df is not None and not df.empty:
                # Add metadata
                df["DATA_DATE"] = pd.to_datetime(df.get("data_date", pd.Timestamp.now()))
                self.save_to_mysql(df, self.table_name)
                self.logger.info(f"成功获取 {len(df)} 条记录")
            else:
                self.logger.warning("获取的数据为空")

        except Exception as e:
            self.logger.error(f"获取数据失败: {str(e)}")
            raise
