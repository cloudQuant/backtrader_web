from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class OpenFundRankEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 开放式基金排行数据表
        self.table_name = "OPEN_FUND_RANK_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `OPEN_FUND_RANK_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'OPEN_FUND_RANK' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '开放式基金排行数据表(东方财富)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',
                              `FUND_TYPE` VARCHAR(20) COMMENT '基金类型',

                              -- 净值信息
                              `TRADE_DATE` DATE COMMENT '日期',
                              `UNIT_NET` DECIMAL(10, 6) COMMENT '单位净值',
                              `ACCUMULATED_NET` DECIMAL(10, 6) COMMENT '累计净值',

                              -- 收益率信息
                              `DAILY_RETURN` DECIMAL(10, 4) COMMENT '日增长率(%)',
                              `WEEKLY_RETURN` DECIMAL(10, 4) COMMENT '近1周(%)',
                              `MONTHLY_RETURN` DECIMAL(10, 4) COMMENT '近1月(%)',
                              `THREE_MONTH_RETURN` DECIMAL(10, 4) COMMENT '近3月(%)',
                              `SIX_MONTH_RETURN` DECIMAL(10, 4) COMMENT '近6月(%)',
                              `YEARLY_RETURN` DECIMAL(10, 4) COMMENT '近1年(%)',
                              `TWO_YEAR_RETURN` DECIMAL(10, 4) COMMENT '近2年(%)',
                              `THREE_YEAR_RETURN` DECIMAL(10, 4) COMMENT '近3年(%)',
                              `YTD_RETURN` DECIMAL(10, 4) COMMENT '今年来(%)',
                              `SINCE_INCEPTION` DECIMAL(10, 4) COMMENT '成立来(%)',
                              `CUSTOM_RETURN` DECIMAL(10, 4) COMMENT '自定义(%)',

                              -- 费用信息
                              `FEE_RATE` VARCHAR(20) COMMENT '手续费',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_OPEN_FUND_RANK_UNIQUE` (`FUND_CODE`, `TRADE_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                              KEY `IDX_FUND_TYPE` (`FUND_TYPE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='开放式基金排行数据表(东方财富)';
                            """

    def parse_date(self, date_str: str) -> datetime.date | None:
        """解析日期字符串"""
        if not date_str or pd.isna(date_str) or str(date_str).strip() == "":
            return None
        try:
            return pd.to_datetime(date_str).date()
        except Exception as e:
            self.logger.warning(f"解析日期失败: {e}, 原始值: {date_str}")
            return None

    def parse_float(self, value: Any, default: float = None) -> float | None:
        """解析浮点数值"""
        if pd.isna(value) or value in ("---", "", "--"):
            return default
        try:
            if isinstance(value, str):
                value = value.strip().rstrip("%")
                if not value or value == "--":
                    return default
            return float(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"解析浮点数失败: {e}, 原始值: {value}")
            return default

    def parse_fee_rate(self, value: str) -> str:
        """解析手续费率"""
        if pd.isna(value) or not isinstance(value, str):
            return "0.00%"
        return value.strip()

    def fetch_fund_rank_data(self, fund_type: str = "全部") -> pd.DataFrame | None:
        """
        获取开放式基金排行数据

        Args:
            fund_type: 基金类型, 可选值: "全部", "股票型", "混合型", "债券型", "指数型", "QDII", "FOF"

        Returns:
            pd.DataFrame: 处理后的基金排行数据
        """
        try:
            self.logger.info(f"开始获取{fund_type}开放式基金排行数据...")

            # 获取数据
            df = self.fetch_ak_data("fund_open_fund_rank_em", symbol=fund_type)

            if df is None or df.empty:
                self.logger.warning(f"未获取到{fund_type}开放式基金排行数据")
                return None

            # 添加基金类型
            df["FUND_TYPE"] = fund_type

            return df

        except Exception as e:
            self.logger.error(f"获取{fund_type}开放式基金排行数据失败: {e}", exc_info=True)
            return None

    def process_fund_rank_data(self, df: pd.DataFrame) -> pd.DataFrame | None:
        """处理基金排行数据"""
        if df is None or df.empty:
            return None

        try:
            # 重命名列
            df = df.rename(
                columns={
                    "基金代码": "FUND_CODE",
                    "基金简称": "FUND_NAME",
                    "日期": "TRADE_DATE_STR",
                    "单位净值": "UNIT_NET_STR",
                    "累计净值": "ACCUMULATED_NET_STR",
                    "日增长率": "DAILY_RETURN_STR",
                    "近1周": "WEEKLY_RETURN_STR",
                    "近1月": "MONTHLY_RETURN_STR",
                    "近3月": "THREE_MONTH_RETURN_STR",
                    "近6月": "SIX_MONTH_RETURN_STR",
                    "近1年": "YEARLY_RETURN_STR",
                    "近2年": "TWO_YEAR_RETURN_STR",
                    "近3年": "THREE_YEAR_RETURN_STR",
                    "今年来": "YTD_RETURN_STR",
                    "成立来": "SINCE_INCEPTION_STR",
                    "自定义": "CUSTOM_RETURN_STR",
                    "手续费": "FEE_RATE_STR",
                }
            )

            # 解析日期
            df["TRADE_DATE"] = df["TRADE_DATE_STR"].apply(self.parse_date)

            # 解析数值
            numeric_columns = {
                "UNIT_NET": "UNIT_NET_STR",
                "ACCUMULATED_NET": "ACCUMULATED_NET_STR",
                "DAILY_RETURN": "DAILY_RETURN_STR",
                "WEEKLY_RETURN": "WEEKLY_RETURN_STR",
                "MONTHLY_RETURN": "MONTHLY_RETURN_STR",
                "THREE_MONTH_RETURN": "THREE_MONTH_RETURN_STR",
                "SIX_MONTH_RETURN": "SIX_MONTH_RETURN_STR",
                "YEARLY_RETURN": "YEARLY_RETURN_STR",
                "TWO_YEAR_RETURN": "TWO_YEAR_RETURN_STR",
                "THREE_YEAR_RETURN": "THREE_YEAR_RETURN_STR",
                "YTD_RETURN": "YTD_RETURN_STR",
                "SINCE_INCEPTION": "SINCE_INCEPTION_STR",
                "CUSTOM_RETURN": "CUSTOM_RETURN_STR",
            }

            for col, src_col in numeric_columns.items():
                df[col] = df[src_col].apply(lambda x: self.parse_float(x, None))

            # 解析手续费
            df["FEE_RATE"] = df["FEE_RATE_STR"].apply(self.parse_fee_rate)

            # 生成主键
            df["R_ID"] = df.apply(
                lambda x: (
                    f"{x['FUND_CODE']}_{x['TRADE_DATE']}"
                    if pd.notna(x["TRADE_DATE"])
                    else x["FUND_CODE"]
                ),
                axis=1,
            )

            # 添加系统字段
            df["REFERENCE_CODE"] = "OPEN_FUND_RANK"
            df["REFERENCE_NAME"] = "开放式基金排行数据表(东方财富)"
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
                "TRADE_DATE",
                "UNIT_NET",
                "ACCUMULATED_NET",
                "DAILY_RETURN",
                "WEEKLY_RETURN",
                "MONTHLY_RETURN",
                "THREE_MONTH_RETURN",
                "SIX_MONTH_RETURN",
                "YEARLY_RETURN",
                "TWO_YEAR_RETURN",
                "THREE_YEAR_RETURN",
                "YTD_RETURN",
                "SINCE_INCEPTION",
                "CUSTOM_RETURN",
                "FEE_RATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功处理{len(df)}条开放式基金排行数据")
            return df

        except Exception as e:
            self.logger.error(f"处理开放式基金排行数据失败: {e}", exc_info=True)
            return None

    def save_fund_rank_data(self, df: pd.DataFrame) -> bool:
        """
        保存开放式基金排行数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有开放式基金排行数据需要保存")
            return False

        # 获取已存在的数据ID
        existing_ids = self._get_existing_ids()

        # 过滤掉已存在的数据
        if existing_ids:
            df = df[~df["R_ID"].isin(existing_ids)]

        if df.empty:
            self.logger.info("没有新的开放式基金排行数据需要保存")
            return True

        return self.save_data(
            df=df,
            table_name=self.table_name,
            on_duplicate_update=True,
            unique_keys=["R_ID"],
        )

    def _get_existing_ids(self) -> set:
        """获取已存在的数据ID"""
        try:
            self.connect_db()
            sql = "SELECT R_ID FROM OPEN_FUND_RANK_EM WHERE IS_ACTIVE = 1"
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
            return {row[0] for row in result} if result else set()
        except Exception as e:
            self.logger.error(f"获取已存在数据ID失败: {e}")
            return set()

    def run(self, fund_types: list[str] = None):
        """
        执行数据获取和保存

        Args:
            fund_types: 基金类型列表，默认为所有类型

        Returns:
            bool: 是否执行成功
        """
        if fund_types is None:
            fund_types = ["全部", "股票型", "混合型", "债券型", "指数型", "QDII", "FOF"]

        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行开放式基金排行数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            all_data = []
            for fund_type in fund_types:
                # 获取数据
                df = self.fetch_fund_rank_data(fund_type)
                if df is not None and not df.empty:
                    all_data.append(df)

            if not all_data:
                self.logger.error("未获取到有效的开放式基金排行数据")
                return False

            # 合并所有数据
            combined_df = pd.concat(all_data, ignore_index=True)

            # 处理数据
            processed_df = self.process_fund_rank_data(combined_df)

            if processed_df is None or processed_df.empty:
                self.logger.error("处理开放式基金排行数据失败")
                return False

            # 保存数据
            success = self.save_fund_rank_data(processed_df)

            if success:
                self.logger.info(f"成功保存{len(processed_df)}条开放式基金排行数据")
            else:
                self.logger.error("保存开放式基金排行数据失败")

            return success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    # 更新开放式基金排行数据
    data_updater = OpenFundRankEm()
    # 可以指定基金类型，如：data_updater.run(["股票型", "混合型"])
    data_updater.run()
