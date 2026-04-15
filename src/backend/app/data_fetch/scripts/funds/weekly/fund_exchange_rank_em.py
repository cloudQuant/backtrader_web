from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundExchangeRankEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 场内交易基金排行数据表
        self.table_name = "FUND_EXCHANGE_RANK_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_EXCHANGE_RANK_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_EXCHANGE_RANK' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '场内交易基金排行数据表(东方财富)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',
                              `FUND_TYPE` VARCHAR(50) COMMENT '基金类型',

                              -- 净值信息
                              `TRADE_DATE` DATE COMMENT '日期',
                              `UNIT_NET` DECIMAL(10, 6) COMMENT '单位净值',
                              `ACCUMULATED_NET` DECIMAL(10, 6) COMMENT '累计净值',

                              -- 收益率信息
                              `WEEKLY_RETURN` DECIMAL(10, 4) COMMENT '近1周(%)',
                              `MONTHLY_RETURN` DECIMAL(10, 4) COMMENT '近1月(%)',
                              `THREE_MONTH_RETURN` DECIMAL(10, 4) COMMENT '近3月(%)',
                              `SIX_MONTH_RETURN` DECIMAL(10, 4) COMMENT '近6月(%)',
                              `YEARLY_RETURN` DECIMAL(10, 4) COMMENT '近1年(%)',
                              `TWO_YEAR_RETURN` DECIMAL(10, 4) COMMENT '近2年(%)',
                              `THREE_YEAR_RETURN` DECIMAL(10, 4) COMMENT '近3年(%)',
                              `YTD_RETURN` DECIMAL(10, 4) COMMENT '今年来(%)',
                              `SINCE_INCEPTION` DECIMAL(10, 4) COMMENT '成立来(%)',

                              -- 成立日期
                              `ESTABLISH_DATE` DATE COMMENT '成立日期',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_EXCHANGE_RANK_UNIQUE` (`FUND_CODE`, `TRADE_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                              KEY `IDX_FUND_TYPE` (`FUND_TYPE`),
                              KEY `IDX_ESTABLISH_DATE` (`ESTABLISH_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场内交易基金排行数据表(东方财富)';
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
        if pd.isna(value) or value in ("---", "", "--", "-", "---%"):
            return default
        try:
            if isinstance(value, str):
                value = value.strip().rstrip("%")
                if not value or value in ("--", "-"):
                    return default
            return float(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"解析浮点数失败: {e}, 原始值: {value}")
            return default

    def fetch_exchange_rank_data(self) -> pd.DataFrame | None:
        """
        获取场内交易基金排行数据

        Returns:
            pd.DataFrame: 处理后的场内交易基金排行数据
        """
        try:
            self.logger.info("开始获取场内交易基金排行数据...")

            # 获取数据
            df = self.fetch_ak_data("fund_exchange_rank_em")

            if df is None or df.empty:
                self.logger.warning("未获取到场内交易基金排行数据")
                return None

            return df

        except Exception as e:
            self.logger.error(f"获取场内交易基金排行数据失败: {e}", exc_info=True)
            return None

    def process_exchange_rank_data(self, df: pd.DataFrame) -> pd.DataFrame | None:
        """处理场内交易基金排行数据"""
        if df is None or df.empty:
            return None

        try:
            # 重命名列
            df = df.rename(
                columns={
                    "基金代码": "FUND_CODE",
                    "基金简称": "FUND_NAME",
                    "类型": "FUND_TYPE",
                    "日期": "TRADE_DATE_STR",
                    "单位净值": "UNIT_NET_STR",
                    "累计净值": "ACCUMULATED_NET_STR",
                    "近1周": "WEEKLY_RETURN_STR",
                    "近1月": "MONTHLY_RETURN_STR",
                    "近3月": "THREE_MONTH_RETURN_STR",
                    "近6月": "SIX_MONTH_RETURN_STR",
                    "近1年": "YEARLY_RETURN_STR",
                    "近2年": "TWO_YEAR_RETURN_STR",
                    "近3年": "THREE_YEAR_RETURN_STR",
                    "今年来": "YTD_RETURN_STR",
                    "成立来": "SINCE_INCEPTION_STR",
                    "成立日期": "ESTABLISH_DATE_STR",
                }
            )

            # 解析日期
            df["TRADE_DATE"] = df["TRADE_DATE_STR"].apply(self.parse_date)
            df["ESTABLISH_DATE"] = df["ESTABLISH_DATE_STR"].apply(self.parse_date)

            # 解析数值
            numeric_columns = {
                "UNIT_NET": "UNIT_NET_STR",
                "ACCUMULATED_NET": "ACCUMULATED_NET_STR",
                "WEEKLY_RETURN": "WEEKLY_RETURN_STR",
                "MONTHLY_RETURN": "MONTHLY_RETURN_STR",
                "THREE_MONTH_RETURN": "THREE_MONTH_RETURN_STR",
                "SIX_MONTH_RETURN": "SIX_MONTH_RETURN_STR",
                "YEARLY_RETURN": "YEARLY_RETURN_STR",
                "TWO_YEAR_RETURN": "TWO_YEAR_RETURN_STR",
                "THREE_YEAR_RETURN": "THREE_YEAR_RETURN_STR",
                "YTD_RETURN": "YTD_RETURN_STR",
                "SINCE_INCEPTION": "SINCE_INCEPTION_STR",
            }

            for col, src_col in numeric_columns.items():
                df[col] = df[src_col].apply(lambda x: self.parse_float(x, None))

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
            df["REFERENCE_CODE"] = "FUND_EXCHANGE_RANK"
            df["REFERENCE_NAME"] = "场内交易基金排行数据表(东方财富)"
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
                "WEEKLY_RETURN",
                "MONTHLY_RETURN",
                "THREE_MONTH_RETURN",
                "SIX_MONTH_RETURN",
                "YEARLY_RETURN",
                "TWO_YEAR_RETURN",
                "THREE_YEAR_RETURN",
                "YTD_RETURN",
                "SINCE_INCEPTION",
                "ESTABLISH_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功处理{len(df)}条场内交易基金排行数据")
            return df

        except Exception as e:
            self.logger.error(f"处理场内交易基金排行数据失败: {e}", exc_info=True)
            return None

    def save_exchange_rank_data(self, df: pd.DataFrame) -> bool:
        """
        保存场内交易基金排行数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有场内交易基金排行数据需要保存")
            return False

        # 获取已存在的数据ID
        existing_ids = self._get_existing_ids()

        # 过滤掉已存在的数据
        if existing_ids:
            df = df[~df["R_ID"].isin(existing_ids)]

        if df.empty:
            self.logger.info("没有新的场内交易基金排行数据需要保存")
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
            sql = "SELECT R_ID FROM FUND_EXCHANGE_RANK_EM WHERE IS_ACTIVE = 1"
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
            return {row[0] for row in result} if result else set()
        except Exception as e:
            self.logger.error(f"获取已存在数据ID失败: {e}")
            return set()

    def run(self):
        """
        执行数据获取和保存

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行场内交易基金排行数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取数据
            df = self.fetch_exchange_rank_data()

            if df is None or df.empty:
                self.logger.error("未获取到有效的场内交易基金排行数据")
                return False

            # 处理数据
            processed_df = self.process_exchange_rank_data(df)

            if processed_df is None or processed_df.empty:
                self.logger.error("处理场内交易基金排行数据失败")
                return False

            # 保存数据
            success = self.save_exchange_rank_data(processed_df)

            if success:
                self.logger.info(f"成功保存{len(processed_df)}条场内交易基金排行数据")
            else:
                self.logger.error("保存场内交易基金排行数据失败")

            return success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    # 更新场内交易基金排行数据
    data_updater = FundExchangeRankEm()
    data_updater.run()
