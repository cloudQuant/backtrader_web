import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundRatingZs(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_RATING_ZS"
        self.create_table_sql = """
            CREATE TABLE `FUND_RATING_ZS` (
                `R_ID` VARCHAR(64) PRIMARY KEY,
                `FUND_CODE` VARCHAR(20) NOT NULL,
                `FUND_NAME` VARCHAR(100),
                `FUND_MANAGER` VARCHAR(100),
                `FUND_COMPANY` VARCHAR(100),
                `RATING_3Y` INT,
                `RATING_3Y_CHANGE` FLOAT,
                `UNIT_NAV` FLOAT,
                `NAV_DATE` DATE,
                `DAILY_RETURN` FLOAT,
                `RETURN_1Y` FLOAT,
                `RETURN_3Y` FLOAT,
                `RETURN_5Y` FLOAT,
                `FEE_RATE` FLOAT,
                `UPDATE_DATE` DATE,
                `IS_ACTIVE` TINYINT(1) DEFAULT 1,
                `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `CREATEUSER` VARCHAR(50) DEFAULT 'system',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system',
                UNIQUE KEY `IDX_FUND_RATING_ZS` (`FUND_CODE`, `NAV_DATE`),
                KEY `IDX_FUND_CODE` (`FUND_CODE`),
                KEY `IDX_NAV_DATE` (`NAV_DATE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='招商证券基金评级表';
        """

    def parse_fee_rate(self, fee_str):
        try:
            return float(fee_str.rstrip("%")) / 100 if fee_str and pd.notna(fee_str) else None
        except (ValueError, AttributeError):
            return None

    def parse_date(self, date_str):
        try:
            import datetime as dt_mod

            if isinstance(date_str, dt_mod.date):
                return date_str
            return datetime.strptime(str(date_str), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def fetch_rating_data(self, date=None):
        try:
            if date:
                df = ak.fund_rating_zs(date=date)
            else:
                df = ak.fund_rating_zs()

            if df is None or df.empty:
                self.logger.warning(f"No data found for date: {date}")
                return pd.DataFrame()

            # Process columns
            df = df.rename(
                columns={
                    "代码": "fund_code",
                    "简称": "fund_name",
                    "基金经理": "fund_manager",
                    "基金公司": "fund_company",
                    "3年期评级-3年评级": "rating_3y",
                    "3年期评级-较上期": "rating_3y_change",
                    "单位净值": "unit_nav",
                    "日期": "nav_date_str",
                    "日增长率": "daily_return",
                    "近1年涨幅": "return_1y",
                    "近3年涨幅": "return_3y",
                    "近5年涨幅": "return_5y",
                    "手续费": "fee_rate_str",
                }
            )

            # Process data
            df["nav_date"] = df["nav_date_str"].apply(self.parse_date)
            df["fee_rate"] = df["fee_rate_str"].apply(self.parse_fee_rate)
            df["update_date"] = datetime.now().date()
            df["r_id"] = "FRZS_" + df["fund_code"] + "_" + df["nav_date"].astype(str)

            return df[
                [
                    "r_id",
                    "fund_code",
                    "fund_name",
                    "fund_manager",
                    "fund_company",
                    "rating_3y",
                    "rating_3y_change",
                    "unit_nav",
                    "nav_date",
                    "daily_return",
                    "return_1y",
                    "return_3y",
                    "return_5y",
                    "fee_rate",
                    "update_date",
                ]
            ]

        except Exception as e:
            self.logger.error(f"Error fetching rating data: {e}")
            return pd.DataFrame()

    def save_rating_data(self, df):
        if df.empty:
            self.logger.warning("No data to save")
            return False

        try:
            # Get existing IDs
            existing_ids = {
                row[0]
                for row in self.query_data(
                    f"SELECT r_id FROM {self.table_name} WHERE is_active = 1"  # nosec B608
                )
                or []
            }

            # Insert new data
            new_data = df[~df["r_id"].isin(existing_ids)]
            if not new_data.empty:
                self.insert_data(
                    new_data,
                    self.table_name,
                    [
                        "r_id",
                        "fund_code",
                        "fund_name",
                        "fund_manager",
                        "fund_company",
                        "rating_3y",
                        "rating_3y_change",
                        "unit_nav",
                        "nav_date",
                        "daily_return",
                        "return_1y",
                        "return_3y",
                        "return_5y",
                        "fee_rate",
                        "update_date",
                    ],
                )
                self.logger.info(f"Inserted {len(new_data)} new records")

            # Update existing data
            updated_data = df[df["r_id"].isin(existing_ids)]
            if not updated_data.empty:
                for _, row in updated_data.iterrows():
                    self.execute_sql(
                        f"""  # nosec B608
                        UPDATE {self.table_name}
                        SET fund_name=%s, fund_manager=%s, fund_company=%s, rating_3y=%s,
                            rating_3y_change=%s, unit_nav=%s, nav_date=%s, daily_return=%s,
                            return_1y=%s, return_3y=%s, return_5y=%s, fee_rate=%s,
                            update_date=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE r_id=%s
                        """,
                        (
                            row["fund_name"],
                            row["fund_manager"],
                            row["fund_company"],
                            row["rating_3y"],
                            row["rating_3y_change"],
                            row["unit_nav"],
                            row["nav_date"],
                            row["daily_return"],
                            row["return_1y"],
                            row["return_3y"],
                            row["return_5y"],
                            row["fee_rate"],
                            row["update_date"],
                            row["r_id"],
                        ),
                    )
                self.logger.info(f"Updated {len(updated_data)} records")

            return True

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def run(self, date=None):
        try:
            self.logger.info(f"Starting fund rating update for date: {date or 'current'}")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_rating_data(date)
            if not df.empty:
                return self.save_rating_data(df)
            return False

        except Exception as e:
            self.logger.error(f"Error in run: {e}")
            return False


if __name__ == "__main__":
    import argparse
    import logging
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(description="Fetch China Merchants Securities fund ratings")
    parser.add_argument("-d", "--date", help="Rating date in YYYYMMDD format")
    args = parser.parse_args()

    fund_rating = FundRatingZs(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_rating.run(args.date) else 1)
