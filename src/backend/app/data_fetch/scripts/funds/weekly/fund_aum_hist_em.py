import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FundAumHistEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUND_AUM_HIST_EM"
        self.create_table_sql = """
            CREATE TABLE `FUND_AUM_HIST_EM` (
                `R_ID` VARCHAR(64) PRIMARY KEY,
                `YEAR` INT NOT NULL COMMENT '年份',
                `COMPANY_NAME` VARCHAR(100) NOT NULL COMMENT '基金公司',
                `TOTAL_AUM` DECIMAL(20, 2) COMMENT '总规模(亿元)',
                `STOCK_AUM` DECIMAL(20, 2) COMMENT '股票型(亿元)',
                `MIXED_AUM` DECIMAL(20, 2) COMMENT '混合型(亿元)',
                `BOND_AUM` DECIMAL(20, 2) COMMENT '债券型(亿元)',
                `INDEX_AUM` DECIMAL(20, 2) COMMENT '指数型(亿元)',
                `QDII_AUM` DECIMAL(20, 2) COMMENT 'QDII(亿元)',
                `MONEY_AUM` DECIMAL(20, 2) COMMENT '货币型(亿元)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '天天基金' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_YEAR_COMPANY` (`YEAR`, `COMPANY_NAME`),
                KEY `IDX_YEAR` (`YEAR`),
                KEY `IDX_COMPANY` (`COMPANY_NAME`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基金公司历年管理规模表(天天基金)';
        """

    def fetch_aum_hist(self, year=None):
        try:
            # 如果未指定年份，默认为当前年份
            if year is None:
                year = datetime.now().year

            # 获取基金公司历年管理规模数据
            df = ak.fund_aum_hist_em(year=str(year))

            if df is None or df.empty:
                self.logger.warning(f"No fund AUM historical data found for year {year}")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "基金公司": "company_name",
                    "总规模": "total_aum",
                    "股票型": "stock_aum",
                    "混合型": "mixed_aum",
                    "债券型": "bond_aum",
                    "指数型": "index_aum",
                    "QDII": "qdii_aum",
                    "货币型": "money_aum",
                }
            )

            # 添加年份列
            df["year"] = int(year)

            # 处理数据中的NaN值
            for col in [
                "total_aum",
                "stock_aum",
                "mixed_aum",
                "bond_aum",
                "index_aum",
                "qdii_aum",
                "money_aum",
            ]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # 生成唯一ID
            df["r_id"] = (
                "FAHE_" + df["year"].astype(str) + "_" + df["company_name"].str[:30].str.upper()
            )

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "year",
                "company_name",
                "total_aum",
                "stock_aum",
                "mixed_aum",
                "bond_aum",
                "index_aum",
                "qdii_aum",
                "money_aum",
            ]
            return df[columns]

        except Exception as e:
            self.logger.error(f"Error fetching fund AUM historical data: {e}")
            return pd.DataFrame()

    def save_aum_hist(self, df):
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
                        "year",
                        "company_name",
                        "total_aum",
                        "stock_aum",
                        "mixed_aum",
                        "bond_aum",
                        "index_aum",
                        "qdii_aum",
                        "money_aum",
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
                        SET total_aum=%s, stock_aum=%s, mixed_aum=%s,
                            bond_aum=%s, index_aum=%s, qdii_aum=%s,
                            money_aum=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE r_id=%s
                        """,
                        (
                            row["total_aum"],
                            row["stock_aum"],
                            row["mixed_aum"],
                            row["bond_aum"],
                            row["index_aum"],
                            row["qdii_aum"],
                            row["money_aum"],
                            row["r_id"],
                        ),
                    )
                self.logger.info(f"Updated {len(updated_data)} records")

            return True

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def run(self, year=None):
        try:
            self.logger.info("Starting fund AUM historical data update")
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            df = self.fetch_aum_hist(year)
            if not df.empty:
                return self.save_aum_hist(df)
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

    parser = argparse.ArgumentParser(description="Fetch fund AUM historical data by year")
    parser.add_argument(
        "-y", "--year", type=int, help="Year to fetch data for (default: current year)"
    )
    args = parser.parse_args()

    fund_aum_hist = FundAumHistEm(logger=logging.getLogger(__name__))
    sys.exit(0 if fund_aum_hist.run(args.year) else 1)
