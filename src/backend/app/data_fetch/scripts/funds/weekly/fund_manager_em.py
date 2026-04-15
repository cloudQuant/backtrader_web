import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundManagerEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_MANAGER_EM"
        self.create_table_sql = """
            CREATE TABLE `FUND_MANAGER_EM` (
                `R_ID` VARCHAR(64) PRIMARY KEY,
                `MANAGER_ID` INT COMMENT '基金经理ID',
                `MANAGER_NAME` VARCHAR(50) NOT NULL COMMENT '基金经理姓名',
                `COMPANY` VARCHAR(100) COMMENT '所属公司',
                `FUND_CODE` VARCHAR(20) COMMENT '基金代码',
                `FUND_NAME` VARCHAR(200) COMMENT '基金名称',
                `WORK_DAYS` INT COMMENT '累计从业时间(天)',
                `TOTAL_ASSETS` DECIMAL(20, 2) COMMENT '现任基金资产总规模(亿元)',
                `BEST_RETURN` FLOAT COMMENT '现任基金最佳回报(%)',
                `UPDATE_DATE` DATE COMMENT '更新日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_MANAGER_FUND` (`MANAGER_ID`, `FUND_CODE`),
                KEY `IDX_MANAGER_NAME` (`MANAGER_NAME`),
                KEY `IDX_COMPANY` (`COMPANY`),
                KEY `IDX_FUND_CODE` (`FUND_CODE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金经理信息表(天天基金)';
        """

    def extract_fund_code(self, fund_name):
        """从基金名称中提取基金代码"""
        import re

        match = re.search(r"\d{6}", fund_name)
        return match.group(0) if match else ""

    def fetch_manager_data(self):
        try:
            # 获取原始数据
            df = ak.fund_manager_em()

            if df is None or df.empty:
                self.logger.warning("No fund manager data found")
                return pd.DataFrame()

            # 重命名列 (use uppercase to match database schema)
            df = df.rename(
                columns={
                    "序号": "MANAGER_ID",
                    "姓名": "MANAGER_NAME",
                    "所属公司": "COMPANY",
                    "现任基金": "FUND_NAME",
                    "现任基金代码": "FUND_CODE",  # Use the fund code column directly
                    "累计从业时间": "WORK_DAYS",
                    "现任基金资产总规模": "TOTAL_ASSETS",
                    "现任基金最佳回报": "BEST_RETURN",
                }
            )

            # If FUND_CODE column doesn't exist (API change), try to extract from fund name
            if "FUND_CODE" not in df.columns:
                df["FUND_CODE"] = df["FUND_NAME"].apply(self.extract_fund_code)

            # 添加系统字段
            df["UPDATE_DATE"] = datetime.now().date()
            df["R_ID"] = (
                "FME_" + df["MANAGER_ID"].astype(str) + "_" + df["FUND_CODE"].fillna("").astype(str)
            )

            # 选择需要的列并重新排序
            columns = [
                "R_ID",
                "MANAGER_ID",
                "MANAGER_NAME",
                "COMPANY",
                "FUND_CODE",
                "FUND_NAME",
                "WORK_DAYS",
                "TOTAL_ASSETS",
                "BEST_RETURN",
                "UPDATE_DATE",
            ]
            # Only keep columns that exist
            available_columns = [c for c in columns if c in df.columns]
            return df[available_columns]

        except Exception as e:
            self.logger.error(f"Error fetching fund manager data: {e}")
            return pd.DataFrame()

    def save_manager_data(self, df):
        if df.empty:
            self.logger.warning("No data to save")
            return False

        try:
            # Normalize df column names to uppercase to match database schema
            df.columns = [c.upper() for c in df.columns]

            # Add system fields that have defaults in DB
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "天天基金"

            # 获取已存在的数据ID
            existing_ids = {
                row[0]
                for row in self.query_data(
                    f"SELECT R_ID FROM {self.table_name} WHERE IS_ACTIVE = 1"  # nosec B608
                )
                or []
            }

            # 插入新数据
            new_data = df[~df["R_ID"].isin(existing_ids)]
            if not new_data.empty:
                self.insert_data(
                    new_data,
                    self.table_name,
                    [
                        "R_ID",
                        "MANAGER_ID",
                        "MANAGER_NAME",
                        "COMPANY",
                        "FUND_CODE",
                        "FUND_NAME",
                        "WORK_DAYS",
                        "TOTAL_ASSETS",
                        "BEST_RETURN",
                        "UPDATE_DATE",
                        "IS_ACTIVE",
                        "DATA_SOURCE",
                    ],
                )
                self.logger.info(f"Inserted {len(new_data)} new records")

            # 更新已有数据
            updated_data = df[df["R_ID"].isin(existing_ids)]
            if not updated_data.empty:
                for _, row in updated_data.iterrows():
                    self.execute_sql(
                        f"""  # nosec B608
                        UPDATE {self.table_name}
                        SET MANAGER_NAME=%s, COMPANY=%s, FUND_NAME=%s,
                            WORK_DAYS=%s, TOTAL_ASSETS=%s, BEST_RETURN=%s,
                            UPDATE_DATE=%s, UPDATEDATE=CURRENT_TIMESTAMP
                        WHERE R_ID=%s
                        """,
                        (
                            row["MANAGER_NAME"],
                            row["COMPANY"],
                            row["FUND_NAME"],
                            row["WORK_DAYS"],
                            row["TOTAL_ASSETS"],
                            row["BEST_RETURN"],
                            row["UPDATE_DATE"],
                            row["R_ID"],
                        ),
                    )
                self.logger.info(f"Updated {len(updated_data)} records")

            return True

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def run(self):
        try:
            self.logger.info("Starting fund manager data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_manager_data()
            if not df.empty:
                return self.save_manager_data(df)
            return False

        except Exception as e:
            self.logger.error(f"Error in run: {e}")
            return False


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    fund_manager = FundManagerEm(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_manager.run() else 1)
