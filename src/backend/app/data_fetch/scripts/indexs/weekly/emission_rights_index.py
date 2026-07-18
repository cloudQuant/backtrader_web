# 4052_emission_rights_index.py
import argparse
import logging
import sys

import numpy as np
import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

SCREEN_API_BASE = "https://screen.zjpwq.com/pwq-index-webapi"
SCREEN_REFERER = "https://screen.zjpwq.com/"


class EmissionRightsIndex(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "EMISSION_RIGHTS_INDEX"
        self.create_table_sql = """
            CREATE TABLE IF NOT EXISTS `EMISSION_RIGHTS_INDEX` (
                `R_ID` VARCHAR(50) PRIMARY KEY,
                `PERIOD_TYPE` ENUM('MONTHLY', 'QUARTERLY') NOT NULL COMMENT '周期类型',
                `PERIOD_DATE` DATE NOT NULL COMMENT '日期',
                `TRADE_INDEX` DECIMAL(15, 6) COMMENT '交易指数',
                `VOLUME` DECIMAL(15, 4) COMMENT '成交量(吨)',
                `TURNOVER` DECIMAL(20, 4) COMMENT '成交额(元)',
                `IS_ACTIVE` TINYINT(1) DEFAULT 1 COMMENT '是否有效(1:是,0:否)',
                `DATA_SOURCE` VARCHAR(50) DEFAULT 'akshare' COMMENT '数据来源',
                `CREATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',
                UNIQUE KEY `IDX_PERIOD` (`PERIOD_TYPE`, `PERIOD_DATE`),
                KEY `IDX_IS_ACTIVE` (`IS_ACTIVE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='浙江省排污权交易指数';
        """

    @staticmethod
    def _screen_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": SCREEN_REFERER,
        }

    def _request_screen_api(self, endpoint: str, cycle: str) -> list[dict]:
        params = {
            "cycle": cycle,
            "regionId": "1",
            "structId": "1",
            "pageSize": "5000",
            "indexId": "1",
            "orderBy": "stage.publishTime",
        }
        response = requests.get(
            f"{SCREEN_API_BASE}/{endpoint}",
            params=params,
            headers=self._screen_headers(),
            timeout=30,
        )
        response.raise_for_status()
        data_json = response.json()
        if data_json.get("success") != 1:
            self.logger.warning(
                "浙江排污权指数接口返回异常: endpoint=%s cycle=%s payload=%s",
                endpoint,
                cycle,
                str(data_json)[:300],
            )
            return []
        return data_json.get("data") or []

    def fetch_source_data(self, period_type: str) -> pd.DataFrame:
        cycle = "MONTH" if period_type == "MONTHLY" else "QUARTER"
        index_records = self._request_screen_api("indexData", cycle)
        stat_records = self._request_screen_api("dataStatistics", cycle)
        if not index_records:
            return pd.DataFrame()

        index_df = pd.DataFrame(
            [
                {
                    "PERIOD_DATE": (record.get("stage") or {}).get("publishTime"),
                    "TRADE_INDEX": record.get("indexValue"),
                }
                for record in index_records
            ]
        )
        stat_df = pd.DataFrame(
            [
                {
                    "PERIOD_DATE": (record.get("stage") or {}).get("publishTime"),
                    "VOLUME": record.get("totalQuantity"),
                    "TURNOVER": record.get("totalCost"),
                }
                for record in stat_records
            ]
        )
        if stat_df.empty:
            result = index_df
            result["VOLUME"] = None
            result["TURNOVER"] = None
        else:
            result = index_df.merge(stat_df, on="PERIOD_DATE", how="left")

        result["PERIOD_DATE"] = pd.to_datetime(result["PERIOD_DATE"], errors="coerce").dt.date
        result["TRADE_INDEX"] = pd.to_numeric(result["TRADE_INDEX"], errors="coerce")
        result["VOLUME"] = pd.to_numeric(result["VOLUME"], errors="coerce")
        result["TURNOVER"] = pd.to_numeric(result["TURNOVER"], errors="coerce")
        result.dropna(subset=["PERIOD_DATE"], inplace=True)
        result.sort_values("PERIOD_DATE", inplace=True, ignore_index=True)
        return result

    def fetch_index_data(self, period_type):
        """
        Fetch Emission Rights Index data

        Args:
            period_type: 'MONTHLY' or 'QUARTERLY'

        Returns:
            DataFrame containing index data
        """
        try:
            symbol = "月度" if period_type == "MONTHLY" else "季度"
            self.logger.info(f"Fetching Emission Rights Index data for {symbol}")

            # AkShare still points at zs.zjpwq.net, which no longer resolves. The
            # same official Zhejiang emission-rights index app now exposes the
            # original webapi path under screen.zjpwq.com.
            df = self.fetch_source_data(period_type)

            if df is None or df.empty:
                self.logger.warning(f"No data found for Emission Rights Index ({symbol})")
                return pd.DataFrame()

            # Convert date format and add metadata
            df["PERIOD_TYPE"] = period_type
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["IS_ACTIVE"] = 1
            df["DATA_SOURCE"] = "浙江省排污权交易指数"

            return df

        except Exception as e:
            self.logger.error(f"Error fetching Emission Rights Index data: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, period_type="ALL", update_all=False):
        """Run the emission rights index update"""
        try:
            if period_type not in ["MONTHLY", "QUARTERLY", "ALL"]:
                raise ValueError("period_type must be one of: MONTHLY, QUARTERLY, ALL")

            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            # Mark old records as inactive if not updating all
            # if not update_all:
            #     self.execute_sql(
            #         f"UPDATE {self.table_name} SET IS_ACTIVE = 0 WHERE PERIOD_TYPE = %s",
            #         (period_type,)
            #     )

            period_types = ["MONTHLY", "QUARTERLY"] if period_type == "ALL" else [period_type]
            frames = []
            for current_period_type in period_types:
                df = self.fetch_index_data(current_period_type)
                if df.empty:
                    continue
                self.save_data(
                    df=df.replace({np.nan: None}),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["PERIOD_TYPE", "PERIOD_DATE"],
                )
                period_name = "Monthly" if current_period_type == "MONTHLY" else "Quarterly"
                self.logger.info(f"Updated {len(df)} {period_name} emission rights index records")
                frames.append(df)

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
    parser = argparse.ArgumentParser(description="Update Emission Rights Index Data")
    parser.add_argument(
        "--period",
        type=str,
        default="ALL",
        choices=["MONTHLY", "QUARTERLY", "ALL"],
        help="Period type: MONTHLY, QUARTERLY, or ALL",
    )
    parser.add_argument("--update-all", action="store_true", help="Update all historical data")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        fetcher = EmissionRightsIndex(logger=logger)
        success = fetcher.run(period_type=args.period, update_all=args.update_all)
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
