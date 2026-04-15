import logging
import re
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundPortfolioChangeEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金组合重大变动数据表
        self.table_name = "FUND_PORTFOLIO_CHANGE_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_PORTFOLIO_CHANGE_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_PORTFOLIO_CHANGE' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金组合重大变动数据表(天天基金)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 股票信息
                              `STOCK_CODE` VARCHAR(20) COMMENT '股票代码',
                              `STOCK_NAME` VARCHAR(100) COMMENT '股票名称',

                              -- 交易信息
                              `TRANSACTION_TYPE` VARCHAR(20) COMMENT '交易类型(累计买入/累计卖出)',
                              `AMOUNT` DECIMAL(20, 2) COMMENT '交易金额(万元)',
                              `RATIO` DECIMAL(10, 4) COMMENT '占期初基金资产净值比例(%)',

                              -- 时间信息
                              `YEAR` INT COMMENT '年份',
                              `QUARTER` TINYINT COMMENT '季度',
                              `QUARTER_STR` VARCHAR(100) COMMENT '季度字符串',

                              -- 系统字段
                              `UPDATE_DATE` DATE COMMENT '更新日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_PORTFOLIO_CHANGE_UNIQUE` (`FUND_CODE`, `STOCK_CODE`, `TRANSACTION_TYPE`, `YEAR`, `QUARTER`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_STOCK_CODE` (`STOCK_CODE`),
                              KEY `IDX_TRANSACTION_TYPE` (`TRANSACTION_TYPE`),
                              KEY `IDX_YEAR_QUARTER` (`YEAR`, `QUARTER`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金组合重大变动数据表(天天基金)';
                            """

    def parse_quarter_info(self, quarter_str: str) -> tuple:
        """
        解析季度信息字符串，返回年份和季度

        Args:
            quarter_str: 季度字符串，例如'2023年2季度累计买入股票明细'

        Returns:
            tuple: (year, quarter, quarter_str)
        """
        try:
            # 匹配年份和季度，例如从'2023年2季度累计买入股票明细'中提取2023和2
            match = re.search(r"(\d{4})年(\d)季度", quarter_str)
            if match:
                year = int(match.group(1))
                quarter = int(match.group(2))
                return year, quarter, f"{year}Q{quarter}"

            # 如果没有匹配到，尝试其他可能的格式
            match_year = re.search(r"(\d{4})", quarter_str)
            if match_year:
                year = int(match_year.group(1))
                return year, 0, str(year)

            return None, None, None

        except Exception as e:
            self.logger.warning(f"解析季度信息失败: {quarter_str}, 错误: {e}")
            return None, None, None

    def fetch_portfolio_change_data(
        self, fund_code: str, indicator: str = "累计买入", year: str = None
    ) -> pd.DataFrame:
        """
        获取基金组合重大变动数据

        Args:
            fund_code: 基金代码
            indicator: 指标类型，'累计买入' 或 '累计卖出'
            year: 年份，如果为None则使用当前年份

        Returns:
            pd.DataFrame: 处理后的基金组合重大变动数据
        """
        try:
            # 如果未指定年份，则使用当前年份
            if year is None:
                year = str(datetime.now().year)

            # 获取原始数据
            df = ak.fund_portfolio_change_em(symbol=fund_code, indicator=indicator, date=year)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 在 {year} 年的{indicator}数据")
                return pd.DataFrame()

            # 重命名列
            df.columns = [
                "seq",
                "stock_code",
                "stock_name",
                "amount",
                "ratio",
                "quarter_str",
            ]

            # 添加基金代码和交易类型
            df["fund_code"] = fund_code
            df["transaction_type"] = indicator

            # 解析季度信息
            quarter_info = df["quarter_str"].apply(self.parse_quarter_info)
            df["year"] = [x[0] for x in quarter_info]
            df["quarter"] = [x[1] for x in quarter_info]
            df["quarter_str"] = [x[2] for x in quarter_info]

            # 添加更新时间
            df["update_date"] = datetime.now().date()

            # 生成主键ID
            df["r_id"] = df.apply(
                lambda x: f"FPC_{x['fund_code']}_{x['stock_code']}_{x['transaction_type']}_{x['year']}_{x['quarter']}",
                axis=1,
            )

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "stock_code",
                "stock_name",
                "transaction_type",
                "amount",
                "ratio",
                "year",
                "quarter",
                "quarter_str",
                "update_date",
            ]
            df = df[columns]

            return df

        except Exception as e:
            self.logger.error(f"获取基金 {fund_code} {indicator} 数据失败: {e}")
            return pd.DataFrame()

    def save_portfolio_change_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金组合重大变动数据到数据库

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
                    "transaction_type",
                    "amount",
                    "ratio",
                    "year",
                    "quarter",
                    "quarter_str",
                    "update_date",
                    "is_active",
                    "data_source",
                ]

                # 添加系统字段
                new_data["is_active"] = 1
                new_data["data_source"] = "天天基金"

                # 插入新数据
                self.insert_data(new_data, self.table_name, columns)
                self.logger.info(f"成功插入 {len(new_data)} 条基金组合重大变动数据")
            else:
                self.logger.info("没有新的基金组合重大变动数据需要插入")

            return True

        except Exception as e:
            self.logger.error(f"保存基金组合重大变动数据失败: {e}")
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

    def run(self, fund_code: str = None, indicator: str = "累计买入", year: str = None):
        """
        执行数据获取和保存

        Args:
            fund_code: 基金代码
            indicator: 指标类型，'累计买入' 或 '累计卖出'
            year: 年份，如果为None则使用当前年份

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info(
                f"开始执行基金组合重大变动数据更新，基金代码: {fund_code}, 类型: {indicator}, 年份: {year or '当前年份'}"
            )

            # 验证indicator参数
            if indicator not in ["累计买入", "累计卖出"]:
                self.logger.error(f"不支持的indicator参数: {indicator}，应为'累计买入'或'累计卖出'")
                return False

            # 创建表（如果不存在）
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            # 获取数据
            df = self.fetch_portfolio_change_data(fund_code, indicator, year)

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金 {fund_code} 的{indicator}数据")
                return False

            # 保存数据
            success = self.save_portfolio_change_data(df)

            if success:
                self.logger.info(f"基金 {fund_code} {indicator} 数据更新完成")
            else:
                self.logger.warning(f"基金 {fund_code} {indicator} 数据更新失败")

            return success

        except Exception as e:
            self.logger.error(f"执行基金组合重大变动数据更新失败: {e}", exc_info=True)
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
    parser = argparse.ArgumentParser(description="获取基金组合重大变动数据")
    parser.add_argument("fund_code", type=str, help="基金代码")
    parser.add_argument(
        "-t",
        "--type",
        type=str,
        choices=["buy", "sell"],
        default="buy",
        help="交易类型: 'buy' 表示'累计买入', 'sell' 表示'累计卖出' (默认: buy)",
    )
    parser.add_argument("-y", "--year", type=str, help="年份，如果不指定则使用当前年份")
    args = parser.parse_args()

    # 转换交易类型
    indicator = "累计买入" if args.type == "buy" else "累计卖出"

    # 创建实例并执行
    fund_change = FundPortfolioChangeEm(logger=logger)
    result = fund_change.run(args.fund_code, indicator, args.year)

    # 返回状态码
    sys.exit(0 if result else 1)
