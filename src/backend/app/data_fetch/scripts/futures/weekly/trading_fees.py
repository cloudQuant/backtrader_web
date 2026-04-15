import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesFees(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_TRADING_FEES"
        self.create_table_sql = r"""
                                CREATE TABLE FUTURES_TRADING_FEES (
                                    R_ID VARCHAR(36) NOT NULL COMMENT '记录唯一标识符',
                                    REFERENCE_CODE VARCHAR(50) NOT NULL COMMENT '数据来源编码',
                                    REFERENCE_NAME VARCHAR(100) NOT NULL COMMENT '数据来源名称',
                                    BASEDATE DATE NOT NULL COMMENT '数据日期',
                                    EXCHANGE VARCHAR(50) COMMENT '交易所',
                                    PRODUCT_CODE VARCHAR(50) COMMENT '品种代码',
                                    PRODUCT_NAME VARCHAR(100) COMMENT '品种名称',
                                    CONTRACT_MULTIPLIER INT COMMENT '合约乘数',
                                    MIN_PRICE_CHANGE DECIMAL(16,4) COMMENT '最小跳动',
                                    OPEN_FEE_RATE DECIMAL(16,6) COMMENT '开仓费率（按金额）',
                                    OPEN_FEE_AMOUNT DECIMAL(16,4) COMMENT '开仓费用（按手）',
                                    CLOSE_FEE_RATE DECIMAL(16,6) COMMENT '平仓费率（按金额）',
                                    CLOSE_FEE_AMOUNT DECIMAL(16,4) COMMENT '平仓费用（按手）',
                                    CLOSE_TODAY_FEE_RATE DECIMAL(16,6) COMMENT '平今费率（按金额）',
                                    CLOSE_TODAY_FEE_AMOUNT DECIMAL(16,4) COMMENT '平今费用（按手）',
                                    LONG_MARGIN_RATE DECIMAL(16,6) COMMENT '做多保证金率（按金额）',
                                    LONG_MARGIN_AMOUNT DECIMAL(16,4) COMMENT '做多保证金（按手）',
                                    SHORT_MARGIN_RATE DECIMAL(16,6) COMMENT '做空保证金率（按金额）',
                                    SHORT_MARGIN_AMOUNT DECIMAL(16,4) COMMENT '做空保证金（按手）',
                                    PREV_SETTLE_PRICE DECIMAL(16,4) COMMENT '上日结算价',
                                    PREV_CLOSE_PRICE DECIMAL(16,4) COMMENT '上日收盘价',
                                    LATEST_PRICE DECIMAL(16,4) COMMENT '最新价',
                                    VOLUME BIGINT COMMENT '成交量',
                                    OPEN_INTEREST BIGINT COMMENT '持仓量',
                                    OPEN_FEE_PER_LOT DECIMAL(16,4) COMMENT '1手开仓费用',
                                    CLOSE_FEE_PER_LOT DECIMAL(16,4) COMMENT '1手平仓费用',
                                    CLOSE_TODAY_FEE_PER_LOT DECIMAL(16,4) COMMENT '1手平今费用',
                                    LONG_MARGIN_PER_LOT DECIMAL(16,4) COMMENT '做多1手保证金',
                                    SHORT_MARGIN_PER_LOT DECIMAL(16,4) COMMENT '做空1手保证金',
                                    VALUE_PER_LOT DECIMAL(16,4) COMMENT '一手市值',
                                    TICK1_PNL DECIMAL(16,4) COMMENT '1Tick平仓盈亏',
                                    TICK1_NET_PNL DECIMAL(16,4) COMMENT '1Tick平仓净盈利',
                                    TICK2_PNL DECIMAL(16,4) COMMENT '2Tick平仓盈亏',
                                    TICK2_NET_PNL DECIMAL(16,4) COMMENT '2Tick平仓净盈利',
                                    TICK1_RETURN_RATE VARCHAR(20) COMMENT '1Tick平仓收益率',
                                    TICK2_RETURN_RATE VARCHAR(20) COMMENT '2Tick平仓收益率',
                                    TICK1_TODAY_PNL DECIMAL(16,4) COMMENT '1Tick平今盈亏',
                                    TICK2_TODAY_PNL DECIMAL(16,4) COMMENT '2Tick平今盈亏',
                                    TICK1_TODAY_RETURN_RATE VARCHAR(20) COMMENT '1Tick平今收益率',
                                    TICK2_TODAY_RETURN_RATE VARCHAR(20) COMMENT '2Tick平今收益率',
                                    UPDATE_TIME VARCHAR(30) COMMENT '更新时间',
                                    -- 系统字段
                                    CREATEDATE DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                    CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建用户',
                                    UPDATEDATE DATETIME COMMENT '更新时间',
                                    UPDATEUSER VARCHAR(50) COMMENT '更新用户',

                                    -- 主键约束
                                    PRIMARY KEY (R_ID),

                                    -- 唯一约束
                                    UNIQUE KEY UK_TRADING_FEES (REFERENCE_CODE, BASEDATE),

                                    -- 普通索引
                                    INDEX IDX_TRADING_FEES_DATE (BASEDATE),
                                    INDEX IDX_TRADING_FEES_EXCHANGE (EXCHANGE),
                                    INDEX IDX_TRADING_FEES_PRODUCT (PRODUCT_CODE)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='期货交易费用参照表';

                                """

    def run(self):
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("正在获取期货交易费用数据")
        df = self.fetch_ak_data("futures_fees_info")
        if df is not None and not df.empty:
            self.logger.info(f"成功获取期货交易费用数据，共 {len(df)} 条记录")
            # self.logger.info(f"数据列名: {list(df.columns)}")
            df.columns = [
                "EXCHANGE",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "PRODUCT_CODE",
                "PRODUCT_NAME",
                "CONTRACT_MULTIPLIER",
                "MIN_PRICE_CHANGE",
                "OPEN_FEE_RATE",
                "OPEN_FEE_AMOUNT",
                "CLOSE_FEE_RATE",
                "CLOSE_FEE_AMOUNT",
                "CLOSE_TODAY_FEE_RATE",
                "CLOSE_TODAY_FEE_AMOUNT",
                "LONG_MARGIN_RATE",
                "LONG_MARGIN_AMOUNT",
                "SHORT_MARGIN_RATE",
                "SHORT_MARGIN_AMOUNT",
                "PREV_SETTLE_PRICE",
                "PREV_CLOSE_PRICE",
                "LATEST_PRICE",
                "VOLUME",
                "OPEN_INTEREST",
                "OPEN_FEE_PER_LOT",
                "CLOSE_FEE_PER_LOT",
                "CLOSE_TODAY_FEE_PER_LOT",
                "LONG_MARGIN_PER_LOT",
                "SHORT_MARGIN_PER_LOT",
                "VALUE_PER_LOT",
                "TICK1_PNL",
                "TICK1_NET_PNL",
                "TICK2_NET_PNL",
                "TICK1_RETURN_RATE",
                "TICK2_RETURN_RATE",
                "TICK1_TODAY_PNL",
                "TICK2_TODAY_PNL",
                "TICK1_TODAY_RETURN_RATE",
                "TICK2_TODAY_RETURN_RATE",
                "UPDATE_TIME",
            ]
            # Drop columns not in DDL to avoid 'Unknown column' errors
            ddl_columns = {
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "BASEDATE",
                "EXCHANGE",
                "PRODUCT_CODE",
                "PRODUCT_NAME",
                "CONTRACT_MULTIPLIER",
                "MIN_PRICE_CHANGE",
                "OPEN_FEE_RATE",
                "OPEN_FEE_AMOUNT",
                "CLOSE_FEE_RATE",
                "CLOSE_FEE_AMOUNT",
                "CLOSE_TODAY_FEE_RATE",
                "CLOSE_TODAY_FEE_AMOUNT",
                "LONG_MARGIN_RATE",
                "LONG_MARGIN_AMOUNT",
                "SHORT_MARGIN_RATE",
                "SHORT_MARGIN_AMOUNT",
                "PREV_SETTLE_PRICE",
                "PREV_CLOSE_PRICE",
                "LATEST_PRICE",
                "VOLUME",
                "OPEN_INTEREST",
                "OPEN_FEE_PER_LOT",
                "CLOSE_FEE_PER_LOT",
                "CLOSE_TODAY_FEE_PER_LOT",
                "LONG_MARGIN_PER_LOT",
                "SHORT_MARGIN_PER_LOT",
                "VALUE_PER_LOT",
                "TICK1_PNL",
                "TICK1_NET_PNL",
                "TICK2_PNL",
                "TICK2_NET_PNL",
                "TICK1_RETURN_RATE",
                "TICK2_RETURN_RATE",
                "TICK1_TODAY_PNL",
                "TICK2_TODAY_PNL",
                "TICK1_TODAY_RETURN_RATE",
                "TICK2_TODAY_RETURN_RATE",
                "UPDATE_TIME",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            }
            df["R_ID"] = [self.get_uuid() for i in range(len(df))]
            df["BASEDATE"] = df["UPDATE_TIME"]
            df["CREATEDATE"] = df["UPDATE_TIME"]
            df["CREATEUSER"] = "system"
            df["UPDATEDATE"] = df["UPDATE_TIME"]
            df["UPDATEUSER"] = "system"
            # Keep only columns that exist in the DDL
            extra_cols = set(df.columns) - ddl_columns
            if extra_cols:
                df = df.drop(columns=list(extra_cols), errors="ignore")
            self.save_data(df, "FUTURES_TRADING_FEES", ignore_duplicates=True)
            return df
        else:
            self.logger.warning("获取到的数据为空")
            return pd.DataFrame()


if __name__ == "__main__":
    data_updater = FuturesFees()
    data_updater.run()
