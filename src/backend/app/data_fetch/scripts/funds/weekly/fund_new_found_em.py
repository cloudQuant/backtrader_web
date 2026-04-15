import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundNewFoundEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_NEW_FOUND_EM"
        self.create_table_sql = """
            CREATE TABLE `FUND_NEW_FOUND_EM` (
                `R_ID` VARCHAR(64) PRIMARY KEY,
                `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                `FUND_NAME` VARCHAR(200) COMMENT '基金简称',
                `COMPANY` VARCHAR(100) COMMENT '发行公司',
                `FUND_TYPE` VARCHAR(50) COMMENT '基金类型',
                `SUBSCRIPTION_PERIOD` VARCHAR(100) COMMENT '集中认购期',
                `RAISED_AMOUNT` DECIMAL(20, 4) COMMENT '募集份额(亿份)',
                `ESTABLISH_DATE` DATE COMMENT '成立日期',
                `RETURN_SINCE_ESTABLISH` FLOAT COMMENT '成立来涨幅(%)',
                `MANAGER` VARCHAR(200) COMMENT '基金经理',
                `SUBSCRIPTION_STATUS` VARCHAR(50) COMMENT '申购状态',
                `PREFERENTIAL_RATE` FLOAT COMMENT '优惠费率(%)',
                `UPDATE_DATE` DATE COMMENT '更新日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_FUND_CODE` (`FUND_CODE`),
                KEY `IDX_COMPANY` (`COMPANY`),
                KEY `IDX_FUND_TYPE` (`FUND_TYPE`),
                KEY `IDX_ESTABLISH_DATE` (`ESTABLISH_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新发基金信息表(天天基金)';
        """

    def parse_date(self, date_str):
        try:
            return (
                datetime.strptime(date_str, "%Y-%m-%d").date()
                if date_str and pd.notna(date_str)
                else None
            )
        except (ValueError, TypeError):
            return None

    def fetch_new_funds(self):
        try:
            # 获取新发基金数据
            df = ak.fund_new_found_em()

            if df is None or df.empty:
                self.logger.warning("No new fund data found")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "基金代码": "fund_code",
                    "基金简称": "fund_name",
                    "发行公司": "company",
                    "基金类型": "fund_type",
                    "集中认购期": "subscription_period",
                    "募集份额": "raised_amount",
                    "成立日期": "establish_date_str",
                    "成立来涨幅": "return_since_establish",
                    "基金经理": "manager",
                    "申购状态": "subscription_status",
                    "优惠费率": "preferential_rate",
                }
            )

            # 处理数据
            df["establish_date"] = df["establish_date_str"].apply(self.parse_date)
            df["update_date"] = datetime.now().date()
            df["r_id"] = "FNFE_" + df["fund_code"]

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "fund_name",
                "company",
                "fund_type",
                "subscription_period",
                "raised_amount",
                "establish_date",
                "return_since_establish",
                "manager",
                "subscription_status",
                "preferential_rate",
                "update_date",
            ]
            return df[columns]

        except Exception as e:
            self.logger.error(f"Error fetching new fund data: {e}")
            return pd.DataFrame()

    def save_fund_data(self, df):
        if df.empty:
            self.logger.warning("No data to save")
            return False

        try:
            # 获取已存在的数据ID
            existing_ids = {
                row[0]
                for row in self.query_data(
                    f"SELECT r_id FROM {self.table_name} WHERE is_active = 1"  # nosec B608
                )
                or []
            }

            # 插入新数据
            new_data = df[~df["r_id"].isin(existing_ids)]
            if not new_data.empty:
                self.insert_data(
                    new_data,
                    self.table_name,
                    [
                        "r_id",
                        "fund_code",
                        "fund_name",
                        "company",
                        "fund_type",
                        "subscription_period",
                        "raised_amount",
                        "establish_date",
                        "return_since_establish",
                        "manager",
                        "subscription_status",
                        "preferential_rate",
                        "update_date",
                    ],
                )
                self.logger.info(f"Inserted {len(new_data)} new records")

            # 更新已有数据
            updated_data = df[df["r_id"].isin(existing_ids)]
            if not updated_data.empty:
                for _, row in updated_data.iterrows():
                    self.execute_sql(
                        f"""  # nosec B608
                        UPDATE {self.table_name}
                        SET fund_name=%s, company=%s, fund_type=%s,
                            subscription_period=%s, raised_amount=%s, establish_date=%s,
                            return_since_establish=%s, manager=%s, subscription_status=%s,
                            preferential_rate=%s, update_date=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE r_id=%s
                        """,
                        (
                            row["fund_name"],
                            row["company"],
                            row["fund_type"],
                            row["subscription_period"],
                            row["raised_amount"],
                            row["establish_date"],
                            row["return_since_establish"],
                            row["manager"],
                            row["subscription_status"],
                            row["preferential_rate"],
                            row["update_date"],
                            row["r_id"],
                        ),
                    )
                self.logger.info(f"Updated {len(updated_data)} records")

            return True

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def run(self):
        try:
            self.logger.info("Starting new fund data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_new_funds()
            if not df.empty:
                return self.save_fund_data(df)
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

    fund_new = FundNewFoundEm(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_new.run() else 1)
