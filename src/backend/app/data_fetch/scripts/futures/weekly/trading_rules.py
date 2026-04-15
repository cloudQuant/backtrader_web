from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesRules(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_TRADING_RULES"
        self.create_table_sql = r"""
                                CREATE TABLE FUTURES_TRADING_RULES (
                                    R_ID VARCHAR(36) NOT NULL COMMENT '记录唯一标识符',
                                    REFERENCE_CODE VARCHAR(50) NOT NULL COMMENT '数据来源编码',
                                    REFERENCE_NAME VARCHAR(100) NOT NULL COMMENT '数据来源名称',
                                    BASEDATE DATE NOT NULL COMMENT '数据日期',
                                    EXCHANGE VARCHAR(50) COMMENT '交易所',
                                    MARGIN_RATIO DECIMAL(10,4) COMMENT '交易保证金比例(%)',
                                    PRICE_LIMIT DECIMAL(10,4) COMMENT '涨跌停板幅度(%)',
                                    CONTRACT_MULTIPLIER INT COMMENT '合约乘数',
                                    MIN_PRICE_CHANGE DECIMAL(16,4) COMMENT '最小变动价位',
                                    MAX_ORDER_VOLUME INT COMMENT '限价单每笔最大下单手数',
                                    SPECIAL_ADJUSTMENT TEXT COMMENT '特殊合约参数调整',
                                    ADJUSTMENT_REMARKS TEXT COMMENT '调整备注',
                                    -- 系统字段
                                    CREATEDATE DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                    CREATEUSER VARCHAR(50) DEFAULT 'system' COMMENT '创建用户',
                                    UPDATEDATE DATETIME COMMENT '更新时间',
                                    UPDATEUSER VARCHAR(50) COMMENT '更新用户',

                                    -- 主键约束
                                    PRIMARY KEY (R_ID),

                                    -- 唯一约束
                                    UNIQUE KEY UK_TRADING_RULES (REFERENCE_CODE, BASEDATE),

                                    -- 普通索引
                                    INDEX IDX_RULES_DATE (BASEDATE),
                                    INDEX IDX_RULES_EXCHANGE (EXCHANGE)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='期货规则交易日历表';

                                """

    def _update_trading_rule_by_day(self, trading_day):
        try:
            new_trading_day = trading_day.replace("-", "")
            df = self.fetch_ak_data("futures_rule", new_trading_day)
            # df = ak.futures_rule(date=new_trading_day)
            if df is not None and not df.empty:
                self.logger.info(f"成功获取期货交易规则数据，共 {len(df)} 条记录")
                self.logger.info(f"数据列名: {list(df.columns)}")
                df.columns = [
                    "EXCHANGE",
                    "REFERENCE_CODE",
                    "REFERENCE_NAME",
                    "MARGIN_RATIO",
                    "PRICE_LIMIT",
                    "CONTRACT_MULTIPLIER",
                    "MIN_PRICE_CHANGE",
                    "MAX_ORDER_VOLUME",
                    "SPECIAL_ADJUSTMENT",
                    "ADJUSTMENT_REMARKS",
                ]
                df["R_ID"] = [self.get_uuid() for i in range(len(df))]
                df["BASEDATE"] = trading_day
                df["CREATEDATE"] = self.get_current_datetime()
                df["CREATEUSER"] = "system"
                df["UPDATEDATE"] = self.get_current_datetime()
                df["UPDATEUSER"] = "system"
                self.save_data(df, "FUTURES_TRADING_RULES")

            else:
                self.logger.warning("获取到的数据为空")
        except Exception as e:
            self.logger.error(e)

    # @retry_on_exception(max_retries=3, retry_delay=5)
    def run(self):
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("正在获取期货交易规则数据")
        latest_date = self.get_latest_date("FUTURES_TRADING_RULES", "BASEDATE")
        if latest_date is None:
            latest_date = "2021-01-01"
            self.logger.info("获取最新日期失败，返回None")
            assert 0
        now_date = self.get_current_date()
        trading_days_list = self.get_trading_day_list(latest_date, now_date)
        for trading_day in trading_days_list:
            self._update_trading_rule_by_day(trading_day)


if __name__ == "__main__":
    data_updater = FuturesRules()
    data_updater.run()
