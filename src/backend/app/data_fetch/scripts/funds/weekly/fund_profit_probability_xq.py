import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundProfitProbabilityXq(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金盈利概率数据表
        self.table_name = "FUND_PROFIT_PROBABILITY_XQ"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_PROFIT_PROBABILITY_XQ` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_PROFIT_PROBABILITY' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金盈利概率数据表(雪球)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 盈利概率数据
                              `HOLDING_PERIOD` VARCHAR(10) COMMENT '持有时长',
                              `PROFIT_PROBABILITY` DECIMAL(10, 2) COMMENT '盈利概率(%)',
                              `AVG_RETURN` DECIMAL(10, 2) COMMENT '平均收益(%)',

                              -- 系统字段
                              `UPDATE_DATE` DATE COMMENT '更新日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '雪球' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_PROFIT_PROBABILITY_UNIQUE` (`FUND_CODE`, `HOLDING_PERIOD`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_UPDATE_DATE` (`UPDATE_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金盈利概率数据表(雪球)';
                            """

    def fetch_profit_probability_data(self, fund_code: str) -> pd.DataFrame:
        """
        获取基金盈利概率数据

        Args:
            fund_code: 基金代码

        Returns:
            pd.DataFrame: 处理后的基金盈利概率数据
        """
        try:
            # 获取原始数据
            df = ak.fund_individual_profit_probability_xq(symbol=fund_code, timeout=10)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 的盈利概率数据")
                return pd.DataFrame()

            # 重命名列
            df.columns = ["holding_period", "profit_probability", "avg_return"]

            # 添加基金代码
            df["fund_code"] = fund_code

            # 添加更新时间
            df["update_date"] = datetime.now().strftime("%Y-%m-%d")

            # 生成主键ID
            df["r_id"] = df.apply(lambda x: f"FPP_{x['fund_code']}_{x['holding_period']}", axis=1)

            # 选择需要的列并重新排序
            df = df[
                [
                    "r_id",
                    "fund_code",
                    "holding_period",
                    "profit_probability",
                    "avg_return",
                    "update_date",
                ]
            ]

            return df

        except Exception as e:
            self.logger.error(f"获取基金 {fund_code} 盈利概率数据失败: {e}")
            return pd.DataFrame()

    def save_profit_probability_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金盈利概率数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有数据需要保存")
            return False

        try:
            # 获取已存在的数据ID
            existing_ids = self._get_existing_ids()

            # 过滤掉已存在的数据
            new_data = df[~df["r_id"].isin(existing_ids)]

            if not new_data.empty:
                # 准备插入数据
                columns = [
                    "r_id",
                    "fund_code",
                    "holding_period",
                    "profit_probability",
                    "avg_return",
                    "update_date",
                    "is_active",
                    "data_source",
                ]

                # 添加系统字段
                new_data["is_active"] = 1
                new_data["data_source"] = "雪球"

                # 插入新数据
                self.insert_data(new_data, self.table_name, columns)
                self.logger.info(f"成功插入 {len(new_data)} 条基金盈利概率数据")
            else:
                self.logger.info("没有新的基金盈利概率数据需要插入")

            return True

        except Exception as e:
            self.logger.error(f"保存基金盈利概率数据失败: {e}")
            return False

    def _get_existing_ids(self) -> set:
        """获取已存在的数据ID"""
        try:
            query = f"SELECT r_id FROM {self.table_name} WHERE is_active = 1"  # nosec B608
            result = self.query_data(query)
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
            self.logger.info(f"开始执行基金盈利概率数据更新，基金代码: {fund_code}")

            # 创建表（如果不存在）
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            # 获取数据
            df = self.fetch_profit_probability_data(fund_code)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 的盈利概率数据")
                return False

            # 保存数据
            success = self.save_profit_probability_data(df)

            if success:
                self.logger.info(f"基金 {fund_code} 盈利概率数据更新完成")
            else:
                self.logger.warning(f"基金 {fund_code} 盈利概率数据更新失败")

            return success

        except Exception as e:
            self.logger.error(f"执行基金盈利概率数据更新失败: {e}", exc_info=True)
            return False


if __name__ == "__main__":
    import logging
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # 检查参数
    if len(sys.argv) < 2:
        logger.error(
            "请提供基金代码作为参数，例如: python 3134_fund_profit_probability_xq.py 000001"
        )
        sys.exit(1)

    fund_code = sys.argv[1]

    # 创建实例并执行
    fund_profit_probability = FundProfitProbabilityXq(logger=logger)
    result = fund_profit_probability.run(fund_code)

    # 返回状态码
    sys.exit(0 if result else 1)
