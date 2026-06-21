import re
import time
from datetime import datetime, timedelta

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesContractInfoShfe(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_CONTRACT_INFO_SHFE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_CONTRACT_INFO_SHFE` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'SHFE_CONTRACT_INFO' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '上海期货交易所合约信息' COMMENT '参考名称',
                                      `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                      `LISTING_DATE` DATE COMMENT '上市日',
                                      `EXPIRY_DATE` DATE COMMENT '到期日',
                                      `DELIVERY_START_DATE` DATE COMMENT '开始交割日',
                                      `DELIVERY_END_DATE` DATE COMMENT '最后交割日',
                                      `LISTING_BASIS_PRICE` DECIMAL(18, 2) COMMENT '挂牌基准价',
                                      `TRADE_DATE` DATE NOT NULL COMMENT '交易日',
                                      `UPDATE_TIME` DATETIME COMMENT '更新时间',
                                      `PRODUCT_CATEGORY` VARCHAR(10) COMMENT '品种代码',
                                      `DELIVERY_MONTH` VARCHAR(6) COMMENT '交割月份(YYYYMM)',
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效合约(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '上海期货交易所' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_SHFE_CONTRACT_UNIQUE` (`CONTRACT_CODE`, `TRADE_DATE`),
                                      KEY `IDX_SHFE_CONTRACT_CODE` (`CONTRACT_CODE`),
                                      KEY `IDX_SHFE_TRADE_DATE` (`TRADE_DATE`),
                                      KEY `IDX_SHFE_PRODUCT_CATEGORY` (`PRODUCT_CATEGORY`),
                                      KEY `IDX_SHFE_DELIVERY_MONTH` (`DELIVERY_MONTH`),
                                      KEY `IDX_SHFE_IS_ACTIVE` (`IS_ACTIVE`),
                                      KEY `IDX_SHFE_EXPIRY_DATE` (`EXPIRY_DATE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海期货交易所合约信息表';

                                """
        self.required_columns = {
            "R_ID",
            "CONTRACT_CODE",
            "LISTING_DATE",
            "EXPIRY_DATE",
            "DELIVERY_START_DATE",
            "DELIVERY_END_DATE",
            "LISTING_BASIS_PRICE",
            "TRADE_DATE",
            "UPDATE_TIME",
            "PRODUCT_CATEGORY",
            "DELIVERY_MONTH",
            "IS_ACTIVE",
            "DATA_SOURCE",
            "CREATEDATE",
            "CREATEUSER",
            "UPDATEDATE",
            "UPDATEUSER",
        }
        self.target_columns = [
            "R_ID",
            "CONTRACT_CODE",
            "LISTING_DATE",
            "EXPIRY_DATE",
            "DELIVERY_START_DATE",
            "DELIVERY_END_DATE",
            "LISTING_BASIS_PRICE",
            "TRADE_DATE",
            "UPDATE_TIME",
            "PRODUCT_CATEGORY",
            "DELIVERY_MONTH",
            "IS_ACTIVE",
            "DATA_SOURCE",
            "CREATEUSER",
            "UPDATEUSER",
        ]

    @staticmethod
    def _get_delivery_month(code):
        match = re.search(r"(\d+)", str(code))
        if not match:
            return None
        num_part = match.group(1)
        if len(num_part) == 4:  # e.g., 2405
            year = f"20{num_part[:2]}"
            month = num_part[2:]
            return f"{year}{month}"
        return None

    def _ensure_current_table_schema(self):
        """Ensure legacy auto-created Chinese-column tables do not block writes."""
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
            return

        safe_table = self.table_name.replace("`", "``")
        try:
            self.connect_db()
            self.cursor.execute(f"SHOW COLUMNS FROM `{safe_table}`")
            columns = {str(row[0]).upper() for row in self.cursor.fetchall() or []}

            if self.required_columns.issubset(columns):
                return

            backup_table = f"{self.table_name}_LEGACY_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            safe_backup = backup_table.replace("`", "``")
            missing = sorted(self.required_columns - columns)
            self.logger.warning(
                "Table %s is missing required columns %s; backing it up as %s and rebuilding",
                self.table_name,
                missing[:10],
                backup_table,
            )
            self.cursor.execute(f"RENAME TABLE `{safe_table}` TO `{safe_backup}`")
            self.cursor.execute(self.create_table_sql)
            self.connection.commit()
            self._columns_cache.pop(safe_table, None)
            self._columns_cache.pop(safe_backup, None)
            self._table_exists_cache[safe_table] = True
            self._table_exists_cache[safe_backup] = True
            self._migrate_legacy_rows(backup_table)
        except Exception:
            if self.connection:
                self.connection.rollback()
            self.logger.error("Failed to ensure SHFE contract info table schema", exc_info=True)
            raise
        finally:
            self.disconnect_db()

    def _migrate_legacy_rows(self, backup_table):
        safe_backup = backup_table.replace("`", "``")
        self.cursor.execute(f"SELECT * FROM `{safe_backup}`")
        rows = self.cursor.fetchall() or []
        if not rows:
            return 0

        columns = [desc[0] for desc in self.cursor.description or []]
        legacy_df = pd.DataFrame(rows, columns=columns)
        legacy_df.rename(
            columns={
                "合约代码": "CONTRACT_CODE",
                "上市日": "LISTING_DATE",
                "到期日": "EXPIRY_DATE",
                "开始交割日": "DELIVERY_START_DATE",
                "最后交割日": "DELIVERY_END_DATE",
                "挂牌基准价": "LISTING_BASIS_PRICE",
                "交易日": "TRADE_DATE",
                "更新时间": "UPDATE_TIME",
            },
            inplace=True,
        )
        if "TRADE_DATE" not in legacy_df.columns and "data_date" in legacy_df.columns:
            legacy_df["TRADE_DATE"] = legacy_df["data_date"]
        if "CONTRACT_CODE" not in legacy_df.columns or "TRADE_DATE" not in legacy_df.columns:
            self.logger.warning("Legacy SHFE table has no mappable contract/date columns; skip migration")
            return 0

        legacy_df = legacy_df.dropna(subset=["CONTRACT_CODE", "TRADE_DATE"]).copy()
        if legacy_df.empty:
            return 0

        legacy_df["R_ID"] = [self.get_uuid() for _ in range(len(legacy_df))]
        legacy_df["PRODUCT_CATEGORY"] = (
            legacy_df["CONTRACT_CODE"].astype(str).str.extract(r"(^\D+)")[0].str.upper()
        )
        legacy_df["DELIVERY_MONTH"] = legacy_df["CONTRACT_CODE"].apply(self._get_delivery_month)
        legacy_df["IS_ACTIVE"] = 1
        legacy_df["DATA_SOURCE"] = "上海期货交易所"
        legacy_df["CREATEUSER"] = "system"
        legacy_df["UPDATEUSER"] = "system"

        for col in [
            "LISTING_DATE",
            "EXPIRY_DATE",
            "DELIVERY_START_DATE",
            "DELIVERY_END_DATE",
            "TRADE_DATE",
        ]:
            if col in legacy_df.columns:
                legacy_df[col] = pd.to_datetime(legacy_df[col], errors="coerce").dt.strftime(
                    "%Y-%m-%d"
                )
            else:
                legacy_df[col] = None

        if "UPDATE_TIME" in legacy_df.columns:
            legacy_df["UPDATE_TIME"] = pd.to_datetime(
                legacy_df["UPDATE_TIME"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            legacy_df["UPDATE_TIME"] = None

        legacy_df = legacy_df.dropna(subset=["CONTRACT_CODE", "TRADE_DATE"])
        if legacy_df.empty:
            return 0

        for col in self.target_columns:
            if col not in legacy_df.columns:
                legacy_df[col] = None

        migrated_rows = self.save_data(
            legacy_df[self.target_columns],
            self.table_name,
            on_duplicate_update=True,
            unique_keys=["CONTRACT_CODE", "TRADE_DATE"],
        )
        self.logger.info(
            "Migrated %s legacy SHFE contract rows from %s",
            migrated_rows,
            backup_table,
        )
        return migrated_rows

    def run(self, start_date=None, end_date=None, lookback_days=None, max_days=None, sleep_seconds=0.5):
        """
        获取并存储上海期货交易所的每日合约信息。
        该函数会记录每个交易日的合约信息。
        """
        self._ensure_current_table_schema()

        self.logger.info("Starting SHFE contract info update.")
        table_name = "FUTURES_CONTRACT_INFO_SHFE"

        try:
            lookback_days = int(lookback_days) if lookback_days is not None else None
            max_days = int(max_days) if max_days is not None else None
            sleep_seconds = float(sleep_seconds or 0)
            # 1. Determine date range
            if end_date is None:
                end_date = datetime.now().strftime("%Y-%m-%d")

            if start_date is None:
                latest_date_in_db = self.get_latest_date(table_name, "TRADE_DATE")
                if latest_date_in_db:
                    start_date = latest_date_in_db
                    self.logger.info(
                        f"Latest data is from {latest_date_in_db}. Starting update from {start_date}."
                    )
                else:
                    start_date = "2016-01-01"  # Default start date if table is empty
                    self.logger.info(f"No existing data found. Starting update from {start_date}.")
            if lookback_days is not None:
                lookback_start = (datetime.now() - timedelta(days=lookback_days)).strftime(
                    "%Y-%m-%d"
                )
                if datetime.strptime(start_date, "%Y-%m-%d") < datetime.strptime(
                    lookback_start, "%Y-%m-%d"
                ):
                    start_date = lookback_start
                    self.logger.info(f"Limiting SHFE update to last {lookback_days} days.")

            if datetime.strptime(start_date, "%Y-%m-%d") > datetime.strptime(end_date, "%Y-%m-%d"):
                self.logger.info("Data is already up to date.")
                return

            trading_days = self.get_trading_day_list(start_date, end_date)
            if not trading_days:
                self.logger.info("No trading days to update in the specified range.")
                return
            if max_days is not None and len(trading_days) > max_days:
                trading_days = trading_days[-max_days:]
                self.logger.info(f"Limiting SHFE update to {max_days} trading days.")

            self.logger.info(
                f"Fetching data for {len(trading_days)} trading days from {trading_days[0]} to {trading_days[-1]}."
            )

            # 2. Loop through each trading day and process data
            for trade_date in trading_days:
                try:
                    self.logger.info(f"Fetching data for trade date: {trade_date}")
                    # df = ak.futures_contract_info_shfe(date=trade_date.replace('-', ''))
                    df = self.fetch_ak_data(
                        "futures_contract_info_shfe", trade_date.replace("-", "")
                    )
                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)

                    if df.empty:
                        self.logger.warning(f"No data returned for {trade_date}.")
                        continue

                    # 3. Data Transformation
                    df.rename(
                        columns={
                            "合约代码": "CONTRACT_CODE",
                            "上市日": "LISTING_DATE",
                            "到期日": "EXPIRY_DATE",
                            "开始交割日": "DELIVERY_START_DATE",
                            "最后交割日": "DELIVERY_END_DATE",
                            "挂牌基准价": "LISTING_BASIS_PRICE",
                            "交易日": "TRADE_DATE",
                            "更新时间": "UPDATE_TIME",
                        },
                        inplace=True,
                    )

                    # Add custom columns
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["PRODUCT_CATEGORY"] = (
                        df["CONTRACT_CODE"].str.extract(r"(^\D+)")[0].str.upper()
                    )

                    df["DELIVERY_MONTH"] = df["CONTRACT_CODE"].apply(self._get_delivery_month)
                    df["IS_ACTIVE"] = 1
                    df["DATA_SOURCE"] = "上海期货交易所"
                    df["CREATEUSER"] = "system"
                    df["UPDATEUSER"] = "system"

                    # Format dates
                    date_cols = [
                        "LISTING_DATE",
                        "EXPIRY_DATE",
                        "DELIVERY_START_DATE",
                        "DELIVERY_END_DATE",
                        "TRADE_DATE",
                    ]
                    for col in date_cols:
                        df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d")
                    df["UPDATE_TIME"] = pd.to_datetime(df["UPDATE_TIME"]).dt.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    # 4. Save to DB
                    self.save_data(
                        df,
                        table_name,
                        on_duplicate_update=True,
                        unique_keys=["CONTRACT_CODE", "TRADE_DATE"],
                    )

                except Exception as e:
                    self.logger.error(
                        f"Failed to process data for {trade_date}: {e}", exc_info=True
                    )
                    continue

            self.logger.info("SHFE contract info update finished.")

        except Exception as e:
            self.logger.error(
                f"An error occurred during the main update process: {e}", exc_info=True
            )


if __name__ == "__main__":
    data_updater = FuturesContractInfoShfe()
    data_updater.run()
