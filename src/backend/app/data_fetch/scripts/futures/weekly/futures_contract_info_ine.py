import re
import time
from datetime import datetime, timedelta

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesContractInfoIne(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_CONTRACT_INFO_INE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_CONTRACT_INFO_INE` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'INE_CONTRACT_INFO' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '上海国际能源交易中心合约信息' COMMENT '参考名称',
                                      `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                      `LISTING_DATE` DATE COMMENT '上市日',
                                      `EXPIRY_DATE` DATE COMMENT '到期日',
                                      `DELIVERY_START_DATE` DATE COMMENT '开始交割日',
                                      `DELIVERY_END_DATE` DATE COMMENT '最后交割日',
                                      `LISTING_BASIS_PRICE` DECIMAL(18, 2) COMMENT '挂牌基准价',
                                      `TRADE_DATE` DATE NOT NULL COMMENT '交易日',
                                      `UPDATE_TIME` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `PRODUCT_CATEGORY` VARCHAR(10) COMMENT '品种代码',
                                      `DELIVERY_MONTH` VARCHAR(6) COMMENT '交割月份(YYYYMM)',
                                      `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效合约(1:是,0:否)',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '上海国际能源交易中心' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                      PRIMARY KEY (`R_ID`),
                                      UNIQUE KEY `IDX_INE_CONTRACT_UNIQUE` (`CONTRACT_CODE`, `TRADE_DATE`),
                                      KEY `IDX_INE_CONTRACT_CODE` (`CONTRACT_CODE`),
                                      KEY `IDX_INE_TRADE_DATE` (`TRADE_DATE`),
                                      KEY `IDX_INE_PRODUCT_CATEGORY` (`PRODUCT_CATEGORY`),
                                      KEY `IDX_INE_DELIVERY_MONTH` (`DELIVERY_MONTH`),
                                      KEY `IDX_INE_IS_ACTIVE` (`IS_ACTIVE`),
                                      KEY `IDX_INE_EXPIRY_DATE` (`EXPIRY_DATE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海国际能源交易中心合约信息表';

                                """

    def run(self, start_date=None, end_date=None):
        """
        Fetches and stores daily contract information from the Shanghai International Energy Exchange (INE).
        This function records contract information for each trading day.
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("Starting INE contract info update.")
        table_name = "FUTURES_CONTRACT_INFO_INE"

        try:
            # 1. Determine date range
            if end_date is None:
                end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            if start_date is None:
                latest_date_in_db = self.get_latest_date(table_name, "TRADE_DATE")
                if latest_date_in_db:
                    start_date = (
                        datetime.strptime(latest_date_in_db, "%Y-%m-%d") + timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                    self.logger.info(
                        f"Latest data is from {latest_date_in_db}. Starting update from {start_date}."
                    )
                else:
                    start_date = "2018-03-26"  # INE launched on this date
                    self.logger.info(f"No existing data found. Starting update from {start_date}.")

            if datetime.strptime(start_date, "%Y-%m-%d") > datetime.strptime(end_date, "%Y-%m-%d"):
                self.logger.info("Data is already up to date.")
                return

            trading_days = self.get_trading_day_list(start_date, end_date)
            if not trading_days:
                self.logger.info("No trading days to update in the specified range.")
                return

            self.logger.info(
                f"Fetching data for {len(trading_days)} trading days from {trading_days[0]} to {trading_days[-1]}."
            )

            # 2. Loop through each trading day and process data
            for trade_date in trading_days:
                try:
                    self.logger.info(f"Fetching data for trade date: {trade_date}")
                    # df = ak.futures_contract_info_ine(date=trade_date.replace('-', ''))
                    df = self.fetch_ak_data(
                        "futures_contract_info_ine", trade_date.replace("-", "")
                    )
                    time.sleep(2)  # Be respectful to the server

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
                        },
                        inplace=True,
                    )

                    # Add custom and default columns
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = "INE_CONTRACT_INFO"
                    df["REFERENCE_NAME"] = "上海国际能源交易中心合约信息"
                    df["PRODUCT_CATEGORY"] = (
                        df["CONTRACT_CODE"].str.extract(r"(^\D+)")[0].str.upper()
                    )

                    def get_delivery_month(code):
                        match = re.search(r"(\d{4})", str(code))
                        if not match:
                            return None
                        num_part = match.group(1)
                        year = f"20{num_part[:2]}"
                        month = num_part[2:]
                        return f"{year}{month}"

                    df["DELIVERY_MONTH"] = df["CONTRACT_CODE"].apply(get_delivery_month)
                    df["IS_ACTIVE"] = 1
                    df["DATA_SOURCE"] = "上海国际能源交易中心"
                    df["CREATEUSER"] = "system"
                    df["UPDATEUSER"] = "system"
                    df["UPDATE_TIME"] = self.get_current_datetime()

                    # Format date and datetime columns
                    date_cols = [
                        "LISTING_DATE",
                        "EXPIRY_DATE",
                        "DELIVERY_START_DATE",
                        "DELIVERY_END_DATE",
                        "TRADE_DATE",
                    ]
                    for col in date_cols:
                        df[col] = self.safe_date_format(df[col])

                    # 4. Save to DB
                    self.save_data(df, table_name, unique_keys=["CONTRACT_CODE", "TRADE_DATE"])

                except Exception as e:
                    self.logger.error(
                        f"Failed to process data for {trade_date}: {e}", exc_info=True
                    )
                    continue

            self.logger.info("INE contract info update finished.")

        except Exception as e:
            self.logger.error(
                f"An error occurred during the main update process: {e}", exc_info=True
            )
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesContractInfoIne()
    data_updater.run()
