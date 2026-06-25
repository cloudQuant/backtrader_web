# 4055_highway_logistics_volume.py
import argparse
import logging
import sys
import time
import urllib3

import numpy as np
import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


CFLP_BASE_URL = "https://index.0256.cn"
CFLP_REFERER = f"{CFLP_BASE_URL}/expx.htm"


class HighwayLogisticsVolume(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "HIGHWAY_LOGISTICS_VOLUME"
        self.create_table_sql = """
            CREATE TABLE IF NOT EXISTS `HIGHWAY_LOGISTICS_VOLUME` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `PERIOD_TYPE` ENUM('MONTHLY', 'QUARTERLY', 'YEARLY') NOT NULL COMMENT '周期类型',
                `TRADE_DATE` DATE NOT NULL COMMENT '日期',
                `BASE_INDEX` DECIMAL(10, 2) COMMENT '定基指数',
                `MOM_INDEX` DECIMAL(10, 2) COMMENT '环比指数',
                `YOY_INDEX` DECIMAL(10, 2) COMMENT '同比指数',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_PERIOD_DATE` (`PERIOD_TYPE`, `TRADE_DATE`),
                KEY `IDX_TRADE_DATE` (`TRADE_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中国公路物流运量指数';
        """
        self.period_mapping = {
            "MONTHLY": "月指数",
            "QUARTERLY": "季度指数",
            "YEARLY": "年度指数",
        }
        self.reverse_period_mapping = {v: k for k, v in self.period_mapping.items()}

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": CFLP_REFERER,
        }

    def _fetch_cflp_volume_source(self, period_type: str) -> pd.DataFrame:
        exp_type_map = {"MONTHLY": "3", "QUARTERLY": "4", "YEARLY": "5"}
        exp_type_id = exp_type_map[period_type]
        params = {
            "type": "1",
            "marketId": "1",
            "expTypeId": exp_type_id,
            "startDate1": "",
            "endDate1": "",
            "city": "",
            "startDate3": "",
            "endDate3": "",
        }
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = self._headers()
        last_error: Exception | None = None
        backoff_seconds = [2, 5, 10, 20, 30]
        for attempt in range(len(backoff_seconds) + 1):
            session = requests.Session()
            session.verify = False
            try:
                session.get(CFLP_REFERER, headers=headers, timeout=(10, 30))
                response = session.get(
                    f"{CFLP_BASE_URL}/volume_query.action",
                    params=params,
                    headers=headers,
                    timeout=(10, 30),
                )
                response.raise_for_status()
                data_json = response.json()
                temp_df = pd.DataFrame(
                    [
                        data_json["chart1"]["xLebal"],
                        data_json["chart1"]["yLebal"],
                        data_json["chart2"]["yLebal"],
                        data_json["chart3"]["yLebal"],
                    ]
                ).T
                if temp_df.empty:
                    return pd.DataFrame()
                temp_df.columns = ["TRADE_DATE", "BASE_INDEX", "MOM_INDEX", "YOY_INDEX"]
                temp_df["TRADE_DATE"] = pd.to_datetime(
                    temp_df["TRADE_DATE"], errors="coerce"
                ).dt.date
                for col in ["BASE_INDEX", "MOM_INDEX", "YOY_INDEX"]:
                    temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce")
                temp_df.dropna(subset=["TRADE_DATE"], inplace=True)
                temp_df.drop_duplicates(subset=["TRADE_DATE"], keep="last", inplace=True)
                return temp_df
            except Exception as exc:
                last_error = exc
                self.logger.debug(
                    "0256 公路物流运量接口第 %s 次请求失败: %s", attempt + 1, exc
                )
                if attempt < len(backoff_seconds):
                    time.sleep(backoff_seconds[attempt])
        self.logger.warning("0256 公路物流运量接口请求失败: %s", last_error)
        return pd.DataFrame()

    def fetch_volume_data(self, period_type):
        """
        Fetch China Highway Logistics Volume Index data

        Args:
            period_type: Period type ('MONTHLY', 'QUARTERLY', 'YEARLY')

        Returns:
            DataFrame containing volume index data
        """
        try:
            symbol = self.period_mapping.get(period_type)
            if not symbol:
                raise ValueError(f"Invalid period type: {period_type}")

            self.logger.info(f"Fetching China Highway Logistics Volume Index for {symbol}")

            # The original HTTP POST endpoint is currently blocked by 0256.cn.
            # The same endpoint works through HTTPS GET after visiting the source page.
            df = self._fetch_cflp_volume_source(period_type)

            if df is None or df.empty:
                self.logger.warning(f"No data found for {symbol}")
                return pd.DataFrame()

            # Convert date format and add metadata
            df["PERIOD_TYPE"] = period_type
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "中国公路物流运量指数"

            return df

        except Exception as e:
            self.logger.error(
                f"Error fetching Highway Logistics Volume data: {str(e)}", exc_info=True
            )
            return pd.DataFrame()

    def run(self, period_type="ALL", update_all=False):
        """Run the highway logistics volume index update"""
        try:
            valid_periods = list(self.period_mapping.keys())
            if period_type not in valid_periods + ["ALL"]:
                raise ValueError(
                    f"Invalid period_type. Must be one of: {', '.join(valid_periods + ['ALL'])}"
                )

            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # # Mark old records as inactive for this period type if not updating all
            # if not update_all:
            #     self.execute_sql(
            #         f"UPDATE {self.table_name} SET IS_ACTIVE = 0 WHERE PERIOD_TYPE = %s",
            #         (period_type,)
            #     )

            period_types = valid_periods if period_type == "ALL" else [period_type]
            remaining_period_types = period_types
            retry_rounds = 2 if period_type == "ALL" else 1
            frames = []
            for round_index in range(retry_rounds):
                failed_period_types = []
                for current_period_type in remaining_period_types:
                    if round_index:
                        self.logger.info("Retrying %s after source reset", current_period_type)
                    df = self.fetch_volume_data(current_period_type)
                    if df.empty:
                        failed_period_types.append(current_period_type)
                        continue
                    self.save_data(
                        df=df.replace({np.nan: None}),
                        table_name=self.table_name,
                        on_duplicate_update=True,
                        unique_keys=["PERIOD_TYPE", "TRADE_DATE"],
                    )
                    period_name = self.period_mapping.get(current_period_type, current_period_type)
                    self.logger.info(f"Updated {len(df)} {period_name} records")
                    frames.append(df)
                    time.sleep(5)
                if not failed_period_types:
                    break
                remaining_period_types = failed_period_types
                if round_index < retry_rounds - 1:
                    time.sleep(30)

            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Error in run: {str(e)}", exc_info=True)
            return False


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Update China Highway Logistics Volume Index Data")
    parser.add_argument(
        "--period",
        type=str,
        default="ALL",
        choices=["MONTHLY", "QUARTERLY", "YEARLY", "ALL"],
        help="Period type: MONTHLY, QUARTERLY, YEARLY, or ALL",
    )
    parser.add_argument(
        "--list-periods",
        action="store_true",
        help="List all available period types and exit",
    )
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = HighwayLogisticsVolume(logger=logger)

        if args.list_periods:
            logger.info("Available period types:")
            for period_id, period_name in fetcher.period_mapping.items():
                logger.info("  %s: %s", period_id, period_name)
            sys.exit(0)

        success = fetcher.run(period_type=args.period, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
