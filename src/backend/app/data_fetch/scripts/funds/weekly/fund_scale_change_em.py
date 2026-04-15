import logging

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundScaleChangeEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_SCALE_CHANGE_EM"
        self.create_table_sql = """
            CREATE TABLE `FUND_SCALE_CHANGE_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `REPORT_DATE` DATE NOT NULL COMMENT '截止日期',
                `FUND_COUNT` INT COMMENT '基金家数',
                `PURCHASE_AMOUNT` DECIMAL(20, 2) COMMENT '期间申购(亿份)',
                `REDEMPTION_AMOUNT` DECIMAL(20, 2) COMMENT '期间赎回(亿份)',
                `TOTAL_SHARES` DECIMAL(20, 2) COMMENT '期末总份额(亿份)',
                `TOTAL_NET_ASSETS` DECIMAL(20, 2) COMMENT '期末净资产(亿元)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_REPORT_DATE` (`REPORT_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金规模变动表(天天基金)';
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

    def fetch_scale_change(self):
        try:
            # 获取基金规模变动数据
            df = ak.fund_scale_change_em()

            if df is None or df.empty:
                self.logger.warning("No fund scale change data found")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "截止日期": "report_date_str",
                    "基金家数": "fund_count_str",
                    "期间申购": "purchase_amount_str",
                    "期间赎回": "redemption_amount_str",
                    "期末总份额": "total_shares_str",
                    "期末净资产": "total_net_assets_str",
                }
            )

            # 处理数据
            df["report_date"] = pd.to_datetime(df["report_date_str"]).dt.date
            df["fund_count"] = df["fund_count_str"].apply(self.parse_numeric).astype("Int64")
            df["purchase_amount"] = df["purchase_amount_str"].apply(self.parse_numeric)
            df["redemption_amount"] = df["redemption_amount_str"].apply(self.parse_numeric)
            df["total_shares"] = df["total_shares_str"].apply(self.parse_numeric)
            df["total_net_assets"] = df["total_net_assets_str"].apply(self.parse_numeric)

            # 生成唯一ID
            df["r_id"] = "FSCE_" + df["report_date"].astype(str).replace("-", "")

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "report_date",
                "fund_count",
                "purchase_amount",
                "redemption_amount",
                "total_shares",
                "total_net_assets",
            ]
            return df[columns].drop_duplicates()

        except Exception as e:
            self.logger.error(f"Error fetching fund scale change data: {e}")
            return pd.DataFrame()

    def save_scale_change(self, df):
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
                        "purchase_amount",
                        "redemption_amount",
                        "total_shares",
                        "total_net_assets",
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
                        SET fund_count=%s, purchase_amount=%s, redemption_amount=%s,
                            total_shares=%s, total_net_assets=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE r_id=%s
                        """,
                        (
                            row["fund_count"],
                            row["purchase_amount"],
                            row["redemption_amount"],
                            row["total_shares"],
                            row["total_net_assets"],
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
            self.logger.info("Starting fund scale change data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_scale_change()
            if not df.empty:
                return self.save_scale_change(df)
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

    fund_scale = FundScaleChangeEm(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_scale.run() else 1)
