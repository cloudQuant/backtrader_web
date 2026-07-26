from app.data_fetch.scripts.funds.weekly._fund_codes import (
    get_codes_from_table,
    normalize_fund_codes,
)


class _Cursor:
    def __init__(self):
        self.params = None

    def execute(self, _sql, params):
        self.params = params

    def fetchall(self):
        return [("000001",), ("000001",), ("000003",)]


class _Fetcher:
    def __init__(self):
        self.cursor = _Cursor()
        self.connected = False

    def connect_db(self):
        self.connected = True


def test_normalize_fund_codes_accepts_single_list_and_csv_values():
    assert normalize_fund_codes("000001") == ["000001"]
    assert normalize_fund_codes(fund_codes=["000001", "000001", "000003"]) == [
        "000001",
        "000003",
    ]
    assert normalize_fund_codes(fund_codes="000001; 000003,000004") == [
        "000001",
        "000003",
        "000004",
    ]


def test_get_codes_from_table_uses_limit_and_returns_string_codes():
    fetcher = _Fetcher()

    codes = get_codes_from_table(fetcher, "OPEN_FUND_DAILY_EM", "FUND_CODE", limit=2)

    assert fetcher.connected is True
    assert fetcher.cursor.params == (2,)
    assert codes == ["000001", "000003"]
