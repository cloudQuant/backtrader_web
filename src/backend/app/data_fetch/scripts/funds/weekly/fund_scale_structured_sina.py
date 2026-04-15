import logging

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundScaleStructuredSina(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_SCALE_STRUCTURED_SINA"
        self.create_table_sql = """
            CREATE TABLE `FUND_SCALE_STRUCTURED_SINA` (
                `R_ID` VARCHAR(64) PRIMARY KEY,
                `FUND_CODE` VARCHAR(20) NOT NULL COMMENT '基金代码',
                `FUND_NAME` VARCHAR(200) COMMENT '基金简称',
                `NAV` DECIMAL(10, 4) COMMENT '单位净值(元)',
                `TOTAL_RAISED` DECIMAL(20, 2) COMMENT '总募集规模(万份)',
                `TOTAL_SHARES` DECIMAL(20, 2) COMMENT '最近总份额(份)',
                `ESTABLISH_DATE` DATE COMMENT '成立日期',
                `MANAGER` VARCHAR(200) COMMENT '基金经理',
                `UPDATE_DATE` DATE COMMENT '更新日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '新浪财经' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_FUND_CODE` (`FUND_CODE`),
                KEY `IDX_ESTABLISH_DATE` (`ESTABLISH_DATE`),
                KEY `IDX_UPDATE_DATE` (`UPDATE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分级子基金规模表(新浪财经)';
        """

    def parse_date(self, date_str):
        try:
            if pd.isna(date_str) or date_str == "":
                return None
            return pd.to_datetime(date_str).date()
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Error parsing date {date_str}: {e}")
            return None

    def fetch_fund_scale(self):
        try:
            # 获取分级子基金规模数据
            df = ak.fund_scale_structured_sina()

            if df is None or df.empty:
                self.logger.warning("No structured fund data found")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "基金代码": "fund_code",
                    "基金简称": "fund_name",
                    "单位净值": "nav",
                    "总募集规模": "total_raised",
                    "最近总份额": "total_shares",
                    "成立日期": "establish_date_str",
                    "基金经理": "manager",
                    "更新日期": "update_date_str",
                }
            )

            # 处理数据
            df["establish_date"] = df["establish_date_str"].apply(self.parse_date)
            df["update_date"] = df["update_date_str"].apply(self.parse_date)
            df["r_id"] = "FSSS_" + df["fund_code"].astype(str)

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "fund_name",
                "nav",
                "total_raised",
                "total_shares",
                "establish_date",
                "manager",
                "update_date",
            ]
            return df[columns]

        except Exception as e:
            self.logger.error(f"Error fetching structured fund scale data: {e}")
            return pd.DataFrame()

    def save_fund_scale(self, df):
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
                        "nav",
                        "total_raised",
                        "total_shares",
                        "establish_date",
                        "manager",
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
                        SET fund_name=%s, nav=%s, total_raised=%s,
                            total_shares=%s, establish_date=%s, manager=%s,
                            update_date=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE r_id=%s
                        """,
                        (
                            row["fund_name"],
                            row["nav"],
                            row["total_raised"],
                            row["total_shares"],
                            row["establish_date"],
                            row["manager"],
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
            self.logger.info("Starting structured fund scale data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_fund_scale()
            if not df.empty:
                return self.save_fund_scale(df)
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

    fund_scale = FundScaleStructuredSina(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_scale.run() else 1)
