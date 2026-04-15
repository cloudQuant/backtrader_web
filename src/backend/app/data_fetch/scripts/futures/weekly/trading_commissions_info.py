import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesCommissionInfo(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_COMMISSION_INFO"
        self.create_table_sql = r"""
                                CREATE TABLE FUTURES_COMMISSION_INFO (
                                    R_ID VARCHAR(36) NOT NULL COMMENT '记录唯一标识符',
                                    REFERENCE_CODE VARCHAR(50) NOT NULL COMMENT '数据来源编码',
                                    REFERENCE_NAME VARCHAR(100) NOT NULL COMMENT '数据来源名称',
                                    BASEDATE DATE NOT NULL COMMENT '数据日期',
                                    EXCHANGE VARCHAR(100) COMMENT '交易所名称',
                                    CURRENT_PRICE DECIMAL(16,4) COMMENT '现价',
                                    UPPER_LIMIT DECIMAL(16,4) COMMENT '涨停板',
                                    LOWER_LIMIT DECIMAL(16,4) COMMENT '跌停板',
                                    MARGIN_BUY DECIMAL(10,4) COMMENT '保证金-买开(%)',
                                    MARGIN_SELL DECIMAL(10,4) COMMENT '保证金-卖开(%)',
                                    MARGIN_PER_LOT DECIMAL(16,4) COMMENT '保证金-每手(元)',
                                    COMMISSION_OPEN_RATIO DECIMAL(10,4) COMMENT '手续费标准-开仓-万分之',
                                    COMMISSION_OPEN_AMOUNT VARCHAR(20) COMMENT '手续费标准-开仓-元',
                                    COMMISSION_CLOSE_RATIO DECIMAL(10,4) COMMENT '手续费标准-平昨-万分之',
                                    COMMISSION_CLOSE_AMOUNT VARCHAR(20) COMMENT '手续费标准-平昨-元',
                                    COMMISSION_CLOSE_TODAY_RATIO DECIMAL(10,4) COMMENT '手续费标准-平今-万分之',
                                    COMMISSION_CLOSE_TODAY_AMOUNT VARCHAR(20) COMMENT '手续费标准-平今-元',
                                    PROFIT_PER_TICK INT COMMENT '每跳毛利(元)',
                                    COMMISSION_TOTAL DECIMAL(10,4) COMMENT '手续费',
                                    NET_PROFIT_PER_TICK DECIMAL(10,4) COMMENT '每跳净利(元)',
                                    REMARKS VARCHAR(100) COMMENT '备注',
                                    COMMISSION_UPDATE_TIME VARCHAR(30) COMMENT '手续费更新时间',
                                    PRICE_UPDATE_TIME VARCHAR(30) COMMENT '价格更新时间',
                                    -- 系统字段
                                    CREATEDATE DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                    CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建用户',
                                    UPDATEDATE DATETIME COMMENT '更新时间',
                                    UPDATEUSER VARCHAR(50) COMMENT '更新用户',

                                    -- 主键约束
                                    PRIMARY KEY (R_ID),

                                    -- 唯一约束
                                    UNIQUE KEY UK_COMMISSION_INFO (REFERENCE_CODE, BASEDATE),

                                    -- 普通索引
                                    INDEX IDX_COMMISSION_DATE (BASEDATE),
                                    INDEX IDX_COMMISSION_EXCHANGE (EXCHANGE)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='期货手续费与保证金表';


                                """

    def run(self):
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        # df = ak.futures_comm_info(symbol="所有")
        df = self.fetch_ak_data("futures_comm_info", "所有")
        if df is not None and not df.empty:
            self.logger.info(f"成功获取期货交易佣金费用，共 {len(df)} 条记录")
            self.logger.info(f"数据列名: {list(df.columns)}")
            df.columns = [
                "EXCHANGE",
                "REFERENCE_NAME",
                "REFERENCE_CODE",
                "CURRENT_PRICE",
                "UPPER_LIMIT",
                "LOWER_LIMIT",
                "MARGIN_BUY",
                "MARGIN_SELL",
                "MARGIN_PER_LOT",
                "COMMISSION_OPEN_RATIO",
                "COMMISSION_OPEN_AMOUNT",
                "COMMISSION_CLOSE_RATIO",
                "COMMISSION_CLOSE_AMOUNT",
                "COMMISSION_CLOSE_TODAY_RATIO",
                "COMMISSION_CLOSE_TODAY_AMOUNT",
                "PROFIT_PER_TICK",
                "COMMISSION_TOTAL",
                "NET_PROFIT_PER_TICK",
                "REMARKS",
                "COMMISSION_UPDATE_TIME",
                "PRICE_UPDATE_TIME",
            ]
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["BASEDATE"] = df["COMMISSION_UPDATE_TIME"]
            df["CREATEDATE"] = df["COMMISSION_UPDATE_TIME"]
            df["CREATEUSER"] = "system"
            df["UPDATEDATE"] = df["COMMISSION_UPDATE_TIME"]
            df["UPDATEUSER"] = "system"
            self.save_data(df, "FUTURES_COMMISSION_INFO", ignore_duplicates=True)
            return df
        else:
            self.logger.warning("获取到的数据为空")
            return pd.DataFrame()


if __name__ == "__main__":
    data_updater = FuturesCommissionInfo()
    data_updater.run()
