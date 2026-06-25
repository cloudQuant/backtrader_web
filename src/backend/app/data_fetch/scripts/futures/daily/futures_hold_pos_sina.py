"""
Futures Hold Pos Sina

数据源: AkShare
函数: futures_hold_pos_sina
频率: daily
"""

import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class FuturesHoldPosSina(AkshareToMySql):
    """Futures Hold Pos Sina"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "FUTURES_HOLD_POS_SINA"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `FUTURES_HOLD_POS_SINA` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `contract` VARCHAR(50) COMMENT '期货合约',
            `rank_type` VARCHAR(20) COMMENT '排名类型',
            `rank_num` INT COMMENT '名次',
            `member_name` VARCHAR(100) COMMENT '会员简称',
            `rank_value` DECIMAL(24, 4) COMMENT '排名数值',
            `change_value` DECIMAL(24, 4) COMMENT '比上交易增减',
            `raw_value_column` VARCHAR(50) COMMENT '原始数值列名',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_symbol_type_rank_date (`symbol`, `rank_type`, `rank_num`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Futures Hold Pos Sina'
    """

    @staticmethod
    def normalize_columns(
        df: pd.DataFrame,
        contract: str | None = None,
        rank_type: str | None = None,
        date: str | None = None,
    ) -> pd.DataFrame:
        """Normalize Sina futures position ranking rows into stable columns."""
        if df.empty:
            return df

        df = df.copy()
        contract_value = str(contract or "").strip().upper()
        rank_type_value = str(rank_type or "").strip()

        value_candidates = [
            col
            for col in df.columns
            if col not in {"名次", "会员简称", "比上交易增减", "data_date"}
        ]
        raw_value_column = value_candidates[0] if value_candidates else None

        if date:
            parsed_date = pd.to_datetime(str(date), format="%Y%m%d", errors="coerce")
            data_date = parsed_date.date() if pd.notna(parsed_date) else pd.Timestamp.now().date()
        else:
            data_date = pd.Timestamp.now().date()

        normalized = pd.DataFrame(
            {
                "symbol": contract_value,
                "name": f"{contract_value} {rank_type_value}".strip(),
                "data_date": data_date,
                "contract": contract_value,
                "rank_type": rank_type_value,
                "rank_num": pd.to_numeric(df.get("名次"), errors="coerce"),
                "member_name": df.get("会员简称"),
                "rank_value": (
                    pd.to_numeric(df[raw_value_column], errors="coerce")
                    if raw_value_column is not None
                    else None
                ),
                "change_value": pd.to_numeric(df.get("比上交易增减"), errors="coerce"),
                "raw_value_column": raw_value_column,
            }
        )
        return normalized

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.futures_hold_pos_sina

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            df = self.fetch_ak_data("futures_hold_pos_sina", **kwargs)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            df = self.normalize_columns(
                df,
                contract=kwargs.get("contract"),
                rank_type=kwargs.get("symbol"),
                date=kwargs.get("date"),
            )

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = FuturesHoldPosSina()
    script.run()


if __name__ == "__main__":
    main()
