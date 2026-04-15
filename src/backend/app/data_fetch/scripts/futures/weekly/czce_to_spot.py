from datetime import datetime

import numpy as np
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesCzceToSpot(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_CZCE_TO_SPOT"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_CZCE_TO_SPOT` (
                                  `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                  `REFERENCE_CODE` VARCHAR(50) DEFAULT 'CZCE_TO_SPOT' COMMENT '参考编码',
                                  `REFERENCE_NAME` VARCHAR(100) DEFAULT '郑州商品交易所期转现统计' COMMENT '参考名称',
                                  `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                  `CONVERSION_DATE` DATE NOT NULL COMMENT '期转现发生日期',
                                  `VOLUME` INT DEFAULT 0 COMMENT '期转现数量(手)',
                                  `TRADE_MONTH` VARCHAR(6) COMMENT '交易年月(YYYYMM)',
                                  `CREATEDATE` DATETIME COMMENT '创建时间',
                                  `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                  `UPDATEDATE` DATETIME COMMENT '更新时间',
                                  `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                  PRIMARY KEY (`R_ID`),
                                --   UNIQUE KEY `IDX_CZCE_TO_SPOT_UNIQUE` (`CONTRACT_CODE`, `CONVERSION_DATE`),
                                  KEY `IDX_CZCE_TO_SPOT_DATE` (`CONVERSION_DATE`),
                                  KEY `IDX_CZCE_TO_SPOT_CONTRACT` (`CONTRACT_CODE`),
                                  KEY `IDX_CZCE_TO_SPOT_TRADE_MONTH` (`TRADE_MONTH`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='郑州商品交易所期转现统计';

                                """

    def run(self, start_date=None, end_date=None):
        """
        更新郑州商品交易所期转现数据
        Args:
            start_date (str, optional): 开始日期，格式为'YYYYMMDD'，如果为None则从数据库最新日期或最早可用日期开始
            end_date (str, optional): 结束日期，格式为'YYYYMMDD'，如果为None则为当前日期前一天
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self.logger.info("正在获取郑州商品交易所期转现数据")
        table_name = "FUTURES_CZCE_TO_SPOT"

        try:
            if end_date is None:
                end_date = self.get_previous_date().replace("-", "")

            if start_date is None:
                start_date = self.get_latest_date(self.table_name, "CONVERSION_DATE")
                start_date = self.get_next_date(start_date)
            if "-" in start_date:
                start_date_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            else:
                start_date_dt = datetime.strptime(start_date, "%Y%m%d").date()
            if "-" in end_date:
                end_date_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            else:
                end_date_dt = datetime.strptime(end_date, "%Y%m%d").date()

            if start_date_dt > end_date_dt:
                self.logger.info(f"开始日期 {start_date} 不能晚于结束日期 {end_date}")
                return pd.DataFrame()

            trading_days = self.get_trading_day_list(
                start_date_dt.strftime("%Y-%m-%d"), end_date_dt.strftime("%Y-%m-%d")
            )

            if not trading_days:
                self.logger.info("在指定范围内没有需要更新的交易日")
                return pd.DataFrame()

            self.logger.info(
                f"准备更新从 {trading_days[0]} 到 {trading_days[-1]} 的郑商所期转现数据，共 {len(trading_days)} 个交易日"
            )

            all_dfs = []
            success_count = 0
            failed_dates = []

            for date_str in trading_days:
                try:
                    date_yyyymmdd = date_str.replace("-", "")
                    self.logger.info(f"正在获取 {date_str} 的郑商所期转现数据")

                    # df = ak.futures_to_spot_czce(date=date_yyyymmdd)
                    df = self.fetch_ak_data("futures_to_spot_czce", date_yyyymmdd)

                    if df is None or df.empty:
                        self.logger.warning(f"未获取到 {date_str} 的郑商所期转现数据")
                        continue

                    df.rename(
                        columns={"合约代码": "CONTRACT_CODE", "合约数量": "VOLUME"},
                        inplace=True,
                    )

                    df["VOLUME"] = pd.to_numeric(df["VOLUME"], errors="coerce").fillna(0)

                    # Extract TRADE_MONTH from CONTRACT_CODE
                    df["TRADE_MONTH"] = None
                    for idx, row in df.iterrows():
                        contract_code = row.get("CONTRACT_CODE")
                        if contract_code and len(contract_code) >= 4:
                            current_year_prefix = str(datetime.now().year)[:-1]
                            contract_year_digit = contract_code[len(contract_code) - 3]
                            contract_month = contract_code[len(contract_code) - 2 :]

                            if int(contract_year_digit) > int(str(datetime.now().year)[3]):
                                trade_year = int(current_year_prefix + contract_year_digit) - 10
                            else:
                                trade_year = int(current_year_prefix + contract_year_digit)

                            df.loc[idx, "TRADE_MONTH"] = f"{trade_year}{contract_month}"

                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = "CZCE_TO_SPOT"
                    df["REFERENCE_NAME"] = "郑州商品交易所期转现统计"
                    df["CONVERSION_DATE"] = datetime.strptime(date_str, "%Y-%m-%d").date()
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"
                    df = df.replace(np.nan, None)
                    self.save_data(
                        df,
                        table_name,
                        on_duplicate_update=True,
                        unique_keys=["CONTRACT_CODE", "CONVERSION_DATE"],
                    )
                    success_count += 1
                    self.logger.info(f"成功保存 {date_str} 的郑商所期转现数据，共 {len(df)} 条记录")
                    all_dfs.append(df)

                except Exception as e:
                    self.logger.error(f"处理 {date_str} 郑商所期转现数据时出错: {str(e)}")
                    failed_dates.append(date_str)
                    continue

            if success_count > 0:
                self.logger.info(f"成功更新 {success_count} 个交易日的郑商所期转现数据")
                final_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            else:
                self.logger.warning("没有成功更新任何郑商所期转现数据")
                final_df = pd.DataFrame()

            if failed_dates:
                self.logger.warning(f"以下日期的数据处理失败: {', '.join(failed_dates)}")

            return final_df

        except Exception as e:
            self.logger.error(f"更新郑商所期转现数据失败: {str(e)}")
            raise
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesCzceToSpot()
    data_updater.run()
