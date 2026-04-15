import logging

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexGlobalHistSina(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_GLOBAL_HIST_SINA"
        self.valid_indices = self.get_indices()
        self.create_table_sql = """
            CREATE TABLE `INDEX_GLOBAL_HIST_SINA` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_NAME` VARCHAR(100) NOT NULL COMMENT '指数名称',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(20, 4) COMMENT '开盘价',
                `HIGH` DECIMAL(20, 4) COMMENT '最高价',
                `LOW` DECIMAL(20, 4) COMMENT '最低价',
                `CLOSE` DECIMAL(20, 4) COMMENT '收盘价',
                `VOLUME` BIGINT COMMENT '成交量',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '新浪财经-全球指数' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_NAME_DATE` (`INDEX_NAME`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='全球指数历史行情表(新浪财经)';
        """

    def get_indices(self):
        try:
            df = self.fetch_ak_data("index_global_name_table")
            return (
                df["指数名称"].drop_duplicates().tolist()
                if df is not None and not df.empty
                else ["道琼斯", "纳斯达克", "标普500"]
            )
        except Exception:
            # print(e)
            return ["道琼斯", "纳斯达克", "标普500"]

    def fetch_index_hist(self, index_name):
        try:
            df = self.fetch_ak_data("index_global_hist_sina", symbol=index_name)
            if df is None or df.empty:
                self.logger.warning(f"No data found for {index_name}")
                return pd.DataFrame()

            df = df.rename(
                columns={
                    "date": "TRADE_DATE_STR",
                    "open": "OPEN",
                    "high": "HIGH",
                    "low": "LOW",
                    "close": "CLOSE",
                    "volume": "VOLUME",
                }
            )

            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE_STR"]).dt.date
            df["VOLUME"] = (
                pd.to_numeric(df["VOLUME"].astype(str).str.replace(",", ""), errors="coerce")
                .fillna(0)
                .astype("int64")
            )

            for col in ["OPEN", "HIGH", "LOW", "CLOSE"]:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")

            df["INDEX_NAME"] = index_name
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["DATA_SOURCE"] = "新浪财经-全球指数"
            df["IS_ACTIVE"] = 1

            return df[
                [
                    "R_ID",
                    "INDEX_NAME",
                    "TRADE_DATE",
                    "OPEN",
                    "HIGH",
                    "LOW",
                    "CLOSE",
                    "VOLUME",
                    "IS_ACTIVE",
                    "DATA_SOURCE",
                ]
            ]

        except Exception as e:
            self.logger.error(f"Error fetching {index_name}: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, index_name=None):
        try:
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)

            indices = [index_name] if index_name else self.valid_indices
            all_success = True

            for idx in indices:
                try:
                    df = self.fetch_index_hist(idx)
                    if not df.empty:
                        success = self.save_data(
                            df=df.replace(np.nan, None),
                            table_name=self.table_name,
                            on_duplicate_update=True,
                            unique_keys=["INDEX_NAME", "TRADE_DATE"],
                        )
                        if success:
                            self.logger.info(f"Updated {len(df)} records for {idx}")
                        else:
                            all_success = False
                except Exception as e:
                    all_success = False
                    self.logger.error(f"Error processing {idx}: {str(e)}", exc_info=True)

            return all_success

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(
        description="Fetch historical global index data from Sina Finance"
    )
    parser.add_argument(
        "--index",
        type=str,
        required=False,
        help="指数名称，如：道琼斯, 纳斯达克, 标普500",
    )

    try:
        fetcher = IndexGlobalHistSina(logger=logging.getLogger(__name__))
        sys.exit(0 if fetcher.run(parser.parse_args().index) else 1)
    except Exception as e:
        logging.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
