from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class EtfFundDailyEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # ETF基金实时数据表
        self.table_name = "ETF_FUND_DAILY_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `ETF_FUND_DAILY_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'ETF_FUND_DAILY' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT 'ETF基金实时数据表(东方财富)' COMMENT '参考名称',

                              -- 基金基本信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',
                              `FUND_TYPE` VARCHAR(50) COMMENT '基金类型',

                              -- 当前交易日净值信息
                              `CUR_UNIT_NET_VALUE` DECIMAL(10, 4) COMMENT '当前交易日-单位净值(元)',
                              `CUR_ACCUMULATED_NET_VALUE` DECIMAL(10, 4) COMMENT '当前交易日-累计净值(元)',

                              -- 前一个交易日净值信息
                              `PREV_UNIT_NET_VALUE` DECIMAL(10, 4) COMMENT '前一个交易日-单位净值(元)',
                              `PREV_ACCUMULATED_NET_VALUE` DECIMAL(10, 4) COMMENT '前一个交易日-累计净值(元)',

                              -- 增长信息
                              `GROWTH_VALUE` DECIMAL(10, 4) COMMENT '增长值',
                              `GROWTH_RATE` DECIMAL(10, 4) COMMENT '增长率(%)',

                              -- 市场信息
                              `MARKET_PRICE` DECIMAL(10, 4) COMMENT '市价(元)',
                              `DISCOUNT_RATE` DECIMAL(10, 4) COMMENT '折价率(%)',

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
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETF基金实时数据表(东方财富)';
                            """

    def parse_percentage(self, value):
        """
        解析百分比字符串，如'0.12%'，返回0.12

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

    def parse_net_value(self, value):
        """
        解析净值字符串，如'1.2345'，返回1.2345

        Args:
            value: 净值字符串或数值

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
            self.logger.warning(f"解析净值失败: {e}, 原始值: {value}")
            return None

    def extract_date_from_column(self, df, column_prefix):
        """
        从列名中提取日期

        Args:
            df: 数据框
            column_prefix: 列名前缀，如'当前交易日-单位净值'

        Returns:
            str: 日期字符串，格式为'YYYY-MM-DD'
        """
        for col in df.columns:
            if col.startswith(column_prefix):
                # 尝试从列名中提取日期，例如："2023-08-11-单位净值" -> "2023-08-11"
                date_str = col.replace(column_prefix, "").strip(" -")
                try:
                    # 尝试解析日期
                    datetime.strptime(date_str, "%Y-%m-%d")
                    return date_str
                except ValueError:
                    continue
        return None

    def fetch_etf_daily_data(self):
        """
        获取ETF基金每日数据

        Returns:
            pd.DataFrame: 处理后的ETF基金数据
        """
        try:
            self.logger.info("开始获取ETF基金每日数据...")

            # 获取数据
            df = self.fetch_ak_data("fund_etf_fund_daily_em")

            if df is None or df.empty:
                self.logger.warning("未获取到ETF基金每日数据")
                return None

            # 动态列名匹配：akshare返回的列名格式为 '{date}-单位净值' 等
            cols = df.columns.tolist()
            cur_date = datetime.now().strftime("%Y-%m-%d")

            # 构建动态列名映射
            column_mapping = {
                "基金代码": "FUND_CODE",
                "基金简称": "FUND_NAME",
                "类型": "FUND_TYPE",
                "增长值": "GROWTH_VALUE_STR",
                "增长率": "GROWTH_RATE_STR",
                "市价": "MARKET_PRICE_STR",
                "折价率": "DISCOUNT_RATE_STR",
            }

            # 匹配包含 '单位净值' 或 '累计净值' 的动态列名
            nav_cols = [c for c in cols if "单位净值" in c or "累计净值" in c]
            if len(nav_cols) >= 4:
                column_mapping[nav_cols[0]] = "CUR_UNIT_NET_VALUE_STR"
                column_mapping[nav_cols[1]] = "CUR_ACCUMULATED_NET_VALUE_STR"
                column_mapping[nav_cols[2]] = "PREV_UNIT_NET_VALUE_STR"
                column_mapping[nav_cols[3]] = "PREV_ACCUMULATED_NET_VALUE_STR"
                # 从第一个列名提取日期
                import re

                m = re.search(r"(\d{4}-\d{2}-\d{2})", nav_cols[0])
                if m:
                    cur_date = m.group(1)
            elif len(nav_cols) >= 2:
                column_mapping[nav_cols[0]] = "CUR_UNIT_NET_VALUE_STR"
                column_mapping[nav_cols[1]] = "CUR_ACCUMULATED_NET_VALUE_STR"

            df = df.rename(columns=column_mapping)

            # 添加交易日期
            df["TRADE_DATE"] = cur_date if cur_date else datetime.now().strftime("%Y-%m-%d")

            # 解析数值型数据
            df["CUR_UNIT_NET_VALUE"] = df["CUR_UNIT_NET_VALUE_STR"].apply(self.parse_net_value)
            df["CUR_ACCUMULATED_NET_VALUE"] = df["CUR_ACCUMULATED_NET_VALUE_STR"].apply(
                self.parse_net_value
            )
            df["PREV_UNIT_NET_VALUE"] = df["PREV_UNIT_NET_VALUE_STR"].apply(self.parse_net_value)
            df["PREV_ACCUMULATED_NET_VALUE"] = df["PREV_ACCUMULATED_NET_VALUE_STR"].apply(
                self.parse_net_value
            )
            df["GROWTH_VALUE"] = df["GROWTH_VALUE_STR"].apply(self.parse_net_value)
            df["GROWTH_RATE"] = df["GROWTH_RATE_STR"].apply(self.parse_percentage)
            df["MARKET_PRICE"] = df["MARKET_PRICE_STR"].apply(self.parse_net_value)
            df["DISCOUNT_RATE"] = df["DISCOUNT_RATE_STR"].apply(self.parse_percentage)

            # 生成主键
            df["R_ID"] = df["FUND_CODE"] + "_" + df["TRADE_DATE"]

            # 添加系统字段
            df["REFERENCE_CODE"] = "ETF_FUND_DAILY"
            df["REFERENCE_NAME"] = "ETF基金实时数据表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "FUND_NAME",
                "FUND_TYPE",
                "CUR_UNIT_NET_VALUE",
                "CUR_ACCUMULATED_NET_VALUE",
                "PREV_UNIT_NET_VALUE",
                "PREV_ACCUMULATED_NET_VALUE",
                "GROWTH_VALUE",
                "GROWTH_RATE",
                "MARKET_PRICE",
                "DISCOUNT_RATE",
                "TRADE_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功获取{len(df)}条ETF基金每日数据")
            return df

        except Exception as e:
            self.logger.error(f"获取ETF基金每日数据失败: {e}", exc_info=True)
            return None

    def save_etf_daily_data(self, df):
        """
        保存ETF基金每日数据到数据库

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
            self.logger.info("开始执行ETF基金每日数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取数据
            df = self.fetch_etf_daily_data()

            if df is None or df.empty:
                self.logger.error("未获取到有效数据")
                return False

            # 保存数据
            success = self.save_etf_daily_data(df)

            if success:
                self.logger.info(f"成功保存{len(df)}条ETF基金每日数据")
            else:
                self.logger.error("保存ETF基金每日数据失败")

            return success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    # 更新ETF基金每日数据
    data_updater = EtfFundDailyEm()
    data_updater.run()
