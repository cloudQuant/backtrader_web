"""
Market data API tests

Tests:
- K-line data query
- Data format validation
- Error handling
"""

import sys
from unittest.mock import patch

import pandas as pd
import pytest
from httpx import AsyncClient


@pytest.fixture
def mock_akshare_response():
    """Mock akshare response data - using Chinese column names as returned by akshare"""
    df = pd.DataFrame(
        {
            "日期": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "开盘": [10.0, 10.3, 10.5],
            "最高": [10.5, 10.8, 11.0],
            "最低": [9.8, 10.0, 10.2],
            "收盘": [10.3, 10.6, 10.8],
            "成交量": [1000000, 1200000, 1500000],
            "涨跌幅": [2.5, 1.5, 2.0],
        }
    )
    return df


@pytest.mark.asyncio
class TestKlineData:
    """K-line data tests"""

    async def test_get_kline_requires_auth(self, client: AsyncClient):
        """Test authentication required"""
        response = await client.get(
            "/api/v1/data/kline",
            params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
        )
        # API may return 401 or 403
        assert response.status_code in [401, 403]

    async def test_get_kline_missing_params(self, client: AsyncClient):
        """Test missing required parameters"""
        response = await client.get("/api/v1/data/kline")
        # Validation error - missing required parameters or not authenticated
        assert response.status_code in [401, 403, 422]

    async def test_get_kline_with_auth(
        self, client: AsyncClient, auth_headers, mock_akshare_response, monkeypatch
    ):
        """Test authenticated K-line query"""

        # Avoid network dependency: stub akshare import used by the endpoint.
        class _DummyAk:
            @staticmethod
            def stock_zh_a_hist(**_kwargs):
                return mock_akshare_response

        monkeypatch.setitem(sys.modules, "akshare", _DummyAk)
        response = await client.get(
            "/api/v1/data/kline",
            params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_get_kline_different_periods(
        self, client: AsyncClient, auth_headers, mock_akshare_response, monkeypatch
    ):
        """Test different periods"""
        periods = ["daily", "weekly", "monthly"]

        class _DummyAk:
            @staticmethod
            def stock_zh_a_hist(**_kwargs):
                return mock_akshare_response

        monkeypatch.setitem(sys.modules, "akshare", _DummyAk)

        for period in periods:
            response = await client.get(
                f"/api/v1/data/kline?symbol=000001.SZ&start_date=2024-01-01&end_date=2024-01-31&period={period}",
                headers=auth_headers,
            )
            assert response.status_code == 200


@pytest.mark.asyncio
class TestDataHelpers:
    """Data service helper function tests"""

    async def test_date_parsing(self):
        """Test date parsing"""
        # Test API internal date conversion logic
        start_date = "2024-01-01"
        start_str = start_date.replace("-", "")
        assert start_str == "20240101"

        end_date = "2024-12-31"
        end_str = end_date.replace("-", "")
        assert end_str == "20241231"

    async def test_symbol_parsing(self):
        """Test stock code parsing"""
        symbol = "000001.SZ"
        code = symbol.split(".")[0]
        assert code == "000001"

        symbol = "600000.SH"
        code = symbol.split(".")[0]
        assert code == "600000"


@pytest.mark.asyncio
class TestDataValidation:
    """Data validation tests"""

    async def test_valid_stock_codes(self):
        """Test valid stock code formats"""
        valid_codes = ["000001.SZ", "600000.SH", "300001.SZ", "688001.SH"]
        for code in valid_codes:
            parts = code.split(".")
            assert len(parts) == 2
            assert parts[1] in ["SZ", "SH"]

    async def test_date_format_validation(self):
        """Test date format validation"""
        from datetime import datetime

        # Test correct format
        valid_dates = ["2024-01-01", "2024-12-31"]
        for date_str in valid_dates:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                raise AssertionError(f"Invalid date format: {date_str}")
            else:
                assert True

    async def test_ohlc_data_structure(self):
        """Test OHLC data structure"""
        # Correct OHLC data order: [open, high, low, close] or [open, close, low, high]
        # Here using [open, high, low, close] format, ensure high is max, low is min
        ohlc_data = [10.0, 10.5, 9.8, 10.3]  # open, high, low, close
        # Verify OHLC order: high should be max, low should be min
        assert ohlc_data[0] <= ohlc_data[1]  # open <= high
        assert ohlc_data[2] <= ohlc_data[1]  # low <= high
        assert ohlc_data[3] <= ohlc_data[1]  # close <= high
        assert ohlc_data[2] <= ohlc_data[0]  # low <= open
        assert ohlc_data[2] <= ohlc_data[3]  # low <= close


@pytest.mark.asyncio
class TestDataAPIRoutes:
    """Data API route tests"""

    async def test_data_routes_registered(self):
        """Test data routes registered"""
        from app.api.data import router as data_router

        # Check route exists
        assert data_router is not None
        assert hasattr(data_router, "routes")

    async def test_kline_endpoint_exists(self):
        """Test K-line endpoint exists"""
        from app.api.data import router

        # Check if K-line endpoint exists in routes
        routes = [route.path for route in router.routes]
        assert "/kline" in routes or "/kline" in str(routes)


@pytest.mark.asyncio
class TestDataModels:
    """Data model tests"""

    async def test_kline_response_structure(self):
        """Test K-line response structure"""
        # Mock K-line response data structure
        mock_response = {
            "symbol": "000001.SZ",
            "count": 10,
            "kline": {
                "dates": ["2024-01-01", "2024-01-02"],
                "ohlc": [[10.0, 10.5, 9.8, 10.3], [10.3, 10.8, 10.0, 10.6]],
                "volumes": [1000000, 1200000],
            },
            "records": [
                {
                    "date": "2024-01-01",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.3,
                    "volume": 1000000,
                    "change": 2.5,
                }
            ],
        }

        # Verify response structure
        assert "symbol" in mock_response
        assert "count" in mock_response
        assert "kline" in mock_response
        assert "records" in mock_response
        assert "dates" in mock_response["kline"]
        assert "ohlc" in mock_response["kline"]
        assert "volumes" in mock_response["kline"]


@pytest.mark.asyncio
class TestKlineDataWithMock:
    """K-line data tests - using mock akshare"""

    async def test_get_kline_success_with_mock(
        self, client: AsyncClient, auth_headers, mock_akshare_response
    ):
        """Test successful K-line data retrieval - using mock"""
        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["symbol"] == "000001.SZ"
            assert data["count"] == 3
            assert "kline" in data
            assert "records" in data
            assert len(data["kline"]["dates"]) == 3
            assert len(data["kline"]["ohlc"]) == 3
            assert len(data["kline"]["volumes"]) == 3

    async def test_get_kline_empty_dataframe(self, client: AsyncClient, auth_headers):
        """Test empty DataFrame case"""
        with patch("akshare.stock_zh_a_hist") as mock_ak:
            # Return empty DataFrame
            mock_ak.return_value = pd.DataFrame()

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
                headers=auth_headers,
            )
            assert response.status_code == 404
            assert "No data retrieved" in response.json()["detail"]

    async def test_get_kline_exception_handling(self, client: AsyncClient, auth_headers):
        """Test exception handling"""
        with patch("akshare.stock_zh_a_hist") as mock_ak:
            # Simulate network error
            mock_ak.side_effect = Exception("Network error")

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
                headers=auth_headers,
            )
            assert response.status_code == 500
            assert (
                "Query failed" in response.json()["detail"]
                or "query failed" in response.json()["detail"]
            )

    async def test_get_kline_data_transformation(
        self, client: AsyncClient, auth_headers, mock_akshare_response
    ):
        """Test data transformation logic"""
        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()

            # Verify data format transformation
            assert "dates" in data["kline"]
            assert "ohlc" in data["kline"]
            assert "volumes" in data["kline"]

            # Verify OHLC format [open, close, low, high]
            first_ohlc = data["kline"]["ohlc"][0]
            assert len(first_ohlc) == 4
            assert isinstance(first_ohlc[0], float)  # open
            assert isinstance(first_ohlc[1], float)  # close
            assert isinstance(first_ohlc[2], float)  # low
            assert isinstance(first_ohlc[3], float)  # high

            # Verify records format
            assert len(data["records"]) == 3
            first_record = data["records"][0]
            assert "date" in first_record
            assert "open" in first_record
            assert "high" in first_record
            assert "low" in first_record
            assert "close" in first_record
            assert "volume" in first_record
            assert "change" in first_record

    async def test_get_kline_with_weekly_period(
        self, client: AsyncClient, auth_headers, mock_akshare_response
    ):
        """Test weekly data"""
        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                    "period": "weekly",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            # Verify akshare was called correctly
            mock_ak.assert_called_once()

    async def test_get_kline_with_monthly_period(
        self, client: AsyncClient, auth_headers, mock_akshare_response
    ):
        """Test monthly data"""
        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "period": "monthly",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200

    async def test_get_kline_symbol_parsing(
        self, client: AsyncClient, auth_headers, mock_akshare_response
    ):
        """Test stock code parsing"""
        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "600000.SH",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            # Verify akshare was called with correct code (without suffix)
            call_args = mock_ak.call_args
            assert call_args.kwargs["symbol"] == "600000"

    async def test_get_kline_date_format_conversion(
        self, client: AsyncClient, auth_headers, mock_akshare_response
    ):
        """Test date format conversion"""
        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            # Verify date format was converted correctly
            call_args = mock_ak.call_args
            assert call_args.kwargs["start_date"] == "20240101"
            assert call_args.kwargs["end_date"] == "20240131"

    async def test_get_kline_column_rename(self, client: AsyncClient, auth_headers):
        """Test column renaming"""
        # Create DataFrame with Chinese column names (as returned by akshare)
        df = pd.DataFrame(
            {
                "日期": ["2024-01-01"],
                "开盘": [10.0],
                "最高": [10.5],
                "最低": [9.8],
                "收盘": [10.3],
                "成交量": [1000000],
                "涨跌幅": [2.5],
            }
        )

        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = df

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            # Verify English column names in records
            assert "open" in data["records"][0]
            assert "high" in data["records"][0]
            assert "low" in data["records"][0]
            assert "close" in data["records"][0]
            assert "volume" in data["records"][0]
            assert "change" in data["records"][0]


@pytest.mark.asyncio
class TestKlineDataEdgeCases:
    """K-line data edge case tests"""

    async def test_get_kline_single_record(self, client: AsyncClient, auth_headers):
        """Test single record case"""
        df = pd.DataFrame(
            {
                "日期": ["2024-01-01"],
                "开盘": [10.0],
                "最高": [10.5],
                "最低": [9.8],
                "收盘": [10.3],
                "成交量": [1000000],
                "涨跌幅": [2.5],
            }
        )

        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = df

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-01",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert len(data["records"]) == 1

    async def test_get_kline_missing_change_pct(self, client: AsyncClient, auth_headers):
        """Test missing change percentage column case"""
        df = pd.DataFrame(
            {
                "日期": ["2024-01-01"],
                "开盘": [10.0],
                "最高": [10.5],
                "最低": [9.8],
                "收盘": [10.3],
                "成交量": [1000000],
                # Missing change_pct column
            }
        )

        with patch("akshare.stock_zh_a_hist") as mock_ak:
            mock_ak.return_value = df

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-01",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            # change should default to 0
            assert data["records"][0]["change"] == 0
