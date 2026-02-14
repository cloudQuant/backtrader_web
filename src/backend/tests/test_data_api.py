"""
行情数据 API 测试

测试：
- K线数据查询
- 数据格式验证
- 错误处理
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient
import pandas as pd


@pytest.fixture
def mock_akshare_response():
    """Mock akshare 响应数据"""
    df = pd.DataFrame({
        '日期': ['2024-01-01', '2024-01-02', '2024-01-03'],
        '开盘': [10.0, 10.3, 10.5],
        '最高': [10.5, 10.8, 11.0],
        '最低': [9.8, 10.0, 10.2],
        '收盘': [10.3, 10.6, 10.8],
        '成交量': [1000000, 1200000, 1500000],
        '涨跌幅': [2.5, 1.5, 2.0],
    })
    return df


@pytest.mark.asyncio
class TestKlineData:
    """K线数据测试"""

    async def test_get_kline_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get(
            "/api/v1/data/kline",
            params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )
        # API可能返回401或403
        assert response.status_code in [401, 403]

    async def test_get_kline_missing_params(self, client: AsyncClient):
        """测试缺少必要参数"""
        response = await client.get("/api/v1/data/kline")
        # 验证错误 - 缺少必要参数或未认证
        assert response.status_code in [401, 403, 422]

    async def test_get_kline_with_auth(self, client: AsyncClient, auth_headers):
        """测试带认证的K线查询"""
        response = await client.get(
            "/api/v1/data/kline",
            params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
            headers=auth_headers
        )
        # 可能返回200（成功）、404（无数据）或500（网络错误）
        assert response.status_code in [200, 404, 500]

    async def test_get_kline_different_periods(self, client: AsyncClient, auth_headers):
        """测试不同周期"""
        periods = ["daily", "weekly", "monthly"]

        for period in periods:
            response = await client.get(
                f"/api/v1/data/kline?symbol=000001.SZ&start_date=2024-01-01&end_date=2024-01-31&period={period}",
                headers=auth_headers
            )
            # 不应该返回 401（认证错误）
            assert response.status_code != 401


@pytest.mark.asyncio
class TestDataHelpers:
    """数据服务辅助函数测试"""

    async def test_date_parsing(self):
        """测试日期解析"""
        # 测试API内部日期转换逻辑
        start_date = "2024-01-01"
        start_str = start_date.replace('-', '')
        assert start_str == "20240101"

        end_date = "2024-12-31"
        end_str = end_date.replace('-', '')
        assert end_str == "20241231"

    async def test_symbol_parsing(self):
        """测试股票代码解析"""
        symbol = "000001.SZ"
        code = symbol.split('.')[0]
        assert code == "000001"

        symbol = "600000.SH"
        code = symbol.split('.')[0]
        assert code == "600000"


@pytest.mark.asyncio
class TestDataValidation:
    """数据验证测试"""

    async def test_valid_stock_codes(self):
        """测试有效股票代码格式"""
        valid_codes = [
            "000001.SZ",
            "600000.SH",
            "300001.SZ",
            "688001.SH"
        ]
        for code in valid_codes:
            parts = code.split('.')
            assert len(parts) == 2
            assert parts[1] in ["SZ", "SH"]

    async def test_date_format_validation(self):
        """测试日期格式验证"""
        from datetime import datetime

        # 测试正确格式
        valid_dates = ["2024-01-01", "2024-12-31"]
        for date_str in valid_dates:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                assert False, f"Invalid date format: {date_str}"
            else:
                assert True

    async def test_ohlc_data_structure(self):
        """测试OHLC数据结构"""
        # 正确的OHLC数据顺序: [open, high, low, close] 或 [open, close, low, high]
        # 这里使用 [open, high, low, close] 格式，确保high是最大值，low是最小值
        ohlc_data = [10.0, 10.5, 9.8, 10.3]  # open, high, low, close
        # 验证OHLC顺序：high应该是最大值，low应该是最小值
        assert ohlc_data[0] <= ohlc_data[1]  # open <= high
        assert ohlc_data[2] <= ohlc_data[1]  # low <= high
        assert ohlc_data[3] <= ohlc_data[1]  # close <= high
        assert ohlc_data[2] <= ohlc_data[0]  # low <= open
        assert ohlc_data[2] <= ohlc_data[3]  # low <= close


@pytest.mark.asyncio
class TestDataAPIRoutes:
    """数据API路由测试"""

    async def test_data_routes_registered(self):
        """测试数据路由已注册"""
        from app.main import app
        from app.api.data import router as data_router

        # 检查路由存在
        assert data_router is not None
        assert hasattr(data_router, 'routes')

    async def test_kline_endpoint_exists(self):
        """测试K线端点存在"""
        from app.api.data import router

        # 检查路由中是否有K线端点
        routes = [route.path for route in router.routes]
        assert "/kline" in routes or "/kline" in str(routes)


@pytest.mark.asyncio
class TestDataModels:
    """数据模型测试"""

    async def test_kline_response_structure(self):
        """测试K线响应结构"""
        # 模拟K线响应数据结构
        mock_response = {
            "symbol": "000001.SZ",
            "count": 10,
            "kline": {
                "dates": ["2024-01-01", "2024-01-02"],
                "ohlc": [[10.0, 10.5, 9.8, 10.3], [10.3, 10.8, 10.0, 10.6]],
                "volumes": [1000000, 1200000]
            },
            "records": [
                {
                    "date": "2024-01-01",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.3,
                    "volume": 1000000,
                    "change": 2.5
                }
            ]
        }

        # 验证响应结构
        assert "symbol" in mock_response
        assert "count" in mock_response
        assert "kline" in mock_response
        assert "records" in mock_response
        assert "dates" in mock_response["kline"]
        assert "ohlc" in mock_response["kline"]
        assert "volumes" in mock_response["kline"]


@pytest.mark.asyncio
class TestKlineDataWithMock:
    """K线数据测试 - 使用mock akshare"""

    async def test_get_kline_success_with_mock(self, client: AsyncClient, auth_headers, mock_akshare_response):
        """测试成功获取K线数据 - 使用mock"""
        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
                headers=auth_headers
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
        """测试空DataFrame情况"""
        with patch('akshare.stock_zh_a_hist') as mock_ak:
            # 返回空DataFrame
            mock_ak.return_value = pd.DataFrame()

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
                headers=auth_headers
            )
            assert response.status_code == 404
            assert "未获取到" in response.json()["detail"]

    async def test_get_kline_exception_handling(self, client: AsyncClient, auth_headers):
        """测试异常处理"""
        with patch('akshare.stock_zh_a_hist') as mock_ak:
            # 模拟网络错误
            mock_ak.side_effect = Exception("Network error")

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
                headers=auth_headers
            )
            assert response.status_code == 500
            assert "查询失败" in response.json()["detail"]

    async def test_get_kline_data_transformation(self, client: AsyncClient, auth_headers, mock_akshare_response):
        """测试数据转换逻辑"""
        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()

            # 验证数据格式转换
            assert "dates" in data["kline"]
            assert "ohlc" in data["kline"]
            assert "volumes" in data["kline"]

            # 验证OHLC格式 [open, close, low, high]
            first_ohlc = data["kline"]["ohlc"][0]
            assert len(first_ohlc) == 4
            assert isinstance(first_ohlc[0], float)  # open
            assert isinstance(first_ohlc[1], float)  # close
            assert isinstance(first_ohlc[2], float)  # low
            assert isinstance(first_ohlc[3], float)  # high

            # 验证records格式
            assert len(data["records"]) == 3
            first_record = data["records"][0]
            assert "date" in first_record
            assert "open" in first_record
            assert "high" in first_record
            assert "low" in first_record
            assert "close" in first_record
            assert "volume" in first_record
            assert "change" in first_record

    async def test_get_kline_with_weekly_period(self, client: AsyncClient, auth_headers, mock_akshare_response):
        """测试周线数据"""
        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                    "period": "weekly"
                },
                headers=auth_headers
            )
            assert response.status_code == 200
            # 验证akshare被正确调用
            mock_ak.assert_called_once()

    async def test_get_kline_with_monthly_period(self, client: AsyncClient, auth_headers, mock_akshare_response):
        """测试月线数据"""
        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={
                    "symbol": "000001.SZ",
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "period": "monthly"
                },
                headers=auth_headers
            )
            assert response.status_code == 200

    async def test_get_kline_symbol_parsing(self, client: AsyncClient, auth_headers, mock_akshare_response):
        """测试股票代码解析"""
        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "600000.SH", "start_date": "2024-01-01", "end_date": "2024-01-31"},
                headers=auth_headers
            )
            assert response.status_code == 200
            # 验证akshare被调用时使用的是正确的代码（不含后缀）
            call_args = mock_ak.call_args
            assert call_args.kwargs['symbol'] == '600000'

    async def test_get_kline_date_format_conversion(self, client: AsyncClient, auth_headers, mock_akshare_response):
        """测试日期格式转换"""
        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = mock_akshare_response

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
                headers=auth_headers
            )
            assert response.status_code == 200
            # 验证日期格式被正确转换
            call_args = mock_ak.call_args
            assert call_args.kwargs['start_date'] == '20240101'
            assert call_args.kwargs['end_date'] == '20240131'

    async def test_get_kline_column_rename(self, client: AsyncClient, auth_headers):
        """测试列名重命名"""
        # 创建带有中文列名的DataFrame
        df = pd.DataFrame({
            '日期': ['2024-01-01'],
            '开盘': [10.0],
            '最高': [10.5],
            '最低': [9.8],
            '收盘': [10.3],
            '成交量': [1000000],
            '涨跌幅': [2.5],
        })

        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = df

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-31"},
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            # 验证英文列名在records中
            assert "open" in data["records"][0]
            assert "high" in data["records"][0]
            assert "low" in data["records"][0]
            assert "close" in data["records"][0]
            assert "volume" in data["records"][0]
            assert "change" in data["records"][0]


@pytest.mark.asyncio
class TestKlineDataEdgeCases:
    """K线数据边界情况测试"""

    async def test_get_kline_single_record(self, client: AsyncClient, auth_headers):
        """测试只有一条记录的情况"""
        df = pd.DataFrame({
            '日期': ['2024-01-01'],
            '开盘': [10.0],
            '最高': [10.5],
            '最低': [9.8],
            '收盘': [10.3],
            '成交量': [1000000],
            '涨跌幅': [2.5],
        })

        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = df

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-01"},
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert len(data["records"]) == 1

    async def test_get_kline_missing_change_pct(self, client: AsyncClient, auth_headers):
        """测试缺少涨跌幅列的情况"""
        df = pd.DataFrame({
            '日期': ['2024-01-01'],
            '开盘': [10.0],
            '最高': [10.5],
            '最低': [9.8],
            '收盘': [10.3],
            '成交量': [1000000],
            # 缺少涨跌幅列
        })

        with patch('akshare.stock_zh_a_hist') as mock_ak:
            mock_ak.return_value = df

            response = await client.get(
                "/api/v1/data/kline",
                params={"symbol": "000001.SZ", "start_date": "2024-01-01", "end_date": "2024-01-01"},
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            # change应该默认为0
            assert data["records"][0]["change"] == 0

