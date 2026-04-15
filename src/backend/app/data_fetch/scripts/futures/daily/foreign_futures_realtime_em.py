import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class ForeignFuturesRealtimeEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FOREIGN_FUTURES_REALTIME_EM"
        self.create_table_sql = r"""
                                CREATE TABLE `FOREIGN_FUTURES_REALTIME_EM` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FOREIGN_FUTURES_REALTIME' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '外盘期货实时行情数据(东方财富)' COMMENT '参考名称',

                                      -- 基础信息
                                      `SYMBOL_CODE` VARCHAR(50) NOT NULL COMMENT '品种代码',
                                      `SYMBOL_NAME` VARCHAR(100) NOT NULL COMMENT '品种名称',
                                      `SORT_ORDER` INT COMMENT '排序序号',

                                      -- 价格数据
                                      `LAST_PRICE` DECIMAL(20, 4) COMMENT '最新价',
                                      `OPEN_PRICE` DECIMAL(20, 4) COMMENT '今开价',
                                      `HIGH_PRICE` DECIMAL(20, 4) COMMENT '最高价',
                                      `LOW_PRICE` DECIMAL(20, 4) COMMENT '最低价',
                                      `PREV_SETTLE` DECIMAL(20, 4) COMMENT '昨结算价',

                                      -- 涨跌数据
                                      `CHANGE_AMOUNT` DECIMAL(20, 4) COMMENT '涨跌额',
                                      `CHANGE_PERCENT` DECIMAL(10, 4) COMMENT '涨跌幅(%)',

                                      -- 成交量持仓量
                                      `VOLUME` BIGINT COMMENT '成交量',
                                      `OPEN_INTEREST` BIGINT COMMENT '持仓量',
                                      `BID_VOLUME` BIGINT COMMENT '买盘量',
                                      `ASK_VOLUME` BIGINT COMMENT '卖盘量',

                                      -- 交易时间
                                      `TRADE_DATE` DATETIME COMMENT '交易日期',
                                      `UPDATE_TIME` DATETIME COMMENT '数据更新时间',

                                      -- 系统字段
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_SYMBOL_DATE` (`SYMBOL_CODE`, `TRADE_DATE`),
                                      KEY `IDX_SYMBOL_NAME` (`SYMBOL_NAME`),
                                      KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                                      KEY `IDX_UPDATE_TIME` (`UPDATE_TIME`),
                                      KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='外盘期货实时行情数据表(东方财富)';

                                """

    def run(self):
        """
        Fetches and stores real-time foreign futures data from Eastmoney.
        This function overwrites today's data with the latest snapshot upon each run.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("Starting foreign futures real-time data update.")
        table_name = "FOREIGN_FUTURES_REALTIME_EM"

        try:
            # 1. Fetch Data
            self.logger.info("Fetching real-time data from Eastmoney.")
            # df = ak.futures_global_spot_em()
            df = self.fetch_ak_data("futures_global_spot_em")
            time.sleep(2)  # Be respectful

            if df.empty:
                self.logger.warning("No real-time data returned from Eastmoney.")
                return

            # 2. Data Transformation
            df.rename(
                columns={
                    "序号": "SORT_ORDER",
                    "代码": "SYMBOL_CODE",
                    "名称": "SYMBOL_NAME",
                    "最新价": "LAST_PRICE",
                    "涨跌额": "CHANGE_AMOUNT",
                    "涨跌幅": "CHANGE_PERCENT",
                    "今开": "OPEN_PRICE",
                    "最高": "HIGH_PRICE",
                    "最低": "LOW_PRICE",
                    "昨结": "PREV_SETTLE",
                    "成交量": "VOLUME",
                    "买盘": "BID_VOLUME",
                    "卖盘": "ASK_VOLUME",
                    "持仓量": "OPEN_INTEREST",
                },
                inplace=True,
            )

            # Add custom and default columns
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["REFERENCE_CODE"] = "FOREIGN_FUTURES_REALTIME"
            df["REFERENCE_NAME"] = "外盘期货实时行情数据(东方财富)"
            df["TRADE_DATE"] = self.get_current_datetime()
            df["UPDATE_TIME"] = self.get_current_datetime()
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"
            df["CREATEUSER"] = "system"
            df["UPDATEUSER"] = "system"

            # Convert percentage to decimal
            if "CHANGE_PERCENT" in df.columns:
                df["CHANGE_PERCENT"] = pd.to_numeric(df["CHANGE_PERCENT"], errors="coerce") / 100
            # 3. Save to DB
            self.save_data(df, table_name, unique_keys=["SYMBOL_CODE", "TRADE_DATE"])
            self.logger.info("Foreign futures real-time data update finished successfully.")
            return df["SYMBOL_CODE"].tolist()

        except Exception as e:
            self.logger.error(f"An error occurred during the update process: {e}", exc_info=True)
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = ForeignFuturesRealtimeEm()
    data_updater.run()
