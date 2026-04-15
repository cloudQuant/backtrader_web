import logging

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundHoldStructureEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_HOLD_STRUCTURE_EM"
        self.create_table_sql = """
            CREATE TABLE `FUND_HOLD_STRUCTURE_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `REPORT_DATE` DATE NOT NULL COMMENT '截止日期',
                `FUND_COUNT` INT COMMENT '基金家数',
                `INSTITUTION_RATIO` DECIMAL(10, 4) COMMENT '机构持有比例(%)',
                `INDIVIDUAL_RATIO` DECIMAL(10, 4) COMMENT '个人持有比例(%)',
                `INTERNAL_RATIO` DECIMAL(10, 4) COMMENT '内部持有比例(%)',
                `TOTAL_SHARES` DECIMAL(20, 2) COMMENT '总份额(亿份)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_REPORT_DATE` (`REPORT_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金持有人结构表(天天基金)';
        """

    def parse_numeric(self, value):
        """Convert string to float, handling None and empty strings"""
        try:
            if pd.isna(value) or value == "":
                return None
            return float(str(value).replace(",", ""))
        except Exception as e:
            self.logger.warning(f"Error parsing numeric value {value}: {e}")
            return None

    def fetch_hold_structure(self):
        try:
            # 获取基金持有人结构数据
            df = ak.fund_hold_structure_em()

            if df is None or df.empty:
                self.logger.warning("No fund holder structure data found")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "截止日期": "report_date_str",
                    "基金家数": "fund_count_str",
                    "机构持有比列": "institution_ratio_str",
                    "个人持有比列": "individual_ratio_str",
                    "内部持有比列": "internal_ratio_str",
                    "总份额": "total_shares_str",
                }
            )

            # 处理数据
            df["report_date"] = pd.to_datetime(df["report_date_str"]).dt.date
            df["fund_count"] = df["fund_count_str"].apply(self.parse_numeric).astype("Int64")
            df["institution_ratio"] = df["institution_ratio_str"].apply(self.parse_numeric)
            df["individual_ratio"] = df["individual_ratio_str"].apply(self.parse_numeric)
            df["internal_ratio"] = df["internal_ratio_str"].apply(self.parse_numeric)
            df["total_shares"] = df["total_shares_str"].apply(self.parse_numeric)

            # 生成唯一ID
            df["r_id"] = "FHSE_" + df["report_date"].astype(str).replace("-", "")

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "report_date",
                "fund_count",
                "institution_ratio",
                "individual_ratio",
                "internal_ratio",
                "total_shares",
            ]
            return df[columns].drop_duplicates()

        except Exception as e:
            self.logger.error(f"Error fetching fund holder structure data: {e}")
            return pd.DataFrame()

    def save_hold_structure(self, df):
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
                        "report_date",
                        "fund_count",
                        "institution_ratio",
                        "individual_ratio",
                        "internal_ratio",
                        "total_shares",
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
                        SET fund_count=%s, institution_ratio=%s, individual_ratio=%s,
                            internal_ratio=%s, total_shares=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE r_id=%s
                        """,
                        (
                            row["fund_count"],
                            row["institution_ratio"],
                            row["individual_ratio"],
                            row["internal_ratio"],
                            row["total_shares"],
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
            self.logger.info("Starting fund holder structure data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_hold_structure()
            if not df.empty:
                return self.save_hold_structure(df)
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

    fund_hold = FundHoldStructureEm(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_hold.run() else 1)
