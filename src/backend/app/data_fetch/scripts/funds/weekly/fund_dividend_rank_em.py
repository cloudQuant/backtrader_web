import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundDividendRankEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 基金分红排行数据表
        self.table_name = "FUND_DIVIDEND_RANK_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `FUND_DIVIDEND_RANK_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'FUND_DIVIDEND_RANK' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '基金分红排行数据表(东方财富)' COMMENT '参考名称',

                              -- 基金信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',

                              -- 分红信息
                              `TOTAL_DIVIDEND` DECIMAL(20, 6) COMMENT '累计分红(元/份)',
                              `DIVIDEND_COUNT` INT COMMENT '累计分红次数',
                              `ESTABLISH_DATE` DATE COMMENT '成立日期',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_FUND_DIVIDEND_RANK_UNIQUE` (`FUND_CODE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_TOTAL_DIVIDEND` (`TOTAL_DIVIDEND`),
                              KEY `IDX_ESTABLISH_DATE` (`ESTABLISH_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金分红排行数据表(东方财富)';
                            """

    def parse_date(self, date_str):
        """
        解析日期字符串

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

    def parse_float(self, value, default=None):
        """
        解析浮点数值

        Args:
            value: 要解析的值
            default: 解析失败时的默认值

        Returns:
            float or default: 解析后的浮点数值或默认值
        """
        if pd.isna(value) or value == "---" or value == "":
            return default

        try:
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return default
            return float(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"解析浮点数失败: {e}, 原始值: {value}")
            return default

    def parse_int(self, value, default=None):
        """
        解析整数值

        Args:
            value: 要解析的值
            default: 解析失败时的默认值

        Returns:
            int or default: 解析后的整数值或默认值
        """
        if pd.isna(value) or value == "---" or value == "":
            return default

        try:
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return default
            return int(float(value))
        except (ValueError, TypeError) as e:
            self.logger.warning(f"解析整数失败: {e}, 原始值: {value}")
            return default

    def fetch_dividend_rank_data(self):
        """
        获取基金分红排行数据

        Returns:
            pd.DataFrame: 处理后的分红排行数据
        """
        try:
            self.logger.info("开始获取基金分红排行数据...")

            # 获取数据
            df = self.fetch_ak_data("fund_fh_rank_em")

            if df is None or df.empty:
                self.logger.warning("未获取到基金分红排行数据")
                return None

            # 重命名列
            df = df.rename(
                columns={
                    "基金代码": "FUND_CODE",
                    "基金简称": "FUND_NAME",
                    "累计分红": "TOTAL_DIVIDEND_STR",
                    "累计次数": "DIVIDEND_COUNT_STR",
                    "成立日期": "ESTABLISH_DATE_STR",
                }
            )

            # 解析数据
            df["TOTAL_DIVIDEND"] = df["TOTAL_DIVIDEND_STR"].apply(
                lambda x: self.parse_float(x, 0.0)
            )
            df["DIVIDEND_COUNT"] = df["DIVIDEND_COUNT_STR"].apply(lambda x: self.parse_int(x, 0))
            df["ESTABLISH_DATE"] = df["ESTABLISH_DATE_STR"].apply(self.parse_date)

            # 生成主键
            df["R_ID"] = df["FUND_CODE"]

            # 添加系统字段
            df["REFERENCE_CODE"] = "FUND_DIVIDEND_RANK"
            df["REFERENCE_NAME"] = "基金分红排行数据表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 只保留需要的列
            columns_to_keep = [
                "R_ID",
                "REFERENCE_CODE",
                "REFERENCE_NAME",
                "FUND_CODE",
                "FUND_NAME",
                "TOTAL_DIVIDEND",
                "DIVIDEND_COUNT",
                "ESTABLISH_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
                "CREATEDATE",
                "CREATEUSER",
                "UPDATEDATE",
                "UPDATEUSER",
            ]
            df = df[[col for col in columns_to_keep if col in df.columns]]

            self.logger.info(f"成功获取{len(df)}条基金分红排行数据")
            return df

        except Exception as e:
            self.logger.error(f"获取基金分红排行数据失败: {e}", exc_info=True)
            return None

    def save_dividend_rank_data(self, df):
        """
        保存基金分红排行数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有基金分红排行数据需要保存")
            return False

        # 获取已存在的数据ID
        existing_ids = self._get_existing_ids()

        # 过滤掉已存在的数据
        if existing_ids:
            df = df[~df["R_ID"].isin(existing_ids)]

        if df.empty:
            self.logger.info("没有新的基金分红排行数据需要保存")
            return True

        return self.save_data(
            df=df,
            table_name=self.table_name,
            on_duplicate_update=True,
            unique_keys=["R_ID"],
        )

    def _get_existing_ids(self):
        """
        获取已存在的数据ID

        Returns:
            set: 已存在的数据ID集合
        """
        try:
            self.connect_db()
            sql = "SELECT R_ID FROM FUND_DIVIDEND_RANK_EM WHERE IS_ACTIVE = 1"
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
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
            self.logger.info("开始执行基金分红排行数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取数据
            df = self.fetch_dividend_rank_data()

            if df is None or df.empty:
                self.logger.error("未获取到有效的基金分红排行数据")
                return False

            # 保存数据
            success = self.save_dividend_rank_data(df)

            if success:
                self.logger.info(f"成功保存{len(df)}条基金分红排行数据")
            else:
                self.logger.error("保存基金分红排行数据失败")

            return success

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    # 更新基金分红排行数据
    data_updater = FundDividendRankEm()
    data_updater.run()
