"""
Futures To Spot Shfe

数据源: 上海期货交易所
频率: hourly
"""

import time
from datetime import datetime

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


SHFE_MONTHDATA_URL = "https://www.shfe.com.cn/data/tradedata/future/monthdata"
PREFER_LOCAL_SCRIPT = True


class FuturesToSpotShfe(AkshareToMySql):
    """上海期货交易所交割查询（含期转现量）"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_TO_SPOT_SHFE"
        self.create_table_sql = """
            CREATE TABLE IF NOT EXISTS `FUTURES_TO_SPOT_SHFE` (
                `R_ID` VARCHAR(64) NOT NULL COMMENT '主键ID',
                `TRADE_MONTH` VARCHAR(6) NOT NULL COMMENT '统计月份(YYYYMM)',
                `DELIVERY_DAY` DATE NOT NULL COMMENT '交割日期',
                `INSTRUMENT_ID` VARCHAR(32) NOT NULL COMMENT '合约',
                `DELIVERY_VOLUME` DECIMAL(20, 4) COMMENT '交割量',
                `DELIVERY_AMOUNT` DECIMAL(24, 4) COMMENT '交割金额',
                `EXCHANGE_DELIVERY_VOLUME` DECIMAL(20, 4) COMMENT '期转现量',
                `EXCHANGE_DELIVERY_AMOUNT` DECIMAL(24, 4) COMMENT '期转现金额',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '上海期货交易所' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                PRIMARY KEY (`R_ID`),
                UNIQUE KEY `IDX_SHFE_TO_SPOT_UNIQUE` (`TRADE_MONTH`, `DELIVERY_DAY`, `INSTRUMENT_ID`),
                KEY `IDX_SHFE_TO_SPOT_MONTH` (`TRADE_MONTH`),
                KEY `IDX_SHFE_TO_SPOT_DAY` (`DELIVERY_DAY`),
                KEY `IDX_SHFE_TO_SPOT_INSTRUMENT` (`INSTRUMENT_ID`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上海期货交易所交割查询';
        """

    @staticmethod
    def _next_month(month: str) -> str:
        month_dt = datetime.strptime(month, "%Y%m")
        if month_dt.month == 12:
            return month_dt.replace(year=month_dt.year + 1, month=1).strftime("%Y%m")
        return month_dt.replace(month=month_dt.month + 1).strftime("%Y%m")

    @staticmethod
    def _iter_months(start_month: str, end_month: str):
        current = datetime.strptime(start_month, "%Y%m")
        end = datetime.strptime(end_month, "%Y%m")
        while current <= end:
            yield current.strftime("%Y%m")
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    @staticmethod
    def _subtract_months(month: str, months: int) -> str:
        month_dt = datetime.strptime(month, "%Y%m")
        total_months = month_dt.year * 12 + month_dt.month - 1 - max(months - 1, 0)
        return datetime(total_months // 12, total_months % 12 + 1, 1).strftime("%Y%m")

    def _ensure_unique_index(self):
        rows = self.execute_sql(
            "SHOW INDEX FROM `FUTURES_TO_SPOT_SHFE` "
            "WHERE Key_name = 'IDX_SHFE_TO_SPOT_UNIQUE'",
            fetch_all=True,
        )
        if rows:
            return
        self.execute_sql(
            "ALTER TABLE `FUTURES_TO_SPOT_SHFE` "
            "ADD UNIQUE KEY `IDX_SHFE_TO_SPOT_UNIQUE` (`TRADE_MONTH`, `DELIVERY_DAY`, `INSTRUMENT_ID`)"
        )

    def _fetch_month(self, trade_month: str) -> pd.DataFrame:
        url = f"{SHFE_MONTHDATA_URL}/ExchangeDelivery{trade_month}.dat"
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
                rows = data_json.get("ExchangeDelivery") or []
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows)
                rename_map = {
                    "INSTRUMENTID": "INSTRUMENT_ID",
                    "DELIVERYDAY": "DELIVERY_DAY",
                    "DELIVERYVOLUME": "DELIVERY_VOLUME",
                    "DELIVERYAMOUNT": "DELIVERY_AMOUNT",
                    "EXCHANGE_DELIVERYVOLUME": "EXCHANGE_DELIVERY_VOLUME",
                    "EXCHANGE_DELIVERYAMOUNT": "EXCHANGE_DELIVERY_AMOUNT",
                }
                df = df.rename(columns=rename_map)
                for col in rename_map.values():
                    if col not in df.columns:
                        df[col] = None
                df["DELIVERY_DAY"] = pd.to_datetime(
                    df["DELIVERY_DAY"], format="%Y%m%d", errors="coerce"
                ).dt.date
                for col in [
                    "DELIVERY_VOLUME",
                    "DELIVERY_AMOUNT",
                    "EXCHANGE_DELIVERY_VOLUME",
                    "EXCHANGE_DELIVERY_AMOUNT",
                ]:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
                df.dropna(subset=["DELIVERY_DAY", "INSTRUMENT_ID"], inplace=True)
                if df.empty:
                    return pd.DataFrame()
                df["TRADE_MONTH"] = trade_month
                df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
                df["DATA_SOURCE"] = "上海期货交易所"
                df["CREATEDATE"] = self.get_current_datetime()
                df["CREATEUSER"] = "system"
                df["UPDATEDATE"] = self.get_current_datetime()
                df["UPDATEUSER"] = "system"
                columns = [
                    "R_ID",
                    "TRADE_MONTH",
                    "DELIVERY_DAY",
                    "INSTRUMENT_ID",
                    "DELIVERY_VOLUME",
                    "DELIVERY_AMOUNT",
                    "EXCHANGE_DELIVERY_VOLUME",
                    "EXCHANGE_DELIVERY_AMOUNT",
                    "DATA_SOURCE",
                    "CREATEDATE",
                    "CREATEUSER",
                    "UPDATEDATE",
                    "UPDATEUSER",
                ]
                return df[columns]
            except Exception as exc:
                last_error = exc
                time.sleep(1 + attempt)
        self.logger.warning("上期所交割查询请求失败 %s: %s", trade_month, last_error)
        return pd.DataFrame()

    def run(
        self,
        start_month: str | None = None,
        end_month: str | None = None,
        lookback_months: int | None = None,
        max_months: int | None = None,
        sleep_seconds: float = 0,
    ):
        if not self.table_exists(self.table_name):
            self.create_table(self.create_table_sql)
        self._ensure_unique_index()

        if end_month is None:
            end_month = self.get_previous_month()
        if start_month is None:
            latest_month = self.get_latest_date(self.table_name, "TRADE_MONTH")
            start_month = latest_month or "201809"
        if lookback_months is not None:
            lookback_start = self._subtract_months(end_month, int(lookback_months))
            if start_month < lookback_start:
                start_month = lookback_start

        months = list(self._iter_months(start_month, end_month))
        if max_months is not None:
            months = months[-int(max_months) :]
        frames = []
        for trade_month in months:
            df = self._fetch_month(trade_month)
            if df.empty:
                self.logger.warning("未获取到 %s 的上期所交割查询数据", trade_month)
                continue
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["TRADE_MONTH", "DELIVERY_DAY", "INSTRUMENT_ID"],
            )
            frames.append(df)
            if sleep_seconds:
                time.sleep(float(sleep_seconds))

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def fetch_data(self, **kwargs):
        return self.run(**kwargs)


def main():
    script = FuturesToSpotShfe()
    return script.run()


if __name__ == "__main__":
    main()
