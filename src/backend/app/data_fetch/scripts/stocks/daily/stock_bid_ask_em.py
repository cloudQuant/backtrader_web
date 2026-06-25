"""
Stock Bid Ask Em

数据源: AkShare
函数: stock_bid_ask_em
频率: daily
"""

import pandas as pd
from akshare.stock_feature.stock_hist_em import request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class StockBidAskEm(AkshareToMySql):
    """Stock Bid Ask Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_BID_ASK_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_BID_ASK_EM` (
        `R_ID` INT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) COMMENT '品种代码',
            `name` VARCHAR(100) COMMENT '品种名称',
            `data_date` DATE COMMENT '数据日期',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_symbol_date (`symbol`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Bid Ask Em'
    """

    @staticmethod
    def fetch_quote(symbol: str = "000001") -> pd.DataFrame:
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
                "f289,f290,f286,f285,f292,f293,f294,f295"
            ),
            "secid": f"{market_code}.{symbol}",
        }
        response = request_eastmoney(url, params=params, timeout=20)
        data = response.json().get("data") or {}
        tick_dict = {
            "sell_5": data.get("f31"),
            "sell_5_vol": data.get("f32") * 100 if data.get("f32") is not None else None,
            "sell_4": data.get("f33"),
            "sell_4_vol": data.get("f34") * 100 if data.get("f34") is not None else None,
            "sell_3": data.get("f35"),
            "sell_3_vol": data.get("f36") * 100 if data.get("f36") is not None else None,
            "sell_2": data.get("f37"),
            "sell_2_vol": data.get("f38") * 100 if data.get("f38") is not None else None,
            "sell_1": data.get("f39"),
            "sell_1_vol": data.get("f40") * 100 if data.get("f40") is not None else None,
            "buy_1": data.get("f19"),
            "buy_1_vol": data.get("f20") * 100 if data.get("f20") is not None else None,
            "buy_2": data.get("f17"),
            "buy_2_vol": data.get("f18") * 100 if data.get("f18") is not None else None,
            "buy_3": data.get("f15"),
            "buy_3_vol": data.get("f16") * 100 if data.get("f16") is not None else None,
            "buy_4": data.get("f13"),
            "buy_4_vol": data.get("f14") * 100 if data.get("f14") is not None else None,
            "buy_5": data.get("f11"),
            "buy_5_vol": data.get("f12") * 100 if data.get("f12") is not None else None,
            "最新": data.get("f43"),
            "均价": data.get("f71"),
            "涨幅": data.get("f170"),
            "涨跌": data.get("f169"),
            "总手": data.get("f47"),
            "金额": data.get("f48"),
            "换手": data.get("f168"),
            "量比": data.get("f50"),
            "最高": data.get("f44"),
            "最低": data.get("f45"),
            "今开": data.get("f46"),
            "昨收": data.get("f60"),
            "涨停": data.get("f51"),
            "跌停": data.get("f52"),
            "外盘": data.get("f49"),
            "内盘": data.get("f161"),
        }
        df = pd.DataFrame.from_dict(tick_dict, orient="index").reset_index()
        df.columns = ["item", "value"]
        df["symbol"] = data.get("f57") or str(symbol)
        df["name"] = data.get("f58") or str(symbol)
        return StockBidAskEm.normalize_columns(df)

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        if "value" in df.columns:
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
        if "symbol" in df.columns:
            df["symbol"] = df["symbol"].astype(str).str.strip()
        if "name" in df.columns:
            df["name"] = df["name"].astype(str).str.strip()
        df["data_date"] = pd.Timestamp.now().date()
        return df

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_bid_ask_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # Fetch data from AkShare
            symbol = kwargs.pop("symbol", "000001")
            df = self.fetch_quote(symbol=symbol)

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

    script = StockBidAskEm()
    script.run()


if __name__ == "__main__":
    main()
