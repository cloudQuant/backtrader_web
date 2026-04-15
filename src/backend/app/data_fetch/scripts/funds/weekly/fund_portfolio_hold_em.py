import logging
import re
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundPortfolioHoldEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金持仓数据表
        self.table_name = "FUND_PORTFOLIO_HOLD_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_PORTFOLIO_HOLD_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_PORTFOLIO_HOLD' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金持仓数据表(天天基金)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 持仓信息
                              `STOCK_CODE` VARCHAR(20) COMMENT '股票代码',
                              `STOCK_NAME` VARCHAR(100) COMMENT '股票名称',
                              `HOLD_AMOUNT` DECIMAL(20, 2) COMMENT '持股数(万股)',
                              `HOLD_VALUE` DECIMAL(20, 2) COMMENT '持仓市值(万元)',
                              `NET_VALUE_RATIO` DECIMAL(10, 4) COMMENT '占净值比例(%)',
                              `QUARTER` VARCHAR(20) COMMENT '季度',
                              `YEAR` INT COMMENT '年份',
                              `QUARTER_NUM` TINYINT COMMENT '季度(数字)',
                              `REPORT_DATE` DATE COMMENT '报告日期',

                              -- 系统字段
                              `UPDATE_DATE` DATE COMMENT '更新日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_PORTFOLIO_HOLD_UNIQUE` (`FUND_CODE`, `STOCK_CODE`, `REPORT_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_STOCK_CODE` (`STOCK_CODE`),
                              KEY `IDX_REPORT_DATE` (`REPORT_DATE`),
                              KEY `IDX_QUARTER` (`QUARTER`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金持仓数据表(天天基金)';
                            """

    def parse_quarter(self, quarter_str: str) -> tuple:
        """
        解析季度字符串，返回年份和季度

        Args:
            quarter_str: 季度字符串，如'2024年1季度股票投资明细'

        Returns:
            tuple: (year, quarter, report_date)
        """
        try:
            # 提取年份和季度
            match = re.search(r"(\d{4})年(\d)季度", quarter_str)
            if not match:
                return None, None, None

            year = int(match.group(1))
            quarter = int(match.group(2))

            # 计算季度末日期
            if quarter == 1:
                report_date = f"{year}-03-31"
            elif quarter == 2:
                report_date = f"{year}-06-30"
            elif quarter == 3:
                report_date = f"{year}-09-30"
            else:  # Q4
                report_date = f"{year}-12-31"

            return year, quarter, report_date

        except Exception as e:
            self.logger.warning(f"解析季度字符串失败: {quarter_str}, 错误: {e}")
            return None, None, None

    def fetch_portfolio_hold_data(self, fund_code: str, year: str = None) -> pd.DataFrame:
        """
        获取基金持仓数据

        Args:
            fund_code: 基金代码
            year: 年份，如果为None则使用当前年份

        Returns:
            pd.DataFrame: 处理后的基金持仓数据
        """
        try:
            # 如果未指定年份，则使用当前年份
            if year is None:
                year = str(datetime.now().year)

            # 获取原始数据
            df = ak.fund_portfolio_hold_em(symbol=fund_code, date=year)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 在 {year} 年的持仓数据")
                return pd.DataFrame()

            # 重命名列
            df.columns = [
                "seq",
                "stock_code",
                "stock_name",
                "net_value_ratio",
                "hold_amount",
                "hold_value",
                "quarter",
            ]

            # 添加基金代码
            df["fund_code"] = fund_code

            # 解析季度信息
            quarter_info = df["quarter"].apply(self.parse_quarter)
            df["year"] = [x[0] for x in quarter_info]
            df["quarter_num"] = [x[1] for x in quarter_info]
            df["report_date"] = [x[2] for x in quarter_info]

            # 添加更新时间
            df["update_date"] = datetime.now().strftime("%Y-%m-%d")

            # 生成主键ID
            df["r_id"] = df.apply(
                lambda x: f"FPH_{x['fund_code']}_{x['stock_code']}_{x['report_date']}",
                axis=1,
            )

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "stock_code",
                "stock_name",
                "hold_amount",
                "hold_value",
                "net_value_ratio",
                "quarter",
                "year",
                "quarter_num",
                "report_date",
                "update_date",
            ]
            df = df[columns]

            return df

        except Exception as e:
            self.logger.error(f"获取基金 {fund_code} 持仓数据失败: {e}")
            return pd.DataFrame()

    def save_portfolio_hold_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金持仓数据到数据库

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
                    "stock_code",
                    "stock_name",
                    "hold_amount",
                    "hold_value",
                    "net_value_ratio",
                    "quarter",
                    "year",
                    "quarter_num",
                    "report_date",
                    "update_date",
                    "is_active",
                    "data_source",
                ]

                # 添加系统字段
                new_data["is_active"] = 1
                new_data["data_source"] = "天天基金"

                # 插入新数据
                self.insert_data(new_data, self.table_name, columns)
                self.logger.info(f"成功插入 {len(new_data)} 条基金持仓数据")
            else:
                self.logger.info("没有新的基金持仓数据需要插入")

            return True

        except Exception as e:
            self.logger.error(f"保存基金持仓数据失败: {e}")
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
                f"开始执行基金持仓数据更新，基金代码: {fund_code}, 年份: {year or '当前年份'}"
            )

            # 创建表（如果不存在）
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            # 获取数据
            df = self.fetch_portfolio_hold_data(fund_code, year)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 的持仓数据")
                return False

            # 保存数据
            success = self.save_portfolio_hold_data(df)

            if success:
                self.logger.info(f"基金 {fund_code} 持仓数据更新完成")
            else:
                self.logger.warning(f"基金 {fund_code} 持仓数据更新失败")

            return success

        except Exception as e:
            self.logger.error(f"执行基金持仓数据更新失败: {e}", exc_info=True)
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
    parser = argparse.ArgumentParser(description="获取基金持仓数据")
    parser.add_argument("fund_code", type=str, help="基金代码")
    parser.add_argument("-y", "--year", type=str, help="年份，如果不指定则使用当前年份")
    args = parser.parse_args()

    # 创建实例并执行
    fund_portfolio = FundPortfolioHoldEm(logger=logger)
    result = fund_portfolio.run(args.fund_code, args.year)

    # 返回状态码
    sys.exit(0 if result else 1)
