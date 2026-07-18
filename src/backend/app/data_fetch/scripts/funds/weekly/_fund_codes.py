from collections.abc import Iterable

import pandas as pd

DEFAULT_FUND_CODE_LIMIT = 5


def normalize_fund_codes(
    fund_code: str | None = None,
    fund_codes: Iterable[str] | str | None = None,
) -> list[str]:
    if fund_codes is None:
        values = [fund_code] if fund_code else []
    elif isinstance(fund_codes, str):
        values = fund_codes.replace(";", ",").split(",")
    else:
        values = list(fund_codes)

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        code = str(value).strip()
        if code and code not in seen:
            result.append(code)
            seen.add(code)
    return result


def get_codes_from_table(
    fetcher, table_name: str, column_name: str, limit: int | None = None
) -> list[str]:
    max_rows = DEFAULT_FUND_CODE_LIMIT if limit is None else max(int(limit), 1)
    fetcher.connect_db()
    sql = f"""
    SELECT DISTINCT `{column_name}`
    FROM `{table_name}`
    WHERE `{column_name}` IS NOT NULL AND `{column_name}` <> ''
    ORDER BY `{column_name}`
    LIMIT %s
    """
    fetcher.cursor.execute(sql, (max_rows,))
    return normalize_fund_codes(fund_codes=[row[0] for row in fetcher.cursor.fetchall() if row])


def main() -> pd.DataFrame:
    """Return an audit row when this helper module is scanned as a task."""
    return pd.DataFrame(
        [
            {
                "helper": "_fund_codes",
                "default_fund_code_limit": DEFAULT_FUND_CODE_LIMIT,
            }
        ]
    )
