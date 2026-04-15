import logging
import sys
from datetime import datetime
from typing import Any

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundValueEstimationEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金净值估算数据表
        self.table_name = "FUND_VALUE_ESTIMATION_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_VALUE_ESTIMATION_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_VALUE_EST' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金净值估算表(东方财富)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(200) COMMENT '基金名称',
                              `FUND_TYPE` VARCHAR(20) COMMENT '基金类型',

                              -- 估算数据
                              `TRADE_DATE` DATE COMMENT '交易日期',
                              `ESTIMATED_VALUE` DECIMAL(10, 6) COMMENT '估算值',
                              `ESTIMATED_RETURN` DECIMAL(10, 4) COMMENT '估算增长率(%)',

                              -- 公布数据
                              `PUBLISHED_NAV` DECIMAL(10, 6) COMMENT '公布单位净值',
                              `PUBLISHED_RETURN` DECIMAL(10, 4) COMMENT '公布日增长率(%)',

                              -- 其他信息
                              `ESTIMATION_DEVIATION` VARCHAR(20) COMMENT '估算偏差',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_VALUE_EST_UNIQUE` (`FUND_CODE`, `TRADE_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                              KEY `IDX_FUND_TYPE` (`FUND_TYPE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金净值估算表(东方财富)';
                            """

    def parse_float(self, value: Any, default: float = None) -> float | None:
        """解析浮点数值"""
        if pd.isna(value) or value in (
            "---",
            "",
            "--",
            "-",
            "---%",
            "--%",
            "---%---",
            "--%--",
            "--",
            "None",
        ):
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

    def fetch_estimation_data(self, fund_type: str = "全部") -> pd.DataFrame | None:
        """
        获取基金净值估算数据

        Args:
            fund_type: 基金类型，可选值: '全部', '股票型', '混合型', '债券型', '指数型', 'QDII', 'ETF联接', 'LOF', '场内交易基金'

        Returns:
            pd.DataFrame: 处理后的基金净值估算数据
        """
        try:
            self.logger.info(f"开始获取{fund_type}基金净值估算数据...")

            # 获取数据
            df = self.fetch_ak_data("fund_value_estimation_em", symbol=fund_type)

            if df is None or df.empty:
                self.logger.warning(f"未获取到{fund_type}基金净值估算数据")
                return None

            # 添加基金类型列
            df["FUND_TYPE"] = fund_type

            return df

        except Exception as e:
            self.logger.error(f"获取{fund_type}基金净值估算数据失败: {e}", exc_info=True)
            return None

    def process_estimation_data(self, df: pd.DataFrame) -> pd.DataFrame | None:
        """处理基金净值估算数据"""
        if df is None or df.empty:
            return None

        try:
            # 重命名列
            df = df.rename(
                columns={
                    "基金代码": "FUND_CODE",
                    "基金名称": "FUND_NAME",
                    "交易日-估算数据-估算值": "ESTIMATED_VALUE_STR",
                    "交易日-估算数据-估算增长率": "ESTIMATED_RETURN_STR",
                    "交易日-公布数据-单位净值": "PUBLISHED_NAV_STR",
                    "交易日-公布数据-日增长率": "PUBLISHED_RETURN_STR",
                    "估算偏差": "ESTIMATION_DEVIATION_STR",
                }
            )

            # 获取交易日期（从列名中提取）
            nav_date_col = [col for col in df.columns if "单位净值" in col]
            if nav_date_col:
                try:
                    trade_date_str = nav_date_col[0].split("-")[0]
                    df["TRADE_DATE"] = pd.to_datetime(trade_date_str).date()
                except Exception as e:
                    self.logger.warning(f"解析交易日期失败: {e}")
                    df["TRADE_DATE"] = datetime.now().date()
            else:
                df["TRADE_DATE"] = datetime.now().date()

            # 解析数值
            numeric_columns = {
                "ESTIMATED_VALUE": "ESTIMATED_VALUE_STR",
                "ESTIMATED_RETURN": "ESTIMATED_RETURN_STR",
                "PUBLISHED_NAV": "PUBLISHED_NAV_STR",
                "PUBLISHED_RETURN": "PUBLISHED_RETURN_STR",
            }

            for col, src_col in numeric_columns.items():
                if src_col in df.columns:
                    df[col] = df[src_col].apply(lambda x: self.parse_float(x, None))

            # 处理估算偏差
            if "ESTIMATION_DEVIATION_STR" in df.columns:
                df["ESTIMATION_DEVIATION"] = df["ESTIMATION_DEVIATION_STR"].apply(
                    lambda x: (
                        None if pd.isna(x) or x in ("---", "--", "-", "") else str(x).strip()
                    )
                )

            # 生成主键
            df["R_ID"] = df.apply(lambda x: f"{x['FUND_CODE']}_{x['TRADE_DATE']}", axis=1)

            # 添加系统字段
            df["REFERENCE_CODE"] = "FUND_VALUE_EST"
            df["REFERENCE_NAME"] = "基金净值估算表(东方财富)"
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
                "ESTIMATED_VALUE",
                "ESTIMATED_RETURN",
                "PUBLISHED_NAV",
                "PUBLISHED_RETURN",
                "ESTIMATION_DEVIATION",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功处理{len(df)}条基金净值估算数据")
            return df

        except Exception as e:
            self.logger.error(f"处理基金净值估算数据失败: {e}", exc_info=True)
            return None

    def save_estimation_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金净值估算数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有基金净值估算数据需要保存")
            return False

        # 获取已存在的数据ID
        existing_ids = self._get_existing_ids()

        # 过滤掉已存在的数据
        if existing_ids:
            df = df[~df["R_ID"].isin(existing_ids)]

        if df.empty:
            self.logger.info("没有新的基金净值估算数据需要保存")
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
            sql = "SELECT R_ID FROM FUND_VALUE_ESTIMATION_EM WHERE IS_ACTIVE = 1"
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
            return {row[0] for row in result} if result else set()
        except Exception as e:
            self.logger.error(f"获取已存在数据ID失败: {e}")
            return set()

    def run(self, fund_type: str = "全部"):
        """
        执行数据获取和保存

        Args:
            fund_type: 基金类型，可选值: '全部', '股票型', '混合型', '债券型', '指数型', 'QDII', 'ETF联接', 'LOF', '场内交易基金'

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info(f"开始执行{fund_type}基金净值估算数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取数据
            df = self.fetch_estimation_data(fund_type)

            if df is None or df.empty:
                self.logger.error(f"未获取到有效的{fund_type}基金净值估算数据")
                return False

            # 处理数据
            processed_df = self.process_estimation_data(df)

            if processed_df is None or processed_df.empty:
                self.logger.error(f"处理{fund_type}基金净值估算数据失败")
                return False

            # 保存数据
            success = self.save_estimation_data(processed_df)

            if success:
                self.logger.info(f"成功保存{len(processed_df)}条{fund_type}基金净值估算数据")
            else:
                self.logger.error(f"保存{fund_type}基金净值估算数据失败")

            return success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    # 支持的所有基金类型
    FUND_TYPES = [
        "全部",
        "股票型",
        "混合型",
        "债券型",
        "指数型",
        "QDII",
        "ETF联接",
        "LOF",
        "场内交易基金",
    ]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    logger = logging.getLogger(__name__)

    # 检查是否提供了基金类型参数
    if len(sys.argv) < 2:
        logger.error("请提供基金类型作为参数，例如: python 3132_fund_value_estimation_em.py 混合型")
        logger.info("可选基金类型: %s", ", ".join(FUND_TYPES))
        sys.exit(1)

    # 获取基金类型参数
    fund_type = sys.argv[1]

    if fund_type not in FUND_TYPES:
        logger.error("无效的基金类型: %s", fund_type)
        logger.info("可选基金类型: %s", ", ".join(FUND_TYPES))
        sys.exit(1)

    # 更新基金净值估算数据
    data_updater = FundValueEstimationEm()
    success = data_updater.run(fund_type)

    # 返回状态码
    sys.exit(0 if success else 1)
