"""
Stock Hsgt Hold Stock Em

数据源: AkShare
函数: stock_hsgt_hold_stock_em
频率: daily
"""

from __future__ import annotations

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


EASTMONEY_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_REFERER = "https://data.eastmoney.com/hsgtcg/list.html"
REPORT_NAME = "RPT_MUTUAL_STOCK_NORTHSTA_NEW"

MARKET_TO_MUTUAL_TYPE = {
    "沪股通": "001",
    "深股通": "003",
}
MUTUAL_TYPE_TO_MARKET = {
    "001": "沪股通",
    "003": "深股通",
}
INDICATOR_TO_INTERVAL_CODE = {
    "季排行": "001",
    "季度排行": "001",
    "年排行": "002",
    "年度排行": "002",
}
INTERVAL_CODE_TO_NAME = {
    "001": "季度排行",
    "002": "年度排行",
}


class StockHsgtHoldStockEm(AkshareToMySql):
    """Stock Hsgt Hold Stock Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_HSGT_HOLD_STOCK_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_HSGT_HOLD_STOCK_EM` (
        `R_ID` BIGINT AUTO_INCREMENT PRIMARY KEY,
        `request_market` VARCHAR(20) COMMENT '请求市场',
        `market` VARCHAR(20) COMMENT '市场',
        `mutual_type` VARCHAR(10) COMMENT '互联互通类型',
        `symbol` VARCHAR(20) NOT NULL COMMENT '股票代码',
        `name` VARCHAR(100) COMMENT '股票简称',
        `data_date` DATE NOT NULL COMMENT '持股日期',
        `interval_type_code` VARCHAR(10) NOT NULL COMMENT '排行周期代码',
        `interval_type` VARCHAR(30) COMMENT '排行周期',
        `date_type` VARCHAR(30) COMMENT '日期类型',
        `board_names` TEXT COMMENT '所属板块',
        `participant_num` BIGINT COMMENT '参与机构数',
        `a_shares_ratio` DOUBLE COMMENT 'A股占比',
        `hold_shares_ratio` DOUBLE COMMENT '持股比例',
        `hold_shares` BIGINT COMMENT '持股股数',
        `hold_market_cap` DOUBLE COMMENT '持股市值',
        `free_shares_ratio` DOUBLE COMMENT '占流通股比',
        `total_shares_ratio` DOUBLE COMMENT '占总股本比',
        `close_price` DOUBLE COMMENT '收盘价',
        `change_rate` DOUBLE COMMENT '涨跌幅',
        `freecap` DOUBLE COMMENT '流通市值',
        `total_market_cap` DOUBLE COMMENT '总市值',
        `freecap_hold_ratio` DOUBLE COMMENT '持股市值占流通市值比',
        `total_marketcap_hold_ratio` DOUBLE COMMENT '持股市值占总市值比',
        `add_market_cap` DOUBLE COMMENT '增持估计市值',
        `add_shares_repair` DOUBLE COMMENT '增持估计股数',
        `add_shares_amp` DOUBLE COMMENT '增持估计市值增幅',
        `freecap_ratio_chg` DOUBLE COMMENT '占流通股比变化',
        `total_ratio_chg` DOUBLE COMMENT '占总股本比变化',
        `total_shares` BIGINT COMMENT '总股本',
        `free_shares` BIGINT COMMENT '流通股本',
        `is_new` VARCHAR(10) COMMENT '是否最新',
        `report_date` DATETIME COMMENT '报告日期',
        `effective_date` DATETIME COMMENT '生效日期',
        `org_code` VARCHAR(50) COMMENT '机构代码',
        `source_report` VARCHAR(80) DEFAULT 'RPT_MUTUAL_STOCK_NORTHSTA_NEW' COMMENT '东方财富报表名',
        `data_source` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
        `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
        `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_market_symbol_date_interval (`request_market`, `mutual_type`, `symbol`, `data_date`, `interval_type_code`),
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_market_date (`market`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Hsgt Hold Stock Em'
    """

    @staticmethod
    def _eastmoney_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": EASTMONEY_REFERER,
        }

    def _request_eastmoney(self, params: dict[str, str | int]) -> dict:
        response = requests.get(
            EASTMONEY_DATACENTER_URL,
            params=params,
            headers=self._eastmoney_headers(),
            timeout=30,
        )
        response.raise_for_status()
        data_json = response.json()
        if data_json.get("code") not in (0, "0", None):
            self.logger.warning(
                "东方财富沪深港通持股接口返回空或错误: code=%s message=%s",
                data_json.get("code"),
                data_json.get("message"),
            )
        return data_json

    @staticmethod
    def _filter_expr(
        *,
        market: str,
        interval_code: str | None,
        hold_date: str | None = None,
    ) -> str:
        filters: list[str] = []
        mutual_type = MARKET_TO_MUTUAL_TYPE.get(market)
        if mutual_type:
            filters.append(f'(MUTUAL_TYPE="{mutual_type}")')
        elif market != "北向":
            raise ValueError("market must be one of: 北向, 沪股通, 深股通")
        if hold_date:
            filters.append(f"(HOLD_DATE='{hold_date}')")
        if interval_code:
            filters.append(f'(INTERVAL_TYPE_CODE="{interval_code}")')
        return "".join(filters)

    def _latest_hold_date(self, *, market: str, interval_code: str | None) -> str | None:
        params = {
            "sortColumns": "HOLD_DATE",
            "sortTypes": "-1",
            "pageSize": "1",
            "pageNumber": "1",
            "reportName": REPORT_NAME,
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
            "filter": self._filter_expr(market=market, interval_code=interval_code),
        }
        data_json = self._request_eastmoney(params)
        records = ((data_json.get("result") or {}).get("data") or [])
        if not records:
            return None
        value = records[0].get("HOLD_DATE")
        if not value:
            return None
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return str(value)[:10]
        return parsed.strftime("%Y-%m-%d")

    def _fetch_current_report(
        self,
        *,
        market: str,
        indicator: str,
        hold_date: str | None,
        page_size: int,
        max_pages: int,
    ) -> pd.DataFrame:
        interval_code = INDICATOR_TO_INTERVAL_CODE.get(indicator)
        if interval_code is None:
            self.logger.warning(
                "东方财富当前公开报表不再返回 %s，改用年度排行字段集",
                indicator,
            )
            interval_code = INDICATOR_TO_INTERVAL_CODE["年排行"]

        if hold_date is None:
            hold_date = self._latest_hold_date(market=market, interval_code=interval_code)
        if hold_date is None:
            return pd.DataFrame()

        page_size = max(1, min(int(page_size), 5000))
        max_pages = max(1, int(max_pages))
        filter_expr = self._filter_expr(
            market=market,
            interval_code=interval_code,
            hold_date=hold_date,
        )

        frames: list[pd.DataFrame] = []
        for page_number in range(1, max_pages + 1):
            params = {
                "sortColumns": "ADD_MARKET_CAP",
                "sortTypes": "-1",
                "pageSize": str(page_size),
                "pageNumber": str(page_number),
                "reportName": REPORT_NAME,
                "columns": "ALL",
                "source": "WEB",
                "client": "WEB",
                "filter": filter_expr,
            }
            data_json = self._request_eastmoney(params)
            result = data_json.get("result") or {}
            records = result.get("data") or []
            if not records:
                break
            frames.append(pd.DataFrame(records))
            pages = int(result.get("pages") or 0)
            if pages and page_number >= pages:
                break

        if not frames:
            return pd.DataFrame()
        raw_df = pd.concat(frames, ignore_index=True)
        return self.normalize_columns(raw_df, request_market=market)

    @staticmethod
    def _join_unique(values: pd.Series) -> str | None:
        unique_values = [
            str(value).strip()
            for value in values.dropna().tolist()
            if str(value).strip()
        ]
        if not unique_values:
            return None
        return ",".join(dict.fromkeys(unique_values))

    @classmethod
    def normalize_columns(cls, df: pd.DataFrame, *, request_market: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        normalized = pd.DataFrame(index=df.index)
        normalized["request_market"] = request_market
        normalized["market"] = df["MUTUAL_TYPE"].astype(str).map(MUTUAL_TYPE_TO_MARKET)
        normalized["mutual_type"] = df["MUTUAL_TYPE"].astype(str)
        normalized["symbol"] = df["SECURITY_CODE"].astype(str).str.zfill(6)
        normalized["name"] = df["SECURITY_NAME_ABBR"]
        normalized["data_date"] = pd.to_datetime(df["HOLD_DATE"], errors="coerce").dt.date
        normalized["interval_type_code"] = df["INTERVAL_TYPE_CODE"].astype(str)
        normalized["interval_type"] = df["INTERVAL_TYPE"].fillna(
            df["INTERVAL_TYPE_CODE"].astype(str).map(INTERVAL_CODE_TO_NAME)
        )
        normalized["date_type"] = df["DATE_TYPE"]
        normalized["board_name"] = df.get("BOARD_NAME")

        direct_columns = {
            "PARTICIPANT_NUM": "participant_num",
            "A_SHARES_RATIO": "a_shares_ratio",
            "HOLD_SHARES_RATIO": "hold_shares_ratio",
            "HOLD_SHARES": "hold_shares",
            "HOLD_MARKET_CAP": "hold_market_cap",
            "FREE_SHARES_RATIO": "free_shares_ratio",
            "TOTAL_SHARES_RATIO": "total_shares_ratio",
            "CLOSE_PRICE": "close_price",
            "CHANGE_RATE": "change_rate",
            "FREECAP": "freecap",
            "TOTAL_MARKET_CAP": "total_market_cap",
            "FREECAP_HOLD_RATIO": "freecap_hold_ratio",
            "TOTAL_MARKETCAP_HOLD_RATIO": "total_marketcap_hold_ratio",
            "ADD_MARKET_CAP": "add_market_cap",
            "ADD_SHARES_REPAIR": "add_shares_repair",
            "ADD_SHARES_AMP": "add_shares_amp",
            "FREECAP_RATIO_CHG": "freecap_ratio_chg",
            "TOTAL_RATIO_CHG": "total_ratio_chg",
            "TOTAL_SHARES": "total_shares",
            "FREE_SHARES": "free_shares",
            "IS_NEW": "is_new",
            "REPORTDATE": "report_date",
            "EFFECTIVE_DATE": "effective_date",
            "ORG_CODE": "org_code",
        }
        for source_col, target_col in direct_columns.items():
            normalized[target_col] = df.get(source_col)

        for date_col in ["report_date", "effective_date"]:
            normalized[date_col] = pd.to_datetime(normalized[date_col], errors="coerce")

        numeric_columns = [
            "participant_num",
            "a_shares_ratio",
            "hold_shares_ratio",
            "hold_shares",
            "hold_market_cap",
            "free_shares_ratio",
            "total_shares_ratio",
            "close_price",
            "change_rate",
            "freecap",
            "total_market_cap",
            "freecap_hold_ratio",
            "total_marketcap_hold_ratio",
            "add_market_cap",
            "add_shares_repair",
            "add_shares_amp",
            "freecap_ratio_chg",
            "total_ratio_chg",
            "total_shares",
            "free_shares",
        ]
        for col in numeric_columns:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

        group_cols = [
            "request_market",
            "market",
            "mutual_type",
            "symbol",
            "name",
            "data_date",
            "interval_type_code",
            "interval_type",
            "date_type",
        ]
        agg_map = {
            "board_name": cls._join_unique,
        }
        for col in normalized.columns:
            if col not in group_cols and col not in agg_map:
                agg_map[col] = "first"

        normalized = (
            normalized.groupby(group_cols, dropna=False, as_index=False)
            .agg(agg_map)
            .rename(columns={"board_name": "board_names"})
        )
        normalized["source_report"] = REPORT_NAME
        normalized["data_source"] = "东方财富"

        front_columns = [
            "request_market",
            "market",
            "mutual_type",
            "symbol",
            "name",
            "data_date",
            "interval_type_code",
            "interval_type",
            "date_type",
            "board_names",
        ]
        ordered = [col for col in front_columns if col in normalized.columns]
        ordered.extend(col for col in normalized.columns if col not in ordered)
        return normalized[ordered]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_hsgt_hold_stock_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            market = kwargs.pop("market", "沪股通")
            indicator = kwargs.pop("indicator", "年排行")
            hold_date = kwargs.pop("hold_date", None)
            page_size = int(kwargs.pop("page_size", 5000))
            max_pages = int(kwargs.pop("max_pages", 1))

            # 东方财富旧 RPT_MUTUAL_STOCK_NORTHSTA 报表当前返回 9701。
            # 同一页面已暴露新的 RPT_MUTUAL_STOCK_NORTHSTA_NEW 字段集，直接走当前报表。
            df = self._fetch_current_report(
                market=market,
                indicator=indicator,
                hold_date=hold_date,
                page_size=page_size,
                max_pages=max_pages,
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
                unique_keys=[
                    "request_market",
                    "mutual_type",
                    "symbol",
                    "data_date",
                    "interval_type_code",
                ],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockHsgtHoldStockEm()
    script.run()


if __name__ == "__main__":
    main()
