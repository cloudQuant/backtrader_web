import re
import time
from datetime import datetime, timedelta

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesStockWeeklyShfe(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_STOCK_WEEKLY_SHFE"
        self.create_table_sql = r"""
                                CREATE TABLE `FUTURES_STOCK_WEEKLY_SHFE` (
                                      `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                                      `REFERENCE_CODE` VARCHAR(50) DEFAULT 'SHFE_WEEKLY_STOCK' COMMENT '参考编码',
                                      `REFERENCE_NAME` VARCHAR(100) DEFAULT '上海期货交易所库存周报' COMMENT '参考名称',
                                      `PRODUCT_NAME` VARCHAR(50) NOT NULL COMMENT '商品名称',
                                      `PRODUCT_CODE` VARCHAR(20) COMMENT '商品代码',
                                      `REPORT_DATE` DATE NOT NULL COMMENT '报告日期(数据日期)',
                                      `CURRENT_WEEK_STOCK` DECIMAL(18, 4) COMMENT '本周库存',
                                      `PREVIOUS_WEEK_STOCK` DECIMAL(18, 4) COMMENT '上周库存',
                                      `CHANGE_AMOUNT` DECIMAL(18, 4) COMMENT '增减量',
                                      `CHANGE_PERCENT` DECIMAL(10, 6) COMMENT '增减幅度(%)',
                                      `UNIT` VARCHAR(20) COMMENT '单位',
                                      `CURRENCY` VARCHAR(3) DEFAULT 'CNY' COMMENT '币种',
                                      `DATA_SOURCE` VARCHAR(50) DEFAULT '金十数据' COMMENT '数据来源',
                                      `CREATEDATE` DATETIME COMMENT '创建时间',
                                      `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                                      `UPDATEDATE` DATETIME COMMENT '更新时间',
                                      `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                                      PRIMARY KEY (`R_ID`),
                                      -- UNIQUE KEY `IDX_SHFE_WEEKLY_STOCK_UNIQUE` (`PRODUCT_NAME`, `REPORT_DATE`),
                                      KEY `IDX_SHFE_WEEKLY_STOCK_DATE` (`REPORT_DATE`),
                                      KEY `IDX_SHFE_WEEKLY_STOCK_PRODUCT` (`PRODUCT_NAME`),
                                      KEY `IDX_SHFE_WEEKLY_STOCK_CODE` (`PRODUCT_CODE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海期货交易所库存周报表';

                                """

    def run(self, start_date=None, end_date=None):
        """
        更新上海期货交易所库存周报数据。

        :param start_date: 开始日期，格式为'YYYY-MM-DD'，如果为None则从数据库最新日期或最早可用日期开始
        :param end_date: 结束日期，格式为'YYYY-MM-DD'，如果为None则为当前日期前一天
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)

        self.logger.info("正在获取上海期货交易所库存周报数据")
        table_name = "FUTURES_STOCK_WEEKLY_SHFE"

        # Product name to code and unit mapping
        product_mapping = {
            "黄金": {"code": "AU", "unit": "千克"},
            "镍": {"code": "NI", "unit": "吨"},
            "锡": {"code": "SN", "unit": "吨"},
            "锌": {"code": "ZN", "unit": "吨"},
            "铝": {"code": "AL", "unit": "吨"},
            "铜": {"code": "CU", "unit": "吨"},
            "铅": {"code": "PB", "unit": "吨"},
            "螺纹钢": {"code": "RB", "unit": "吨"},
            "线材": {"code": "WR", "unit": "吨"},
            "纸浆": {"code": "SP", "unit": "吨"},
            "白银(千克)": {"code": "AG", "unit": "千克"},
            "燃料油": {"code": "FU", "unit": "吨"},
            "热轧卷板": {"code": "HC", "unit": "吨"},
            "沥青厂库": {"code": "BU", "unit": "吨"},
            "沥青仓库": {"code": "BU", "unit": "吨"},
            "天然橡胶": {"code": "RU", "unit": "吨"},
            "中质含硫原油(桶)": {"code": "SC", "unit": "桶"},
            "20号胶": {"code": "NR", "unit": "吨"},
        }

        try:
            # 1. Date Handling
            if end_date is None:
                end_date = self.get_previous_date()

            if start_date is None:
                latest_date_in_db = self.get_latest_date(table_name, "REPORT_DATE")
                if latest_date_in_db:
                    start_date = (
                        datetime.strptime(latest_date_in_db, "%Y-%m-%d") + timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                    self.logger.info(f"最新数据日期: {latest_date_in_db}，从 {start_date} 开始更新")
                else:
                    start_date = "2016-05-06"  # Adjust as per actual earliest data available
                    self.logger.info(f"无历史数据，从 {start_date} 开始获取")

            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

            if start_date_dt > end_date_dt:
                self.logger.info(
                    f"数据已是最新，无需更新。开始日期 {start_date} > 结束日期 {end_date}"
                )
                return

            trading_days = self.get_trading_day_list(
                start_date_dt.strftime("%Y-%m-%d"), end_date_dt.strftime("%Y-%m-%d")
            )

            report_dates = []
            if trading_days:
                trading_days_dt = [datetime.strptime(d, "%Y-%m-%d").date() for d in trading_days]
                temp_df = pd.DataFrame({"date": trading_days_dt})
                temp_df["week_start"] = temp_df["date"].apply(
                    lambda x: x - timedelta(days=x.weekday())
                )
                weekly_last_trading_days = temp_df.groupby("week_start")["date"].max().tolist()
                report_dates = [d.strftime("%Y-%m-%d") for d in weekly_last_trading_days]
                report_dates = [
                    d
                    for d in report_dates
                    if start_date_dt <= datetime.strptime(d, "%Y-%m-%d").date() <= end_date_dt
                ]

            if not report_dates:
                self.logger.info("在指定范围内没有需要更新的周报日期")
                return

            self.logger.info(
                f"准备更新从 {report_dates[0]} 到 {report_dates[-1]} 的库存周报数据，共 {len(report_dates)} 个报告日"
            )

            all_dfs = []
            failed_dates = []

            for date_str in report_dates:
                try:
                    self.logger.info(f"正在获取 {date_str} 的上海期货交易所库存周报数据")

                    # df = ak.futures_stock_shfe_js(date=date_str.replace('-', ''))
                    df = self.fetch_ak_data("futures_stock_shfe_js", date_str.replace("-", ""))
                    time.sleep(2)  # Respectful delay

                    if df is None or df.empty:
                        self.logger.warning(f"未获取到 {date_str} 的库存周报数据")
                        continue

                    stock_cols = [col for col in df.columns if "期货总量" in col]
                    if len(stock_cols) != 2:
                        self.logger.warning(
                            f"无法识别 {date_str} 的库存周报列名，跳过。列: {df.columns}"
                        )
                        continue

                    # Extract dates from column names to correctly identify current and previous
                    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})")
                    col_dates = {col: date_pattern.search(col) for col in stock_cols}

                    valid_cols = {col: match.group(1) for col, match in col_dates.items() if match}

                    if len(valid_cols) != 2:
                        self.logger.warning(f"无法从列名中解析日期: {stock_cols}")
                        continue

                    sorted_cols = sorted(
                        valid_cols.items(),
                        key=lambda item: datetime.strptime(item[1], "%Y-%m-%d"),
                        reverse=True,
                    )

                    current_week_col = sorted_cols[0][0]
                    previous_week_col = sorted_cols[1][0]

                    df.rename(
                        columns={
                            "商品": "PRODUCT_NAME",
                            current_week_col: "CURRENT_WEEK_STOCK",
                            previous_week_col: "PREVIOUS_WEEK_STOCK",
                            "增减": "CHANGE_AMOUNT",
                            "增减幅度": "CHANGE_PERCENT",
                        },
                        inplace=True,
                    )

                    df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                    df["REFERENCE_CODE"] = "SHFE_WEEKLY_STOCK"
                    df["REFERENCE_NAME"] = "上海期货交易所库存周报"
                    df["REPORT_DATE"] = date_str
                    df["CURRENCY"] = "CNY"
                    df["DATA_SOURCE"] = "金十数据"

                    df["CREATEDATE"] = self.get_current_datetime()
                    df["CREATEUSER"] = "system"
                    df["UPDATEDATE"] = self.get_current_datetime()
                    df["UPDATEUSER"] = "system"

                    df["PRODUCT_CODE"] = df["PRODUCT_NAME"].apply(
                        lambda x: product_mapping.get(x, {}).get("code")
                    )
                    df["UNIT"] = df["PRODUCT_NAME"].apply(
                        lambda x: product_mapping.get(x, {}).get("unit")
                    )

                    numeric_cols = [
                        "CURRENT_WEEK_STOCK",
                        "PREVIOUS_WEEK_STOCK",
                        "CHANGE_AMOUNT",
                        "CHANGE_PERCENT",
                    ]
                    for col in numeric_cols:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

                    # Change percentage to decimal
                    if "CHANGE_PERCENT" in df.columns:
                        df["CHANGE_PERCENT"] = df["CHANGE_PERCENT"] / 100

                    self.save_data(
                        df,
                        table_name,
                        on_duplicate_update=True,
                        unique_keys=["PRODUCT_NAME", "REPORT_DATE"],
                    )
                    self.logger.info(f"成功保存 {date_str} 的库存周报数据，共 {len(df)} 条记录")
                    all_dfs.append(df)

                except Exception as e:
                    self.logger.error(
                        f"处理 {date_str} 库存周报数据时出错: {str(e)}", exc_info=True
                    )
                    failed_dates.append(date_str)
                    continue

            if failed_dates:
                self.logger.warning(f"以下报告日期的数据处理失败: {', '.join(failed_dates)}")

        except Exception as e:
            self.logger.error(f"更新上海期货交易所库存周报数据失败: {str(e)}", exc_info=True)
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesStockWeeklyShfe()
    # data_updater.run()
