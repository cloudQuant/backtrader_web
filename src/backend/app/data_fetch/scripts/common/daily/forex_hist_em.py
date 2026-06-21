"""
Forex Hist Em

数据源: AkShare
函数: forex_hist_em
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


PREFER_LOCAL_SCRIPT = True


def _normalise_symbols(kwargs: dict, spot_df: pd.DataFrame | None = None) -> list[str]:
    if "symbols" in kwargs:
        symbols = kwargs["symbols"]
        if isinstance(symbols, str):
            return [item.strip() for item in symbols.split(",") if item.strip()]
        if isinstance(symbols, list):
            return [str(item).strip() for item in symbols if str(item).strip()]
        raise TypeError("symbols must be a comma separated string or list")

    if "symbol" in kwargs and kwargs["symbol"]:
        return [str(kwargs["symbol"]).strip()]

    if spot_df is None or spot_df.empty or "代码" not in spot_df.columns:
        return []
    return spot_df["代码"].dropna().astype(str).drop_duplicates().tolist()


class ForexHistEm(AkshareToMySql):
    """Forex Hist Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FOREX_HIST_EM"
        self.create_table_sql = """
	    CREATE TABLE IF NOT EXISTS `FOREX_HIST_EM` (
	        `R_ID` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `日期` DATE COMMENT '交易日期',
            `代码` VARCHAR(32) COMMENT '品种代码',
            `名称` VARCHAR(100) COMMENT '品种名称',
            `今开` DOUBLE COMMENT '今开',
            `最新价` DOUBLE COMMENT '最新价',
            `最高` DOUBLE COMMENT '最高',
            `最低` DOUBLE COMMENT '最低',
            `振幅` DOUBLE COMMENT '振幅',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
	        UNIQUE KEY uk_code_date (`代码`, `日期`),
	        INDEX idx_date (`日期`)
	    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Forex Hist Em'
	    """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.forex_hist_em

        Returns:
            pd.DataFrame: Fetched data
        """
        self.create_table_if_not_exists(self.table_name, self.create_table_sql)
        spot_df = None
        if "symbol" not in kwargs and "symbols" not in kwargs:
            try:
                spot_df = self.fetch_ak_data("forex_spot_em", _call_timeout=60)
            except Exception as e:
                self.logger.warning(f"Failed to fetch forex spot symbols: {e}")
                return pd.DataFrame()

        symbols = _normalise_symbols(kwargs, spot_df)
        if not symbols:
            self.logger.warning("No forex symbols found")
            return pd.DataFrame()

        frames = []
        for symbol in symbols:
            try:
                df = self.fetch_ak_data("forex_hist_em", symbol=symbol, _call_timeout=60)
            except Exception as e:
                self.logger.warning(f"Failed to fetch forex history for {symbol}: {e}")
                continue
            if df is not None and not df.empty:
                frames.append(df)

        if not frames:
            self.logger.warning("No forex history data found")
            return pd.DataFrame()

        result = pd.concat(frames, ignore_index=True)
        self.save_data(
            result,
            self.table_name,
            on_duplicate_update=True,
            unique_keys=["代码", "日期"],
        )
        return result


def main():
    """Main function to run the data fetch"""

    script = ForexHistEm()
    script.run()


if __name__ == "__main__":
    main()
