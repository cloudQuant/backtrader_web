"""
Stock Gpzy Distribute Statistics Company Em

数据源: AkShare
函数: stock_gpzy_distribute_statistics_company_em
频率: daily
"""

from __future__ import annotations

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


EASTMONEY_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_REFERER = "https://data.eastmoney.com/gpzy/distributeStatistics.aspx"
REPORT_NAME = "RPT_GDZY_ZYJG_SUM"


class StockGpzyDistributeStatisticsCompanyEm(AkshareToMySql):
    """Stock Gpzy Distribute Statistics Company Em"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "STOCK_GPZY_DISTRIBUTE_STATISTICS_COMPANY_EM"
        self.create_table_sql = """
    CREATE TABLE IF NOT EXISTS `STOCK_GPZY_DISTRIBUTE_STATISTICS_COMPANY_EM` (
        `R_ID` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `symbol` VARCHAR(50) NOT NULL COMMENT '质押机构代码',
            `name` VARCHAR(100) COMMENT '质押机构',
            `data_date` DATE NOT NULL COMMENT '快照日期',
            `pforg_code` VARCHAR(50) COMMENT '质押机构内部代码',
            `pforg_type` VARCHAR(50) COMMENT '质押机构类型',
            `secucode` VARCHAR(50) COMMENT '证券代码带市场',
            `security_code` VARCHAR(20) COMMENT '证券代码',
            `org_num` BIGINT COMMENT '质押公司数量',
            `pledge_deal_num` BIGINT COMMENT '质押笔数',
            `pledge_num` DOUBLE COMMENT '质押数量',
            `warning_state_1` BIGINT COMMENT '未达预警线数量',
            `warning_state_2` BIGINT COMMENT '达到预警线未达平仓线数量',
            `warning_state_3` BIGINT COMMENT '达到平仓线数量',
            `warning_state_1_rate` DOUBLE COMMENT '未达预警线比例',
            `warning_state_2_rate` DOUBLE COMMENT '达到预警线未达平仓线比例',
            `warning_state_3_rate` DOUBLE COMMENT '达到平仓线比例',
            `source_report` VARCHAR(80) DEFAULT 'RPT_GDZY_ZYJG_SUM' COMMENT '东方财富报表名',
            `data_source` VARCHAR(50) DEFAULT '东方财富' COMMENT '数据来源',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        UNIQUE KEY uk_pforg_date (`pforg_type`, `pforg_code`, `data_date`),
        INDEX idx_data_date (`data_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stock Gpzy Distribute Statistics Company Em'
    """

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": EASTMONEY_REFERER,
        }

    def _fetch_distribution(self, pforg_type: str) -> pd.DataFrame:
        params = {
            "sortColumns": "ORG_NUM",
            "sortTypes": "-1",
            "pageSize": "500",
            "pageNumber": "1",
            "reportName": REPORT_NAME,
            "columns": "ALL",
            "quoteColumns": "",
            "source": "WEB",
            "client": "WEB",
            "filter": f'(PFORG_TYPE="{pforg_type}")',
        }
        response = requests.get(
            EASTMONEY_DATACENTER_URL,
            params=params,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        data_json = response.json()
        records = (data_json.get("result") or {}).get("data") or []
        if not records:
            self.logger.warning(
                "东方财富股权质押机构分布无数据: pforg_type=%s code=%s message=%s",
                pforg_type,
                data_json.get("code"),
                data_json.get("message"),
            )
            return pd.DataFrame()
        return self.normalize_columns(pd.DataFrame(records))

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        result = pd.DataFrame(index=df.index)
        result["symbol"] = df["PFORG_CODE"].astype(str)
        result["name"] = df["SECURITY_NAME_ABBR"]
        result["data_date"] = pd.Timestamp.now().date()
        result["pforg_code"] = df["PFORG_CODE"].astype(str)
        result["pforg_type"] = df["PFORG_TYPE"]
        result["secucode"] = df.get("SECUCODE")
        result["security_code"] = df.get("SECURITY_CODE")

        numeric_map = {
            "ORG_NUM": "org_num",
            "PLEDGE_DEAL_NUM": "pledge_deal_num",
            "PLEDGE_NUM": "pledge_num",
            "WARNING_STATE_1": "warning_state_1",
            "WARNING_STATE_2": "warning_state_2",
            "WARNING_STATE_3": "warning_state_3",
            "WARNING_STATE_1_RATE": "warning_state_1_rate",
            "WARNING_STATE_2_RATE": "warning_state_2_rate",
            "WARNING_STATE_3_RATE": "warning_state_3_rate",
        }
        for source_col, target_col in numeric_map.items():
            result[target_col] = pd.to_numeric(df.get(source_col), errors="coerce")

        result["source_report"] = REPORT_NAME
        result["data_source"] = "东方财富"
        return result

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.stock_gpzy_distribute_statistics_company_em

        Returns:
            pd.DataFrame: Fetched data
        """
        try:
            # 东方财富当前 PFORG_TYPE 使用行业二级名称，旧筛选值“证券”已返回空。
            df = self._fetch_distribution(str(kwargs.pop("pforg_type", "证券Ⅱ")))

            if df is None or df.empty:
                self.logger.warning("No data found")
                return pd.DataFrame()

            # Save to database
            self.create_table_if_not_exists(self.table_name, self.create_table_sql)
            self.save_data(
                df,
                self.table_name,
                on_duplicate_update=True,
                unique_keys=["pforg_type", "pforg_code", "data_date"],
            )

            return df

        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()


def main():
    """Main function to run the data fetch"""

    script = StockGpzyDistributeStatisticsCompanyEm()
    script.run()


if __name__ == "__main__":
    main()
