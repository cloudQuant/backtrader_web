import argparse
import logging

import akshare as ak
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class ReitsHistEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "REITS_HIST_EM"
        self.create_table_sql = """
            CREATE TABLE `REITS_HIST_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `SECURITY_CODE` VARCHAR(20) NOT NULL COMMENT 'REITs代码',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(10, 3) COMMENT '开盘价',
                `HIGH` DECIMAL(10, 3) COMMENT '最高价',
                `LOW` DECIMAL(10, 3) COMMENT '最低价',
                `CLOSE` DECIMAL(10, 3) COMMENT '收盘价',
                `VOLUME` BIGINT COMMENT '成交量(手)',
                `TURNOVER` DECIMAL(20, 2) COMMENT '成交额(元)',
                `AMPLITUDE` DECIMAL(10, 2) COMMENT '振幅(%)',
                `TURNOVER_RATE` DECIMAL(10, 2) COMMENT '换手率(%)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_SECURITY_DATE` (`SECURITY_CODE`, `TRADE_DATE`),
                KEY `IDX_SECURITY` (`SECURITY_CODE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='REITs历史行情表(东方财富)';
        """

    def fetch_reits_hist(self, symbol, start_date=None, end_date=None):
        try:
            # 获取REITs历史行情数据
            df = ak.reits_hist_em(symbol=symbol)

            if df is None or df.empty:
                self.logger.warning(f"No historical data found for REIT {symbol}")
                return pd.DataFrame()

            # 重命名列
            df = df.rename(
                columns={
                    "日期": "trade_date_str",
                    "今开": "open",
                    "最高": "high",
                    "最低": "low",
                    "最新价": "close",
                    "成交量": "volume",
                    "成交额": "turnover",
                    "振幅": "amplitude",
                    "换手": "turnover_rate",
                }
            )

            # 添加证券代码
            df["security_code"] = symbol

            # 转换日期格式
            df["trade_date"] = pd.to_datetime(df["trade_date_str"]).dt.date

            # 筛选日期范围
            if start_date:
                start_date = pd.to_datetime(start_date).date()
                df = df[df["trade_date"] >= start_date]

            if end_date:
                end_date = pd.to_datetime(end_date).date()
                df = df[df["trade_date"] <= end_date]

            if df.empty:
                self.logger.warning("No data in the specified date range")
                return pd.DataFrame()

            # 生成唯一ID
            df["r_id"] = (
                "RHE_"
                + df["security_code"]
                + "_"
                + df["trade_date"].astype(str).str.replace("-", "")
            )

            # 选择需要的列并重新排序
            columns = [
                "r_id",
                "security_code",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
                "amplitude",
                "turnover_rate",
            ]
            return df[columns]

        except Exception as e:
            self.logger.error(f"Error fetching historical data for REIT {symbol}: {e}")
            return pd.DataFrame()

    def save_reits_hist(self, df):
        if df.empty:
            self.logger.warning("No data to save")
            return False

        try:
            # 获取已存在的数据ID
            existing_ids = {
                row[0]
                for row in self.query_data(
                    f"SELECT r_id FROM {self.table_name} WHERE is_active = 1"  # nosec B608
                )
                or []
            }

            # 插入新数据
            new_data = df[~df["r_id"].isin(existing_ids)]
            if not new_data.empty:
                self.insert_data(
                    new_data,
                    self.table_name,
                    [
                        "r_id",
                        "security_code",
                        "trade_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "turnover",
                        "amplitude",
                        "turnover_rate",
                        "is_active",
                        "data_source",
                    ],
                )
                self.logger.info(
                    f"Inserted {len(new_data)} new records for {df['security_code'].iloc[0]}"
                )

            # 更新已有数据
            updated_data = df[df["r_id"].isin(existing_ids)]
            if not updated_data.empty:
                for _, row in updated_data.iterrows():
                    self.execute_sql(
                        f"""  # nosec B608
                        UPDATE {self.table_name}
                        SET open=%s, high=%s, low=%s, close=%s,
                            volume=%s, turnover=%s, amplitude=%s,
                            turnover_rate=%s, updatedate=CURRENT_TIMESTAMP
                        WHERE r_id=%s
                        """,
                        (
                            row["open"],
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                            row["turnover"],
                            row["amplitude"],
                            row["turnover_rate"],
                            row["r_id"],
                        ),
                    )
                self.logger.info(
                    f"Updated {len(updated_data)} records for {df['security_code'].iloc[0]}"
                )

            return True

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def _get_all_reits_symbols(self):
        """Fetch all REITs symbols from ak.reits_realtime_em()"""
        try:
            df = ak.reits_realtime_em()
            if df is not None and not df.empty:
                col = "代码" if "代码" in df.columns else df.columns[0]
                return df[col].astype(str).tolist()
        except Exception as e:
            self.logger.error(f"Error fetching REITs symbol list: {e}")
        return []

    def run(self, symbol=None, start_date=None, end_date=None):
        try:
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)

            if symbol:
                symbols = [symbol]
            else:
                symbols = self._get_all_reits_symbols()
                if not symbols:
                    self.logger.error("No REITs symbols found")
                    return False

            self.logger.info(f"Starting REITs historical data update for {len(symbols)} symbols")
            success_count = 0
            for sym in symbols:
                try:
                    df = self.fetch_reits_hist(sym, start_date, end_date)
                    if not df.empty:
                        if self.save_reits_hist(df):
                            success_count += 1
                except Exception as e:
                    self.logger.error(f"Error processing REIT {sym}: {e}")

            self.logger.info(f"Completed: {success_count}/{len(symbols)} REITs updated")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"Error in run: {e}")
            return False


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(description="Fetch REIT historical market data")
    parser.add_argument("symbol", type=str, help="REIT code (e.g., 508097)")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    reits_hist = ReitsHistEm(logger=logging.getLogger(__name__))
    sys.exit(0 if reits_hist.run(args.symbol, args.start_date, args.end_date) else 1)
