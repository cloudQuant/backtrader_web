import time

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class HkFundDividendEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 香港基金分红数据表
        self.table_name = "HK_FUND_DIVIDEND_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `HK_FUND_DIVIDEND_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'HK_FUND_DIVIDEND' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '香港基金分红数据表(东方财富)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 分红信息
                              `DIVIDEND_YEAR` VARCHAR(10) COMMENT '分红年份',
                              `RECORD_DATE` DATE COMMENT '权益登记日',
                              `EX_DIVIDEND_DATE` DATE COMMENT '除息日',
                              `PAY_DATE` DATE COMMENT '分红发放日',
                              `DIVIDEND_AMOUNT` DECIMAL(10, 6) COMMENT '分红金额',
                              `CURRENCY` VARCHAR(10) COMMENT '币种',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_DIVIDEND_UNIQUE` (`FUND_CODE`, `DIVIDEND_YEAR`, `RECORD_DATE`, `DIVIDEND_AMOUNT`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_RECORD_DATE` (`RECORD_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='香港基金分红数据表(东方财富)';
                            """

    def parse_dividend_amount(self, value):
        """
        解析分红金额字符串，如'0.0522'，返回0.0522

        Args:
            value: 分红金额字符串或数值

        Returns:
            float or None: 解析后的数值，如果解析失败返回None
        """
        if pd.isna(value) or value == "---" or value == "":
            return None

        try:
            if isinstance(value, str):
                value = value.strip()
                if not value:  # 空字符串
                    return None
            return float(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"解析分红金额失败: {e}, 原始值: {value}")
            return None

    def parse_date(self, date_str):
        """
        解析日期字符串，支持空字符串

        Args:
            date_str: 日期字符串

        Returns:
            date or None: 解析后的日期，如果解析失败或为空返回None
        """
        if not date_str or pd.isna(date_str) or str(date_str).strip() == "":
            return None

        try:
            return pd.to_datetime(date_str).date()
        except Exception as e:
            self.logger.warning(f"解析日期失败: {e}, 原始值: {date_str}")
            return None

    def fetch_fund_dividend_data(self, fund_code):
        """
        获取香港基金分红数据

        Args:
            fund_code: 基金代码

        Returns:
            pd.DataFrame: 处理后的分红数据
        """
        try:
            self.logger.info(f"开始获取香港基金[{fund_code}]分红数据...")

            # 获取数据 - 分红送配详情
            df = self.fetch_ak_data("fund_hk_fund_hist_em", code=fund_code, symbol="分红送配详情")

            if df is None or df.empty:
                self.logger.warning(f"未获取到香港基金[{fund_code}]分红数据")
                return None

            # 重命名列
            df = df.rename(
                columns={
                    "年份": "DIVIDEND_YEAR",
                    "权益登记日": "RECORD_DATE_STR",
                    "除息日": "EX_DIVIDEND_DATE_STR",
                    "分红发放日": "PAY_DATE_STR",
                    "分红金额": "DIVIDEND_AMOUNT_STR",
                    "单位": "CURRENCY",
                }
            )

            # 添加基金代码
            df["FUND_CODE"] = fund_code

            # 解析日期
            df["RECORD_DATE"] = df["RECORD_DATE_STR"].apply(self.parse_date)
            df["EX_DIVIDEND_DATE"] = df["EX_DIVIDEND_DATE_STR"].apply(self.parse_date)
            df["PAY_DATE"] = df["PAY_DATE_STR"].apply(self.parse_date)

            # 解析分红金额
            df["DIVIDEND_AMOUNT"] = df["DIVIDEND_AMOUNT_STR"].apply(self.parse_dividend_amount)

            # 生成主键
            df["R_ID"] = df.apply(
                lambda x: f"{x['FUND_CODE']}_{x['DIVIDEND_YEAR']}_{x['RECORD_DATE'] or ''}_{x['DIVIDEND_AMOUNT'] or '0'}",
                axis=1,
            )

            # 添加系统字段
            df["REFERENCE_CODE"] = "HK_FUND_DIVIDEND"
            df["REFERENCE_NAME"] = "香港基金分红数据表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "DIVIDEND_YEAR",
                "RECORD_DATE",
                "EX_DIVIDEND_DATE",
                "PAY_DATE",
                "DIVIDEND_AMOUNT",
                "CURRENCY",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功获取香港基金[{fund_code}]{len(df)}条分红数据")
            return df

        except Exception as e:
            self.logger.error(f"获取香港基金[{fund_code}]分红数据失败: {e}", exc_info=True)
            return None

    def save_fund_dividend_data(self, df, fund_code):
        """
        保存香港基金分红数据到数据库

        Args:
            df: 要保存的数据
            fund_code: 基金代码

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning(f"香港基金[{fund_code}]没有分红数据需要保存")
            return False

        # 获取已存在的数据ID
        existing_ids = self._get_existing_ids(fund_code)

        # 过滤掉已存在的数据
        if existing_ids:
            df = df[~df["R_ID"].isin(existing_ids)]

        if df.empty:
            self.logger.info(f"香港基金[{fund_code}]没有新分红数据需要保存")
            return True

        return self.save_data(
            df=df,
            table_name=self.table_name,
            on_duplicate_update=True,
            unique_keys=["R_ID"],
        )

    def _get_existing_ids(self, fund_code):
        """
        获取已存在的数据ID

        Args:
            fund_code: 基金代码

        Returns:
            set: 已存在的数据ID集合
        """
        try:
            self.connect_db()
            sql = """
            SELECT R_ID
            FROM HK_FUND_DIVIDEND_EM
            WHERE FUND_CODE = %s AND IS_ACTIVE = 1
            """
            self.cursor.execute(sql, (fund_code,))
            result = self.cursor.fetchall()
            return {row[0] for row in result} if result else set()
        except Exception as e:
            self.logger.error(f"获取已存在数据ID失败: {e}")
            return set()

    def run(self, fund_codes=None):
        """
        执行数据获取和保存

        Args:
            fund_codes: 基金代码列表，如果为None则从数据库获取所有香港基金代码

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行香港基金分红数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 如果未指定基金代码，则从数据库获取所有香港基金代码
            if fund_codes is None:
                fund_codes = self._get_all_hk_fund_codes()
                if not fund_codes:
                    self.logger.error("未获取到香港基金代码")
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
                    success = self.save_fund_dividend_data(df, fund_code)

                    if success:
                        total_count += len(df)
                        self.logger.info(f"成功保存香港基金[{fund_code}]{len(df)}条分红数据")
                    else:
                        self.logger.error(f"保存香港基金[{fund_code}]分红数据失败")
                        total_success = False

                    # 避免请求过于频繁
                    time.sleep(1)

                except Exception as e:
                    self.logger.error(
                        f"处理香港基金[{fund_code}]分红数据时出错: {e}", exc_info=True
                    )
                    total_success = False
                    continue

            self.logger.info(f"香港基金分红数据更新完成，共处理{total_count}条数据")
            return total_success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()

    def _get_all_hk_fund_codes(self):
        """
        从数据库获取所有香港基金代码

        Returns:
            list: 基金代码列表
        """
        # 注意：需要先实现获取香港基金列表的功能
        # 这里暂时返回空列表，需要根据实际情况实现
        self.logger.warning("获取香港基金代码列表功能待实现，需要使用fund_em_hk_rank接口获取")
        return []


if __name__ == "__main__":
    # 示例：更新指定香港基金的分红数据
    fund_codes = ["1002200683"]  # 可以指定要更新的基金代码，如果为None则尝试从数据库获取

    data_updater = HkFundDividendEm()
    data_updater.run(fund_codes=fund_codes)
