from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class OpenFundDailyEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        # 开放式基金日净值数据表
        self.table_name = "OPEN_FUND_DAILY_EM"

        # 表结构定义
        self.create_table_sql = """
                            CREATE TABLE `OPEN_FUND_DAILY_EM` (
                              `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                              `REFERENCE_CODE` VARCHAR(50) DEFAULT 'OPEN_FUND_DAILY' COMMENT '参考编码',
                              `REFERENCE_NAME` VARCHAR(100) DEFAULT '开放式基金日净值表(东方财富)' COMMENT '参考名称',

                              -- 基金基本信息
                              `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                              `FUND_NAME` VARCHAR(100) COMMENT '基金简称',

                              -- 净值信息
                              `NAV_DATE` DATE NOT NULL COMMENT '净值日期',
                              `NAV` DECIMAL(10, 4) COMMENT '单位净值',
                              `ACCUMULATED_NAV` DECIMAL(10, 4) COMMENT '累计净值',
                              `PREV_NAV` DECIMAL(10, 4) COMMENT '前交易日-单位净值',
                              `PREV_ACCUMULATED_NAV` DECIMAL(10, 4) COMMENT '前交易日-累计净值',
                              `DAILY_GROWTH` DECIMAL(10, 4) COMMENT '日增长值',
                              `DAILY_GROWTH_RATE` DECIMAL(10, 4) COMMENT '日增长率(%)',

                              -- 交易状态
                              `PURCHASE_STATUS` VARCHAR(20) COMMENT '申购状态',
                              `REDEMPTION_STATUS` VARCHAR(20) COMMENT '赎回状态',
                              `FEE_RATE` VARCHAR(20) COMMENT '手续费率(%)',

                              -- 系统字段
                              `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                              `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                              `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                              `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                              PRIMARY KEY (`R_ID`),
                              UNIQUE KEY `IDX_OPEN_FUND_DAILY_UNIQUE` (`FUND_CODE`, `NAV_DATE`),
                              KEY `IDX_FUND_CODE` (`FUND_CODE`),
                              KEY `IDX_NAV_DATE` (`NAV_DATE`),
                              KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='开放式基金日净值表(东方财富)';
                            """

    def get_latest_date_from_table(self):
        """
        获取数据库中最新净值日期

        Returns:
            datetime: 最新净值日期，如果没有数据返回None
        """
        try:
            self.connect_db()
            sql = f"""  # nosec B608
            SELECT MAX(NAV_DATE) as latest_date
            FROM {self.table_name}
            WHERE IS_ACTIVE = 1
            """

            self.cursor.execute(sql)
            result = self.cursor.fetchone()
            if result and result[0]:
                return result[0]
            return None
        except Exception as e:
            self.logger.warning(f"获取最新净值日期失败: {e}")
            return None

    def fetch_open_fund_daily_data(self):
        """
        获取开放式基金日净值数据

        Returns:
            pd.DataFrame: 处理后的数据
        """
        try:
            self.logger.info("开始获取开放式基金日净值数据...")

            # 获取数据
            df = self.fetch_ak_data("fund_open_fund_daily_em")

            if df is None or df.empty:
                self.logger.warning("未获取到开放式基金日净值数据")
                return None

            # 重命名列
            column_mapping = {
                "基金代码": "FUND_CODE",
                "基金简称": "FUND_NAME",
                "2020-12-28-单位净值": "NAV",  # 动态列名，需要特殊处理
                "累计净值": "ACCUMULATED_NAV",
                "前交易日-单位净值": "PREV_NAV",
                "前交易日-累计净值": "PREV_ACCUMULATED_NAV",
                "日增长值": "DAILY_GROWTH",
                "日增长率": "DAILY_GROWTH_RATE",
                "申购状态": "PURCHASE_STATUS",
                "赎回状态": "REDEMPTION_STATUS",
                "手续费": "FEE_RATE",
            }

            # 动态获取净值日期列
            nav_date_col = [
                col for col in df.columns if "单位净值" in col and col != "前交易日-单位净值"
            ]
            if not nav_date_col:
                self.logger.error("未找到净值日期列")
                return None

            # 列名格式: YYYY-MM-DD-单位净值，需要提取日期部分
            # 例如: 2026-02-13-单位净值 -> 2026-02-13
            col_name = nav_date_col[0]
            # 找到最后一个 "-单位净值" 之前的部分
            if "-单位净值" in col_name:
                nav_date_str = col_name.split("-单位净值")[0]
            else:
                # 备用方案：用 "-" 分割后取前3部分
                parts = col_name.split("-")
                if len(parts) >= 3:
                    nav_date_str = "-".join(parts[:3])
                else:
                    nav_date_str = parts[0]

            try:
                nav_date = datetime.strptime(nav_date_str, "%Y-%m-%d").date()
            except ValueError:
                self.logger.error(f"净值日期格式错误: {nav_date_str}")
                return None

            # 重命名列
            df = df.rename(columns={nav_date_col[0]: "NAV"})

            # 重命名列
            df = df.rename(columns=column_mapping)

            # 添加日期列（必须在重命名之后，因为 column_mapping 中有 NAV）
            df["NAV_DATE"] = nav_date

            # 只保留需要的列（确保 NAV_DATE 被保留）
            columns_to_keep = ["FUND_CODE", "NAV_DATE"]
            columns_to_keep += [
                col
                for col in column_mapping.values()
                if col in df.columns and col not in columns_to_keep
            ]
            df = df[columns_to_keep]

            # 生成主键
            df["R_ID"] = df["FUND_CODE"] + "_" + df["NAV_DATE"].astype(str)

            # 添加系统字段
            df["REFERENCE_CODE"] = "OPEN_FUND_DAILY"
            df["REFERENCE_NAME"] = "开放式基金日净值表(东方财富)"
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "东方财富"

            # 转换数据类型
            numeric_cols = [
                "NAV",
                "ACCUMULATED_NAV",
                "PREV_NAV",
                "PREV_ACCUMULATED_NAV",
                "DAILY_GROWTH",
                "DAILY_GROWTH_RATE",
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 处理手续费率，移除百分号并转为浮点数
            if "FEE_RATE" in df.columns:
                df["FEE_RATE"] = df["FEE_RATE"].str.rstrip("%").replace("", None).astype(float)

            self.logger.info(f"成功获取{len(df)}条开放式基金日净值数据")
            return df

        except Exception as e:
            self.logger.error(f"获取开放式基金日净值数据失败: {e}", exc_info=True)
            return None

    def save_open_fund_daily_data(self, df):
        """
        保存开放式基金日净值数据到数据库

        Args:
            df: 要保存的数据

        Returns:
            bool: 是否保存成功
        """
        if df is None or df.empty:
            self.logger.warning("没有数据需要保存")
            return False

        # 获取需要的列
        columns = [
            "R_ID",
            "REFERENCE_CODE",
            "REFERENCE_NAME",
            "FUND_CODE",
            "FUND_NAME",
            "NAV_DATE",
            "NAV",
            "ACCUMULATED_NAV",
            "PREV_NAV",
            "PREV_ACCUMULATED_NAV",
            "DAILY_GROWTH",
            "DAILY_GROWTH_RATE",
            "PURCHASE_STATUS",
            "REDEMPTION_STATUS",
            "FEE_RATE",
            "IS_ACTIVE",
            "DATA_SOURCE",
            "CREATEDATE",
            "CREATEUSER",
            "UPDATEDATE",
            "UPDATEUSER",
        ]

        # 确保所有需要的列都存在
        df = df[[col for col in columns if col in df.columns]]

        return self.save_data(
            df=df,
            table_name=self.table_name,
            on_duplicate_update=True,
            unique_keys=["R_ID"],
        )

    def run(self):
        """
        执行数据获取和保存
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始执行开放式基金日净值数据更新")

            # 创建表（如果不存在）
            self.create_table_if_not_exists()

            # 获取最新净值日期
            latest_date = self.get_latest_date_from_table()
            today = datetime.now().date()

            if latest_date and latest_date >= today:
                self.logger.info(f"数据已是最新，最新净值日期: {latest_date}")
                return True

            # 获取数据
            df = self.fetch_open_fund_daily_data()

            if df is None or df.empty:
                self.logger.warning("未获取到有效数据")
                return False

            # 保存数据
            rows_saved = self.save_open_fund_daily_data(df)

            # save_data 返回保存的行数或 False
            if rows_saved and rows_saved > 0:
                self.logger.info(f"成功保存{rows_saved}条开放式基金日净值数据")
                return True
            else:
                self.logger.error("保存数据失败")
                return False

        except Exception as e:
            self.logger.error(f"执行失败: {e}", exc_info=True)
            return False
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = OpenFundDailyEm()
    data_updater.run()
