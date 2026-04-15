import re
import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundDividendEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金分红数据表
        self.table_name = "FUND_DIVIDEND_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_DIVIDEND_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_DIVIDEND' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金分红送配详情表(东方财富)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 分红信息
                              `YEAR` VARCHAR(10) COMMENT '年份',
                              `REGISTER_DATE` DATE COMMENT '权益登记日',
                              `EX_DIVIDEND_DATE` DATE COMMENT '除息日',
                              `DIVIDEND_PER_UNIT` DECIMAL(10, 4) COMMENT '每份分红(元)',
                              `PAYOUT_DATE` DATE COMMENT '分红发放日',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_DIVIDEND_UNIQUE` (`FUND_CODE`, `REGISTER_DATE`, `DIVIDEND_PER_UNIT`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_REGISTER_DATE` (`REGISTER_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金分红送配详情表(东方财富)';
                            """

    def extract_dividend_amount(self, dividend_str):
        """
        从分红字符串中提取分红金额

        Args:
            dividend_str: 分红字符串，如'每份派现金0.0050元'

        Returns:
            float: 提取的分红金额，如果提取失败返回None
        """
        if not isinstance(dividend_str, str):
            return None

        try:
            # 使用正则表达式提取数字
            match = re.search(r"(\d+\.?\d*)", dividend_str)
            if match:
                return float(match.group(1))
            return None
        except Exception as e:
            self.logger.warning(f"提取分红金额失败: {e}, 原始字符串: {dividend_str}")
            return None

    def fetch_fund_dividend_data(self, fund_code):
        """
        获取基金分红数据

        Args:
            fund_code: 基金代码

        Returns:
            pd.DataFrame: 处理后的分红数据
        """
        try:
            self.logger.info(f"开始获取基金[{fund_code}]分红数据...")

            # 获取数据
            df = self.fetch_ak_data(
                "fund_open_fund_info_em", symbol=fund_code, indicator="分红送配详情"
            )

            if df is None or df.empty:
                self.logger.warning(f"未获取到基金[{fund_code}]分红数据")
                return None

            # 重命名列
            df = df.rename(
                columns={
                    "年份": "YEAR",
                    "权益登记日": "REGISTER_DATE",
                    "除息日": "EX_DIVIDEND_DATE",
                    "每份分红": "DIVIDEND_STR",
                    "分红发放日": "PAYOUT_DATE",
                }
            )

            # 提取分红金额
            df["DIVIDEND_PER_UNIT"] = df["DIVIDEND_STR"].apply(self.extract_dividend_amount)

            # 添加基金代码
            df["FUND_CODE"] = fund_code

            # 转换日期格式
            date_columns = ["REGISTER_DATE", "EX_DIVIDEND_DATE", "PAYOUT_DATE"]
            for col in date_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

            # 生成主键
            df["R_ID"] = (
                df["FUND_CODE"]
                + "_"
                + df["REGISTER_DATE"].astype(str)
                + "_"
                + df["DIVIDEND_PER_UNIT"].astype(str)
            )

            # 添加系统字段
            df["REFERENCE_CODE"] = "FUND_DIVIDEND"
            df["REFERENCE_NAME"] = "基金分红送配详情表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "YEAR",
                "REGISTER_DATE",
                "EX_DIVIDEND_DATE",
                "DIVIDEND_PER_UNIT",
                "PAYOUT_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功获取基金[{fund_code}]{len(df)}条分红数据")
            return df

        except Exception as e:
            self.logger.error(f"获取基金[{fund_code}]分红数据失败: {e}", exc_info=True)
            return None

    def save_fund_dividend_data(self, df):
        """
        保存基金分红数据到数据库

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
            self.logger.info("开始执行基金分红数据更新")

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
                    df = self.fetch_fund_dividend_data(fund_code)

                    if df is None or df.empty:
                        continue

                    # 保存数据
                    success = self.save_fund_dividend_data(df)

                    if success:
                        total_count += len(df)
                        self.logger.info(f"成功保存基金[{fund_code}]{len(df)}条分红数据")
                    else:
                        self.logger.error(f"保存基金[{fund_code}]分红数据失败")
                        total_success = False

                    # 避免请求过于频繁
                    time.sleep(1)

                except Exception as e:
                    self.logger.error(f"处理基金[{fund_code}]分红数据时出错: {e}", exc_info=True)
                    total_success = False
                    continue

            self.logger.info(f"基金分红数据更新完成，共处理{total_count}条数据")
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
    # 示例：更新指定基金的分红数据
    fund_codes = [
        "161606",
        "000001",
    ]  # 可以指定要更新的基金代码，如果为None则更新所有基金

    data_updater = FundDividendEm()
    data_updater.run(fund_codes=fund_codes)
