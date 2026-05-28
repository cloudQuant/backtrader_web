"""
Web server for displaying backtest results.

This module provides a web-based visualization interface for backtrader
backtest results, including interactive charts for equity and drawdown curves.
"""
import json
import webbrowser
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional
import backtrader as bt

from .analyzer import BacktestAnalyzer, BacktestResult


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Results - {strategy_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header .meta {{ opacity: 0.9; font-size: 14px; }}
        .card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        }}
        .card-title {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid #f0f0f0;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }}
        .metric {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            transition: transform 0.2s;
        }}
        .metric:hover {{ transform: translateY(-2px); }}
        .metric-label {{
            font-size: 13px;
            color: #666;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .metric-value {{
            font-size: 28px;
            font-weight: 700;
        }}
        .positive {{ color: #10b981; }}
        .negative {{ color: #ef4444; }}
        .neutral {{ color: #6b7280; }}
        .chart-container {{ height: 400px; }}
        .two-cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 768px) {{
            .two-cols {{ grid-template-columns: 1fr; }}
        }}
        .info-table {{ width: 100%; border-collapse: collapse; }}
        .info-table td {{ padding: 12px 0; border-bottom: 1px solid #f0f0f0; }}
        .info-table td:first-child {{ color: #666; width: 40%; }}
        .info-table td:last-child {{ font-weight: 500; text-align: right; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 {strategy_name}</h1>
            <div class="meta">
                Symbol: {symbol} | Period: {start_date} to {end_date} |
                Initial Capital: ¥{initial_cash:,.2f} | Final Value: ¥{final_value:,.2f}
            </div>
        </div>

        <div class="card">
            <div class="card-title">Key Metrics</div>
            <div class="metrics-grid">
                <div class="metric">
                    <div class="metric-label">Total Return</div>
                    <div class="metric-value {return_class}">{total_return}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Annual Return</div>
                    <div class="metric-value {annual_class}">{annual_return}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Sharpe Ratio</div>
                    <div class="metric-value neutral">{sharpe_ratio}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Max Drawdown</div>
                    <div class="metric-value negative">{max_drawdown}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value neutral">{win_rate}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Total Trades</div>
                    <div class="metric-value neutral">{total_trades}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Profitable Trades</div>
                    <div class="metric-value positive">{profitable_trades}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Losing Trades</div>
                    <div class="metric-value negative">{losing_trades}</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">Equity Curve</div>
            <div id="equity-chart" class="chart-container"></div>
        </div>

        <div class="card">
            <div class="card-title">Drawdown Curve</div>
            <div id="drawdown-chart" class="chart-container"></div>
        </div>
    </div>

    <script>
        const resultData = {result_json};

        // Equity curve chart
        const equityChart = echarts.init(document.getElementById('equity-chart'));
        equityChart.setOption({{
            tooltip: {{
                trigger: 'axis',
                formatter: function(params) {{
                    return params[0].name + '<br/>Equity: ¥' + params[0].value.toLocaleString();
                }}
            }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', containLabel: true }},
            xAxis: {{
                type: 'category',
                data: resultData.equity_dates,
                axisLabel: {{ rotate: 45 }}
            }},
            yAxis: {{
                type: 'value',
                axisLabel: {{ formatter: '¥{{value}}' }}
            }},
            series: [{{
                name: 'Equity',
                type: 'line',
                data: resultData.equity_curve,
                smooth: true,
                lineStyle: {{ width: 2 }},
                areaStyle: {{
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        {{ offset: 0, color: 'rgba(102, 126, 234, 0.4)' }},
                        {{ offset: 1, color: 'rgba(102, 126, 234, 0.05)' }}
                    ])
                }},
                itemStyle: {{ color: '#667eea' }}
            }}]
        }});

        // Drawdown curve chart
        const drawdownChart = echarts.init(document.getElementById('drawdown-chart'));
        drawdownChart.setOption({{
            tooltip: {{
                trigger: 'axis',
                formatter: function(params) {{
                    return params[0].name + '<br/>Drawdown: ' + params[0].value.toFixed(2) + '%';
                }}
            }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', containLabel: true }},
            xAxis: {{
                type: 'category',
                data: resultData.equity_dates,
                axisLabel: {{ rotate: 45 }}
            }},
            yAxis: {{
                type: 'value',
                inverse: true,
                axisLabel: {{ formatter: '{{value}}%' }}
            }},
            series: [{{
                name: 'Drawdown',
                type: 'line',
                data: resultData.drawdown_curve,
                smooth: true,
                lineStyle: {{ width: 2 }},
                areaStyle: {{
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        {{ offset: 0, color: 'rgba(239, 68, 68, 0.4)' }},
                        {{ offset: 1, color: 'rgba(239, 68, 68, 0.05)' }}
                    ])
                }},
                itemStyle: {{ color: '#ef4444' }}
            }}]
        }});

        // Responsive to window resize
        window.addEventListener('resize', function() {{
            equityChart.resize();
            drawdownChart.resize();
        }});
    </script>
</body>
</html>'''


class ResultHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for serving backtest results."""

    result_html = ""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.result_html.encode('utf-8'))
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        """Suppress log messages."""
        pass  # Silent logging


class WebServer:
    """
    Web server for visualizing backtrader backtest results.

    This server runs a backtest and displays the results through an
    interactive web interface with ECharts visualization.

    Example:
        cerebro = bt.Cerebro()
        # ... configure strategy and data

        server = WebServer(cerebro)
        server.run(port=8000)
    """

    def __init__(self, cerebro: bt.Cerebro):
        """
        Initialize the WebServer.

        Args:
            cerebro: A configured Cerebro instance with strategy and data.
        """
        self.cerebro = cerebro
        self.analyzer = BacktestAnalyzer(cerebro)
        self.result: Optional[BacktestResult] = None
        self._server: Optional[HTTPServer] = None

    def run(self, port: int = 8000, open_browser: bool = True, blocking: bool = True):
        """
        Run backtest and start web server to display results.

        Args:
            port: Server port number, defaults to 8000.
            open_browser: Whether to automatically open browser, defaults to True.
            blocking: Whether to block execution, defaults to True.

        Returns:
            HTTPServer instance if blocking=False, None otherwise.
        """
        print("=" * 60)
        print("🚀 Backtrader Web - Backtest Visualization")
        print("=" * 60)

        # Run backtest
        print("\n📊 Running backtest...")
        self.result = self.analyzer.run()

        # Print result summary
        self._print_summary()

        # Generate HTML
        html = self._generate_html()
        ResultHandler.result_html = html

        # Start HTTP server
        self._server = HTTPServer(('0.0.0.0', port), ResultHandler)

        url = f"http://localhost:{port}"
        print(f"\n🌐 Web server started: {url}")
        print("   Press Ctrl+C to stop the server")

        # Open browser
        if open_browser:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()

        # Run server
        if blocking:
            try:
                self._server.serve_forever()
            except KeyboardInterrupt:
                print("\n\n👋 Server stopped")
                self._server.shutdown()
        else:
            thread = threading.Thread(target=self._server.serve_forever)
            thread.daemon = True
            thread.start()
            return self._server

    def stop(self):
        """Stop the web server."""
        if self._server:
            self._server.shutdown()

    def get_result(self) -> Optional[BacktestResult]:
        """
        Get the backtest result.

        Returns:
            BacktestResult object or None if backtest hasn't run.
        """
        return self.result

    def _print_summary(self):
        """Print backtest result summary to console."""
        r = self.result
        print(f"\n✅ Backtest completed!")
        print(f"   Strategy: {r.strategy_name}")
        print(f"   Symbol: {r.symbol}")
        print(f"   Period: {r.start_date} ~ {r.end_date}")
        print(f"\n📈 Return Metrics:")
        print(f"   Total Return: {r.total_return:+.2f}%")
        print(f"   Annual Return: {r.annual_return:+.2f}%")
        print(f"   Sharpe Ratio: {r.sharpe_ratio:.2f}")
        print(f"   Max Drawdown: {r.max_drawdown:.2f}%")
        print(f"\n📊 Trading Statistics:")
        print(f"   Total Trades: {r.total_trades}")
        print(f"   Win Rate: {r.win_rate:.1f}%")
        print(f"   Profitable/Losing: {r.profitable_trades}/{r.losing_trades}")

    def _generate_html(self) -> str:
        """
        Generate HTML page for backtest results.

        Returns:
            HTML string with embedded chart configuration.
        """
        r = self.result

        return HTML_TEMPLATE.format(
            strategy_name=r.strategy_name,
            symbol=r.symbol,
            start_date=r.start_date,
            end_date=r.end_date,
            initial_cash=r.initial_cash,
            final_value=r.final_value,
            total_return=r.total_return,
            annual_return=r.annual_return,
            sharpe_ratio=r.sharpe_ratio,
            max_drawdown=r.max_drawdown,
            win_rate=r.win_rate,
            total_trades=r.total_trades,
            profitable_trades=r.profitable_trades,
            losing_trades=r.losing_trades,
            return_class='positive' if r.total_return >= 0 else 'negative',
            annual_class='positive' if r.annual_return >= 0 else 'negative',
            result_json=json.dumps(r.to_dict(), ensure_ascii=False),
        )
