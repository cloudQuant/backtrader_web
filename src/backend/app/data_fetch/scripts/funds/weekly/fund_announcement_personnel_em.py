import logging

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundAnnouncementPersonnelEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_ANNOUNCEMENT_PERSONNEL_EM"
        self.create_table_sql = """
            CREATE TABLE `FUND_ANNOUNCEMENT_PERSONNEL_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `FUND_CODE` VARCHAR(10) NOT NULL COMMENT '基金代码',
                `FUND_NAME` VARCHAR(100) COMMENT '基金名称',
                `ANNOUNCEMENT_TITLE` VARCHAR(255) COMMENT '公告标题',
                `ANNOUNCEMENT_DATE` DATE COMMENT '公告日期',
                `REPORT_ID` VARCHAR(50) COMMENT '报告ID',
                `ANNOUNCEMENT_URL` VARCHAR(255) COMMENT '公告URL',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_REPORT_ID` (`REPORT_ID`),
                KEY `IDX_FUND_CODE` (`FUND_CODE`),
                KEY `IDX_ANNOUNCEMENT_DATE` (`ANNOUNCEMENT_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金人事公告表(东方财富)';
        """

    def fetch_personnel_announcements(self, symbol):
        try:
            # 获取基金人事公告数据
            df = ak.fund_announcement_personnel_em(symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No personnel announcements found for fund {symbol}")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "基金代码": "fund_code",
                    "公告标题": "announcement_title",
                    "基金名称": "fund_name",
                    "公告日期": "announcement_date_str",
                    "报告ID": "report_id",
                }
            )

            # 处理数据
            df["announcement_date"] = pd.to_datetime(df["announcement_date_str"]).dt.date
            df["announcement_url"] = df["report_id"].apply(
                lambda x: f"http://fundf10.eastmoney.com/jjgg_{symbol}_4_{x}.html"
            )

            # 生成唯一ID
            df["r_id"] = "FAPE_" + df["report_id"]

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "fund_code",
                "fund_name",
                "announcement_title",
                "announcement_date",
                "report_id",
                "announcement_url",
            ]
            return df[columns].drop_duplicates()

        except Exception as e:
            self.logger.error(f"Error fetching personnel announcements for fund {symbol}: {e}")
            return pd.DataFrame()

    def save_personnel_announcements(self, df):
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
                        "announcement_title",
                        "announcement_date",
                        "report_id",
                        "announcement_url",
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
                        SET fund_name=%s, announcement_title=%s, announcement_date=%s,
                            announcement_url=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE r_id=%s
                        """,
                        (
                            row["fund_name"],
                            row["announcement_title"],
                            row["announcement_date"],
                            row["announcement_url"],
                            row["r_id"],
                        ),
                    )
                self.logger.info(f"Updated {len(updated_data)} records")

            return True

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def run(self, symbol=None):
        try:
            self.logger.info(f"Starting personnel announcements update for fund {symbol}")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_personnel_announcements(symbol)
            if not df.empty:
                return self.save_personnel_announcements(df)
            return False

        except Exception as e:
            self.logger.error(f"Error in run: {e}")
            return False


if __name__ == "__main__":
    import argparse
    import logging
    import sys

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Fetch fund personnel announcements")
    parser.add_argument("--symbol", type=str, required=True, help="基金代码")

    try:
        args = parser.parse_args()
        fund_announcement = FundAnnouncementPersonnelEm(logger=logging.getLogger(__name__))
        sys.exit(0 if fund_announcement.run(args.symbol) else 1)
    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)
