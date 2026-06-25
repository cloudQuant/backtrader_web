"""
Stock Individual Info Em

数据源: AkShare
函数: stock_individual_info_em
频率: daily
"""

import pandas as pd
from akshare.stock_feature.stock_hist_em import request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockIndividualInfoEm(AkshareToMySql):
    """Stock Individual Info Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_INDIVIDUAL_INFO_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_INDIVIDUAL_INFO_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Individual Info Em'
    """

    @staticmethod
    def fetch_info(symbol: str = "000001", timeout: float | None = 20) -> pd.DataFrame:
        market_code = 1 if str(symbol).startswith("6") else 0
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": (
                "f120,f121,f122,f174,f175,f59,f163,f43,f57,f58,f169,f170,f46,f44,"
                "f51,f168,f47,f164,f116,f60,f45,f52,f50,f48,f167,f117,f71,f161,"
                "f49,f530,f135,f136,f137,f138,f139,f141,f142,f144,f145,f147,f148,"
                "f140,f143,f146,f149,f55,f62,f162,f92,f173,f104,f105,f84,f85,f183,"
                "f184,f185,f186,f187,f188,f189,f190,f191,f192,f107,f111,f86,f177,"
                "f78,f110,f262,f263,f264,f267,f268,f255,f256,f257,f258,f127,f199,"
                "f128,f198,f259,f260,f261,f171,f277,f278,f279,f288,f152,f250,f251,"
                "f252,f253,f254,f269,f270,f271,f272,f273,f274,f275,f276,f265,f266,"
                "f289,f290,f286,f285,f292,f293,f294,f295,f43"
            ),
            "secid": f"{market_code}.{symbol}",
        }
        response = request_eastmoney(url, params=params, timeout=timeout)
        data = (response.json().get("data") or {})
        code_name_map = {
            "f57": "股票代码",
            "f58": "股票简称",
            "f84": "总股本",
            "f85": "流通股",
            "f127": "行业",
            "f116": "总市值",
            "f117": "流通市值",
            "f189": "上市时间",
            "f43": "最新",
        }
        df = pd.DataFrame(
            [{"item": item, "value": data.get(field)} for field, item in code_name_map.items()]
        )
        return StockIndividualInfoEm.normalize_columns(df)

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        if {"item", "value"}.issubset(df.columns):
            value_by_item = dict(zip(df["item"], df["value"], strict=False))
            df["symbol"] = str(value_by_item.get("股票代码") or "").strip()
            df["name"] = str(value_by_item.get("股票简称") or "").strip()
        df["data_date"] = pd.Timestamp.now().date()
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_individual_info_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            symbol = kwargs.pop("symbol", "000001")
            timeout = kwargs.pop("timeout", 20)
            df = self.fetch_info(symbol=symbol, timeout=timeout)

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Process data if needed
            # Add data_date if not exists
            df = self.normalize_columns(df)
            if "data_date" not in df.columns:
                df["data_date"] = pd.Timestamp.now().date()

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            if {"symbol", "data_date"}.issubset(df.columns):
                for symbol_value in sorted(df["symbol"].dropna().astype(str).unique()):
                    symbol_df = df[df["symbol"].astype(str) == symbol_value]
                    for data_date in sorted(symbol_df["data_date"].dropna().astype(str).unique()):
                        self.delete_data(
                            self.table_name,
                            {"symbol": symbol_value, "data_date": data_date},
                        )
            self.save_data(df, self.table_name, ignore_duplicates=True)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockIndividualInfoEm()
    script.run()


if __name__ == "__main__":
    main()
