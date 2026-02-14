"""
回测报告生成服务

支持导出 HTML、PDF、Excel 格式的专业回测报告
"""
import io
from typing import Dict, Any, Optional
from datetime import datetime, timezone

try:
    from jinja2 import Template
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    print("Warning: jinja2 not installed. HTML/PDF export will be disabled.")

try:
    import pandas as pd
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    PANDAS_AVAILABLE = True
    OPENPYXL_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    OPENPYXL_AVAILABLE = False
    print("Warning: pandas or openpyxl not installed. Excel export will be disabled.")

try:
    from weasyprint import HTML as WeasyPrintHTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    print("Warning: weasyprint not installed. PDF export will be disabled.")


class ReportService:
    """
    回测报告生成服务

    支持以下格式：
    1. HTML - 交互式网页报告
    2. PDF - 专业 PDF 报告
    3. Excel - 可编辑的 Excel 文件
    """

    async def generate_html_report(
        self,
        result: Dict[str, Any],
        strategy: Dict[str, Any],
    ) -> str:
        """
        生成 HTML 报告

        Args:
            result: 回测结果
            strategy: 策略信息

        Returns:
            str: HTML 内容
        """
        if not JINJA2_AVAILABLE:
            raise ImportError("请安装 jinja2: pip install jinja2")

        # HTML 模板
        template_str = '''
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{{ strategy.name }} - 回测报告</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background: #f5f5f5;
                    padding: 20px;
                }
                
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    overflow: hidden;
                }
                
                .header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                }
                
                .header h1 {
                    margin: 0;
                    font-size: 28px;
                    font-weight: bold;
                }
                
                .header p {
                    margin: 10px 0 0 0;
                    opacity: 0.9;
                }
                
                .content {
                    padding: 30px;
                }
                
                .section {
                    margin-bottom: 40px;
                }
                
                .section h2 {
                    color: #2c3e50;
                    border-bottom: 3px solid #667eea;
                    padding-bottom: 10px;
                    margin-bottom: 20px;
                }
                
                .metrics {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                }
                
                .metric-card {
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }
                
                .metric-label {
                    color: #6c757d;
                    font-size: 14px;
                    margin-bottom: 10px;
                }
                
                .metric-value {
                    font-size: 24px;
                    font-weight: bold;
                    color: #2c3e50;
                }
                
                .metric-value.positive {
                    color: #28a745;
                }
                
                .metric-value.negative {
                    color: #dc3545;
                }
                
                .table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }
                
                .table th, .table td {
                    border: 1px solid #dee2e6;
                    padding: 12px;
                    text-align: left;
                }
                
                .table th {
                    background: #f8f9fa;
                    font-weight: bold;
                }
                
                .table tr:nth-child(even) {
                    background: #f8f9fa;
                }
                
                .table tr:hover {
                    background: #e9ecef;
                }
                
                .footer {
                    background: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    color: #6c757d;
                    font-size: 14px;
                }
                
                .chart-container {
                    height: 400px;
                    margin: 20px 0;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ strategy.name }} - 回测报告</h1>
                    <p>生成时间: {{ created_at }}</p>
                    <p>回测时间范围: {{ start_date }} 至 {{ end_date }}</p>
                </div>
                
                <div class="content">
                    <div class="section">
                        <h2>回测概览</h2>
                        <div class="metrics">
                            <div class="metric-card">
                                <div class="metric-label">总收益率</div>
                                <div class="metric-value {{ 'positive' if total_return >= 0 else 'negative' }}">
                                    {{ total_return }}%
                                </div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">年化收益率</div>
                                <div class="metric-value {{ 'positive' if annual_return >= 0 else 'negative' }}">
                                    {{ annual_return }}%
                                </div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">夏普比率</div>
                                <div class="metric-value">{{ sharpe_ratio }}</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">最大回撤</div>
                                <div class="metric-value negative">{{ max_drawdown }}%</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">胜率</div>
                                <div class="metric-value">{{ win_rate }}%</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">总交易次数</div>
                                <div class="metric-value">{{ total_trades }}</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">盈利交易</div>
                                <div class="metric-value positive">{{ profitable_trades }}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>交易统计</h2>
                        <table class="table">
                            <tr>
                                <th>统计项</th>
                                <th>数值</th>
                            </tr>
                            <tr>
                                <td>总交易次数</td>
                                <td>{{ total_trades }}</td>
                            </tr>
                            <tr>
                                <td>盈利交易</td>
                                <td class="positive">{{ profitable_trades }}</td>
                            </tr>
                            <tr>
                                <td>亏损交易</td>
                                <td class="negative">{{ losing_trades }}</td>
                            </tr>
                            <tr>
                                <td>胜率</td>
                                <td>{{ win_rate }}%</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div class="section">
                        <h2>策略参数</h2>
                        <table class="table">
                            <tr>
                                <th>参数名</th>
                                <th>参数值</th>
                            </tr>
                            {% for key, value in params.items() %}
                            <tr>
                                <td>{{ key }}</td>
                                <td>{{ value }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    </div>
                    
                    <div class="section">
                        <h2>风险提示</h2>
                        <p style="color: #dc3545; background: #f8d7da; padding: 15px; border-radius: 4px;">
                            ⚠️ 本报告基于历史数据回测，历史表现不代表未来收益。实际交易可能因市场波动、手续费、滑点等因素产生与回测不同的结果。
                            请谨慎投资，控制风险。
                        </p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>由 Backtrader Web 生成</p>
                </div>
            </div>
        </body>
        </html>
        '''

        template = Template(template_str)

        # 渲染模板
        html_content = template.render(
            strategy=strategy,
            total_return=result.get('total_return', 0),
            annual_return=result.get('annual_return', 0),
            sharpe_ratio=result.get('sharpe_ratio', 0),
            max_drawdown=result.get('max_drawdown', 0),
            win_rate=result.get('win_rate', 0),
            total_trades=result.get('total_trades', 0),
            profitable_trades=result.get('profitable_trades', 0),
            losing_trades=result.get('losing_trades', 0),
            params=result.get('params', {}),
            created_at=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            start_date=result.get('start_date', ''),
            end_date=result.get('end_date', ''),
        )

        return html_content

    async def generate_pdf_report(
        self,
        result: Dict[str, Any],
        strategy: Dict[str, Any],
    ) -> bytes:
        """
        生成 PDF 报告

        Args:
            result: 回测结果
            strategy: 策略信息

        Returns:
            bytes: PDF 文件内容
        """
        if not WEASYPRINT_AVAILABLE:
            raise ImportError("请安装 weasyprint: pip install weasyprint")

        # 先生成 HTML
        html_content = await self.generate_html_report(result, strategy)

        # 转换为 PDF
        pdf_bytes = WeasyPrintHTML(string=html_content).write_pdf()

        return pdf_bytes

    async def generate_excel_report(
        self,
        result: Dict[str, Any],
        strategy: Dict[str, Any],
    ) -> bytes:
        """
        生成 Excel 报告

        Args:
            result: 回测结果
            strategy: 策略信息

        Returns:
            bytes: Excel 文件内容
        """
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            raise ImportError("请安装 pandas 和 openpyxl: pip install pandas openpyxl")

        # 创建 Excel 文件
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 概览 sheet
            overview_df = pd.DataFrame({
                '指标': ['策略名称', '标的', '开始日期', '结束日期', '总收益率', '年化收益率',
                         '夏普比率', '最大回撤', '胜率', '总交易次数', '盈利交易', '亏损交易'],
                '值': [
                    strategy.get('name', ''),
                    result.get('symbol', ''),
                    str(result.get('start_date', '')),
                    str(result.get('end_date', '')),
                    result.get('total_return', 0),
                    result.get('annual_return', 0),
                    result.get('sharpe_ratio', 0),
                    result.get('max_drawdown', 0),
                    result.get('win_rate', 0),
                    result.get('total_trades', 0),
                    result.get('profitable_trades', 0),
                    result.get('losing_trades', 0),
                ]
            })
            overview_df.to_excel(writer, sheet_name='概览', index=False)

            # 交易记录 sheet
            trades_data = result.get('trades', [])
            if trades_data:
                trades_df = pd.DataFrame(trades_data)
                trades_df.to_excel(writer, sheet_name='交易记录', index=False)

            # 资金曲线 sheet
            equity_dates = result.get('equity_dates', [])
            equity_curve = result.get('equity_curve', [])
            if equity_dates and equity_curve:
                equity_df = pd.DataFrame({
                    '日期': equity_dates,
                    '资金': equity_curve,
                })
                equity_df.to_excel(writer, sheet_name='资金曲线', index=False)

        output.seek(0)
        return output.getvalue()
