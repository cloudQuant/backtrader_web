"""
Option Sse Minute Sina

数据源: AkShare
函数: option_sse_minute_sina
频率: hourly
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class OptionSseMinuteSina(AkshareToMySql):
    """Option Sse Minute Sina"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "OPTION_SSE_MINUTE_SINA"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `OPTION_SSE_MINUTE_SINA` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Option Sse Minute Sina'
    """

    def resolve_symbol(
        self,
        *,
        option_type: str = "看涨期权",
        trade_date: str | None = None,
        underlying: str = "510050",
        call_timeout: int | None = None,
    ) -> str | None:
        trade_date = trade_date or pd.Timestamp.now().strftime("%Y%m")
        kwargs = {
            "symbol": option_type,
            "trade_date": trade_date,
            "underlying": underlying,
        }
        if call_timeout is not None:
            kwargs["_call_timeout"] = call_timeout
        codes_df = self.fetch_ak_data("option_sse_codes_sina", **kwargs)
        if codes_df is None or codes_df.empty or "期权代码" not in codes_df.columns:
            return None
        return str(codes_df["期权代码"].dropna().astype(str).iloc[0])

    @staticmethod
    def normalize_columns(df: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        df["symbol"] = str(symbol)
        df["name"] = str(symbol)
        if "日期" in df.columns:
            df["data_date"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
        elif "data_date" not in df.columns:
            df["data_date"] = pd.Timestamp.now().date()
        front_columns = ["symbol", "name", "data_date"]
        ordered = [col for col in front_columns if col in df.columns]
        ordered.extend(col for col in df.columns if col not in ordered)
        return df[ordered]

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.option_sse_minute_sina

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            call_timeout = kwargs.pop("_call_timeout", None)
            symbol = kwargs.pop("symbol", None)
            option_type = kwargs.pop("option_type", "看涨期权")
            trade_date = kwargs.pop("trade_date", None)
            underlying = kwargs.pop("underlying", "510050")
            if symbol is None:
                symbol = self.resolve_symbol(
                    option_type=option_type,
                    trade_date=trade_date,
                    underlying=underlying,
                    call_timeout=call_timeout,
                )
            if not symbol:
                self.logger.warning("No option symbol found")
                return pd.DataFrame()

            fetch_kwargs = {"symbol": str(symbol)}
            if call_timeout is not None:
                fetch_kwargs["_call_timeout"] = call_timeout
            df = self.fetch_ak_data("option_sse_minute_sina", **fetch_kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            df = self.normalize_columns(df, symbol=str(symbol))

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            for data_date in sorted(df["data_date"].dropna().astype(str).unique()):
                self.delete_data(
                    self.table_name,
                    {"symbol": str(symbol), "data_date": data_date},
                )
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = OptionSseMinuteSina()
    script.run()


if __name__ == "__main__":
    main()
