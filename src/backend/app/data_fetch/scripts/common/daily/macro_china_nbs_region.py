"""
Macro China Nbs Region

数据源: AkShare
函数: macro_china_nbs_region
频率: daily
"""

import hashlib

import pandas as pd
import requests

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import AkshareToMySql

PREFER_LOCAL_SCRIPT = True
SOURCE_URL = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData"
REGION_LIST_URL = (
    "https://data.stats.gov.cn/dg/website/publicrelease/web/external/getDasByDaCatalogId"
)
FS_QUARTER_REFERER = "https://data.stats.gov.cn/dg/website/page.html#/pc/national/fsQuarterData"
FS_QUARTER_ROOT_ID = "854f819b04104191a5ae2f2cba270e6c"
FS_QUARTER_REGION_CATALOG_ID = "a10dceae75d245008bf4b9a0e6fe1d55"

DEFAULT_REGION_QUERIES = [
    {
        "kind": "分省季度数据",
        "path": "国民经济核算 > 地区生产总值",
        "indicator": "地区生产总值_累计值(亿元)",
        "region": None,
        "period": "LAST10",
        "cid": "44ecf9ea21884caea5451c35e9c08fff",
        "indicator_ids": ["dc168397231c49f391ee9e11966de389"],
        "root_id": FS_QUARTER_ROOT_ID,
        "da_catalog_id": FS_QUARTER_REGION_CATALOG_ID,
    },
    {
        "kind": "分省季度数据",
        "path": "人民生活 > 居民人均可支配收入",
        "indicator": "居民人均可支配收入_累计值(元)",
        "region": None,
        "period": "LAST10",
        "cid": "1065e991d0c84623bf0e0d012f36c0e3",
        "indicator_ids": ["0f6eafa0055f46bfbe61c3e2eafeb218"],
        "root_id": FS_QUARTER_ROOT_ID,
        "da_catalog_id": FS_QUARTER_REGION_CATALOG_ID,
    },
]

OUTPUT_COLUMNS = [
    "record_key",
    "kind",
    "path",
    "indicator",
    "region",
    "period",
    "dimension_name",
    "item_name",
    "data_period",
    "period_name",
    "indicator_id",
    "indicator_name",
    "category_name",
    "value",
    "unit",
    "source_url",
    "fetched_at",
]


def _record_key(*parts: object) -> str:
    raw = "\x1f".join("" if part is None else str(part) for part in parts)
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def _normalise_queries(kwargs: dict) -> list[dict]:
    preset_by_key = {
        (item["kind"], item["path"], item["indicator"]): item for item in DEFAULT_REGION_QUERIES
    }

    if "queries" in kwargs:
        queries = kwargs["queries"]
        if isinstance(queries, dict):
            queries = [queries]
        if not isinstance(queries, list):
            raise TypeError("queries must be a JSON object or list of objects")
        normalised = []
        for item in queries:
            query = dict(item)
            preset = preset_by_key.get(
                (query.get("kind"), query.get("path"), query.get("indicator"))
            )
            if preset:
                merged = dict(preset)
                merged.update(query)
                query = merged
            normalised.append(query)
        return normalised

    if {"kind", "path", "indicator"}.issubset(kwargs):
        query = dict(kwargs)
        preset = preset_by_key.get((query.get("kind"), query.get("path"), query.get("indicator")))
        if preset:
            merged = dict(preset)
            merged.update(query)
            query = merged
        return [query]

    return [dict(item) for item in DEFAULT_REGION_QUERIES]


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Referer": FS_QUARTER_REFERER,
    }


def _resolve_quarter_dts(period: str) -> str:
    if not period or period == "LAST10":
        today = pd.Timestamp.now()
        current_quarter = ((today.month - 1) // 3) + 1
        if current_quarter == 1:
            end_year = today.year - 1
            end_quarter = 4
        else:
            end_year = today.year
            end_quarter = current_quarter - 1
        end_index = end_year * 4 + end_quarter - 1
        start_index = end_index - 9
        start_year = start_index // 4
        start_quarter = start_index % 4 + 1
        return f"{start_year}{start_quarter:02d}SS-{end_year}{end_quarter:02d}SS"
    period = str(period).strip()
    if "SS" in period:
        return period
    return period


def _fetch_regions(da_catalog_id: str, region: str | None = None) -> list[dict]:
    response = requests.get(
        REGION_LIST_URL,
        params={"daCid": da_catalog_id},
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("data") or []
    regions = [
        {"text": item.get("show_name") or item.get("name_text"), "value": item.get("name_value")}
        for item in items
        if item.get("name_value")
    ]
    if not region:
        return regions
    matched = [item for item in regions if region in {item.get("text"), item.get("value")}]
    if matched:
        return matched
    if str(region).isdigit():
        return [{"text": str(region), "value": str(region)}]
    raise ValueError(f"NBS region name not found in official region catalog: {region}")


def _fetch_nbs_stream_data(query: dict, timeout: int = 30) -> pd.DataFrame:
    cid = query.get("cid")
    indicator_ids = query.get("indicator_ids") or query.get("indicatorIds")
    da_catalog_id = query.get("da_catalog_id")
    if not cid or not indicator_ids or not da_catalog_id:
        raise ValueError(f"NBS region query has no official catalog mapping: {query}")

    regions = _fetch_regions(da_catalog_id, query.get("region"))
    fetched_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for region_item in regions:
        payload = {
            "cid": cid,
            "indicatorIds": list(indicator_ids),
            "daCatalogId": query.get("payload_da_catalog_id", ""),
            "das": [region_item],
            "showType": query.get("show_type", "1"),
            "dts": [query.get("dts") or _resolve_quarter_dts(query.get("period", "LAST10"))],
            "rootId": query.get("root_id", FS_QUARTER_ROOT_ID),
        }
        response = requests.post(SOURCE_URL, json=payload, headers=_headers(), timeout=timeout)
        response.raise_for_status()
        data = response.json().get("data") or []
        for period_item in data:
            data_period = period_item.get("code")
            period_name = period_item.get("name")
            for value_item in period_item.get("values") or []:
                raw_value = str(value_item.get("value") or "").strip()
                if not raw_value:
                    continue
                indicator_name = str(value_item.get("i_showname") or "").strip()
                region_name = value_item.get("da_name") or region_item.get("text")
                item_name = region_name if query.get("region") is None else indicator_name
                record = {
                    "kind": query.get("kind"),
                    "path": query.get("path"),
                    "indicator": query.get("indicator"),
                    "region": query.get("region"),
                    "period": query.get("period", "LAST10"),
                    "dimension_name": "地区",
                    "item_name": item_name,
                    "data_period": str(data_period),
                    "period_name": period_name,
                    "indicator_id": value_item.get("_id"),
                    "indicator_name": indicator_name,
                    "category_name": str(value_item.get("_name") or "").strip(),
                    "value": pd.to_numeric(raw_value, errors="coerce"),
                    "unit": value_item.get("du_name"),
                    "source_url": SOURCE_URL,
                    "fetched_at": fetched_at,
                }
                record["record_key"] = _record_key(
                    record["kind"],
                    record["path"],
                    record["indicator_id"],
                    record["data_period"],
                    region_name,
                )
                records.append(record)
    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)


class MacroChinaNbsRegion(AkshareToMySql):
    """Macro China Nbs Region"""

    def __init__(self, db_config=DB_CONFIG, logger=None):
        super().__init__(db_config, logger)
        self.table_name = "MACRO_CHINA_NBS_REGION"
        self.create_table_sql = """
        CREATE TABLE IF NOT EXISTS `MACRO_CHINA_NBS_REGION` (
            `R_ID` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `record_key` CHAR(32) NOT NULL COMMENT '配置和数据期唯一键',
            `kind` VARCHAR(32) COMMENT '数据类别',
            `path` VARCHAR(255) COMMENT '数据路径',
            `indicator` VARCHAR(255) COMMENT '指标',
            `region` VARCHAR(100) COMMENT '地区',
            `period` VARCHAR(32) COMMENT '查询区间',
            `dimension_name` VARCHAR(255) COMMENT '矩阵列维度',
            `item_name` VARCHAR(255) COMMENT '行项目',
            `data_period` VARCHAR(64) COMMENT '数据期',
            `period_name` VARCHAR(64) COMMENT '数据期名称',
            `indicator_id` VARCHAR(64) COMMENT '指标ID',
            `indicator_name` VARCHAR(255) COMMENT '指标名称',
            `category_name` VARCHAR(255) COMMENT '分类名称',
            `value` DOUBLE COMMENT '数值',
            `unit` VARCHAR(32) COMMENT '单位',
            `source_url` TEXT COMMENT '数据源地址',
            `fetched_at` DATETIME COMMENT '抓取时间',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_record_key (`record_key`),
            INDEX idx_kind_period (`kind`, `data_period`),
            INDEX idx_item_name (`item_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Macro China Nbs Region'
        """

    def fetch_data(self, **kwargs):
        """Fetch data from AkShare and save to database.

        Args:
            **kwargs: Parameters to pass to ak.macro_china_nbs_region

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
                self.logger.warning(f"NBS region query failed for {query}: {e}")
                continue
            frames.append(df)

        result = (
            pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
        )
        if result.empty:
            self.logger.warning("No NBS region data found")
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

    script = MacroChinaNbsRegion()
    script.fetch_data()


if __name__ == "__main__":
    main()
