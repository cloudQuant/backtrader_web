import time
from datetime import datetime, timedelta

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class EtfFundHistEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # ETF基金历史数据表
        self.table_name = "ETF_FUND_HIST_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `ETF_FUND_HIST_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'ETF_FUND_HIST' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT 'ETF基金历史数据表(东方财富)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',

                              -- 净值信息
                              `VALUE_DATE` DATE COMMENT '净值日期',
                              `UNIT_NET_VALUE` DECIMAL(10, 4) COMMENT '单位净值(元)',
                              `ACCUMULATED_NET_VALUE` DECIMAL(10, 4) COMMENT '累计净值(元)',
                              `DAILY_GROWTH_RATE` DECIMAL(10, 4) COMMENT '日增长率(%)',
                              `PURCHASE_STATUS` VARCHAR(50) COMMENT '申购状态',
                              `REDEMPTION_STATUS` VARCHAR(50) COMMENT '赎回状态',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_DATE_UNIQUE` (`FUND_CODE`, `VALUE_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_VALUE_DATE` (`VALUE_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETF基金历史数据表(东方财富)';
                            """

    def parse_growth_rate(self, value):
        """
        解析增长率字符串，如'0.03'，返回0.03

        Args:
            value: 增长率字符串或数值

        Returns:
            float or None: 解析后的数值，如果解析失败返回None
        """
        if pd.isna(value) or value == "---" or value == "":
            return None

        try:
            if isinstance(value, str):
                value = value.replace("%", "").strip()
                if not value:  # 空字符串
                    return None
            return float(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"解析增长率失败: {e}, 原始值: {value}")
            return None

    def parse_net_value(self, value):
        """
        解析净值字符串，如'1.0000'，返回1.0

        Args:
            value: 净值字符串或数值

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
            self.logger.warning(f"解析净值失败: {e}, 原始值: {value}")
            return None

    def fetch_fund_hist_data(self, fund_code, start_date=None, end_date=None):
        """
        获取ETF基金历史数据

        Args:
            fund_code: 基金代码
            start_date: 开始日期，格式'YYYYMMDD'，如果为None则默认为10年前
            end_date: 结束日期，格式'YYYYMMDD'，如果为None则默认为当前日期

        Returns:
            pd.DataFrame: 处理后的历史数据
        """
        try:
            self.logger.info(f"开始获取ETF基金[{fund_code}]历史数据...")

            # 设置默认日期范围
            if end_date is None:
                end_date = datetime.now().strftime("%Y%m%d")
            if start_date is None:
                ten_years_ago = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y%m%d")
                start_date = ten_years_ago

            # 获取数据
            df = self.fetch_ak_data(
                "fund_etf_fund_info_em",
                fund=fund_code,
                start_date=start_date,
                end_date=end_date,
            )

            if df is None or df.empty:
                self.logger.warning(f"未获取到ETF基金[{fund_code}]历史数据")
                return None

            # 重命名列
            df = df.rename(
                columns={
                    "净值日期": "VALUE_DATE",
                    "单位净值": "UNIT_NET_VALUE_STR",
                    "累计净值": "ACCUMULATED_NET_VALUE_STR",
                    "日增长率": "DAILY_GROWTH_RATE_STR",
                    "申购状态": "PURCHASE_STATUS",
                    "赎回状态": "REDEMPTION_STATUS",
                }
            )

            # 添加基金代码
            df["FUND_CODE"] = fund_code

            # 转换日期格式
            df["VALUE_DATE"] = pd.to_datetime(df["VALUE_DATE"], errors="coerce").dt.date

            # 解析数值型数据
            df["UNIT_NET_VALUE"] = df["UNIT_NET_VALUE_STR"].apply(self.parse_net_value)
            df["ACCUMULATED_NET_VALUE"] = df["ACCUMULATED_NET_VALUE_STR"].apply(
                self.parse_net_value
            )
            df["DAILY_GROWTH_RATE"] = df["DAILY_GROWTH_RATE_STR"].apply(self.parse_growth_rate)

            # 生成主键
            df["R_ID"] = df["FUND_CODE"] + "_" + df["VALUE_DATE"].astype(str)

            # 添加系统字段
            df["REFERENCE_CODE"] = "ETF_FUND_HIST"
            df["REFERENCE_NAME"] = "ETF基金历史数据表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "VALUE_DATE",
                "UNIT_NET_VALUE",
                "ACCUMULATED_NET_VALUE",
                "DAILY_GROWTH_RATE",
                "PURCHASE_STATUS",
                "REDEMPTION_STATUS",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功获取ETF基金[{fund_code}]{len(df)}条历史数据")
            return df

        except Exception as e:
            self.logger.error(f"获取ETF基金[{fund_code}]历史数据失败: {e}", exc_info=True)
            return None

    def save_fund_hist_data(self, df, fund_code):
        """
        保存ETF基金历史数据到数据库

        Args:
            df: 要保存的数据
            fund_code: 基金代码

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning(f"基金[{fund_code}]没有数据需要保存")
            return False

        # 获取已存在的数据日期
        existing_dates = self._get_existing_dates(fund_code)

        # 过滤掉已存在的数据
        if existing_dates:
            df = df[~df["VALUE_DATE"].isin(existing_dates)]

        if df.empty:
            self.logger.info(f"基金[{fund_code}]没有新数据需要保存")
            return True

        return self.save_data(
            df=df,
            table_name=self.table_name,
            on_duplicate_update=True,
            unique_keys=["R_ID"],
        )

    def _get_existing_dates(self, fund_code):
        """
        获取已存在的数据日期

        Args:
            fund_code: 基金代码

        Returns:
            set: 已存在的日期集合
        """
        try:
            self.connect_db()
            sql = """
            SELECT VALUE_DATE
            FROM ETF_FUND_HIST_EM
            WHERE FUND_CODE = %s AND IS_ACTIVE = 1
            """
            self.cursor.execute(sql, (fund_code,))
            result = self.cursor.fetchall()
            return {row[0] for row in result} if result else set()
        except Exception as e:
            self.logger.error(f"获取已存在数据日期失败: {e}")
            return set()

    def run(self, fund_codes=None, start_date=None, end_date=None):
        """
        执行数据获取和保存

        Args:
            fund_codes: 基金代码列表，如果为None则从数据库获取所有ETF基金代码
            start_date: 开始日期，格式'YYYYMMDD'，如果为None则默认为10年前
            end_date: 结束日期，格式'YYYYMMDD'，如果为None则默认为当前日期

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行ETF基金历史数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 如果未指定基金代码，则从数据库获取所有ETF基金代码
            if fund_codes is None:
                fund_codes = self._get_all_etf_fund_codes()
                if not fund_codes:
                    self.logger.error("未获取到ETF基金代码")
                    return False

            total_success = True
            total_count = 0

            # 遍历基金代码
            for fund_code in fund_codes:
                try:
                    # 获取数据
                    df = self.fetch_fund_hist_data(fund_code, start_date, end_date)

                    if df is None or df.empty:
                        continue

                    # 保存数据
                    success = self.save_fund_hist_data(df, fund_code)

                    if success:
                        total_count += len(df)
                        self.logger.info(f"成功保存基金[{fund_code}]{len(df)}条历史数据")
                    else:
                        self.logger.error(f"保存基金[{fund_code}]历史数据失败")
                        total_success = False

                    # 避免请求过于频繁
                    time.sleep(1)

                except Exception as e:
                    self.logger.error(f"处理基金[{fund_code}]历史数据时出错: {e}", exc_info=True)
                    total_success = False
                    continue

            self.logger.info(f"ETF基金历史数据更新完成，共处理{total_count}条数据")
            return total_success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()

    def _get_all_etf_fund_codes(self):
        """
        从数据库获取所有ETF基金代码

        Returns:
            list: 基金代码列表
        """
        try:
            self.connect_db()
            sql = """
            SELECT DISTINCT FUND_CODE
            FROM ETF_FUND_DAILY_EM
            WHERE IS_ACTIVE = 1
            ORDER BY FUND_CODE
            """
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
            return [row[0] for row in result] if result else []
        except Exception as e:
            self.logger.error(f"获取ETF基金代码列表失败: {e}")
            return []


if __name__ == "__main__":
    # 示例：更新指定ETF基金的历史数据
    fund_codes = [
        "511280",
        "510300",
    ]  # 可以指定要更新的基金代码，如果为None则更新所有ETF基金
    start_date = "20200101"  # 开始日期，格式'YYYYMMDD'，如果为None则默认为10年前
    end_date = "20230811"  # 结束日期，格式'YYYYMMDD'，如果为None则默认为当前日期

    data_updater = EtfFundHistEm()
    data_updater.run(fund_codes=fund_codes, start_date=start_date, end_date=end_date)
