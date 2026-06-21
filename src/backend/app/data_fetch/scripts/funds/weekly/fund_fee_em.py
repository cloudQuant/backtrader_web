import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql
from app.data_fetch.scripts.funds.weekly._fund_codes import (
    DEFAULT_FUND_CODE_LIMIT,
    get_codes_from_table,
    normalize_fund_codes,
)


class FundFeeEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金费率数据表
        self.table_name = "FUND_FEE_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_FEE_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_FEE' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金费率数据表(天天基金)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 费率信息
                              `FEE_TYPE` VARCHAR(20) NOT NULL COMMENT '费率类型',
                              `CONDITION` VARCHAR(200) COMMENT '适用条件',
                              `TERM` VARCHAR(50) COMMENT '适用期限（如适用）',
                              `ORIGINAL_RATE` VARCHAR(50) COMMENT '原费率',
                              `PROMOTION_RATE` VARCHAR(50) COMMENT '优惠费率',

                              -- 系统字段
                              `UPDATE_DATE` DATE COMMENT '更新日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_FEE_UNIQUE` (`FUND_CODE`, `FEE_TYPE`, `CONDITION`(50), `TERM`(20)),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_FEE_TYPE` (`FEE_TYPE`),
                              KEY `IDX_UPDATE_DATE` (`UPDATE_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金费率数据表(天天基金)';
                            """

        # 支持的费率类型
        self.supported_fee_types = [
            "交易状态",
            "申购与赎回金额",
            "交易确认日",
            "运作费用",
            "认购费率",
            "申购费率",
            "赎回费率",
        ]

    @staticmethod
    def normalize_fee_frame(df: pd.DataFrame, fee_type: str) -> pd.DataFrame:
        def limit_text(value, max_length: int):
            if value is None:
                return None
            text = str(value)
            return text[:max_length]

        rows = []
        for _, row in df.iterrows():
            values = [None if pd.isna(value) else value for value in row.tolist()]
            if len(values) >= 4 and fee_type in {"认购费率", "申购费率", "赎回费率"}:
                condition, term, original_rate, promotion_rate = values[:4]
            elif len(values) >= 2:
                condition = values[0]
                term = None
                original_rate = " | ".join(str(value) for value in values[1:] if value is not None)
                promotion_rate = None
            else:
                condition = fee_type
                term = None
                original_rate = str(values[0]) if values and values[0] is not None else None
                promotion_rate = None

            rows.append(
                {
                    "condition": limit_text(condition, 200),
                    "term": limit_text(term, 50),
                    "original_rate": limit_text(original_rate, 50),
                    "promotion_rate": limit_text(promotion_rate, 50),
                }
            )

        return pd.DataFrame(rows, columns=["condition", "term", "original_rate", "promotion_rate"])

    def fetch_fee_data(self, fund_code: str, fee_type: str = None) -> pd.DataFrame:
        """
        获取基金费率数据

        Args:
            fund_code: 基金代码
            fee_type: 费率类型，如果为None则获取所有支持的费率类型

        Returns:
            pd.DataFrame: 处理后的基金费率数据
        """
        try:
            fee_types = [fee_type] if fee_type else self.supported_fee_types
            all_data = []

            for ft in fee_types:
                try:
                    # 获取原始数据
                    df = ak.fund_fee_em(symbol=fund_code, indicator=ft)

                    if df is not None and not df.empty:
                        normalized_df = self.normalize_fee_frame(df, ft)
                        normalized_df["fee_type"] = ft
                        all_data.append(normalized_df)

                except Exception as e:
                    self.logger.warning(f"获取基金 {fund_code} 的{ft}数据失败: {e}")

            if not all_data:
                self.logger.warning(f"未获取到基金 {fund_code} 的费率数据")
                return pd.DataFrame()

            # 合并所有数据
            result_df = pd.concat(all_data, ignore_index=True)

            # 添加基金代码和更新日期
            result_df["fund_code"] = fund_code
            result_df["update_date"] = datetime.now().strftime("%Y-%m-%d")

            # 生成主键ID
            result_df["r_id"] = result_df.apply(
                lambda x: (
                    f"FFEE_{x['fund_code']}_{x['fee_type']}_{hash(frozenset(x[['condition', 'term']].dropna().items()))}"
                ),
                axis=1,
            )

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "fee_type",
                "condition",
                "term",
                "original_rate",
                "promotion_rate",
                "update_date",
            ]
            result_df = result_df[columns]

            return result_df

        except Exception as e:
            self.logger.error(f"获取基金 {fund_code} 费率数据失败: {e}")
            return pd.DataFrame()

    def save_fee_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金费率数据到数据库

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
                    "fee_type",
                    "condition",
                    "term",
                    "original_rate",
                    "promotion_rate",
                    "update_date",
                    "is_active",
                    "data_source",
                ]

                # 添加系统字段
                new_data["is_active"] = 1
                new_data["data_source"] = "天天基金"

                # 插入新数据
                self.insert_data(new_data, self.table_name, columns)
                self.logger.info(f"成功插入 {len(new_data)} 条基金费率数据")
            else:
                self.logger.info("没有新的基金费率数据需要插入")

            return True

        except Exception as e:
            self.logger.error(f"保存基金费率数据失败: {e}")
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

    def run(
        self,
        fund_code: str = None,
        fee_type: str = None,
        fund_codes=None,
        limit: int = DEFAULT_FUND_CODE_LIMIT,
    ):
        """
        执行数据获取和保存

        Args:
            fund_code: 基金代码
            fee_type: 费率类型，如果为None则获取所有支持的费率类型

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info(
                f"开始执行基金费率数据更新，基金代码: {fund_code}, 费率类型: {fee_type or '全部'}"
            )

            # 创建表（如果不存在）
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            codes = normalize_fund_codes(fund_code=fund_code, fund_codes=fund_codes)
            if not codes:
                codes = get_codes_from_table(self, "OPEN_FUND_DAILY_EM", "FUND_CODE", limit)
            if not codes:
                self.logger.warning("未获取到默认基金代码")
                return False

            total_success = True
            total_count = 0
            for code in codes:
                df = self.fetch_fee_data(code, fee_type)
                if df is None or df.empty:
                    continue

                success = self.save_fee_data(df)
                if success:
                    total_count += len(df)
                    self.logger.info(f"基金 {code} 费率数据更新完成")
                else:
                    total_success = False
                    self.logger.warning(f"基金 {code} 费率数据更新失败")

            self.logger.info(f"基金费率数据更新完成，共处理{total_count}条数据")
            return total_success and total_count > 0

        except Exception as e:
            self.logger.error(f"执行基金费率数据更新失败: {e}", exc_info=True)
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
    parser = argparse.ArgumentParser(description="获取基金费率数据")
    parser.add_argument("fund_code", type=str, help="基金代码")
    parser.add_argument(
        "-t",
        "--fee-type",
        type=str,
        choices=[
            "交易状态",
            "申购与赎回金额",
            "交易确认日",
            "运作费用",
            "认购费率",
            "申购费率",
            "赎回费率",
        ],
        help="费率类型，如果不指定则获取所有类型",
    )
    args = parser.parse_args()

    # 创建实例并执行
    fund_fee = FundFeeEm(logger=logger)
    result = fund_fee.run(args.fund_code, args.fee_type)

    # 返回状态码
    sys.exit(0 if result else 1)
