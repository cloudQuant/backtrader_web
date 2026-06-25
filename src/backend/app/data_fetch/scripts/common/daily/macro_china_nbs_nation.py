"""
Macro China Nbs Nation

数据源: AkShare
函数: macro_china_nbs_nation
频率: daily
"""

import hashlib
import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql


PREFER_LOCAL_SCRIPT = True
SOURCE_URL = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData"
YEAR_DATA_REFERER = "https://data.stats.gov.cn/dg/website/page.html#/pc/national/yearData"
YEAR_DATA_ROOT_ID = "884c062607104a91967b22742537f44f"

DEFAULT_NATION_QUERIES = [
    {
        "kind": "年度数据",
        "path": "人口 > 总人口",
        "period": "LAST10",
        "cid": "6331ad868e8b4f55b8e9b6e765609ce1",
        "indicator_ids": [
            "806083491dbe46a08995783945a30b9d",
            "b808a4131bd041c4abc87b52385cd578",
            "30d59b42875145c696883366172bb3d1",
            "07e1e3444cd34c43b4fd749f060bba5f",
            "2dd9894936d448fcb88605863d90d85c",
        ],
        "root_id": YEAR_DATA_ROOT_ID,
    },
    {
        "kind": "年度数据",
        "path": "国民经济核算 > 支出法国内生产总值",
        "period": "LAST10",
        "cid": "0bb77c6247864057968547a9ea8b1134",
        "indicator_ids": [
            "5d95e29a86f94dcdabed1441fd30d430",
            "4505839ba207460585a7f534b469d776",
            "a9d6271fcbad4003943ec01f74305436",
            "66acc412c0fa4340a48f68c391058d59",
            "5ef39109dd48455599daac40d08cac18",
            "245fadf5ea4a4ac688575be8f4ee71f0",
            "bc1988566be14ea99fe79541da2f2962",
            "d13131557f2e4873a56a9e84373bda1c",
            "84f4b89495b14ec296f641be0a02905e",
            "ab05c1fdde01485e88589917a2c3ea07",
            "5f848228bd7d4f179843aae92bc75fd6",
            "a74d735476e2442da591079fd18f1bc7",
        ],
        "root_id": YEAR_DATA_ROOT_ID,
    },
]

OUTPUT_COLUMNS = [
    "record_key",
    "kind",
    "path",
    "period",
    "item_name",
    "data_period",
    "period_name",
    "indicator_id",
    "category_name",
    "region_name",
    "value",
    "unit",
    "source_url",
    "fetched_at",
]


def _record_key(*parts: object) -> str:
    raw = "\x1f".join("" if part is None else str(part) for part in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _normalise_queries(kwargs: dict) -> list[dict]:
    preset_by_path = {(item["kind"], item["path"]): item for item in DEFAULT_NATION_QUERIES}

    if "queries" in kwargs:
        queries = kwargs["queries"]
        if isinstance(queries, dict):
            queries = [queries]
        if not isinstance(queries, list):
            raise TypeError("queries must be a JSON object or list of objects")
        normalised = []
        for item in queries:
            query = dict(item)
            preset = preset_by_path.get((query.get("kind"), query.get("path")))
            if preset:
                merged = dict(preset)
                merged.update(query)
                query = merged
            normalised.append(query)
        return normalised

    if {"kind", "path"}.issubset(kwargs):
        query = dict(kwargs)
        preset = preset_by_path.get((query.get("kind"), query.get("path")))
        if preset:
            merged = dict(preset)
            merged.update(query)
            query = merged
        return [query]

    return [dict(item) for item in DEFAULT_NATION_QUERIES]


def _resolve_year_dts(period: str) -> str:
    if not period or period == "LAST10":
        end_year = pd.Timestamp.now().year - 1
        start_year = end_year - 9
        return f"{start_year}YY-{end_year}YY"
    period = str(period).strip()
    if "YY" in period:
        return period
    if "-" in period:
        start, end = period.split("-", 1)
        if start.isdigit() and end.isdigit():
            return f"{start}YY-{end}YY"
    if period.isdigit():
        return f"{period}YY"
    return period


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Referer": YEAR_DATA_REFERER,
    }


def _fetch_nbs_stream_data(query: dict, timeout: int = 30) -> pd.DataFrame:
    cid = query.get("cid")
    indicator_ids = query.get("indicator_ids") or query.get("indicatorIds")
    if not cid or not indicator_ids:
        raise ValueError(f"NBS nation query has no official catalog mapping: {query}")

    payload = {
        "cid": cid,
        "indicatorIds": list(indicator_ids),
        "daCatalogId": query.get("da_catalog_id", ""),
        "das": query.get("das") or [{"text": "全国", "value": "000000000000"}],
        "showType": query.get("show_type", "1"),
        "dts": [query.get("dts") or _resolve_year_dts(query.get("period", "LAST10"))],
        "rootId": query.get("root_id", YEAR_DATA_ROOT_ID),
    }
    response = requests.post(SOURCE_URL, json=payload, headers=_headers(), timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or []
    fetched_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for period_item in data:
        data_period = period_item.get("code")
        period_name = period_item.get("name")
        for value_item in period_item.get("values") or []:
            raw_value = str(value_item.get("value") or "").strip()
            if not raw_value:
                continue
            record = {
                "kind": query.get("kind"),
                "path": query.get("path"),
                "period": query.get("period", "LAST10"),
                "item_name": str(value_item.get("i_showname") or "").strip(),
                "data_period": str(data_period),
                "period_name": period_name,
                "indicator_id": value_item.get("_id"),
                "category_name": str(value_item.get("_name") or "").strip(),
                "region_name": value_item.get("da_name"),
                "value": pd.to_numeric(raw_value, errors="coerce"),
                "unit": value_item.get("du_name"),
                "source_url": SOURCE_URL,
                "fetched_at": fetched_at,
            }
            record["record_key"] = _record_key(
                record["kind"],
                record["path"],
                record["data_period"],
                record["indicator_id"],
                record["region_name"],
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
            `period_name` VARCHAR(64) COMMENT '数据期名称',
            `indicator_id` VARCHAR(64) COMMENT '指标ID',
            `category_name` VARCHAR(255) COMMENT '分类名称',
            `region_name` VARCHAR(64) COMMENT '地区',
            `value` DOUBLE COMMENT '数值',
            `unit` VARCHAR(32) COMMENT '单位',
            `source_url` TEXT COMMENT '数据源地址',
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
            try:
                df = _fetch_nbs_stream_data(query, timeout=int(query.get("_call_timeout", 30)))
            except Exception as e:
                self.logger.warning(f"NBS nation query failed for {query}: {e}")
                continue
            frames.append(df)

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
    script.fetch_data()


if __name__ == "__main__":
    main()
