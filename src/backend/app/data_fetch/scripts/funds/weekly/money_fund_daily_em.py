from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class MoneyFundDailyEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 货币型基金收益数据表
        self.table_name = "MONEY_FUND_DAILY_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `MONEY_FUND_DAILY_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'MONEY_FUND_DAILY' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '货币型基金收益表(东方财富)' COMMENT '参考名称',

                              -- 基金基本信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',

                              -- 当前交易日数据
                              `CUR_DAY_INCOME_PER_10K` DECIMAL(10, 4) COMMENT '当前交易日-万份收益(元)',
                              `CUR_DAY_ANNUAL_YIELD` DECIMAL(10, 4) COMMENT '当前交易日-7日年化(%)',
                              `CUR_DAY_NET_VALUE` DECIMAL(10, 4) COMMENT '当前交易日-单位净值(元)',

                              -- 前一交易日数据
                              `PREV_DAY_INCOME_PER_10K` DECIMAL(10, 4) COMMENT '前一交易日-万份收益(元)',
                              `PREV_DAY_ANNUAL_YIELD` DECIMAL(10, 4) COMMENT '前一交易日-7日年化(%)',
                              `PREV_DAY_NET_VALUE` DECIMAL(10, 4) COMMENT '前一交易日-单位净值(元)',

                              -- 其他信息
                              `DAILY_RETURN` VARCHAR(50) COMMENT '日涨幅',
                              `ESTABLISHMENT_DATE` DATE COMMENT '成立日期',
                              `FUND_MANAGER` VARCHAR(200) COMMENT '基金经理',
                              `FEE` VARCHAR(50) COMMENT '手续费',
                              `PURCHASE_STATUS` VARCHAR(50) COMMENT '可购全部',

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
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='货币型基金收益表(东方财富)';
                            """

    def parse_percentage(self, value):
        """
        解析百分比字符串，如'3.97%'，返回3.97

        Args:
            value: 百分比字符串

        Returns:
            float or None: 解析后的数值，如果解析失败返回None
        """
        if pd.isna(value) or value == "---":
            return None

        try:
            if isinstance(value, str):
                value = value.replace("%", "")
            return float(value)
        except (ValueError, TypeError):
            return None

    def parse_float(self, value):
        """
        解析浮点数字符串，如'0.8585'，返回0.8585

        Args:
            value: 浮点数字符串

        Returns:
            float or None: 解析后的数值，如果解析失败返回None
        """
        if pd.isna(value) or value == "---":
            return None

        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def fetch_money_fund_daily_data(self):
        """
        获取货币型基金每日收益数据

        Returns:
            pd.DataFrame: 处理后的货币型基金收益数据
        """
        try:
            self.logger.info("开始获取货币型基金每日收益数据...")

            # 获取数据
            df = self.fetch_ak_data("fund_money_fund_daily_em")

            if df is None or df.empty:
                self.logger.warning("未获取到货币型基金每日收益数据")
                return None

            # 重命名列 - 动态匹配日期列名
            cols = df.columns.tolist()
            column_mapping = {
                "基金代码": "FUND_CODE",
                "基金简称": "FUND_NAME",
                "日涨幅": "DAILY_RETURN",
                "成立日期": "ESTABLISHMENT_DATE_STR",
                "基金经理": "FUND_MANAGER",
                "手续费": "FEE",
                "可购全部": "PURCHASE_STATUS",
            }

            # 匹配包含 '万份收益'/'7日年化%'/'单位净值' 的动态列名
            income_cols = [c for c in cols if "万份收益" in c]
            yield_cols = [c for c in cols if "7日年化" in c]
            nav_cols = [c for c in cols if "单位净值" in c]

            if len(income_cols) >= 2:
                column_mapping[income_cols[0]] = "CUR_DAY_INCOME_PER_10K_STR"
                column_mapping[income_cols[1]] = "PREV_DAY_INCOME_PER_10K_STR"
            if len(yield_cols) >= 2:
                column_mapping[yield_cols[0]] = "CUR_DAY_ANNUAL_YIELD_STR"
                column_mapping[yield_cols[1]] = "PREV_DAY_ANNUAL_YIELD_STR"
            if len(nav_cols) >= 2:
                column_mapping[nav_cols[0]] = "CUR_DAY_NET_VALUE_STR"
                column_mapping[nav_cols[1]] = "PREV_DAY_NET_VALUE_STR"

            df = df.rename(columns=column_mapping)

            # 解析数值型数据
            df["CUR_DAY_INCOME_PER_10K"] = df["CUR_DAY_INCOME_PER_10K_STR"].apply(self.parse_float)
            df["CUR_DAY_ANNUAL_YIELD"] = df["CUR_DAY_ANNUAL_YIELD_STR"].apply(self.parse_percentage)
            df["CUR_DAY_NET_VALUE"] = df["CUR_DAY_NET_VALUE_STR"].apply(self.parse_float)
            df["PREV_DAY_INCOME_PER_10K"] = df["PREV_DAY_INCOME_PER_10K_STR"].apply(
                self.parse_float
            )
            df["PREV_DAY_ANNUAL_YIELD"] = df["PREV_DAY_ANNUAL_YIELD_STR"].apply(
                self.parse_percentage
            )
            df["PREV_DAY_NET_VALUE"] = df["PREV_DAY_NET_VALUE_STR"].apply(self.parse_float)

            # 转换日期格式
            df["ESTABLISHMENT_DATE"] = pd.to_datetime(
                df["ESTABLISHMENT_DATE_STR"], errors="coerce"
            ).dt.date

            # 添加交易日期（当前日期）
            current_date = datetime.now().date()
            df["TRADE_DATE"] = current_date

            # 生成主键
            df["R_ID"] = df["FUND_CODE"] + "_" + df["TRADE_DATE"].astype(str)

            # 添加系统字段
            df["REFERENCE_CODE"] = "MONEY_FUND_DAILY"
            df["REFERENCE_NAME"] = "货币型基金收益表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "FUND_NAME",
                "CUR_DAY_INCOME_PER_10K",
                "CUR_DAY_ANNUAL_YIELD",
                "CUR_DAY_NET_VALUE",
                "PREV_DAY_INCOME_PER_10K",
                "PREV_DAY_ANNUAL_YIELD",
                "PREV_DAY_NET_VALUE",
                "DAILY_RETURN",
                "ESTABLISHMENT_DATE",
                "FUND_MANAGER",
                "FEE",
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

            self.logger.info(f"成功获取{len(df)}条货币型基金每日收益数据")
            return df

        except Exception as e:
            self.logger.error(f"获取货币型基金每日收益数据失败: {e}", exc_info=True)
            return None

    def save_money_fund_daily_data(self, df):
        """
        保存货币型基金每日收益数据到数据库

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
            self.logger.info("开始执行货币型基金每日收益数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取数据
            df = self.fetch_money_fund_daily_data()

            if df is None or df.empty:
                self.logger.error("未获取到有效数据")
                return False

            # 保存数据
            success = self.save_money_fund_daily_data(df)

            if success:
                self.logger.info(f"成功保存{len(df)}条货币型基金每日收益数据")
            else:
                self.logger.error("保存货币型基金每日收益数据失败")

            return success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    # 更新货币型基金每日收益数据
    data_updater = MoneyFundDailyEm()
    data_updater.run()
