"""
Air Quality Hist

数据源: AkShare
函数: air_quality_hist
频率: weekly
"""

import re
from datetime import date, datetime, timedelta
from io import StringIO

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class AirQualityHist(AkshareToMySql):
    """Air Quality Hist"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "AIR_QUALITY_HIST"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `AIR_QUALITY_HIST` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `city` VARCHAR(64) NOT NULL COMMENT '城市',
            `province` VARCHAR(64) COMMENT '省份',
            `period` VARCHAR(16) NOT NULL COMMENT '周期',
            `data_date` DATE NOT NULL COMMENT '数据日期',
            `rank_no` INT COMMENT '排名',
            `aqi` DOUBLE COMMENT 'AQI',
            `quality` VARCHAR(32) COMMENT '空气质量',
            `pm25` DOUBLE COMMENT 'PM2.5浓度',
            `primary_pollutant` VARCHAR(64) COMMENT '首要污染物',
            `source_url` TEXT COMMENT '数据源地址',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_city_period_date (`city`, `period`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Air Quality Hist'
    """
        self.source_url = "https://www.zq12369.com/environment.php"

    @staticmethod
    def _parse_yyyymmdd(value: str | None) -> date | None:
        if not value:
            return None
        raw = str(value).strip()
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Unsupported date format: {value}")

    @staticmethod
    def _parse_pm25(value):
        if pd.isna(value):
            return None
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else None

    def _fetch_daily_rank_for_date(self, city: str, day: date) -> pd.DataFrame:
        params = {
            "date": day.strftime("%Y-%m-%d"),
            "tab": "rank",
            "order": "DESC",
            "type": "DAY",
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        }
        response = requests.get(self.source_url, params=params, headers=headers, timeout=20)
        response.raise_for_status()

        tables = pd.read_html(StringIO(response.text))
        if len(tables) < 2:
            return pd.DataFrame()

        daily_df = tables[1].iloc[1:].copy()
        if daily_df.empty or "城市" not in daily_df.columns:
            return pd.DataFrame()

        row_df = daily_df[daily_df["城市"].astype(str).str.strip() == city].copy()
        if row_df.empty:
            return pd.DataFrame()

        row_df.rename(
            columns={
                "降序": "rank_no",
                "省份": "province",
                "城市": "city",
                "AQI": "aqi",
                "空气质量": "quality",
                "PM2.5浓度": "pm25",
                "首要污染物": "primary_pollutant",
            },
            inplace=True,
        )
        row_df["period"] = "day"
        row_df["data_date"] = day
        row_df["source_url"] = response.url
        row_df["rank_no"] = pd.to_numeric(row_df["rank_no"], errors="coerce").astype("Int64")
        row_df["aqi"] = pd.to_numeric(row_df["aqi"], errors="coerce")
        row_df["pm25"] = row_df["pm25"].map(self._parse_pm25)
        row_df["primary_pollutant"] = row_df["primary_pollutant"].where(
            pd.notna(row_df["primary_pollutant"]), None
        )
        return row_df[
            [
                "city",
                "province",
                "period",
                "data_date",
                "rank_no",
                "aqi",
                "quality",
                "pm25",
                "primary_pollutant",
                "source_url",
            ]
        ]

    def _fetch_daily_rank_history(
        self,
        city: str = "杭州",
        start_date: str | None = None,
        end_date: str | None = None,
        lookback_days: int = 7,
    ) -> pd.DataFrame:
        end_day = self._parse_yyyymmdd(end_date) or (date.today() - timedelta(days=1))
        start_day = self._parse_yyyymmdd(start_date) or (
            end_day - timedelta(days=max(lookback_days, 1) - 1)
        )
        if start_day > end_day:
            start_day, end_day = end_day, start_day

        frames = []
        current = start_day
        while current <= end_day:
            try:
                day_df = self._fetch_daily_rank_for_date(city, current)
                if not day_df.empty:
                    frames.append(day_df)
            except Exception as exc:
                self.logger.warning("Fetch zq12369 daily rank failed for %s: %s", current, exc)
            current += timedelta(days=1)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to same-source zq12369 fetch

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            city = kwargs.pop("city", "杭州")
            period = str(kwargs.pop("period", "day")).lower()
            start_date = kwargs.pop("start_date", None)
            end_date = kwargs.pop("end_date", None)
            lookback_days = int(kwargs.pop("lookback_days", 7))

            if period != "day":
                self.logger.warning("Only day period is available from zq12369 rank pages")
                return pd.DataFrame()

            df = self._fetch_daily_rank_history(
                city=city,
                start_date=start_date,
                end_date=end_date,
                lookback_days=lookback_days,
            )

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["city", "period", "data_date"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = AirQualityHist()
    script.fetch_data()


if __name__ == "__main__":
    main()
