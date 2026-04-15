from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockZhIndexSpotEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_ZH_INDEX_SPOT_EM"
        self.create_table_sql = """
            CREATE TABLE `STOCK_ZH_INDEX_SPOT_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `INDEX_NAME` VARCHAR(100) COMMENT '指数名称',
                `LATEST_PRICE` DECIMAL(20, 4) COMMENT '最新价',
                `CHANGE_AMOUNT` DECIMAL(20, 4) COMMENT '涨跌额',
                `CHANGE_PERCENT` DECIMAL(10, 4) COMMENT '涨跌幅(%)',
                `VOLUME` BIGINT COMMENT '成交量(手)',
                `TURNOVER` DECIMAL(30, 2) COMMENT '成交额(元)',
                `AMPLITUDE` DECIMAL(10, 4) COMMENT '振幅(%)',
                `HIGH` DECIMAL(20, 4) COMMENT '最高',
                `LOW` DECIMAL(20, 4) COMMENT '最低',
                `OPEN` DECIMAL(20, 4) COMMENT '今开',
                `PREV_CLOSE` DECIMAL(20, 4) COMMENT '昨收',
                `VOLUME_RATIO` DECIMAL(10, 4) COMMENT '量比',
                `INDEX_TYPE` VARCHAR(50) COMMENT '指数类型',
                `TRADE_DATE` DATE COMMENT '交易日期',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE_DATE` (`INDEX_CODE`, `TRADE_DATE`),
                KEY `IDX_INDEX_TYPE` (`INDEX_TYPE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指数实时行情表(东方财富)';
        """

        # 支持的指数类型
        self.INDEX_TYPES = [
            "沪深重要指数",
            "上证系列指数",
            "深证系列指数",
            "指数成份",
            "中证系列指数",
        ]

    def fetch_index_data(self, index_type):
        """Fetch index spot data from East Money and process it.

        Args:
            index_type: Type of index to fetch (e.g., '沪深重要指数')

        Returns:
            pd.DataFrame: Processed DataFrame with index data or empty DataFrame on error
        """
        try:
            # 1. Fetch data from AKShare
            df = self.fetch_ak_data("stock_zh_index_spot_em", index_type)
            if df is None or df.empty:
                self.logger.warning(f"No index data found for type: {index_type}")
                return pd.DataFrame()

            # 2. Define column mappings (Chinese to database column names)
            column_mapping = {
                "代码": "INDEX_CODE",
                "名称": "INDEX_NAME",
                "最新价": "LATEST_PRICE",
                "涨跌额": "CHANGE_AMOUNT",
                "涨跌幅": "CHANGE_PERCENT",
                "成交量": "VOLUME",
                "成交额": "TURNOVER",
                "振幅": "AMPLITUDE",
                "最高": "HIGH",
                "最低": "LOW",
                "今开": "OPEN",
                "昨收": "PREV_CLOSE",
                "量比": "VOLUME_RATIO",
            }

            # 3. Rename and select only the columns we need
            df = df.rename(columns=column_mapping)
            df = df[list(column_mapping.values())]  # Only keep mapped columns

            # 4. Process numeric columns
            numeric_columns = [
                "LATEST_PRICE",
                "CHANGE_AMOUNT",
                "CHANGE_PERCENT",
                "VOLUME",
                "TURNOVER",
                "AMPLITUDE",
                "HIGH",
                "LOW",
                "OPEN",
                "PREV_CLOSE",
                "VOLUME_RATIO",
            ]

            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 5. Add metadata columns
            df["INDEX_TYPE"] = index_type
            trade_date = datetime.now().date()
            df["TRADE_DATE"] = trade_date
            # Stable primary key so ON DUPLICATE doesn't try to mutate PK.
            df["R_ID"] = df["INDEX_CODE"].astype(str) + "_" + trade_date.strftime("%Y%m%d")
            df["DATA_SOURCE"] = "东方财富"
            df["IS_ACTIVE"] = 1

            # 6. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "INDEX_NAME",
                "LATEST_PRICE",
                "CHANGE_AMOUNT",
                "CHANGE_PERCENT",
                "VOLUME",
                "TURNOVER",
                "AMPLITUDE",
                "HIGH",
                "LOW",
                "OPEN",
                "PREV_CLOSE",
                "VOLUME_RATIO",
                "INDEX_TYPE",
                "TRADE_DATE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE", "TRADE_DATE"])

        except Exception as e:
            self.logger.error(
                f"Error fetching index data for type {index_type}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, index_type=None):
        try:
            self.logger.info("Starting index spot data update")
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)

            # 如果指定了指数类型，只处理该类型；否则处理所有类型
            index_types = [index_type] if index_type else self.INDEX_TYPES

            any_saved = False
            for it in index_types:
                if it not in self.INDEX_TYPES:
                    self.logger.warning(f"Unsupported index type: {it}")
                    continue

                self.logger.info(f"Processing index type: {it}")
                df = self.fetch_index_data(it)
                if not df.empty:
                    df = df.replace(np.nan, None)
                    self.save_data(
                        df,
                        self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["R_ID", "INDEX_CODE", "TRADE_DATE"],
                    )
                    any_saved = True
                else:
                    self.logger.warning(f"No data found for index type: {it}")

            # Market may be closed; treat "no data" as success to avoid noisy failed executions.
            return True if any_saved or not index_type else True

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
    parser = argparse.ArgumentParser(
        description="Fetch real-time index market data from East Money"
    )
    parser.add_argument(
        "--index-type",
        type=str,
        help="指数类型: 沪深重要指数, 上证系列指数, 深证系列指数, 指数成份, 中证系列指数",
    )

    try:
        args = parser.parse_args()
        index_spot = StockZhIndexSpotEm(logger=logging.getLogger(__name__))
        sys.exit(0 if index_spot.run(args.index_type) else 1)
    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)
