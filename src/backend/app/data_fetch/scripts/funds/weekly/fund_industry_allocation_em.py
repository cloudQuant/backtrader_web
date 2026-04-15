import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundIndustryAllocationEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金行业配置数据表
        self.table_name = "FUND_INDUSTRY_ALLOCATION_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_INDUSTRY_ALLOCATION_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_INDUSTRY_ALLOC' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金行业配置数据表(天天基金)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 行业配置信息
                              `INDUSTRY_NAME` VARCHAR(100) COMMENT '行业名称',
                              `ALLOCATION_RATIO` DECIMAL(10, 4) COMMENT '占净值比例(%)',
                              `MARKET_VALUE` DECIMAL(20, 2) COMMENT '市值(万元)',
                              `REPORT_DATE` DATE COMMENT '报告日期',
                              `YEAR` INT COMMENT '年份',
                              `QUARTER` TINYINT COMMENT '季度',

                              -- 系统字段
                              `UPDATE_DATE` DATE COMMENT '更新日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_INDUSTRY_ALLOC_UNIQUE` (`FUND_CODE`, `INDUSTRY_NAME`, `REPORT_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_INDUSTRY_NAME` (`INDUSTRY_NAME`),
                              KEY `IDX_REPORT_DATE` (`REPORT_DATE`),
                              KEY `IDX_YEAR_QUARTER` (`YEAR`, `QUARTER`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金行业配置数据表(天天基金)';
                            """

    def parse_report_date(self, date_str: str) -> tuple:
        """
        解析报告日期字符串，返回日期对象和季度信息

        Args:
            date_str: 日期字符串，格式如'2023-09-30'

        Returns:
            tuple: (report_date, year, quarter)
        """
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            year = report_date.year
            month = report_date.month
            quarter = (month - 1) // 3 + 1
            return report_date, year, quarter
        except Exception as e:
            self.logger.warning(f"解析报告日期失败: {date_str}, 错误: {e}")
            return None, None, None

    def fetch_industry_allocation_data(self, fund_code: str, year: str = None) -> pd.DataFrame:
        """
        获取基金行业配置数据

        Args:
            fund_code: 基金代码
            year: 年份，如果为None则使用当前年份

        Returns:
            pd.DataFrame: 处理后的基金行业配置数据
        """
        try:
            # 如果未指定年份，则使用当前年份
            if year is None:
                year = str(datetime.now().year)

            # 获取原始数据
            df = ak.fund_portfolio_industry_allocation_em(symbol=fund_code, date=year)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 在 {year} 年的行业配置数据")
                return pd.DataFrame()

            # 重命名列
            df.columns = [
                "seq",
                "industry_name",
                "allocation_ratio",
                "market_value",
                "report_date_str",
            ]

            # 添加基金代码
            df["fund_code"] = fund_code

            # 解析报告日期
            date_info = df["report_date_str"].apply(self.parse_report_date)
            df["report_date"] = [x[0] for x in date_info]
            df["year"] = [x[1] for x in date_info]
            df["quarter"] = [x[2] for x in date_info]

            # 添加更新时间
            df["update_date"] = datetime.now().date()

            # 生成主键ID
            df["r_id"] = df.apply(
                lambda x: f"FIA_{x['fund_code']}_{x['industry_name']}_{x['report_date']}",
                axis=1,
            )

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "industry_name",
                "allocation_ratio",
                "market_value",
                "report_date",
                "year",
                "quarter",
                "update_date",
            ]
            df = df[columns]

            return df

        except Exception as e:
            self.logger.error(f"获取基金 {fund_code} 行业配置数据失败: {e}")
            return pd.DataFrame()

    def save_industry_allocation_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金行业配置数据到数据库

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
                    "industry_name",
                    "allocation_ratio",
                    "market_value",
                    "report_date",
                    "year",
                    "quarter",
                    "update_date",
                    "is_active",
                    "data_source",
                ]

                # 添加系统字段
                new_data["is_active"] = 1
                new_data["data_source"] = "天天基金"

                # 插入新数据
                self.insert_data(new_data, self.table_name, columns)
                self.logger.info(f"成功插入 {len(new_data)} 条基金行业配置数据")
            else:
                self.logger.info("没有新的基金行业配置数据需要插入")

            return True

        except Exception as e:
            self.logger.error(f"保存基金行业配置数据失败: {e}")
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

    def run(self, fund_code: str = None, year: str = None):
        """
        执行数据获取和保存

        Args:
            fund_code: 基金代码
            year: 年份，如果为None则使用当前年份

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info(
                f"开始执行基金行业配置数据更新，基金代码: {fund_code}, 年份: {year or '当前年份'}"
            )

            # 创建表（如果不存在）
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            # 获取数据
            df = self.fetch_industry_allocation_data(fund_code, year)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 的行业配置数据")
                return False

            # 保存数据
            success = self.save_industry_allocation_data(df)

            if success:
                self.logger.info(f"基金 {fund_code} 行业配置数据更新完成")
            else:
                self.logger.warning(f"基金 {fund_code} 行业配置数据更新失败")

            return success

        except Exception as e:
            self.logger.error(f"执行基金行业配置数据更新失败: {e}", exc_info=True)
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
    parser = argparse.ArgumentParser(description="获取基金行业配置数据")
    parser.add_argument("fund_code", type=str, help="基金代码")
    parser.add_argument("-y", "--year", type=str, help="年份，如果不指定则使用当前年份")
    args = parser.parse_args()

    # 创建实例并执行
    fund_industry = FundIndustryAllocationEm(logger=logger)
    result = fund_industry.run(args.fund_code, args.year)

    # 返回状态码
    sys.exit(0 if result else 1)
