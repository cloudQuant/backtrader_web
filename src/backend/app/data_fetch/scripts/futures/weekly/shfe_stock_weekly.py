import json
import re
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


JIN10_SHFE_WEEKLY_STOCK_ALL_URL = (
    "https://cdn.jin10.com/dc/reports/dc_shfe_weekly_stock_all.js"
)
PREFER_LOCAL_SCRIPT = True


class FuturesStockWeeklyShfe(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_STOCK_WEEKLY_SHFE"
        self.create_table_sql = r"""
                                CREATE TABLE IF NOT EXISTS `FUTURES_STOCK_WEEKLY_SHFE` (
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
                                      UNIQUE KEY `IDX_SHFE_WEEKLY_STOCK_UNIQUE` (`PRODUCT_NAME`, `REPORT_DATE`),
                                      KEY `IDX_SHFE_WEEKLY_STOCK_DATE` (`REPORT_DATE`),
                                      KEY `IDX_SHFE_WEEKLY_STOCK_PRODUCT` (`PRODUCT_NAME`),
                                      KEY `IDX_SHFE_WEEKLY_STOCK_CODE` (`PRODUCT_CODE`)
                                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海期货交易所库存周报表';

                                """

    def _ensure_unique_index(self):
        rows = self.execute_sql(
            "SHOW INDEX FROM `FUTURES_STOCK_WEEKLY_SHFE` "
            "WHERE Key_name = 'IDX_SHFE_WEEKLY_STOCK_UNIQUE'",
            fetch_all=True,
        )
        if rows:
            return
        self.execute_sql(
            "ALTER TABLE `FUTURES_STOCK_WEEKLY_SHFE` "
            "ADD UNIQUE KEY `IDX_SHFE_WEEKLY_STOCK_UNIQUE` (`PRODUCT_NAME`, `REPORT_DATE`)"
        )

    @staticmethod
    def _coerce_stock_value(value):
        if isinstance(value, list):
            value = value[0] if value else None
        return pd.to_numeric(value, errors="coerce")

    def _fetch_jin10_weekly_stock_all(self, product_mapping: dict[str, dict[str, str]]):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://datacenter.jin10.com/reportType/dc_shfe_weekly_stock",
        }
        response = requests.get(JIN10_SHFE_WEEKLY_STOCK_ALL_URL, headers=headers, timeout=30)
        response.raise_for_status()
        match = re.search(r"var\s+dataCenter_data\s*=\s*(\{.*\})\s*;?\s*$", response.text, re.S)
        if not match:
            self.logger.warning("无法解析金十上期所库存周报全量 JS")
            return pd.DataFrame()
        data_json = json.loads(match.group(1))
        records = sorted(data_json.get("list") or [], key=lambda item: item.get("date") or "")
        rows = []
        previous_datas = {}
        for record in records:
            date_raw = str(record.get("date") or "")
            report_date = pd.to_datetime(date_raw, format="%Y%m%d", errors="coerce")
            if pd.isna(report_date):
                continue
            current_datas = record.get("datas") or {}
            for product_name, raw_value in current_datas.items():
                current_stock = self._coerce_stock_value(raw_value)
                if pd.isna(current_stock):
                    continue
                previous_stock = self._coerce_stock_value(previous_datas.get(product_name, [0]))
                if pd.isna(previous_stock):
                    previous_stock = 0
                change_amount = current_stock - previous_stock
                change_percent = change_amount / previous_stock if previous_stock else 0
                product_meta = product_mapping.get(product_name, {})
                rows.append(
                    {
                        "R_ID": self.get_uuid(),
                        "REFERENCE_CODE": "SHFE_WEEKLY_STOCK",
                        "REFERENCE_NAME": "上海期货交易所库存周报",
                        "PRODUCT_NAME": product_name,
                        "PRODUCT_CODE": product_meta.get("code"),
                        "REPORT_DATE": report_date.date(),
                        "CURRENT_WEEK_STOCK": float(current_stock),
                        "PREVIOUS_WEEK_STOCK": float(previous_stock),
                        "CHANGE_AMOUNT": float(change_amount),
                        "CHANGE_PERCENT": float(change_percent),
                        "UNIT": product_meta.get("unit"),
                        "CURRENCY": "CNY",
                        "DATA_SOURCE": "金十数据",
                        "CREATEDATE": self.get_current_datetime(),
                        "CREATEUSER": "system",
                        "UPDATEDATE": self.get_current_datetime(),
                        "UPDATEUSER": "system",
                    }
                )
            previous_datas = current_datas
        return pd.DataFrame(rows)

    def run(
        self,
        start_date=None,
        end_date=None,
        sleep_seconds=0.5,
        lookback_days=None,
        max_reports=None,
    ):
        """
        更新上海期货交易所库存周报数据。

        :param start_date: 开始日期，格式为'YYYY-MM-DD'，如果为None则从数据库最新日期或最早可用日期开始
        :param end_date: 结束日期，格式为'YYYY-MM-DD'，如果为None则为当前日期前一天
        :param sleep_seconds: 请求间隔秒数
        """
        # 如果当前表不存在，创建一个新的表
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self._ensure_unique_index()

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
            "中质含硫原油": {"code": "SC", "unit": "桶"},
            "20号胶": {"code": "NR", "unit": "吨"},
            "白银": {"code": "AG", "unit": "千克"},
        }

        try:
            lookback_days = int(lookback_days) if lookback_days is not None else None
            max_reports = int(max_reports) if max_reports is not None else None
            sleep_seconds = float(sleep_seconds or 0)
            # 1. Date Handling
            if end_date is None:
                end_date = self.get_current_date()

            if start_date is None:
                latest_date_in_db = self.get_latest_date(table_name, "REPORT_DATE")
                if latest_date_in_db:
                    start_date = latest_date_in_db
                    self.logger.info(f"最新数据日期: {latest_date_in_db}，从 {start_date} 开始更新")
                else:
                    start_date = "2014-05-23"
                    self.logger.info(f"无历史数据，从 {start_date} 开始获取")

            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            if lookback_days is not None:
                lookback_start = end_date_dt - timedelta(days=lookback_days)
                if start_date_dt < lookback_start:
                    start_date_dt = lookback_start
                    start_date = start_date_dt.strftime("%Y-%m-%d")
                    self.logger.info(f"限制库存周报更新为最近 {lookback_days} 天")

            if start_date_dt > end_date_dt:
                self.logger.info(
                    f"数据已是最新，无需更新。开始日期 {start_date} > 结束日期 {end_date}"
                )
                return

            df = self._fetch_jin10_weekly_stock_all(product_mapping)
            if df.empty:
                self.logger.warning("未获取到上海期货交易所库存周报全量数据")
                return pd.DataFrame()

            mask = (
                (pd.to_datetime(df["REPORT_DATE"]).dt.date >= start_date_dt)
                & (pd.to_datetime(df["REPORT_DATE"]).dt.date <= end_date_dt)
            )
            df = df.loc[mask].copy()
            if max_reports is not None and not df.empty:
                report_dates = sorted(df["REPORT_DATE"].drop_duplicates().tolist())
                keep_dates = set(report_dates[-max_reports:])
                df = df[df["REPORT_DATE"].isin(keep_dates)].copy()
                self.logger.info(f"限制库存周报更新为 {max_reports} 个报告日")

            if df.empty:
                self.logger.info("在指定范围内没有需要更新的周报日期")
                return pd.DataFrame()

            self.save_data(
                df,
                table_name,
                on_duplicate_update=True,
                unique_keys=["PRODUCT_NAME", "REPORT_DATE"],
            )
            self.logger.info(
                "成功保存上海期货交易所库存周报数据，共 %s 条记录，日期范围 %s 至 %s",
                len(df),
                df["REPORT_DATE"].min(),
                df["REPORT_DATE"].max(),
            )
            if sleep_seconds > 0:
                time.sleep(float(sleep_seconds))
            return df

        except Exception as e:
            self.logger.error(f"更新上海期货交易所库存周报数据失败: {str(e)}", exc_info=True)
            return pd.DataFrame()
        finally:
            self.disconnect_db()


if __name__ == "__main__":
    data_updater = FuturesStockWeeklyShfe()
    data_updater.run()
