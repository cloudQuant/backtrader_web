import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundRatingAll(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金评级数据表
        self.table_name = "FUND_RATING_ALL"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_RATING_ALL` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_RATING' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金评级数据表(天天基金)' COMMENT '参考名称',

                              -- 基金基本信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',
                              `FUND_MANAGER` VARCHAR(100) COMMENT '基金经理',
                              `FUND_COMPANY` VARCHAR(100) COMMENT '基金公司',

                              -- 评级信息
                              `FIVE_STAR_RATING_COUNT` INT COMMENT '5星评级家数',
                              `SHANGHAI_SECURITIES_RATING` DECIMAL(5,2) COMMENT '上海证券评级',
                              `CMS_SECURITIES_RATING` DECIMAL(5,2) COMMENT '招商证券评级',
                              `JIANJINXIN_RATING` DECIMAL(5,2) COMMENT '济安金信评级',

                              -- 其他信息
                              `FEE_RATE` DECIMAL(10,6) COMMENT '手续费率',
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
                              UNIQUE KEY `IDX_FUND_RATING_UNIQUE` (`FUND_CODE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_FUND_NAME` (`FUND_NAME`),
                              KEY `IDX_FUND_COMPANY` (`FUND_COMPANY`),
                              KEY `IDX_FUND_TYPE` (`FUND_TYPE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金评级数据表(天天基金)';
                            """

    def fetch_rating_data(self) -> pd.DataFrame:
        """
        获取基金评级数据

        Returns:
            pd.DataFrame: 处理后的基金评级数据
        """
        try:
            # 获取原始数据
            df = ak.fund_rating_all()

            if df is None or df.empty:
                self.logger.warning("未获取到基金评级数据")
                return pd.DataFrame()

            # 重命名列
            column_mapping = {
                "代码": "fund_code",
                "简称": "fund_name",
                "基金经理": "fund_manager",
                "基金公司": "fund_company",
                "5星评级家数": "five_star_rating_count",
                "上海证券": "shanghai_securities_rating",
                "招商证券": "cms_securities_rating",
                "济安金信": "jianjinxin_rating",
                "手续费": "fee_rate",
                "类型": "fund_type",
            }
            df = df.rename(columns=column_mapping)

            # 添加更新时间
            df["update_date"] = datetime.now().date()

            # 生成主键ID
            df["r_id"] = "FRA_" + df["fund_code"]

            # 处理数据类型
            df["five_star_rating_count"] = (
                pd.to_numeric(df["five_star_rating_count"], errors="coerce").fillna(0).astype(int)
            )

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "fund_name",
                "fund_manager",
                "fund_company",
                "five_star_rating_count",
                "shanghai_securities_rating",
                "cms_securities_rating",
                "jianjinxin_rating",
                "fee_rate",
                "fund_type",
                "update_date",
            ]
            df = df[columns]

            return df

        except Exception as e:
            self.logger.error(f"获取基金评级数据失败: {e}")
            return pd.DataFrame()

    def save_rating_data(self, df: pd.DataFrame) -> bool:
        """
        保存基金评级数据到数据库

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
            updated_data = df[df["r_id"].isin(existing_ids)]

            # 插入新数据
            if not new_data.empty:
                # 准备插入数据
                columns = [
                    "r_id",
                    "fund_code",
                    "fund_name",
                    "fund_manager",
                    "fund_company",
                    "five_star_rating_count",
                    "shanghai_securities_rating",
                    "cms_securities_rating",
                    "jianjinxin_rating",
                    "fee_rate",
                    "fund_type",
                    "update_date",
                    "is_active",
                    "data_source",
                ]

                # 添加系统字段
                new_data["is_active"] = 1
                new_data["data_source"] = "天天基金"

                # 插入新数据
                self.insert_data(new_data, self.table_name, columns)
                self.logger.info(f"成功插入 {len(new_data)} 条基金评级数据")

            # 更新已有数据
            if not updated_data.empty:
                updated_count = 0
                for _, row in updated_data.iterrows():
                    # 构建更新SQL
                    update_sql = f"""  # nosec B608
                    UPDATE {self.table_name}
                    SET
                        fund_name = %s,
                        fund_manager = %s,
                        fund_company = %s,
                        five_star_rating_count = %s,
                        shanghai_securities_rating = %s,
                        cms_securities_rating = %s,
                        jianjinxin_rating = %s,
                        fee_rate = %s,
                        fund_type = %s,
                        update_date = %s,
                        updatedate = CURRENT_TIMESTAMP
                    WHERE r_id = %s
                    """

                    # 执行更新
                    params = (
                        row["fund_name"],
                        row["fund_manager"],
                        row["fund_company"],
                        row["five_star_rating_count"],
                        row["shanghai_securities_rating"],
                        row["cms_securities_rating"],
                        row["jianjinxin_rating"],
                        row["fee_rate"],
                        row["fund_type"],
                        row["update_date"],
                        row["r_id"],
                    )

                    self.execute_sql(update_sql, params)
                    updated_count += 1

                if updated_count > 0:
                    self.logger.info(f"成功更新 {updated_count} 条基金评级数据")

            if new_data.empty and updated_data.empty:
                self.logger.info("没有新的基金评级数据需要更新")

            return True

        except Exception as e:
            self.logger.error(f"保存基金评级数据失败: {e}")
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

    def run(self):
        """
        执行数据获取和保存

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行基金评级数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            # 获取数据
            df = self.fetch_rating_data()

            if df is None or df.empty:
                self.logger.warning("未获取到基金评级数据")
                return False

            # 保存数据
            success = self.save_rating_data(df)

            if success:
                self.logger.info(f"基金评级数据更新完成，共处理 {len(df)} 条记录")
            else:
                self.logger.warning("基金评级数据更新失败")

            return success

        except Exception as e:
            self.logger.error(f"执行基金评级数据更新失败: {e}", exc_info=True)
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

    # 创建实例并执行
    fund_rating = FundRatingAll(logger=logger)
    result = fund_rating.run()

    # 返回状态码
    sys.exit(0 if result else 1)
