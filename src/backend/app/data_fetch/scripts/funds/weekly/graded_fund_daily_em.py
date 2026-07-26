from datetime import datetime

import pandas as pd
import requests
from akshare.utils import demjson

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class GradedFundDailyEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 分级基金实时数据表
        self.table_name = "GRADED_FUND_DAILY_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `GRADED_FUND_DAILY_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'GRADED_FUND_DAILY' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '分级基金实时数据表(东方财富)' COMMENT '参考名称',

                              -- 基金基本信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',

                              -- 净值信息
                              `UNIT_NET_VALUE` DECIMAL(10, 4) COMMENT '单位净值(元)',
                              `ACCUMULATED_NET_VALUE` DECIMAL(10, 4) COMMENT '累计净值(元)',
                              `PREV_UNIT_NET_VALUE` DECIMAL(10, 4) COMMENT '前交易日-单位净值(元)',
                              `PREV_ACCUMULATED_NET_VALUE` DECIMAL(10, 4) COMMENT '前交易日-累计净值(元)',
                              `DAILY_GROWTH_VALUE` DECIMAL(10, 4) COMMENT '日增长值',
                              `DAILY_GROWTH_RATE` DECIMAL(10, 4) COMMENT '日增长率(%)',

                              -- 市场信息
                              `MARKET_PRICE` DECIMAL(10, 4) COMMENT '市价(元)',
                              `DISCOUNT_RATE` DECIMAL(10, 4) COMMENT '折价率(%)',
                              `FEE` VARCHAR(50) COMMENT '手续费',

                              -- 系统字段
                              `TRADE_DATE` DATE COMMENT '交易日期',
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_DATE_UNIQUE` (`FUND_CODE`, `TRADE_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分级基金实时数据表(东方财富)';
                            """

    def parse_percentage(self, value):
        """
        解析百分比字符串，如'15.85'，返回15.85

        Args:
            value: 百分比字符串或数值

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
            self.logger.warning(f"解析百分比失败: {e}, 原始值: {value}")
            return None

    def parse_net_value(self, value):
        """
        解析净值字符串，如'0.5598'，返回0.5598

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

    def parse_discount_rate(self, value):
        """
        解析折价率字符串，如'-62.20'，返回-62.20

        Args:
            value: 折价率字符串或数值

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
            self.logger.warning(f"解析折价率失败: {e}, 原始值: {value}")
            return None

    @staticmethod
    def _first_existing(row, positions):
        for pos in positions:
            if pos < len(row) and row[pos] not in (None, "", "---"):
                return row[pos]
        return None

    def _fetch_source_frame(self):
        url = "https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://fund.eastmoney.com/fjjj.html",
        }
        params = {
            "t": "1",
            "lx": "9",
            "letter": "",
            "gsid": "0",
            "text": "",
            "sort": "zdf,desc",
            "page": "1,10000",
            "dt": "1580914040623",
            "atfc": "",
        }
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data_json = demjson.decode(response.text.strip().removeprefix("var db="))
        rows = data_json.get("datas") or []
        if not rows:
            return pd.DataFrame()

        parsed_rows = []
        for row in rows:
            parsed_rows.append(
                {
                    "FUND_CODE": self._first_existing(row, [0]),
                    "FUND_NAME": self._first_existing(row, [1]),
                    "UNIT_NET_VALUE_STR": self._first_existing(row, [3]),
                    "ACCUMULATED_NET_VALUE_STR": self._first_existing(row, [4]),
                    "PREV_UNIT_NET_VALUE_STR": self._first_existing(row, [5]),
                    "PREV_ACCUMULATED_NET_VALUE_STR": self._first_existing(row, [6]),
                    "DAILY_GROWTH_VALUE_STR": self._first_existing(row, [7]),
                    "DAILY_GROWTH_RATE_STR": self._first_existing(row, [8]),
                    "MARKET_PRICE_STR": None,
                    "DISCOUNT_RATE_STR": None,
                    "FEE": self._first_existing(row, [17, 18, 20]),
                }
            )
        return pd.DataFrame(parsed_rows)

    def fetch_graded_fund_daily_data(self):
        """
        获取分级基金每日数据

        Returns:
            pd.DataFrame: 处理后的分级基金数据
        """
        try:
            self.logger.info("开始获取分级基金每日数据...")

            # AkShare's wrapper still targets this Eastmoney endpoint, but its fixed
            # column count is stale. Parse the current source response directly.
            df = self._fetch_source_frame()

            if df is None or df.empty:
                self.logger.warning("未获取到分级基金每日数据")
                return None

            # 解析数值型数据
            df["UNIT_NET_VALUE"] = df["UNIT_NET_VALUE_STR"].apply(self.parse_net_value)
            df["ACCUMULATED_NET_VALUE"] = df["ACCUMULATED_NET_VALUE_STR"].apply(
                self.parse_net_value
            )
            df["PREV_UNIT_NET_VALUE"] = df["PREV_UNIT_NET_VALUE_STR"].apply(self.parse_net_value)
            df["PREV_ACCUMULATED_NET_VALUE"] = df["PREV_ACCUMULATED_NET_VALUE_STR"].apply(
                self.parse_net_value
            )
            df["DAILY_GROWTH_VALUE"] = df["DAILY_GROWTH_VALUE_STR"].apply(self.parse_net_value)
            df["DAILY_GROWTH_RATE"] = df["DAILY_GROWTH_RATE_STR"].apply(self.parse_percentage)
            df["MARKET_PRICE"] = df["MARKET_PRICE_STR"].apply(self.parse_net_value)
            df["DISCOUNT_RATE"] = df["DISCOUNT_RATE_STR"].apply(self.parse_discount_rate)

            # 添加交易日期（当前日期）
            current_date = datetime.now().date()
            df["TRADE_DATE"] = current_date

            # 生成主键
            df["R_ID"] = df["FUND_CODE"] + "_" + df["TRADE_DATE"].astype(str)

            # 添加系统字段
            df["REFERENCE_CODE"] = "GRADED_FUND_DAILY"
            df["REFERENCE_NAME"] = "分级基金实时数据表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "FUND_NAME",
                "UNIT_NET_VALUE",
                "ACCUMULATED_NET_VALUE",
                "PREV_UNIT_NET_VALUE",
                "PREV_ACCUMULATED_NET_VALUE",
                "DAILY_GROWTH_VALUE",
                "DAILY_GROWTH_RATE",
                "MARKET_PRICE",
                "DISCOUNT_RATE",
                "FEE",
                "TRADE_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功获取{len(df)}条分级基金每日数据")
            return df

        except Exception as e:
            self.logger.error(f"获取分级基金每日数据失败: {e}", exc_info=True)
            return None

    def save_graded_fund_daily_data(self, df):
        """
        保存分级基金每日数据到数据库

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

    def run(self):
        """
        执行数据获取和保存

        Returns:
            bool: 是否执行成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行分级基金每日数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取数据
            df = self.fetch_graded_fund_daily_data()

            if df is None or df.empty:
                self.logger.error("未获取到有效数据")
                return False

            # 保存数据
            success = self.save_graded_fund_daily_data(df)

            if success:
                self.logger.info(f"成功保存{len(df)}条分级基金每日数据")
            else:
                self.logger.error("保存分级基金每日数据失败")

            return success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    # 更新分级基金每日数据
    data_updater = GradedFundDailyEm()
    data_updater.run()
