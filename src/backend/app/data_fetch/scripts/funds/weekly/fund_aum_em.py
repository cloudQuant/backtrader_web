import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundAumEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_AUM_EM"
        self.create_table_sql = """
            CREATE TABLE `FUND_AUM_EM` (
                `R_ID` VARCHAR(64) PRIMARY KEY,
                `COMPANY_NAME` VARCHAR(100) NOT NULL COMMENT '基金公司',
                `ESTABLISH_DATE` DATE COMMENT '成立日期',
                `TOTAL_AUM` DECIMAL(20, 2) COMMENT '全部管理规模(亿元)',
                `TOTAL_FUNDS` INT COMMENT '全部基金数',
                `TOTAL_MANAGERS` INT COMMENT '全部经理数',
                `UPDATE_DATE_STR` VARCHAR(10) COMMENT '更新日期字符串',
                `UPDATE_DATE` DATE COMMENT '更新日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_COMPANY_NAME` (`COMPANY_NAME`),
                KEY `IDX_ESTABLISH_DATE` (`ESTABLISH_DATE`),
                KEY `IDX_UPDATE_DATE` (`UPDATE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金公司规模表(天天基金)';
        """

    def parse_date(self, date_str, format_str="%Y-%m-%d"):
        try:
            if pd.isna(date_str) or date_str == "":
                return None
            import datetime as dt_mod

            if isinstance(date_str, dt_mod.date):
                return date_str
            return datetime.strptime(str(date_str), format_str).date()
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Error parsing date {date_str}: {e}")
            return None

    def parse_update_date(self, date_str):
        """处理更新日期，格式为MM-DD，需要补充年份"""
        try:
            if pd.isna(date_str) or date_str == "":
                return None, None

            # 获取当前年份
            current_year = datetime.now().year
            full_date_str = f"{current_year}-{date_str}"

            # 解析日期
            update_date = self.parse_date(full_date_str, "%Y-%m-%d")

            # 如果解析出的日期在将来，则使用去年
            if update_date and update_date > datetime.now().date():
                full_date_str = f"{current_year - 1}-{date_str}"
                update_date = self.parse_date(full_date_str, "%Y-%m-%d")

            return date_str, update_date
        except Exception as e:
            self.logger.warning(f"Error parsing update date {date_str}: {e}")
            return date_str, None

    def fetch_aum_data(self):
        try:
            # 获取基金规模数据
            df = ak.fund_aum_em()

            if df is None or df.empty:
                self.logger.warning("No fund AUM data found")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "基金公司": "company_name",
                    "成立时间": "establish_date_str",
                    "全部管理规模": "total_aum",
                    "全部基金数": "total_funds",
                    "全部经理数": "total_managers",
                    "更新日期": "update_date_str",
                }
            )

            # 处理数据
            df["establish_date"] = df["establish_date_str"].apply(
                lambda x: self.parse_date(x, "%Y-%m-%d")
            )

            # 处理更新日期
            df[["update_date_str", "update_date"]] = df["update_date_str"].apply(
                lambda x: pd.Series(self.parse_update_date(x))
            )

            # 生成唯一ID
            df["R_ID"] = "FAE_" + df["company_name"].str[:20].str.upper()

            # 选择需要的列并重新排序
            columns = [
                "R_ID",
                "company_name",
                "establish_date",
                "total_aum",
                "total_funds",
                "total_managers",
                "update_date_str",
                "update_date",
            ]
            return df[columns]

        except Exception as e:
            self.logger.error(f"Error fetching fund AUM data: {e}")
            return pd.DataFrame()

    def save_aum_data(self, df):
        if df.empty:
            self.logger.warning("No data to save")
            return False

        try:
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
                        "company_name",
                        "establish_date",
                        "total_aum",
                        "total_funds",
                        "total_managers",
                        "update_date_str",
                        "update_date",
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
                        SET establish_date=%s, total_aum=%s, total_funds=%s,
                            total_managers=%s, update_date_str=%s, update_date=%s,
                            updatedate=CURRENT_TIMESTAMP
                        WHERE R_ID=%s
                        """,
                        (
                            row["establish_date"],
                            row["total_aum"],
                            row["total_funds"],
                            row["total_managers"],
                            row["update_date_str"],
                            row["update_date"],
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
            self.logger.info("Starting fund AUM data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_aum_data()
            if not df.empty:
                return self.save_aum_data(df)
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

    fund_aum = FundAumEm(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_aum.run() else 1)
