import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

SHFE_MONTHDATA_URL = "https://www.shfe.com.cn/data/tradedata/future/monthdata"
PREFER_LOCAL_SCRIPT = True


class FuturesDeliveryShfe(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_DELIVERY_SHFE"
        self.create_table_sql = r"""
                                CREATE TABLE IF NOT EXISTS `FUTURES_DELIVERY_SHFE` (
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
                                  UNIQUE KEY `IDX_SHFE_DELIVERY_UNIQUE` (`PRODUCT_NAME`, `TRADE_MONTH`),
                                  KEY `IDX_SHFE_DELIVERY_MONTH` (`TRADE_MONTH`),
                                  KEY `IDX_SHFE_DELIVERY_PRODUCT` (`PRODUCT_NAME`),
                                  KEY `IDX_SHFE_DELIVERY_STAT_RANGE` (`STAT_START_DATE`, `STAT_END_DATE`)
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海期货交易所交割统计';
                                """

    @staticmethod
    def _subtract_months(month_dt: datetime, months: int) -> datetime:
        total_months = month_dt.year * 12 + month_dt.month - 1 - max(months - 1, 0)
        return datetime(total_months // 12, total_months % 12 + 1, 1)

    def _ensure_unique_index(self):
        rows = self.execute_sql(
            "SHOW INDEX FROM `FUTURES_DELIVERY_SHFE` WHERE Key_name = 'IDX_SHFE_DELIVERY_UNIQUE'",
            fetch_all=True,
        )
        if rows:
            return
        self.execute_sql(
            "ALTER TABLE `FUTURES_DELIVERY_SHFE` "
            "ADD UNIQUE KEY `IDX_SHFE_DELIVERY_UNIQUE` (`PRODUCT_NAME`, `TRADE_MONTH`)"
        )

    def _fetch_shfe_delivery(self, trade_month: str) -> pd.DataFrame:
        url = f"{SHFE_MONTHDATA_URL}/{trade_month}monthvarietystatistics.dat"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.shfe.com.cn/reports/tradedata/monthlyandyearlydata/",
        }
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code != 200:
                    return pd.DataFrame()
                data_json = response.json()
                rows = data_json.get("o_curdelivery") or []
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows)
                return df.rename(
                    columns={
                        "PRODUCTNAME": "品种",
                        "DELIVERYVOLUME": "交割量-本月",
                        "ACCOUNTS": "交割量-比重",
                        "YEARDELIVERYVOLUME": "交割量-本年累计",
                        "YOYCHANGE": "交割量-累计同比",
                    }
                )[
                    [
                        "品种",
                        "交割量-本月",
                        "交割量-比重",
                        "交割量-本年累计",
                        "交割量-累计同比",
                    ]
                ]
            except Exception as exc:
                last_error = exc
                time.sleep(1 + attempt)
        self.logger.warning("上期所交割统计请求失败 %s: %s", trade_month, last_error)
        return pd.DataFrame()

    def run(
        self,
        start_month: str = None,
        end_month: str = None,
        sleep_seconds=0,
        lookback_months=None,
        max_months=None,
    ):
        """
        更新上海商品交易所交割统计数据
        Args:
            start_month (str, optional): 开始月份，格式为'YYYYMM'，如果为None则从数据库最新月份或最早可用月份开始
            end_month (str, optional): 结束月份，格式为'YYYYMM'，如果为None则为当前月份
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self._ensure_unique_index()

        self.logger.info("正在获取上海商品交易所交割统计数据")
        table_name = self.table_name

        try:
            sleep_seconds = float(sleep_seconds or 0)
            lookback_months = int(lookback_months) if lookback_months is not None else None
            max_months = int(max_months) if max_months is not None else None
            if end_month is None:
                end_month = self.get_previous_month()

            if start_month is None:
                start_month = self.get_latest_date(self.table_name, "TRADE_MONTH")
                start_month = "201211" if start_month is None else self.get_next_month(start_month)

            start_month_dt = datetime.strptime(start_month, "%Y%m").date()
            end_month_dt = datetime.strptime(end_month, "%Y%m").date()
            if lookback_months is not None:
                lookback_start = self._subtract_months(
                    datetime.strptime(end_month, "%Y%m"), lookback_months
                ).date()
                if start_month_dt < lookback_start:
                    start_month_dt = lookback_start
                    start_month = start_month_dt.strftime("%Y%m")
                    self.logger.info(f"限制上海期货交易所交割统计更新为最近 {lookback_months} 个月")

            if start_month_dt > end_month_dt:
                self.logger.info(f"开始月份 {start_month} 不能晚于结束月份 {end_month}")
                return pd.DataFrame()

            all_dfs = []
            success_count = 0
            failed_months = []

            current_month = datetime.strptime(start_month, "%Y%m")
            months_processed = 0
            while current_month <= datetime.strptime(end_month, "%Y%m"):
                if max_months is not None and months_processed >= max_months:
                    self.logger.info(f"达到 max_months={max_months}，停止处理剩余月份")
                    break
                months_processed += 1
                month_str = current_month.strftime("%Y%m")
                try:
                    self.logger.info(f"正在获取 {month_str} 的上海商品交易所交割统计数据")
                    df = self._fetch_shfe_delivery(month_str)

                    if df is None or df.empty:
                        self.logger.warning(f"未获取到 {month_str} 的上海商品交易所交割统计数据")
                        # Move to next month
                        if current_month.month == 12:
                            current_month = current_month.replace(
                                year=current_month.year + 1, month=1
                            )
                        else:
                            current_month = current_month.replace(month=current_month.month + 1)
                        if sleep_seconds > 0:
                            time.sleep(sleep_seconds)
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
                    month_start = datetime.strptime(month_str, "%Y%m")
                    previous_month_end = month_start.replace(day=1) - timedelta(days=1)
                    df["STAT_START_DATE"] = previous_month_end.replace(day=16).date()
                    df["STAT_END_DATE"] = month_start.replace(day=15).date()
                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = "SHFE_DELIVERY"
                    df["REFERENCE_NAME"] = "上海期货交易所交割统计"
                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"

                    columns = [
                        "R_ID",
                        "REFERENCE_CODE",
                        "REFERENCE_NAME",
                        "PRODUCT_NAME",
                        "DELIVERY_VOLUME",
                        "DELIVERY_PERCENT",
                        "YTD_DELIVERY_VOLUME",
                        "YOY_PERCENT",
                        "TRADE_MONTH",
                        "STAT_START_DATE",
                        "STAT_END_DATE",
                        "CREATEDATE",
                        "CREATEUSER",
                        "UPDATEDATE",
                        "UPDATEUSER",
                    ]
                    for col in columns:
                        if col not in df.columns:
                            df[col] = None

                    self.delete_data(table_name, {"TRADE_MONTH": month_str})
                    self.save_data(
                        df[columns],
                        table_name,
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
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

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
