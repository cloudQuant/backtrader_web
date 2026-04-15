from typing import Any

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundAchievementXq(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金业绩数据表
        self.table_name = "FUND_ACHIEVEMENT_XQ"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_ACHIEVEMENT_XQ` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_ACHIEVEMENT' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金业绩数据表(雪球)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 业绩信息
                              `ACHIEVEMENT_TYPE` VARCHAR(20) COMMENT '业绩类型(年度业绩/阶段业绩)',
                              `PERIOD` VARCHAR(20) COMMENT '周期',
                              `RETURN_RATE` DECIMAL(10, 4) COMMENT '区间收益率(%)',
                              `MAX_DRAWDOWN` DECIMAL(10, 4) COMMENT '最大回撤(%)',
                              `RANK` VARCHAR(50) COMMENT '同类排名',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '雪球' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_ACHIEVEMENT_UNIQUE` (`FUND_CODE`, `ACHIEVEMENT_TYPE`, `PERIOD`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_ACHIEVEMENT_TYPE` (`ACHIEVEMENT_TYPE`),
                              KEY `IDX_PERIOD` (`PERIOD`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金业绩数据表(雪球)';
                            """

    def parse_float(self, value: Any, default: float = None) -> float | None:
        """解析浮点数值"""
        if pd.isna(value) or value in ("---", "", "--", "-", "---%", "--%"):
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

    def fetch_achievement_data(self, fund_code: str) -> pd.DataFrame | None:
        """
        获取基金业绩数据

        Args:
            fund_code: 基金代码

        Returns:
            pd.DataFrame: 处理后的基金业绩数据
        """
        try:
            self.logger.info(f"开始获取基金业绩数据，基金代码: {fund_code}")

            # 获取数据
            df = self.fetch_ak_data("fund_individual_achievement_xq", symbol=fund_code)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金业绩数据，基金代码: {fund_code}")
                return None

            # 添加基金代码列
            df["FUND_CODE"] = fund_code

            return df

        except Exception as e:
            self.logger.error(
                f"获取基金业绩数据失败，基金代码: {fund_code}, 错误: {e}", exc_info=True
            )
            return None

    def process_achievement_data(self, df: pd.DataFrame) -> pd.DataFrame | None:
        """处理基金业绩数据"""
        if df is None or df.empty:
            return None

        try:
            # 重命名列
            df = df.rename(
                columns={
                    "业绩类型": "ACHIEVEMENT_TYPE",
                    "周期": "PERIOD",
                    "本产品区间收益": "RETURN_RATE_STR",
                    "本产品最大回撒": "MAX_DRAWDOWN_STR",
                    "周期收益同类排名": "RANK",
                }
            )

            # 解析数值
            numeric_columns = {
                "RETURN_RATE": "RETURN_RATE_STR",
                "MAX_DRAWDOWN": "MAX_DRAWDOWN_STR",
            }

            for col, src_col in numeric_columns.items():
                if src_col in df.columns:
                    df[col] = df[src_col].apply(lambda x: self.parse_float(x, None))

            # 生成主键
            df["R_ID"] = df.apply(
                lambda x: f"{x['FUND_CODE']}_{x['ACHIEVEMENT_TYPE']}_{x['PERIOD']}",
                axis=1,
            )

            # 添加系统字段
            df["REFERENCE_CODE"] = "FUND_ACHIEVEMENT"
            df["REFERENCE_NAME"] = "基金业绩数据表(雪球)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "雪球"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "ACHIEVEMENT_TYPE",
                "PERIOD",
                "RETURN_RATE",
                "MAX_DRAWDOWN",
                "RANK",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功处理{len(df)}条基金业绩数据")
            return df

        except Exception as e:
            self.logger.error(f"处理基金业绩数据失败: {e}", exc_info=True)
            return None

    def save_achievement_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金业绩数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有基金业绩数据需要保存")
            return False

        # 获取已存在的数据ID
        existing_ids = self._get_existing_ids()

        # 过滤掉已存在的数据
        if existing_ids:
            df = df[~df["R_ID"].isin(existing_ids)]

        if df.empty:
            self.logger.info("没有新的基金业绩数据需要保存")
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
            sql = "SELECT R_ID FROM FUND_ACHIEVEMENT_XQ WHERE IS_ACTIVE = 1"
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
            return {row[0] for row in result} if result else set()
        except Exception as e:
            self.logger.error(f"获取已存在数据ID失败: {e}")
            return set()

    def run(self, fund_code: str = None):
        """
        执行数据获取和保存

        Args:
            fund_code: 基金代码

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info(f"开始执行基金业绩数据更新，基金代码: {fund_code}")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取数据
            df = self.fetch_achievement_data(fund_code)

            if df is None or df.empty:
                self.logger.error(f"未获取到有效的基金业绩数据，基金代码: {fund_code}")
                return False

            # 处理数据
            processed_df = self.process_achievement_data(df)

            if processed_df is None or processed_df.empty:
                self.logger.error(f"处理基金业绩数据失败，基金代码: {fund_code}")
                return False

            # 保存数据
            success = self.save_achievement_data(processed_df)

            if success:
                self.logger.info(
                    f"成功保存{len(processed_df)}条基金业绩数据，基金代码: {fund_code}"
                )
            else:
                self.logger.error(f"保存基金业绩数据失败，基金代码: {fund_code}")

            return success

        except Exception as e:
            self.logger.error(f"执行失败，基金代码: {fund_code}, 错误: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    logger = logging.getLogger(__name__)

    # 检查是否提供了基金代码参数
    if len(sys.argv) < 2:
        logger.error("请提供基金代码作为参数，例如: python 3131_fund_achievement_xq.py 000001")
        sys.exit(1)

    # 获取基金代码参数
    fund_code = sys.argv[1]

    # 更新基金业绩数据
    data_updater = FundAchievementXq()
    success = data_updater.run(fund_code)

    # 返回状态码
    sys.exit(0 if success else 1)
