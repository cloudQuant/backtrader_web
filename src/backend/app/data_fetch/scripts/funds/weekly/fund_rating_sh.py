import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundRatingSh(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 上海证券基金评级数据表
        self.table_name = "FUND_RATING_SH"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_RATING_SH` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_RATING_SH' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '上海证券基金评级数据表(天天基金)' COMMENT '参考名称',

                              -- 基金基本信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',
                              `FUND_MANAGER` VARCHAR(100) COMMENT '基金经理',
                              `FUND_COMPANY` VARCHAR(100) COMMENT '基金公司',

                              -- 评级信息
                              `RATING_3Y` INT COMMENT '3年期评级',
                              `RATING_3Y_CHANGE` FLOAT COMMENT '3年期评级较上期变化',
                              `RATING_5Y` FLOAT COMMENT '5年期评级',
                              `RATING_5Y_CHANGE` FLOAT COMMENT '5年期评级较上期变化',

                              -- 净值信息
                              `UNIT_NAV` FLOAT COMMENT '单位净值',
                              `NAV_DATE` DATE COMMENT '净值日期',
                              `DAILY_RETURN` FLOAT COMMENT '日增长率(%)',

                              -- 收益率信息
                              `RETURN_1Y` FLOAT COMMENT '近1年涨幅(%)',
                              `RETURN_3Y` FLOAT COMMENT '近3年涨幅(%)',
                              `RETURN_5Y` FLOAT COMMENT '近5年涨幅(%)',

                              -- 其他信息
                              `FEE_RATE` FLOAT COMMENT '手续费率(%)',
                              `FUND_TYPE` VARCHAR(50) COMMENT '基金类型',

                              -- 系统字段
                              `UPDATE_DATE` DATE COMMENT '更新日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_RATING_SH_UNIQUE` (`FUND_CODE`, `NAV_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_NAV_DATE` (`NAV_DATE`),
                              KEY `IDX_RATING_3Y` (`RATING_3Y`),
                              KEY `IDX_RATING_5Y` (`RATING_5Y`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海证券基金评级数据表(天天基金)';
                            """

    def parse_fee_rate(self, fee_str: str) -> float:
        """
        解析手续费率字符串，转换为小数

        Args:
            fee_str: 手续费率字符串，如'0.15%'

        Returns:
            float: 手续费率小数
        """
        if not fee_str or pd.isna(fee_str):
            return None

        try:
            # 移除百分号并转换为浮点数
            return float(fee_str.rstrip("%")) / 100
        except (ValueError, AttributeError):
            return None

    def parse_date(self, date_str: str) -> tuple:
        """
        解析日期字符串，返回日期对象

        Args:
            date_str: 日期字符串，格式如'2023-06-30'

        Returns:
            date: 日期对象
        """
        try:
            import datetime as dt_mod

            if isinstance(date_str, dt_mod.date):
                return date_str
            return datetime.strptime(str(date_str), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def fetch_rating_data(self, date: str = None) -> pd.DataFrame:
        """
        获取上海证券基金评级数据

        Args:
            date: 评级日期，格式为'YYYYMMDD'，如果为None则使用当前日期

        Returns:
            pd.DataFrame: 处理后的基金评级数据
        """
        try:
            # 获取原始数据
            if date:
                df = ak.fund_rating_sh(date=date)
            else:
                df = ak.fund_rating_sh()

            if df is None or df.empty:
                self.logger.warning(f"未获取到 {date} 的上海证券基金评级数据")
                return pd.DataFrame()

            # 重命名列
            column_mapping = {
                "代码": "fund_code",
                "简称": "fund_name",
                "基金经理": "fund_manager",
                "基金公司": "fund_company",
                "3年期评级-3年评级": "rating_3y",
                "3年期评级-较上期": "rating_3y_change",
                "5年期评级-5年评级": "rating_5y",
                "5年期评级-较上期": "rating_5y_change",
                "单位净值": "unit_nav",
                "日期": "nav_date_str",
                "日增长率": "daily_return",
                "近1年涨幅": "return_1y",
                "近3年涨幅": "return_3y",
                "近5年涨幅": "return_5y",
                "手续费": "fee_rate_str",
                "类型": "fund_type",
            }
            df = df.rename(columns=column_mapping)

            # 添加系统字段
            df["update_date"] = datetime.now().date()

            # 解析日期
            df["nav_date"] = df["nav_date_str"].apply(self.parse_date)

            # 解析手续费率
            df["fee_rate"] = df["fee_rate_str"].apply(self.parse_fee_rate)

            # 生成主键ID
            df["r_id"] = df.apply(
                lambda x: (
                    f"FRSH_{x['fund_code']}_{x['nav_date'] if pd.notna(x['nav_date']) else date}"
                ),
                axis=1,
            )

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "fund_name",
                "fund_manager",
                "fund_company",
                "rating_3y",
                "rating_3y_change",
                "rating_5y",
                "rating_5y_change",
                "unit_nav",
                "nav_date",
                "daily_return",
                "return_1y",
                "return_3y",
                "return_5y",
                "fee_rate",
                "fund_type",
                "update_date",
            ]
            df = df[columns]

            return df

        except Exception as e:
            self.logger.error(f"获取上海证券基金评级数据失败: {e}")
            return pd.DataFrame()

    def save_rating_data(self, df: pd.DataFrame) -> bool:
        """
        保存上海证券基金评级数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有数据需要保存")
            return False

        try:
            save_df = df.copy()
            save_df["is_active"] = 1
            save_df["data_source"] = "天天基金"
            saved_rows = self.save_data(
                save_df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["R_ID"],
            )
            self.logger.info("批量写入/更新 %s 条上海证券基金评级数据", saved_rows)
            return bool(saved_rows)

        except Exception as e:
            self.logger.error(f"保存上海证券基金评级数据失败: {e}")
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

    def run(self, date: str = None):
        """
        执行数据获取和保存

        Args:
            date: 评级日期，格式为'YYYYMMDD'，如果为None则使用当前日期

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info(f"开始执行上海证券基金评级数据更新，日期: {date or '当前日期'}")

            # 创建表（如果不存在）
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            # 获取数据
            df = self.fetch_rating_data(date)

            if df is None or df.empty:
                self.logger.warning("未获取到上海证券基金评级数据")
                return False

            # 保存数据
            success = self.save_rating_data(df)

            if success:
                self.logger.info(f"上海证券基金评级数据更新完成，共处理 {len(df)} 条记录")
            else:
                self.logger.warning("上海证券基金评级数据更新失败")

            return success

        except Exception as e:
            self.logger.error(f"执行上海证券基金评级数据更新失败: {e}", exc_info=True)
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
    parser = argparse.ArgumentParser(description="获取上海证券基金评级数据")
    parser.add_argument(
        "-d",
        "--date",
        type=str,
        help="评级日期，格式为YYYYMMDD，如果不指定则使用当前日期",
    )
    args = parser.parse_args()

    # 创建实例并执行
    fund_rating_sh = FundRatingSh(logger=logger)
    result = fund_rating_sh.run(args.date)

    # 返回状态码
    sys.exit(0 if result else 1)
