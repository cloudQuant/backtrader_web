from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FinancialFundDailyEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 理财型基金收益数据表
        self.table_name = "FINANCIAL_FUND_DAILY_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FINANCIAL_FUND_DAILY_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FINANCIAL_FUND_DAILY' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '理财型基金收益表(东方财富)' COMMENT '参考名称',

                              -- 基金基本信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',

                              -- 收益信息
                              `PREV_ANNUAL_YIELD` DECIMAL(10, 4) COMMENT '上一期年化收益率(%)',

                              -- 当前交易日数据
                              `CUR_DAY_INCOME_PER_10K` DECIMAL(10, 4) COMMENT '当前交易日-万份收益(元)',
                              `CUR_DAY_ANNUAL_YIELD` DECIMAL(10, 4) COMMENT '当前交易日-7日年化(%)',

                              -- 前一交易日数据
                              `PREV_DAY_INCOME_PER_10K` DECIMAL(10, 4) COMMENT '前一交易日-万份收益(元)',
                              `PREV_DAY_ANNUAL_YIELD` DECIMAL(10, 4) COMMENT '前一交易日-7日年化(%)',

                              -- 其他信息
                              `LOCK_PERIOD` VARCHAR(20) COMMENT '封闭期',
                              `PURCHASE_STATUS` VARCHAR(50) COMMENT '申购状态',

                              -- 系统字段
                              `TRADE_DATE` DATE COMMENT '交易日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_DATE_UNIQUE` (`FUND_CODE`, `TRADE_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='理财型基金收益表(东方财富)';
                            """

    def parse_percentage(self, value):
        """
        解析百分比字符串，如'1.8150'，返回1.8150

        Args:
            value: 百分比字符串或数值

        Returns:
            float or None: 解析后的数值，如果解析失败返回None
        """
        if pd.isna(value) or value == "---" or value == "":
            return None

        try:
            if isinstance(value, str):
                value = value.replace("%", "").strip()
                if not value:  # 空字符串
                    return None
            return float(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"解析百分比失败: {e}, 原始值: {value}")
            return None

    def parse_float(self, value):
        """
        解析浮点数字符串，如'0.4548'，返回0.4548

        Args:
            value: 浮点数字符串或数值

        Returns:
            float or None: 解析后的数值，如果解析失败返回None
        """
        if pd.isna(value) or value == "---" or value == "":
            return None

        try:
            if isinstance(value, str):
                value = value.strip()
                if not value:  # 空字符串
                    return None
            return float(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"解析浮点数失败: {e}, 原始值: {value}")
            return None

    def parse_lock_period(self, value):
        """
        解析封闭期字符串，如'28天'，返回'28天'

        Args:
            value: 封闭期字符串

        Returns:
            str: 处理后的封闭期字符串，如果为空则返回None
        """
        if pd.isna(value) or value == "---" or value == "":
            return None

        try:
            value = str(value).strip()
            return value if value else None
        except Exception as e:
            self.logger.warning(f"解析封闭期失败: {e}, 原始值: {value}")
            return None

    def fetch_financial_fund_daily_data(self):
        """
        获取理财型基金每日收益数据

        Returns:
            pd.DataFrame: 处理后的理财型基金收益数据
        """
        try:
            self.logger.info("开始获取理财型基金每日收益数据...")

            # 获取数据
            df = self.fetch_ak_data("fund_financial_fund_daily_em")

            if df is None or df.empty:
                self.logger.warning("未获取到理财型基金每日收益数据")
                return None

            # 重命名列
            column_mapping = {
                "基金代码": "FUND_CODE",
                "基金简称": "FUND_NAME",
                "上一期年化收益率": "PREV_ANNUAL_YIELD_STR",
                "当前交易日-万份收益": "CUR_DAY_INCOME_PER_10K_STR",
                "当前交易日-7日年华": "CUR_DAY_ANNUAL_YIELD_STR",
                "前一个交易日-万份收益": "PREV_DAY_INCOME_PER_10K_STR",
                "前一个交易日-7日年华": "PREV_DAY_ANNUAL_YIELD_STR",
                "封闭期": "LOCK_PERIOD",
                "申购状态": "PURCHASE_STATUS",
            }

            df = df.rename(columns=column_mapping)

            # 解析数值型数据
            df["PREV_ANNUAL_YIELD"] = df["PREV_ANNUAL_YIELD_STR"].apply(self.parse_percentage)
            df["CUR_DAY_INCOME_PER_10K"] = df["CUR_DAY_INCOME_PER_10K_STR"].apply(self.parse_float)
            df["CUR_DAY_ANNUAL_YIELD"] = df["CUR_DAY_ANNUAL_YIELD_STR"].apply(self.parse_percentage)
            df["PREV_DAY_INCOME_PER_10K"] = df["PREV_DAY_INCOME_PER_10K_STR"].apply(
                self.parse_float
            )
            df["PREV_DAY_ANNUAL_YIELD"] = df["PREV_DAY_ANNUAL_YIELD_STR"].apply(
                self.parse_percentage
            )

            # 处理封闭期
            df["LOCK_PERIOD"] = df["LOCK_PERIOD"].apply(self.parse_lock_period)

            # 添加交易日期（当前日期）
            current_date = datetime.now().date()
            df["TRADE_DATE"] = current_date

            # 生成主键
            df["R_ID"] = df["FUND_CODE"] + "_" + df["TRADE_DATE"].astype(str)

            # 添加系统字段
            df["REFERENCE_CODE"] = "FINANCIAL_FUND_DAILY"
            df["REFERENCE_NAME"] = "理财型基金收益表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "FUND_NAME",
                "PREV_ANNUAL_YIELD",
                "CUR_DAY_INCOME_PER_10K",
                "CUR_DAY_ANNUAL_YIELD",
                "PREV_DAY_INCOME_PER_10K",
                "PREV_DAY_ANNUAL_YIELD",
                "LOCK_PERIOD",
                "PURCHASE_STATUS",
                "TRADE_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功获取{len(df)}条理财型基金每日收益数据")
            return df

        except Exception as e:
            self.logger.error(f"获取理财型基金每日收益数据失败: {e}", exc_info=True)
            return None

    def save_financial_fund_daily_data(self, df):
        """
        保存理财型基金每日收益数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有数据需要保存")
            return False

        return self.save_data(
            df=df,
            table_name=self.table_name,
            on_duplicate_update=True,
            unique_keys=["R_ID"],
        )

    def run(self):
        """
        执行数据获取和保存

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行理财型基金每日收益数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取数据
            df = self.fetch_financial_fund_daily_data()

            if df is None or df.empty:
                self.logger.error("未获取到有效数据")
                return False

            # 保存数据
            success = self.save_financial_fund_daily_data(df)

            if success:
                self.logger.info(f"成功保存{len(df)}条理财型基金每日收益数据")
            else:
                self.logger.error("保存理财型基金每日收益数据失败")

            return success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    # 更新理财型基金每日收益数据
    data_updater = FinancialFundDailyEm()
    data_updater.run()
