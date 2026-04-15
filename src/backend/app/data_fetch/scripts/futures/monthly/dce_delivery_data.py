import time
from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesDeliveryDce(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_DELIVERY_DCE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_DELIVERY_DCE` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'DCE_DELIVERY' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '大连商品交易所交割统计' COMMENT '参考名称',
                                      `PRODUCT_NAME` VARCHAR(50) NOT NULL COMMENT '品种名称',
                                      `CONTRACT_CODE` VARCHAR(20) NOT NULL COMMENT '合约代码',
                                      `DELIVERY_DATE` DATE NOT NULL COMMENT '交割日期',
                                      `DELIVERY_VOLUME` INT DEFAULT 0 COMMENT '交割量',
                                      `DELIVERY_AMOUNT` BIGINT DEFAULT 0 COMMENT '交割金额(元)',
                                      `TRADE_MONTH` VARCHAR(6) COMMENT '交易年月(YYYYMM)',
                                      `CREATEDATE` DATETIME COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                      PRIMARY KEY (`R_ID`),
                                    --   UNIQUE KEY `IDX_DCE_DELIVERY_UNIQUE` (`CONTRACT_CODE`, `DELIVERY_DATE`),
                                      KEY `IDX_DCE_DELIVERY_DATE` (`DELIVERY_DATE`),
                                      KEY `IDX_DCE_DELIVERY_CONTRACT` (`CONTRACT_CODE`),
                                      KEY `IDX_DCE_DELIVERY_PRODUCT` (`PRODUCT_NAME`),
                                      KEY `IDX_DCE_DELIVERY_TRADE_MONTH` (`TRADE_MONTH`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大连商品交易所交割统计';
                                """

    def run(self, start_month: str = None, end_month: str = None):
        """
        更新大连商品交易所交割统计数据
        Args:
            start_month (str, optional): 开始月份，格式为'YYYYMM'，如果为None则从数据库最新月份或最早可用月份开始
            end_month (str, optional): 结束月份，格式为'YYYYMM'，如果为None则为当前月份
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("正在获取大连商品交易所交割统计数据")
        table_name = "FUTURES_DELIVERY_DCE"

        try:
            if end_month is None:
                end_month = self.get_previous_month()

            if start_month is None:
                start_month = self.get_latest_date(self.table_name, "DELIVERY_DATE")
                start_month = self.get_next_month(start_month)

            start_month_dt = datetime.strptime(start_month, "%Y%m").date()
            end_month_dt = datetime.strptime(end_month, "%Y%m").date()

            if start_month_dt > end_month_dt:
                self.logger.info(f"开始月份 {start_month} 不能晚于结束月份 {end_month}")
                return pd.DataFrame()

            all_dfs = []
            success_count = 0
            failed_months = []

            current_month = datetime.strptime(start_month, "%Y%m")
            while current_month <= datetime.strptime(end_month, "%Y%m"):
                month_str = current_month.strftime("%Y%m")
                try:
                    self.logger.info(f"正在获取 {month_str} 的大连商品交易所交割统计数据")
                    df = self.fetch_ak_data("futures_delivery_dce", month_str)

                    if df is None or df.empty:
                        self.logger.warning(f"未获取到 {month_str} 的大连商品交易所交割统计数据")
                        # Move to next month
                        if current_month.month == 12:
                            current_month = current_month.replace(
                                year=current_month.year + 1, month=1
                            )
                        else:
                            current_month = current_month.replace(month=current_month.month + 1)
                        time.sleep(1)
                        continue

                    df.rename(
                        columns={
                            "品种": "PRODUCT_NAME",
                            "合约": "CONTRACT_CODE",
                            "交割日期": "DELIVERY_DATE",
                            "交割量": "DELIVERY_VOLUME",
                            "交割金额": "DELIVERY_AMOUNT",
                        },
                        inplace=True,
                    )

                    df["DELIVERY_DATE"] = pd.to_datetime(df["DELIVERY_DATE"]).dt.date
                    df["DELIVERY_VOLUME"] = pd.to_numeric(
                        df["DELIVERY_VOLUME"], errors="coerce"
                    ).fillna(0)
                    df["DELIVERY_AMOUNT"] = pd.to_numeric(
                        df["DELIVERY_AMOUNT"], errors="coerce"
                    ).fillna(0)

                    df["TRADE_MONTH"] = df["DELIVERY_DATE"].apply(lambda x: x.strftime("%Y%m"))

                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = "DCE_DELIVERY"
                    df["REFERENCE_NAME"] = "大连商品交易所交割统计"
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"

                    self.save_data(
                        df,
                        table_name,
                        on_duplicate_update=True,
                        unique_keys=["CONTRACT_CODE", "DELIVERY_DATE"],
                    )
                    success_count += 1
                    self.logger.info(
                        f"成功保存 {month_str} 的大连商品交易所交割统计数据，共 {len(df)} 条记录"
                    )
                    all_dfs.append(df)

                except Exception as e:
                    self.logger.error(
                        f"处理 {month_str} 大连商品交易所交割统计数据时出错: {str(e)}"
                    )
                    failed_months.append(month_str)

                # Move to next month
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)
                time.sleep(1)

            if success_count > 0:
                self.logger.info(f"成功更新 {success_count} 个月份的大连商品交易所交割统计数据")
                final_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            else:
                self.logger.warning("没有成功更新任何大连商品交易所交割统计数据")
                final_df = pd.DataFrame()

            if failed_months:
                self.logger.warning(f"以下月份的数据处理失败: {', '.join(failed_months)}")

            return final_df

        except Exception as e:
            self.logger.error(f"更新大连商品交易所交割统计数据失败: {str(e)}")
            raise
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesDeliveryDce()
    data_updater.run()
