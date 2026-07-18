"""
Stock Industry Pe Ratio Cninfo

数据源: AkShare
函数: stock_industry_pe_ratio_cninfo
频率: weekly
"""

import hashlib
from datetime import datetime, timedelta

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

PREFER_LOCAL_SCRIPT = True


class StockIndustryPeRatioCninfo(AkshareToMySql):
    """Stock Industry Pe Ratio Cninfo"""

    DEFAULT_SYMBOLS = ("证监会行业分类", "国证行业分类")

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_INDUSTRY_PE_RATIO_CNINFO"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_INDUSTRY_PE_RATIO_CNINFO` (
        `R_ID` VARCHAR(64) NOT NULL PRIMARY KEY,
        `TRADE_DATE` DATE NOT NULL COMMENT '变动日期',
        `INDUSTRY_CATEGORY` VARCHAR(100) NOT NULL COMMENT '行业分类',
        `INDUSTRY_LEVEL` INT COMMENT '行业层级',
        `INDUSTRY_CODE` VARCHAR(50) NOT NULL COMMENT '行业编码',
        `INDUSTRY_NAME` VARCHAR(100) COMMENT '行业名称',
        `COMPANY_COUNT` DECIMAL(20, 4) COMMENT '公司数量',
        `CALC_COMPANY_COUNT` DECIMAL(20, 4) COMMENT '纳入计算公司数量',
        `TOTAL_MARKET_VALUE_STATIC` DECIMAL(24, 4) COMMENT '总市值-静态(亿元)',
        `NET_PROFIT_STATIC` DECIMAL(24, 4) COMMENT '净利润-静态(亿元)',
        `PE_WEIGHTED_STATIC` DECIMAL(20, 4) COMMENT '静态市盈率-加权平均',
        `PE_MEDIAN_STATIC` DECIMAL(20, 4) COMMENT '静态市盈率-中位数',
        `PE_AVG_STATIC` DECIMAL(20, 4) COMMENT '静态市盈率-算术平均',
        `DATA_SOURCE` VARCHAR(50) DEFAULT '巨潮资讯' COMMENT '数据来源',
        `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
        `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_trade_category_code (`TRADE_DATE`, `INDUSTRY_CATEGORY`, `INDUSTRY_CODE`, `INDUSTRY_LEVEL`),
        INDEX idx_trade_date (`TRADE_DATE`),
        INDEX idx_industry_code (`INDUSTRY_CODE`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Industry Pe Ratio Cninfo'
    """

    @staticmethod
    def _stable_id(row: pd.Series) -> str:
        key = "|".join(
            [
                str(row.get("TRADE_DATE", "")),
                str(row.get("INDUSTRY_CATEGORY", "")),
                str(row.get("INDUSTRY_CODE", "")),
                str(row.get("INDUSTRY_LEVEL", "")),
            ]
        )
        return hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest().upper()

    @staticmethod
    def _normalize_date(value) -> str:
        if value is None:
            return ""
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return ""
        return parsed.strftime("%Y%m%d")

    @classmethod
    def _candidate_dates(cls, date=None, lookback_days=10) -> list[str]:
        normalized = cls._normalize_date(date)
        if normalized:
            return [normalized]
        today = datetime.now().date()
        return [
            (today - timedelta(days=offset)).strftime("%Y%m%d")
            for offset in range(max(1, int(lookback_days)))
        ]

    @staticmethod
    def normalize_pe_data(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        column_map = {
            "变动日期": "TRADE_DATE",
            "行业分类": "INDUSTRY_CATEGORY",
            "行业层级": "INDUSTRY_LEVEL",
            "行业编码": "INDUSTRY_CODE",
            "行业名称": "INDUSTRY_NAME",
            "公司数量": "COMPANY_COUNT",
            "纳入计算公司数量": "CALC_COMPANY_COUNT",
            "总市值-静态": "TOTAL_MARKET_VALUE_STATIC",
            "净利润-静态": "NET_PROFIT_STATIC",
            "静态市盈率-加权平均": "PE_WEIGHTED_STATIC",
            "静态市盈率-中位数": "PE_MEDIAN_STATIC",
            "静态市盈率-算术平均": "PE_AVG_STATIC",
        }
        if not set(column_map).issubset(df.columns):
            return pd.DataFrame()

        normalized = df[list(column_map)].rename(columns=column_map).copy()
        normalized["TRADE_DATE"] = pd.to_datetime(normalized["TRADE_DATE"], errors="coerce").dt.date
        normalized["INDUSTRY_LEVEL"] = pd.to_numeric(normalized["INDUSTRY_LEVEL"], errors="coerce")
        for column in [
            "COMPANY_COUNT",
            "CALC_COMPANY_COUNT",
            "TOTAL_MARKET_VALUE_STATIC",
            "NET_PROFIT_STATIC",
            "PE_WEIGHTED_STATIC",
            "PE_MEDIAN_STATIC",
            "PE_AVG_STATIC",
        ]:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
        normalized.dropna(
            subset=["TRADE_DATE", "INDUSTRY_CATEGORY", "INDUSTRY_CODE"],
            inplace=True,
        )
        normalized["R_ID"] = normalized.apply(StockIndustryPeRatioCninfo._stable_id, axis=1)
        normalized["DATA_SOURCE"] = "巨潮资讯"
        return normalized[
            [
                "R_ID",
                "TRADE_DATE",
                "INDUSTRY_CATEGORY",
                "INDUSTRY_LEVEL",
                "INDUSTRY_CODE",
                "INDUSTRY_NAME",
                "COMPANY_COUNT",
                "CALC_COMPANY_COUNT",
                "TOTAL_MARKET_VALUE_STATIC",
                "NET_PROFIT_STATIC",
                "PE_WEIGHTED_STATIC",
                "PE_MEDIAN_STATIC",
                "PE_AVG_STATIC",
                "DATA_SOURCE",
            ]
        ]

    def _prepare_table_schema(self) -> None:
        self.connect_db()
        try:
            self.cursor.execute(f"SHOW TABLES LIKE '{self.table_name}'")
            exists = bool(self.cursor.fetchone())
            if exists:
                self.cursor.execute(f"SHOW COLUMNS FROM `{self.table_name}`")
                columns = [row[0] for row in self.cursor.fetchall() or []]
                self.cursor.execute(f"SELECT COUNT(*) FROM `{self.table_name}`")
                row_count = int((self.cursor.fetchone() or [0])[0] or 0)
                expected = {"R_ID", "TRADE_DATE", "INDUSTRY_CATEGORY", "INDUSTRY_CODE"}
                if row_count == 0 and not expected.issubset(set(columns)):
                    self.cursor.execute(f"DROP TABLE `{self.table_name}`")
                    self.connection.commit()
                    self._columns_cache.pop(self.table_name, None)
                    self._table_exists_cache.pop(self.table_name, None)
                    exists = False
            if not exists:
                self.cursor.execute(self.create_table_sql)
                self.connection.commit()
                self._columns_cache.pop(self.table_name, None)
                self._table_exists_cache[self.table_name] = True
        finally:
            self.disconnect_db()

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_industry_pe_ratio_cninfo

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            params = dict(kwargs)
            lookback_days = int(params.pop("lookback_days", 10) or 10)
            requested_symbol = params.pop("symbol", None)
            requested_date = params.pop("date", None)
            symbols = [requested_symbol] if requested_symbol else list(self.DEFAULT_SYMBOLS)

            df = pd.DataFrame()
            for candidate_date in self._candidate_dates(requested_date, lookback_days):
                frames = []
                for symbol in symbols:
                    try:
                        raw_df = self.fetch_ak_data(
                            "stock_industry_pe_ratio_cninfo",
                            symbol=symbol,
                            date=candidate_date,
                            _call_timeout=20,
                        )
                    except Exception as exc:
                        self.logger.warning(
                            "Failed to fetch industry PE for %s on %s: %s",
                            symbol,
                            candidate_date,
                            exc,
                        )
                        continue
                    normalized_df = self.normalize_pe_data(raw_df)
                    if not normalized_df.empty:
                        frames.append(normalized_df)
                if frames:
                    df = pd.concat(frames, ignore_index=True)
                    self.logger.info(
                        "Fetched industry PE data for %s with %s rows",
                        candidate_date,
                        len(df),
                    )
                    break

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Save to database
            self._prepare_table_schema()
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=[
                    "TRADE_DATE",
                    "INDUSTRY_CATEGORY",
                    "INDUSTRY_CODE",
                    "INDUSTRY_LEVEL",
                ],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockIndustryPeRatioCninfo()
    script.run()


if __name__ == "__main__":
    main()
