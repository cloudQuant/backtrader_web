import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundSplitEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金拆分数据表
        self.table_name = "FUND_SPLIT_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_SPLIT_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_SPLIT' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金拆分详情表(东方财富)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 拆分信息
                              `YEAR` VARCHAR(10) COMMENT '年份',
                              `SPLIT_DATE` DATE COMMENT '拆分折算日',
                              `SPLIT_TYPE` VARCHAR(50) COMMENT '拆分类型',
                              `SPLIT_RATIO` VARCHAR(50) COMMENT '拆分折算比例',
                              `RATIO_FROM` DECIMAL(20, 6) COMMENT '比例-前',
                              `RATIO_TO` DECIMAL(20, 6) COMMENT '比例-后',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_SPLIT_UNIQUE` (`FUND_CODE`, `SPLIT_DATE`, `SPLIT_RATIO`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_SPLIT_DATE` (`SPLIT_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金拆分详情表(东方财富)';
                            """

    def parse_split_ratio(self, ratio_str):
        """
        解析拆分比例字符串，如'1:1.0054'，返回(1, 1.0054)

        Args:
            ratio_str: 拆分比例字符串

        Returns:
            tuple: (from_ratio, to_ratio)
        """
        if not isinstance(ratio_str, str):
            return None, None

        try:
            parts = ratio_str.split(":")
            if len(parts) == 2:
                return float(parts[0].strip()), float(parts[1].strip())
            return None, None
        except Exception as e:
            self.logger.warning(f"解析拆分比例失败: {e}, 原始字符串: {ratio_str}")
            return None, None

    def fetch_fund_split_data(self, fund_code):
        """
        获取基金拆分数据

        Args:
            fund_code: 基金代码

        Returns:
            pd.DataFrame: 处理后的拆分数据
        """
        try:
            self.logger.info(f"开始获取基金[{fund_code}]拆分数据...")

            # 获取数据
            df = self.fetch_ak_data(
                "fund_open_fund_info_em", symbol=fund_code, indicator="拆分详情"
            )

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金[{fund_code}]拆分数据")
                return None

            # 重命名列
            df = df.rename(
                columns={
                    "年份": "YEAR",
                    "拆分折算日": "SPLIT_DATE",
                    "拆分类型": "SPLIT_TYPE",
                    "拆分折算比例": "SPLIT_RATIO",
                }
            )

            # 解析拆分比例
            df[["RATIO_FROM", "RATIO_TO"]] = df["SPLIT_RATIO"].apply(
                lambda x: pd.Series(self.parse_split_ratio(x))
            )

            # 添加基金代码
            df["FUND_CODE"] = fund_code

            # 转换日期格式
            if "SPLIT_DATE" in df.columns:
                df["SPLIT_DATE"] = pd.to_datetime(df["SPLIT_DATE"], errors="coerce").dt.date

            # 生成主键
            df["R_ID"] = (
                df["FUND_CODE"]
                + "_"
                + df["SPLIT_DATE"].astype(str)
                + "_"
                + df["SPLIT_RATIO"].astype(str)
            )

            # 添加系统字段
            df["REFERENCE_CODE"] = "FUND_SPLIT"
            df["REFERENCE_NAME"] = "基金拆分详情表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "YEAR",
                "SPLIT_DATE",
                "SPLIT_TYPE",
                "SPLIT_RATIO",
                "RATIO_FROM",
                "RATIO_TO",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功获取基金[{fund_code}]{len(df)}条拆分数据")
            return df

        except Exception as e:
            self.logger.error(f"获取基金[{fund_code}]拆分数据失败: {e}", exc_info=True)
            return None

    def save_fund_split_data(self, df):
        """
        保存基金拆分数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有数据需要保存")
            return False

        return self.save_data(
            df=df,
            table_name=self.table_name,
            on_duplicate_update=True,
            unique_keys=["R_ID"],
        )

    def run(self, fund_codes=None):
        """
        执行数据获取和保存

        Args:
            fund_codes: 基金代码列表，如果为None则从数据库获取所有基金

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行基金拆分数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 如果未指定基金代码，则从数据库获取所有基金代码
            if fund_codes is None:
                fund_codes = self._get_all_fund_codes()
                if not fund_codes:
                    self.logger.error("未获取到基金代码")
                    return False

            total_success = True
            total_count = 0

            # 遍历基金代码
            for fund_code in fund_codes:
                try:
                    # 获取数据
                    df = self.fetch_fund_split_data(fund_code)

                    if df is None or df.empty:
                        continue

                    # 保存数据
                    success = self.save_fund_split_data(df)

                    if success:
                        total_count += len(df)
                        self.logger.info(f"成功保存基金[{fund_code}]{len(df)}条拆分数据")
                    else:
                        self.logger.error(f"保存基金[{fund_code}]拆分数据失败")
                        total_success = False

                    # 避免请求过于频繁
                    time.sleep(1)

                except Exception as e:
                    self.logger.error(f"处理基金[{fund_code}]拆分数据时出错: {e}", exc_info=True)
                    total_success = False
                    continue

            self.logger.info(f"基金拆分数据更新完成，共处理{total_count}条数据")
            return total_success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()

    def _get_all_fund_codes(self):
        """
        从数据库获取所有基金代码

        Returns:
            list: 基金代码列表
        """
        try:
            self.connect_db()
            sql = """
            SELECT DISTINCT FUND_CODE
            FROM OPEN_FUND_DAILY_EM
            WHERE IS_ACTIVE = 1
            ORDER BY FUND_CODE
            """
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
            return [row[0] for row in result] if result else []
        except Exception as e:
            self.logger.error(f"获取基金代码列表失败: {e}")
            return []


if __name__ == "__main__":
    # 示例：更新指定基金的拆分数据
    fund_codes = [
        "161606",
        "000001",
    ]  # 可以指定要更新的基金代码，如果为None则更新所有基金

    data_updater = FundSplitEm()
    data_updater.run(fund_codes=fund_codes)
