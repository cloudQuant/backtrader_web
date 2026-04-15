import time
from datetime import datetime

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesDeliveryShfe(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_DELIVERY_SHFE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_DELIVERY_SHFE` (
                                  `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                  `REFERENCE_CODE` VARCHAR(50) DEFAULT 'SHFE_DELIVERY' COMMENT '参考编码',
                                  `REFERENCE_NAME` VARCHAR(100) DEFAULT '上海期货交易所交割统计' COMMENT '参考名称',
                                  `PRODUCT_NAME` VARCHAR(50) NOT NULL COMMENT '品种名称',
                                  `DELIVERY_VOLUME` INT DEFAULT 0 COMMENT '交割量(手)',
                                  `DELIVERY_PERCENT` DECIMAL(10,6) DEFAULT 0 COMMENT '交割量占比(%)',
                                  `YTD_DELIVERY_VOLUME` INT DEFAULT 0 COMMENT '本年累计交割量(手)',
                                  `YOY_PERCENT` DECIMAL(10,6) DEFAULT NULL COMMENT '累计同比(%)',
                                  `TRADE_MONTH` VARCHAR(6) NOT NULL COMMENT '统计月份(YYYYMM)',
                                  `STAT_START_DATE` DATE COMMENT '统计开始日期(上月16日)',
                                  `STAT_END_DATE` DATE COMMENT '统计结束日期(本月15日)',
                                  `CREATEDATE` DATETIME COMMENT '创建时间',
                                  `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                  `UPDATEDATE` DATETIME COMMENT '更新时间',
                                  `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                  PRIMARY KEY (`R_ID`),
                                  -- UNIQUE KEY `IDX_SHFE_DELIVERY_UNIQUE` (`PRODUCT_NAME`, `TRADE_MONTH`),
                                  KEY `IDX_SHFE_DELIVERY_MONTH` (`TRADE_MONTH`),
                                  KEY `IDX_SHFE_DELIVERY_PRODUCT` (`PRODUCT_NAME`),
                                  KEY `IDX_SHFE_DELIVERY_STAT_RANGE` (`STAT_START_DATE`, `STAT_END_DATE`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海期货交易所交割统计';
                                """

    def run(self, start_month: str = None, end_month: str = None):
        """
        更新上海商品交易所交割统计数据
        Args:
            start_month (str, optional): 开始月份，格式为'YYYYMM'，如果为None则从数据库最新月份或最早可用月份开始
            end_month (str, optional): 结束月份，格式为'YYYYMM'，如果为None则为当前月份
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("正在获取上海商品交易所交割统计数据")
        table_name = "FUTURES_DELIVERY_DCE"

        try:
            if end_month is None:
                end_month = self.get_previous_month()

            if start_month is None:
                start_month = self.get_latest_date(self.table_name, "TRADE_MONTH")
                start_month = "201211" if start_month is None else self.get_next_month(start_month)

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
                    self.logger.info(f"正在获取 {month_str} 的上海商品交易所交割统计数据")
                    df = self.fetch_ak_data("futures_delivery_shfe", month_str)

                    if df is None or df.empty:
                        self.logger.warning(f"未获取到 {month_str} 的上海商品交易所交割统计数据")
                        # Move to next month
                        if current_month.month == 12:
                            current_month = current_month.replace(
                                year=current_month.year + 1, month=1
                            )
                        else:
                            current_month = current_month.replace(month=current_month.month + 1)
                        time.sleep(1)
                        continue
                    # print(df)
                    # print(df.columns)
                    df.rename(
                        columns={
                            "品种": "PRODUCT_NAME",
                            "交割量-本月": "DELIVERY_VOLUME",
                            "交割量-比重": "DELIVERY_PERCENT",
                            "交割量-本年累计": "YTD_DELIVERY_VOLUME",
                            "交割量-累计同比": "YOY_PERCENT",
                        },
                        inplace=True,
                    )

                    df["DELIVERY_VOLUME"] = pd.to_numeric(
                        df["DELIVERY_VOLUME"], errors="coerce"
                    ).fillna(0)
                    df["DELIVERY_PERCENT"] = pd.to_numeric(
                        df["DELIVERY_PERCENT"], errors="coerce"
                    ).fillna(0)
                    df["YTD_DELIVERY_VOLUME"] = pd.to_numeric(
                        df["YTD_DELIVERY_VOLUME"], errors="coerce"
                    ).fillna(0)
                    df["YOY_PERCENT"] = pd.to_numeric(df["YOY_PERCENT"], errors="coerce")

                    df["TRADE_MONTH"] = month_str

                    self.save_data(
                        df,
                        table_name,
                        on_duplicate_update=True,
                        unique_keys=["CONTRACT_CODE", "TRADE_MONTH"],
                    )
                    success_count += 1
                    self.logger.info(
                        f"成功保存 {month_str} 的上海商品交易所交割统计数据，共 {len(df)} 条记录"
                    )
                    all_dfs.append(df)

                except Exception as e:
                    self.logger.error(
                        f"处理 {month_str} 上海商品交易所交割统计数据时出错: {str(e)}"
                    )
                    failed_months.append(month_str)

                # Move to next month
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)
                time.sleep(1)

            if success_count > 0:
                self.logger.info(f"成功更新 {success_count} 个月份的上海商品交易所交割统计数据")
                final_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            else:
                self.logger.warning("没有成功更新任何上海商品交易所交割统计数据")
                final_df = pd.DataFrame()

            if failed_months:
                self.logger.warning(f"以下月份的数据处理失败: {', '.join(failed_months)}")

            return final_df

        except Exception as e:
            self.logger.error(f"更新上海商品交易所交割统计数据失败: {str(e)}")
            raise
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesDeliveryShfe()
    data_updater.run()
