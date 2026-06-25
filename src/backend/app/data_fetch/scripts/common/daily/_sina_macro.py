import math
import time
from collections.abc import Iterable

import pandas as pd
import requests
from akshare.utils import demjson


def fetch_sina_macro_pages(
    *,
    callback: str,
    cate: str,
    event: str,
    data_path: Iterable[str],
    page_size: int = 31,
    max_pages: int | None = None,
    timeout: tuple[int, int] = (5, 20),
    retries: int = 3,
) -> pd.DataFrame:
    """Fetch paged Sina macro data from the same source used by AkShare."""

    url = (
        "https://quotes.sina.cn/mac/api/jsonp_v3.php/"
        f"{callback}/MacPage_Service.get_pagedata"
    )
    params = {
        "cate": cate,
        "event": event,
        "from": "0",
        "num": str(page_size),
        "condition": "",
    }

    def request_page(offset: int) -> dict:
        params["from"] = str(offset)
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                text = response.text
                return demjson.decode(text[text.find("{") : -3])
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(attempt)
        raise RuntimeError(f"Sina macro page request failed at offset {offset}") from last_error

    first_json = request_page(0)
    total_pages = math.ceil(int(first_json.get("count") or 0) / page_size)
    if max_pages is not None:
        total_pages = min(total_pages, int(max_pages))
    columns = [item[1] for item in first_json["config"]["all"]]

    def extract_records(data_json: dict) -> list:
        data = data_json
        for key in data_path:
            data = data[key]
        return data or []

    frames = [pd.DataFrame(extract_records(first_json))]
    for page in range(1, total_pages):
        page_json = request_page(page * page_size)
        frames.append(pd.DataFrame(extract_records(page_json)))

    big_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if big_df.empty:
        return pd.DataFrame(columns=columns)
    big_df.columns = columns
    return big_df
