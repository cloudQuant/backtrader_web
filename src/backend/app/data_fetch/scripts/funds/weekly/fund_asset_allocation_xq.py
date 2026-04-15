import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundAssetAllocationXq(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金资产配置数据表
        self.table_name = "FUND_ASSET_ALLOCATION_XQ"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_ASSET_ALLOCATION_XQ` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_ASSET_ALLOCATION' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金资产配置数据表(雪球)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 资产配置数据
                              `ASSET_TYPE` VARCHAR(20) COMMENT '资产类型',
                              `ALLOCATION_RATIO` DECIMAL(10, 2) COMMENT '仓位占比(%)',
                              `REPORT_DATE` DATE COMMENT '报告日期',

                              -- 系统字段
                              `UPDATE_DATE` DATE COMMENT '更新日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '雪球' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_ASSET_ALLOCATION_UNIQUE` (`FUND_CODE`, `ASSET_TYPE`, `REPORT_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_REPORT_DATE` (`REPORT_DATE`),
                              KEY `IDX_UPDATE_DATE` (`UPDATE_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金资产配置数据表(雪球)';
                            """

    def fetch_asset_allocation_data(self, fund_code: str, report_date: str) -> pd.DataFrame:
        """
        获取基金资产配置数据

        Args:
            fund_code: 基金代码
            report_date: 报告日期 (格式: YYYYMMDD)

        Returns:
            pd.DataFrame: 处理后的基金资产配置数据
        """
        try:
            # 获取原始数据
            df = ak.fund_individual_detail_hold_xq(symbol=fund_code, date=report_date)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 在 {report_date} 的资产配置数据")
                return pd.DataFrame()

            # 重命名列
            df.columns = ["asset_type", "allocation_ratio"]

            # 添加基金代码和报告日期
            df["fund_code"] = fund_code
            df["report_date"] = datetime.strptime(report_date, "%Y%m%d").strftime("%Y-%m-%d")

            # 添加更新时间
            df["update_date"] = datetime.now().strftime("%Y-%m-%d")

            # 生成主键ID
            df["r_id"] = df.apply(
                lambda x: f"FAA_{x['fund_code']}_{x['asset_type']}_{report_date}",
                axis=1,
            )

            # 选择需要的列并重新排序
            df = df[
                [
                    "r_id",
                    "fund_code",
                    "asset_type",
                    "allocation_ratio",
                    "report_date",
                    "update_date",
                ]
            ]

            return df

        except Exception as e:
            self.logger.error(f"获取基金 {fund_code} 资产配置数据失败: {e}")
            return pd.DataFrame()

    def save_asset_allocation_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金资产配置数据到数据库

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
                    "asset_type",
                    "allocation_ratio",
                    "report_date",
                    "update_date",
                    "is_active",
                    "data_source",
                ]

                # 添加系统字段
                new_data["is_active"] = 1
                new_data["data_source"] = "雪球"

                # 插入新数据
                self.insert_data(new_data, self.table_name, columns)
                self.logger.info(f"成功插入 {len(new_data)} 条基金资产配置数据")
            else:
                self.logger.info("没有新的基金资产配置数据需要插入")

            return True

        except Exception as e:
            self.logger.error(f"保存基金资产配置数据失败: {e}")
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

    def run(self, fund_code: str = None, report_date: str = None):
        """
        执行数据获取和保存

        Args:
            fund_code: 基金代码
            report_date: 报告日期 (格式: YYYYMMDD)，如果为None则使用上季度末日期

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info(
                f"开始执行基金资产配置数据更新，基金代码: {fund_code}, 报告日期: {report_date}"
            )

            # 如果未提供报告日期，则使用上季度末日期
            if report_date is None:
                today = datetime.now()
                quarter = (today.month - 1) // 3
                last_quarter = (quarter - 1) % 4 + 1
                report_date = f"{today.year}{last_quarter * 3:02d}31"
                self.logger.info(f"未指定报告日期，默认使用上季度末日期: {report_date}")

            # 创建表（如果不存在）
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            # 获取数据
            df = self.fetch_asset_allocation_data(fund_code, report_date)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 的资产配置数据")
                return False

            # 保存数据
            success = self.save_asset_allocation_data(df)

            if success:
                self.logger.info(f"基金 {fund_code} 资产配置数据更新完成")
            else:
                self.logger.warning(f"基金 {fund_code} 资产配置数据更新失败")

            return success

        except Exception as e:
            self.logger.error(f"执行基金资产配置数据更新失败: {e}", exc_info=True)
            return False


if __name__ == "__main__":
    import argparse
    import logging
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # 设置参数解析
    parser = argparse.ArgumentParser(description="获取基金资产配置数据")
    parser.add_argument("fund_code", type=str, help="基金代码")
    parser.add_argument(
        "-d", "--date", type=str, help="报告日期 (格式: YYYYMMDD)，默认为上季度末日期"
    )
    args = parser.parse_args()

    # 创建实例并执行
    fund_asset_allocation = FundAssetAllocationXq(logger=logger)
    result = fund_asset_allocation.run(args.fund_code, args.date)

    # 返回状态码
    sys.exit(0 if result else 1)
