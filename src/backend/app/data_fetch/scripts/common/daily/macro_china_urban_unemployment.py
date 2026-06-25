"""
Macro China Urban Unemployment

数据源: AkShare
函数: macro_china_urban_unemployment
频率: daily
"""

import hashlib

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class MacroChinaUrbanUnemployment(AkshareToMySql):
    """Macro China Urban Unemployment"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MACRO_CHINA_URBAN_UNEMPLOYMENT"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `MACRO_CHINA_URBAN_UNEMPLOYMENT` (
            `R_ID` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `record_key` CHAR(32) NOT NULL COMMENT '唯一键',
            `data_period` VARCHAR(16) NOT NULL COMMENT '数据期',
            `period_name` VARCHAR(32) COMMENT '数据期名称',
            `data_date` DATE COMMENT '数据日期',
            `indicator_id` VARCHAR(64) NOT NULL COMMENT '指标ID',
            `indicator_name` VARCHAR(255) COMMENT '指标名称',
            `category_name` VARCHAR(255) COMMENT '分类名称',
            `region_name` VARCHAR(64) COMMENT '地区',
            `value` DOUBLE COMMENT '数值',
            `unit` VARCHAR(32) COMMENT '单位',
            `source_url` TEXT COMMENT '数据源地址',
            `fetched_at` DATETIME COMMENT '抓取时间',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_record_key (`record_key`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Macro China Urban Unemployment'
    """
        self.source_url = (
            "https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData"
        )
        self.payload = {
            "cid": "ee3b7046b390415b9b7745e3d16f6052",
            "indicatorIds": [
                "3888eac6062945a79c8a27e5f13d4953",
                "1d550f3ec77a463bb607d4a3427e1465",
                "1c1b2d9ab24048bfadc5c7d9510dc663",
                "3921da310de24f14b6457c235657baf9",
                "bd6da1abb26046c2acb38aa701d90e86",
                "7bc1bd5daeac48ae8bb413c34ece1d08",
                "c03a36c9562246b6bc8aab010951ef1c",
                "1061f276ce354907b0b9900c266cf851",
                "40ab91b1ef4948e89633c5c7f55b9713",
            ],
            "daCatalogId": "",
            "das": [{"text": "全国", "value": "000000000000"}],
            "dts": ["199001MM-203601MM"],
            "showType": "1",
            "rootId": "fc982599aa684be7969d7b90b1bd0e84",
        }

    @staticmethod
    def _record_key(*parts: object) -> str:
        raw = "\x1f".join("" if part is None else str(part) for part in parts)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _period_to_date(period: str):
        if not period or len(period) < 6:
            return None
        return pd.to_datetime(period[:6] + "01", format="%Y%m%d", errors="coerce")

    def _fetch_nbs_stream_data(self) -> pd.DataFrame:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Referer": "https://data.stats.gov.cn/dg/website/page.html#/pc/national/monthData",
        }
        response = requests.post(self.source_url, json=self.payload, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or []
        fetched_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        records = []
        for month_item in data:
            period = month_item.get("code")
            for value_item in month_item.get("values") or []:
                value = str(value_item.get("value") or "").strip()
                if not value:
                    continue
                indicator_id = value_item.get("_id")
                record = {
                    "data_period": period,
                    "period_name": month_item.get("name"),
                    "data_date": self._period_to_date(period),
                    "indicator_id": indicator_id,
                    "indicator_name": str(value_item.get("i_showname") or "").strip(),
                    "category_name": str(value_item.get("_name") or "").strip(),
                    "region_name": value_item.get("da_name"),
                    "value": pd.to_numeric(value, errors="coerce"),
                    "unit": value_item.get("du_name"),
                    "source_url": self.source_url,
                    "fetched_at": fetched_at,
                }
                record["record_key"] = self._record_key(period, indicator_id, record["region_name"])
                records.append(record)
        return pd.DataFrame(records)

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.macro_china_urban_unemployment

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            df = self._fetch_nbs_stream_data()
        except Exception as e:
            self.logger.error(f"Error fetching NBS urban unemployment data: {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            self.logger.warning("No data found")
            return pd.DataFrame()

        self.create_table_if_not_exists(self.table_name, self.create_table_sql)
        self.save_data(
            df,
            self.table_name,
            on_duplicate_update=True,
            unique_keys=["record_key"],
        )

        return df


def main():
    """Main function to run the data fetch"""

    script = MacroChinaUrbanUnemployment()
    script.fetch_data()


if __name__ == "__main__":
    main()
