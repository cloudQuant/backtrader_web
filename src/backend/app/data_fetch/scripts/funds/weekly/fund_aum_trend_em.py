import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundAumTrendEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_AUM_TREND_EM"
        self.create_table_sql = """
            CREATE TABLE `FUND_AUM_TREND_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `RECORD_DATE` DATE NOT NULL COMMENT '记录日期',
                `AUM` DECIMAL(20, 2) COMMENT '基金规模(元)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_RECORD_DATE` (`RECORD_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金规模走势表(天天基金)';
        """

    def parse_date(self, date_str):
        try:
            import datetime as dt_mod

            if isinstance(date_str, dt_mod.date):
                return date_str
            return datetime.strptime(str(date_str), "%Y-%m-%d").date()
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Error parsing date {date_str}: {e}")
            return None

    # pylint: disable=E1137,E1136
    def fetch_aum_trend(self):
        try:
            # 获取基金规模走势数据
            df = ak.fund_aum_trend_em()

            if df is None or df.empty:
                self.logger.warning("No fund AUM trend data found")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(columns={"date": "record_date_str", "value": "aum"})

            # 处理数据
            df["record_date"] = df["record_date_str"].apply(self.parse_date)
            df["r_id"] = "FATE_" + df["record_date"].astype(str).str.replace("-", "")

            # 选择需要的列并重新排序
            columns = ["r_id", "record_date", "aum"]
            return df[columns]

        except Exception as e:
            self.logger.error(f"Error fetching fund AUM trend data: {e}")
            return pd.DataFrame()

    def save_aum_trend(self, df):
        if df.empty:
            self.logger.warning("No data to save")
            return False

        try:
            # 获取已存在的数据日期
            existing_dates = {
                row[0]
                for row in self.query_data(
                    f"SELECT record_date FROM {self.table_name} WHERE is_active = 1"  # nosec B608
                )
                or []
            }

            # 插入新数据
            new_data = df[~df["record_date"].isin(existing_dates)]
            if not new_data.empty:
                self.insert_data(
                    new_data,
                    self.table_name,
                    [
                        "r_id",
                        "record_date",
                        "aum",
                    ],
                )
                self.logger.info(f"Inserted {len(new_data)} new records")

            # 更新已有数据
            updated_data = df[df["record_date"].isin(existing_dates)]
            if not updated_data.empty:
                for _, row in updated_data.iterrows():
                    self.execute_sql(
                        f"""  # nosec B608
                        UPDATE {self.table_name}
                        SET aum=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE record_date=%s
                        """,
                        (row["aum"], row["record_date"]),
                    )
                self.logger.info(f"Updated {len(updated_data)} records")

            return True

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def run(self):
        try:
            self.logger.info("Starting fund AUM trend data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_aum_trend()
            if not df.empty:
                return self.save_aum_trend(df)
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

    fund_aum_trend = FundAumTrendEm(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_aum_trend.run() else 1)
