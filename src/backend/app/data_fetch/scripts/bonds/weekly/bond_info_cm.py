import argparse
import logging
import sys
from datetime import date

import numpy as np
import pandas as pd
import requests
import urllib3

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

# 忽略SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_BOND_INFO_CM_COLUMNS = [
    "债券简称",
    "债券代码",
    "发行人/受托机构",
    "债券类型",
    "发行日期",
    "最新债项评级",
    "查询代码",
]


def _post_chinamoney_json(
    session: requests.Session,
    url: str,
    payload: dict[str, str],
    headers: dict[str, str],
) -> dict:
    """Request one ChinaMoney result page without depending on AkShare internals."""
    response = session.post(url, data=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


class BondInfoCm(AkshareToMySql):
    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "BOND_INFO_CM"
        self.create_table_sql = """
            CREATE TABLE `BOND_INFO_CM` (
                `R_ID` VARCHAR(36) NOT NULL COMMENT 'UUID生成的唯一标识',
                `BASEDATE` DATE NOT NULL COMMENT '数据日期',
                `CREATEDATE` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建日期',
                `CREATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '创建人',
                `UPDATEDATE` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新日期',
                `UPDATEUSER` VARCHAR(50) DEFAULT 'system' COMMENT '更新人',

                -- 业务字段
                `BOND_NAME` VARCHAR(100) NOT NULL COMMENT '债券简称',
                `BOND_CODE` VARCHAR(50) NOT NULL COMMENT '债券代码',
                `BOND_ISSUER` VARCHAR(200) COMMENT '发行人/受托机构',
                `BOND_TYPE` VARCHAR(100) COMMENT '债券类型',
                `ISSUE_DATE` DATE COMMENT '发行日期',
                `LATEST_RATING` VARCHAR(50) COMMENT '最新债项评级',
                `QUERY_CODE` VARCHAR(100) COMMENT '查询代码',

                PRIMARY KEY (`R_ID`),
                UNIQUE KEY `uk_bond_date` (`BASEDATE`, `BOND_CODE`, `QUERY_CODE`),
                KEY `idx_basedate` (`BASEDATE`),
                KEY `idx_bond_code` (`BOND_CODE`),
                KEY `idx_bond_name` (`BOND_NAME`),
                KEY `idx_bond_type` (`BOND_TYPE`),
                KEY `idx_issue_date` (`ISSUE_DATE`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中国外汇交易中心-债券信息查询数据表';
        """

    def _fetch_limited_bond_info(self, max_pages: int) -> pd.DataFrame:
        url = "https://www.chinamoney.com.cn/ags/ms/cm-u-bond-md/BondMarketInfoList2"
        payload = {
            "pageNo": "1",
            "pageSize": "15",
            "bondName": "",
            "bondCode": "",
            "issueEnty": "",
            "bondType": "",
            "bondSpclPrjctVrty": "",
            "couponType": "",
            "issueYear": "",
            "entyDefinedCode": "",
            "rtngShrt": "",
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
            )
        }
        session = __import__("requests").Session()

        data_json = _post_chinamoney_json(session, url, payload, headers)
        data = data_json.get("data") or {}
        total_page = int(data.get("pageTotal") or 0)
        page_limit = min(total_page, max(1, int(max_pages)))
        records = data.get("resultList") or []
        frames = [pd.DataFrame(records)] if records else []

        for page in range(2, page_limit + 1):
            payload.update({"pageNo": str(page)})
            data_json = _post_chinamoney_json(session, url, payload, headers)
            records = (data_json.get("data") or {}).get("resultList") or []
            if records:
                frames.append(pd.DataFrame(records))

        if not frames:
            return pd.DataFrame(columns=_BOND_INFO_CM_COLUMNS)

        big_df = pd.concat(frames, ignore_index=True)
        big_df.rename(
            columns={
                "bondDefinedCode": "查询代码",
                "bondName": "债券简称",
                "bondCode": "债券代码",
                "issueStartDate": "发行日期",
                "bondType": "债券类型",
                "entyFullName": "发行人/受托机构",
                "debtRtng": "最新债项评级",
            },
            inplace=True,
        )
        for column in _BOND_INFO_CM_COLUMNS:
            if column not in big_df.columns:
                big_df[column] = pd.NA
        return big_df[_BOND_INFO_CM_COLUMNS]

    def fetch_bond_info(self, max_pages=None):
        """
        从AKShare获取债券信息数据

        Returns:
            DataFrame: 处理后的债券数据
        """
        try:
            self.logger.info("Fetching bond information from China Money")

            if max_pages is not None:
                df = self._fetch_limited_bond_info(max_pages=int(max_pages))
            else:
                df = self.fetch_ak_data("bond_info_cm")

            if df is None or df.empty:
                self.logger.warning("No bond information found")
                return pd.DataFrame()

            self.logger.info(f"Fetched {len(df)} bond records")

            # 定义列映射（中文到数据库列名）
            column_mapping = {
                "债券简称": "BOND_NAME",
                "债券代码": "BOND_CODE",
                "发行人/受托机构": "BOND_ISSUER",
                "债券类型": "BOND_TYPE",
                "发行日期": "ISSUE_DATE",
                "最新债项评级": "LATEST_RATING",
                "查询代码": "QUERY_CODE",
            }

            # 重命名列并只保留需要的列
            df = df.rename(columns=column_mapping)
            available_columns = [col for col in column_mapping.values() if col in df.columns]
            df = df[available_columns]

            # 处理日期列
            if "ISSUE_DATE" in df.columns:
                df["ISSUE_DATE"] = pd.to_datetime(df["ISSUE_DATE"], errors="coerce").dt.date

            # 添加元数据列
            df["R_ID"] = [self.get_uuid() for _ in range(len(df))]
            df["BASEDATE"] = date.today()
            df["CREATEUSER"] = "system"
            df["UPDATEUSER"] = "system"

            # 定义最终列顺序
            final_columns = [
                "R_ID",
                "BASEDATE",
                "CREATEUSER",
                "UPDATEUSER",
                "BOND_NAME",
                "BOND_CODE",
                "BOND_ISSUER",
                "BOND_TYPE",
                "ISSUE_DATE",
                "LATEST_RATING",
                "QUERY_CODE",
            ]

            # 确保所有列都存在，缺失的用None填充
            for col in final_columns:
                if col not in df.columns:
                    df[col] = None

            # 去重并返回
            result_df = df[final_columns].drop_duplicates(
                subset=["BOND_CODE", "QUERY_CODE"], keep="first"
            )

            self.logger.info(f"Processed {len(result_df)} unique bond records")
            return result_df

        except Exception as e:
            self.logger.error(f"Error fetching bond information: {str(e)}", exc_info=True)
            return pd.DataFrame()

    def run(self, max_pages=None, **kwargs):
        """
        执行债券信息获取任务

        Returns:
            bool: 执行是否成功
        """
        try:
            self.logger.info("Starting bond information data collection")

            # 确保表存在
            if not self.table_exists(self.table_name):
                self.create_table(self.create_table_sql)
                self.logger.info(f"Created table {self.table_name}")

            df = self.fetch_bond_info(max_pages=max_pages)
            if not df.empty:
                return self.save_data(
                    df=df.replace(np.nan, None),
                    table_name=self.table_name,
                    on_duplicate_update=True,
                    unique_keys=["BASEDATE", "BOND_CODE", "QUERY_CODE"],
                )

            self.logger.warning("No bond data to process")
            return False

        except Exception as e:
            self.logger.error(f"Error in bond info collection: {str(e)}", exc_info=True)
            return False


def main():
    """主函数：配置日志和解析命令行参数"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Fetch bond information from China Money")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    try:
        args = parser.parse_args()
        if args.debug:
            logger.setLevel(logging.DEBUG)

        # 创建实例并运行
        bond_fetcher = BondInfoCm(logger=logger)
        success = bond_fetcher.run()

        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=args.debug if "args" in locals() else False)
        sys.exit(1)


if __name__ == "__main__":
    main()
