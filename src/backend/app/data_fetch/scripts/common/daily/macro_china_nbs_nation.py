"""
Macro China Nbs Nation

数据源: AkShare
函数: macro_china_nbs_nation
频率: daily
"""

import hashlib
import pandas as pd

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


PREFER_LOCAL_SCRIPT = True

DEFAULT_NATION_QUERIES = [
    {
        "kind": "年度数据",
        "path": "人口 > 总人口",
        "period": "LAST10",
    },
    {
        "kind": "年度数据",
        "path": "国民经济核算 > 支出法国内生产总值",
        "period": "LAST10",
    },
]

OUTPUT_COLUMNS = [
    "record_key",
    "kind",
    "path",
    "period",
    "item_name",
    "data_period",
    "value",
    "fetched_at",
]


def _record_key(*parts: object) -> str:
    raw = "\x1f".join("" if part is None else str(part) for part in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _normalise_queries(kwargs: dict) -> list[dict]:
    if "queries" in kwargs:
        queries = kwargs["queries"]
        if isinstance(queries, dict):
            queries = [queries]
        if not isinstance(queries, list):
            raise TypeError("queries must be a JSON object or list of objects")
        return [dict(item) for item in queries]

    if {"kind", "path"}.issubset(kwargs):
        return [dict(kwargs)]

    return [dict(item) for item in DEFAULT_NATION_QUERIES]


def _flatten_nation_frame(df: pd.DataFrame, query: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    fetched_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for item_name, row in df.iterrows():
        for data_period, value in row.items():
            record = {
                "kind": query.get("kind"),
                "path": query.get("path"),
                "period": query.get("period", "LAST10"),
                "item_name": str(item_name),
                "data_period": str(data_period),
                "value": pd.to_numeric(value, errors="coerce"),
                "fetched_at": fetched_at,
            }
            record["record_key"] = _record_key(
                record["kind"],
                record["path"],
                record["period"],
                record["item_name"],
                record["data_period"],
            )
            records.append(record)
    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)


class MacroChinaNbsNation(AkshareToMySql):
    """Macro China Nbs Nation"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MACRO_CHINA_NBS_NATION"
        self.create_table_sql = """
        CREATE TABLE IF NOT EXISTS `MACRO_CHINA_NBS_NATION` (
            `R_ID` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `record_key` CHAR(32) NOT NULL COMMENT '配置和数据期唯一键',
            `kind` VARCHAR(32) COMMENT '数据类别',
            `path` VARCHAR(255) COMMENT '数据路径',
            `period` VARCHAR(32) COMMENT '查询区间',
            `item_name` VARCHAR(255) COMMENT '行项目',
            `data_period` VARCHAR(64) COMMENT '数据期',
            `value` DOUBLE COMMENT '数值',
            `fetched_at` DATETIME COMMENT '抓取时间',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_record_key (`record_key`),
            INDEX idx_kind_period (`kind`, `data_period`),
            INDEX idx_item_name (`item_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Macro China Nbs Nation'
        """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.macro_china_nbs_nation

        Returns:
            pd.DataFrame: Fetched data
        """
        self.create_table_if_not_exists(self.table_name, self.create_table_sql)
        queries = _normalise_queries(kwargs)
        frames = []
        for query in queries:
            ak_kwargs = {
                key: query.get(key)
                for key in ("kind", "path", "period")
                if key in query
            }
            ak_kwargs.setdefault("period", "LAST10")
            try:
                df = self.fetch_ak_data(
                    "macro_china_nbs_nation",
                    _call_timeout=int(query.get("_call_timeout", 60)),
                    **ak_kwargs,
                )
            except Exception as e:
                self.logger.warning(f"NBS nation query failed for {ak_kwargs}: {e}")
                continue
            frames.append(_flatten_nation_frame(df, ak_kwargs))

        result = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=OUTPUT_COLUMNS)
        )
        if result.empty:
            self.logger.warning("No NBS nation data found")
            return result

        self.save_data(
            result,
            self.table_name,
            on_duplicate_update=True,
            unique_keys=["record_key"],
        )
        return result


def main():
    """Main function to run the data fetch"""

    script = MacroChinaNbsNation()
    script.run()


if __name__ == "__main__":
    main()
