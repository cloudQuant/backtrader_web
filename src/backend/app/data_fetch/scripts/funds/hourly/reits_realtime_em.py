from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class ReitsRealtimeEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "REITS_REALTIME_EM"
        self.create_table_sql = """
            CREATE TABLE `REITS_REALTIME_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `SECURITY_CODE` VARCHAR(20) NOT NULL COMMENT '代码',
                `SECURITY_NAME` VARCHAR(100) COMMENT '名称',
                `PRICE` DECIMAL(10, 3) COMMENT '最新价',
                `CHANGE_AMOUNT` DECIMAL(10, 3) COMMENT '涨跌额',
                `CHANGE_PERCENT` DECIMAL(10, 3) COMMENT '涨跌幅(%)',
                `VOLUME` BIGINT COMMENT '成交量(手)',
                `TURNOVER` DECIMAL(20, 2) COMMENT '成交额(万元)',
                `OPEN` DECIMAL(10, 3) COMMENT '开盘价',
                `HIGH` DECIMAL(10, 3) COMMENT '最高价',
                `LOW` DECIMAL(10, 3) COMMENT '最低价',
                `PREV_CLOSE` DECIMAL(10, 3) COMMENT '昨收',
                `UPDATE_TIME` DATETIME COMMENT '更新时间',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_SECURITY_CODE` (`SECURITY_CODE`),
                KEY `IDX_UPDATE_TIME` (`UPDATE_TIME`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='REITs实时行情表(东方财富)';
        """

    def fetch_reits_data(self):
        try:
            # 获取REITs实时行情数据
            df = self.fetch_ak_data("reits_realtime_em")

            if df is None or df.empty:
                self.logger.warning("No REITs real-time data found")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "代码": "SECURITY_CODE",
                    "名称": "SECURITY_NAME",
                    "最新价": "PRICE",
                    "涨跌额": "CHANGE_AMOUNT",
                    "涨跌幅": "CHANGE_PERCENT",
                    "成交量": "VOLUME",
                    "成交额": "TURNOVER",
                    "开盘价": "OPEN",
                    "最高价": "HIGH",
                    "最低价": "LOW",
                    "昨收": "PREV_CLOSE",
                }
            )

            # 添加更新时间
            now = datetime.now()
            df["UPDATE_TIME"] = now

            # 生成唯一ID
            df["R_ID"] = "RRE_" + df["SECURITY_CODE"].astype(str)
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 转换数值类型
            numeric_cols = [
                "PRICE",
                "CHANGE_AMOUNT",
                "CHANGE_PERCENT",
                "VOLUME",
                "TURNOVER",
                "OPEN",
                "HIGH",
                "LOW",
                "PREV_CLOSE",
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 选择需要的列并重新排序
            columns = [
                "R_ID",
                "SECURITY_CODE",
                "SECURITY_NAME",
                "PRICE",
                "CHANGE_AMOUNT",
                "CHANGE_PERCENT",
                "VOLUME",
                "TURNOVER",
                "OPEN",
                "HIGH",
                "LOW",
                "PREV_CLOSE",
                "UPDATE_TIME",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]
            return df[columns]

        except Exception as e:
            self.logger.error(f"Error fetching REITs real-time data: {e}")
            return pd.DataFrame()

    def save_reits_data(self, df):
        if df.empty:
            self.logger.warning("No data to save")
            return True

        try:
            return self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["R_ID", "SECURITY_CODE"],
            )

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def run(self):
        try:
            self.logger.info("Starting REITs real-time data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_reits_data()
            return self.save_reits_data(df)

        except Exception as e:
            self.logger.error(f"Error in run: {e}")
            return False


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    reits_realtime = ReitsRealtimeEm(logger=logging.getLogger(__name__))
    sys.exit(0 if reits_realtime.run() else 1)
