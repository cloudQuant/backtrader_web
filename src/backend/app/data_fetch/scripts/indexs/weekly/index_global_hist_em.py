import logging

import numpy as np
import pandas as pd
from akshare.index.index_global_em import index_global_em_symbol_map
from akshare.utils.request import request_with_retry as request_eastmoney

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


class IndexGlobalHistEm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "INDEX_GLOBAL_HIST_EM"
        self.valid_indices = (
            self.get_indices()
        )  # ['美元指数', '道琼斯', '纳斯达克', '标普500']  # 支持的全球指数
        self.create_table_sql = """
            CREATE TABLE `INDEX_GLOBAL_HIST_EM` (
                `R_ID` VARCHAR(32) PRIMARY KEY,
                `INDEX_CODE` VARCHAR(20) NOT NULL COMMENT '指数代码',
                `INDEX_NAME` VARCHAR(100) COMMENT '指数名称',
                `TRADE_DATE` DATE NOT NULL COMMENT '交易日期',
                `OPEN` DECIMAL(20, 4) COMMENT '开盘价',
                `CLOSE` DECIMAL(20, 4) COMMENT '收盘价',
                `HIGH` DECIMAL(20, 4) COMMENT '最高价',
                `LOW` DECIMAL(20, 4) COMMENT '最低价',
                `AMPLITUDE` DECIMAL(10, 4) COMMENT '振幅(%)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT '东方财富-全球指数' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_INDEX_CODE_DATE` (`INDEX_CODE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='全球指数历史行情表(东方财富)';
        """

    def get_indices(self):
        fallback_indices = ["美元指数", "道琼斯", "纳斯达克", "标普500"]
        try:
            self.get_data_by_columns("INDEX_GLOBAL_SPOT_EM", ["INDEX_NAME"])
            df = self.fetch_ak_data("index_global_spot_em")
            if df is not None and not df.empty and "名称" in df.columns:
                return df["名称"].dropna().astype(str).drop_duplicates().to_list()
        except Exception as exc:
            self.logger.warning(f"Failed to fetch global index list, using fallback: {exc}")
        return fallback_indices

    def validate_index(self, index_name):
        """Validate if the provided index name is supported.

        Args:
            index_name (str): The index name to validate

        Returns:
            tuple: (is_valid, error_message)
        """
        if not index_name:
            return False, "Index name cannot be empty"
        if index_name not in self.valid_indices:
            return False, f"Invalid index name. Must be one of {self.valid_indices}"
        return True, ""

    def _fetch_daily_from_trends(self, index_name):
        if index_name not in index_global_em_symbol_map:
            return pd.DataFrame()
        item = index_global_em_symbol_map[index_name]
        secid = f"{item['market']}.{item['code']}"
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        params = {
            "secid": secid,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "iscr": "0",
            "iscca": "0",
            "ndays": "5",
        }
        try:
            data_json = request_eastmoney(url, params=params, timeout=20).json()
        except Exception as exc:
            self.logger.warning(f"Eastmoney global index trends2 fallback failed: {exc}")
            return pd.DataFrame()

        data = data_json.get("data") or {}
        trends = data.get("trends") or []
        if not trends:
            return pd.DataFrame()
        df = pd.DataFrame([item.split(",") for item in trends])
        if df.empty or df.shape[1] < 5:
            return pd.DataFrame()
        df = df.iloc[:, :5]
        df.columns = ["time", "open", "close", "high", "low"]
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.dropna(subset=["time"])
        if df.empty:
            return pd.DataFrame()
        for column in ("open", "close", "high", "low"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df["TRADE_DATE"] = df["time"].dt.date
        grouped = (
            df.groupby("TRADE_DATE", as_index=False)
            .agg(
                OPEN=("open", "first"),
                CLOSE=("close", "last"),
                HIGH=("high", "max"),
                LOW=("low", "min"),
            )
            .sort_values("TRADE_DATE")
        )
        previous_close = pd.to_numeric(data.get("preClose"), errors="coerce")
        amplitudes = []
        for _, row in grouped.iterrows():
            if pd.isna(previous_close) or previous_close == 0:
                amplitudes.append(None)
            else:
                amplitudes.append((row["HIGH"] - row["LOW"]) / previous_close * 100)
            previous_close = row["CLOSE"]
        grouped["AMPLITUDE"] = amplitudes
        grouped["INDEX_CODE"] = data.get("code") or item["code"]
        grouped["INDEX_NAME"] = data.get("name") or index_name
        grouped["R_ID"] = (
            grouped["INDEX_CODE"].astype(str)
            + "_"
            + pd.to_datetime(grouped["TRADE_DATE"]).dt.strftime("%Y%m%d")
        )
        grouped["DATA_SOURCE"] = "东方财富-全球指数"
        grouped["IS_ACTIVE"] = 1
        if not grouped.empty:
            self.logger.warning(
                "Eastmoney global index kline returned empty; populated "
                "INDEX_GLOBAL_HIST_EM from same-source trends2 aggregation"
            )
        return grouped[
            [
                "R_ID",
                "INDEX_CODE",
                "INDEX_NAME",
                "TRADE_DATE",
                "OPEN",
                "CLOSE",
                "HIGH",
                "LOW",
                "AMPLITUDE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]
        ].reset_index(drop=True)

    def fetch_index_hist(self, index_name):
        """Fetch historical data for a global index from East Money.

        Args:
            index_name (str): Index name in Chinese (e.g., '道琼斯')

        Returns:
            pd.DataFrame: Processed DataFrame with historical data or empty DataFrame on error
        """
        try:
            # 1. Fetch data from AKShare
            try:
                df = self.fetch_ak_data("index_global_hist_em", symbol=index_name)
            except Exception as fetch_exc:
                self.logger.warning(
                    f"Eastmoney global index kline fetch failed, trying same-source "
                    f"trends2 aggregation: {fetch_exc}"
                )
                df = pd.DataFrame()

            if df is None or df.empty:
                df = self._fetch_daily_from_trends(index_name)
                if df is None or df.empty:
                    self.logger.warning(f"No historical data found for global index {index_name}")
                    return pd.DataFrame()
                return df

            # 2. Rename and process columns
            df = df.rename(
                columns={
                    "日期": "TRADE_DATE_STR",
                    "代码": "INDEX_CODE",
                    "名称": "INDEX_NAME",
                    "今开": "OPEN",
                    "最新价": "CLOSE",
                    "最高": "HIGH",
                    "最低": "LOW",
                    "振幅": "AMPLITUDE",
                }
            )

            # 3. Process date and numeric columns
            df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE_STR"]).dt.date

            numeric_columns = ["OPEN", "CLOSE", "HIGH", "LOW", "AMPLITUDE"]
            for col in numeric_columns:
                if col in df.columns:
                    # Remove percentage sign from AMPLITUDE if present
                    if col == "AMPLITUDE":
                        df[col] = df[col].astype(str).str.rstrip("%")
                    df[col] = pd.to_numeric(
                        df[col].astype(str).str.replace(",", ""), errors="coerce"
                    )

            # 4. Add metadata columns
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["DATA_SOURCE"] = "东方财富-全球指数"
            df["IS_ACTIVE"] = 1

            # 5. Define final column order matching database schema
            final_columns = [
                "R_ID",
                "INDEX_CODE",
                "INDEX_NAME",
                "TRADE_DATE",
                "OPEN",
                "CLOSE",
                "HIGH",
                "LOW",
                "AMPLITUDE",
                "IS_ACTIVE",
                "DATA_SOURCE",
            ]

            return df[final_columns].drop_duplicates(subset=["INDEX_CODE", "TRADE_DATE"])

        except Exception as e:
            self.logger.error(
                f"Error fetching historical data for global index {index_name}: {str(e)}",
                exc_info=True,
            )
            return pd.DataFrame()

    def run(self, index_name=None, max_indices=None):
        """Main method to run the data fetching and saving process.

        Args:
            index_name (str, optional): Index name in Chinese. If None, processes all valid indices.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info("Starting global index historical data update from East Money")

            # Create table if not exists
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Determine which indices to process
            if index_name is None:
                index_list = self.valid_indices
                self.logger.info(f"Processing all {len(index_list)} global indices")
            else:
                is_valid, error_msg = self.validate_index(index_name)
                if not is_valid:
                    self.logger.error(error_msg)
                    return False
                index_list = [index_name]
            max_indices = int(max_indices) if max_indices is not None else None
            if max_indices is not None and len(index_list) > max_indices:
                index_list = index_list[:max_indices]
                self.logger.info(f"Limiting global East Money indices to {max_indices}")

            all_success = True
            for idx in index_list:
                try:
                    # Fetch data
                    df = self.fetch_index_hist(idx)

                    if not df.empty:
                        # Handle NaN values
                        df = df.replace(np.nan, None)

                        # Save data using INSERT ... ON DUPLICATE KEY UPDATE
                        success = self.save_data(
                            df=df,
                            table_name=self.table_name,
                            on_duplicate_update=True,
                            unique_keys=["INDEX_CODE", "TRADE_DATE"],
                        )

                        if success:
                            self.logger.info(
                                f"Successfully updated {len(df)} records for index {idx} "
                                f"in {self.table_name}"
                            )
                        else:
                            all_success = False
                            self.logger.error(f"Failed to save data for index {idx}")
                    else:
                        self.logger.warning(f"No data found for index {idx}")

                except Exception as e:
                    all_success = False
                    self.logger.error(f"Error processing index {idx}: {str(e)}", exc_info=True)

            return all_success

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main(index_name=None, max_indices=None):
    import argparse
    import sys

    if index_name is not None or max_indices is not None:
        fetcher = IndexGlobalHistEm(logger=logging.getLogger(__name__))
        return fetcher.run(index_name=index_name, max_indices=max_indices)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Fetch historical global index data from East Money"
    )
    parser.add_argument(
        "--index",
        type=str,
        required=False,
        help="全球指数名称，例如: 美元指数, 道琼斯, 纳斯达克, 标普500。如果不指定，将处理所有指数",
    )

    try:
        args = parser.parse_args()
        fetcher = IndexGlobalHistEm(logger=logger)
        success = fetcher.run(index_name=args.index)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
