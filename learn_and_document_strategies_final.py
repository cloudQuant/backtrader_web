#!/usr/bin/env python3
"""
量化交易策略学习和文档生成系统（修复版）

修复了函数定义顺序问题
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# 论文文件夹路径
PAPERS_DIR = Path("/home/yun/Downloads/论文")
PAPERS_SUBDIR = Path("/home/yun/Downloads/论文/论文")

# backtrader_web 项目路径
BACKTRADER_DIR = Path("/home/yun/Documents/backtrader_web")
STRATEGIES_DIR = BACKTRADER_DIR / "strategies"

# 创建策略目录
STRATEGIES_DIR.mkdir(exist_ok=True)

# ==================== 工具函数 ====================

def extract_strategy_name(filename: str) -> str:
    """从文件名提取策略名称"""
    # 清理文件名
    clean_name = filename.replace('.html', '').replace('_', ' ')
    return clean_name

def classify_strategy_by_keywords(content: str) -> str:
    """基于关键词分类策略"""
    content_lower = content.lower()
    
    # 动量策略
    if any(word in content_lower for word in ['momentum', 'trend', 'price action']):
        return "动量策略 (Momentum)"
    # 均值回归
    elif any(word in content_lower for word in ['mean reversion', 'mean', 'dollar']):
        return "均值回归 (Mean Reversion)"
    # 突破策略
    elif any(word in content_lower for word in ['breakout', 'channel', 'donchian']):
        return "突破策略 (Breakout)"
    # 配对交易/套利
    elif any(word in content_lower for word in ['pair', 'cointegration', 'arbitrage']):
        return "配对交易/套利"
    # 机器学习
    elif any(word in content_lower for word in ['machine learning', 'neural', 'ai', 'lstm', 'deep']):
        return "机器学习/AI 策略"
    # 波动率
    elif any(word in content_lower for word in ['volatility', 'atr', 'std', 'vix']):
        return "波动率策略"
    # 投资组合优化
    elif any(word in content_lower for word in ['optimization', 'portfolio', 'optimizer']):
        return "投资组合优化"
    # 风险管理
    elif any(word in content_lower for word in ['risk', 'drawdown', 'sharpe', 'max']):
        return "风险管理"
    # 轮动
    elif any(word in content_lower for word in ['rotation', 'rebalancing']):
        return "投资组合轮动"
    # 铁式策略
    elif any(word in content_lower for word in ['iron', 'condor']):
        return "铁式策略 (Iron Condor)"
    # 其他
    else:
        return "其他策略"

def extract_strategy_summary(content: str) -> str:
    """提取策略摘要"""
    content_lower = content.lower()
    return classify_strategy_by_keywords(content)

# ==================== 主流程 ====================

def main():
    """主函数"""
    print("="*70)
    print("📚 量化交易策略学习和文档生成系统")
    print("="*70)
    print()
    
    # 第1步：扫描 HTML 策略文档
    print("📋 步骤 1：扫描 HTML 策略文档")
    print("-"*70)
    print()
    
    html_files = list(PAPERS_SUBDIR.glob("*.html"))
    print(f"找到 {len(html_files)} 个 HTML 策略文档")
    print()
    
    # 读取前 100 个文档作为示例
    strategies = []
    for i, html_file in enumerate(html_files[:100], 1):
        try:
            with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 提取策略信息
            name = extract_strategy_name(html_file.name)
            strategy_type = classify_strategy_by_keywords(content)
            summary = extract_strategy_summary(content)
            
            strategy_info = {
                'id': i,
                'name': name,
                'filename': html_file.name,
                'type': strategy_type,
                'summary': summary,
                'content_preview': content[:500],  # 保存前 500 字符作为预览
            }
            
            strategies.append(strategy_info)
            print(f"  {i}. {name}")
            print(f"     类型: {strategy_type}")
            print(f"     摘要: {summary}")
            print()
            
        except Exception as e:
            print(f"  ❌ 读取失败: {html_file.name}: {e}")
    
    print(f"成功读取 {len(strategies)} 个策略文档")
    print()
    
    # 第2步：生成策略总览
    print("📋 步骤 2：生成策略总览")
    print("-"*70)
    print()
    
    # 按类型分组
    strategy_types = {}
    for strategy in strategies:
        if strategy['type'] not in strategy_types:
            strategy_types[strategy['type']] = []
        strategy_types[strategy['type']].append(strategy)
    
    # 生成总览文档
    overview_path = STRATEGIES_DIR / "01_STRATEGY_OVERVIEW.md"
    with open(overview_path, 'w', encoding='utf-8') as f:
        f.write("# 📚 量化交易策略总览\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**总策略数**: {len(strategies)}\n")
        f.write("---\n\n")
        
        f.write("## 📊 策略分类\n\n")
        for strat_type, strat_list in sorted(strategy_types.items()):
            f.write(f"### {strat_type}\n\n")
            f.write(f"策略数量: {len(strat_list)}\n\n")
            for strategy in strat_list[:10]:  # 每个类型只显示前 10 个
                f.write(f"- {strategy['name']}\n")
                f.write(f"  - 摘要: {strategy['summary']}\n")
            f.write(f"  - 文件: {strategy['filename']}\n")
            f.write(f"  - 预览: ... (查看详细文档)\n")
            f.write("---\n\n")
        
        f.write("---\n\n")
        f.write("## 📝 详细策略列表\n\n")
        f.write(f"以下是所有策略的详细信息：\n\n")
        
        # 按字母排序
        sorted_strategies = sorted(strategies, key=lambda x: x['name'])
        
        for i, strategy in enumerate(sorted_strategies, 1):
            f.write(f"### {i}. {strategy['name']}\n\n")
            f.write(f"**类型**: {strategy['type']}\n")
            f.write(f"**文件**: `{strategy['filename']}`\n")
            f.write(f"**摘要**: {strategy['summary']}\n")
            f.write(f"**内容预览**:\n\n")
            f.write(f"```html\n{strategy['content_preview']}\n```\n")
            f.write("---\n\n")
    
    print(f"✅ 生成策略总览: {overview_path}")
    print()
    
    # 第3步：生成策略分析报告
    print("📋 步骤 3：生成策略分析报告")
    print("-"*70)
    print()
    
    analysis_path = STRATEGIES_DIR / "02_STRATEGY_ANALYSIS.md"
    with open(analysis_path, 'w', encoding='utf-8') as f:
        f.write("# 📊 量化交易策略分析报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("---\n\n")
        
        f.write("## 🎯 常见策略类型分析\n\n")
        f.write("### 1. 动量策略 (Momentum)\n")
        f.write("**原理**: 利用价格趋势延续性\n")
        f.write("**适用市场**: 趋势明显的市场\n")
        f.write("**代表指标**: MA, RSI, MACD\n")
        f.write("**有效性原因**: 市场动量效应\n")
        f.write("\n---\n\n")
        
        f.write("### 2. 均值回归 (Mean Reversion)\n")
        f.write("**原理**: 价格回归到均值\n")
        f.write("**适用市场**: 震荡市场\n")
        f.write("**代表指标**: 布林带、均值\n")
        f.write("**有效性原因**: 价格回归理论\n")
        f.write("\n---\n\n")
        
        f.write("### 3. 突破策略 (Breakout)\n")
        f.write("**原理**: 突破关键位置\n")
        f.write("**适用市场**: 横盘市场\n")
        f.write("**代表指标**: 通道、支撑/阻力\n")
        f.write("**有效性原因**: 价格突破效应\n")
        f.write("\n---\n\n")
        
        f.write("### 4. 机器学习/AI 策略\n")
        f.write("**原理**: 使用 ML 模型预测\n")
        f.write("**适用市场**: 高频交易\n")
        f.write("**代表方法**: LSTM, Transformer, RL\n")
        f.write("**有效性原因**: 能发现非线性关系\n")
        f.write("\n---\n\n")
        
        f.write("### 5. 铁式策略 (Iron Condor)\n")
        f.write("**原理**: 利用时间价值衰减\n")
        f.write("**适用市场**: 波动率适中的市场\n")
        f.write("**代表配置**: 不同行权价\n")
        f.write("**有效性原因**: 对冲风险\n")
        f.write("\n---\n\n")
        
        f.write("### 6. 投资组合优化\n")
        f.write("**原理**: 优化资产配置\n")
        f.write("**适用市场**: 长期投资\n")
        f.write("**代表方法**: 马科维茨、遗传算法\n")
        f.write("**有效性原因**: 风险分散化\n")
        f.write("\n---\n\n")
        
        f.write("## 📈 策略有效性分析\n\n")
        f.write("### 为什么这些策略可能有效？\n\n")
        f.write("1. **数据支持**: 有大量历史数据支撑\n")
        f.write("2. **学术研究**: 经过严格的回测和验证\n")
        f.write("3. **市场验证**: 在实盘中有成功案例\n")
        f.write("4. **逻辑完善**: 策略逻辑清晰且可复制\n")
        f.write("5. **参数优化**: 经过优化的参数组合\n")
        f.write("\n---\n\n")
    
    print(f"✅ 生成策略分析报告: {analysis_path}")
    print()
    
    # 第4步：生成策略实现模板
    print("📋 步骤 4：生成策略实现模板")
    print("-"*70)
    print()
    
    # 为每个主要类型生成模板
    template_path = STRATEGIES_DIR / "03_STRATEGY_TEMPLATES.md"
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write("# 🧪 策略实现模板\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("---\n\n")
        
        f.write("## 📝 模板 1: 动量策略实现\n\n")
        f.write("```python\n")
        f.write("import backtrader as bt\n\n")
        f.write("class MomentumStrategy(bt.Strategy):\n")
        f.write("    params = (\n")
        f.write("        ('period', 20),\n")
        f.write("    )\n\n")
        f.write("    def __init__(self):\n")
        f.write("        self.dataclose = self.datas[0].close\n")
        f.write("        self.order = self.datas[0].close\n")
        f.write("        self.sma = bt.indicators.SMA(self.dataclose, period=self.params.period)\n\n")
        f.write("    def next(self):\n")
        f.write("        if not self.position:\n")
        f.write("            if self.sma[0] > self.sma[-1]:  # 上升趋势\n")
        f.write("                self.buy()\n")
        f.write("            elif self.sma[0] < self.sma[-1]:  # 下降趋势\n")
        f.write("                self.sell()\n")
        f.write("\n")
        f.write("    # TODO: 实现具体的动量策略逻辑\n")
        f.write("    pass\n")
        f.write("```\n")
        f.write("\n---\n\n")
        
        f.write("## 📝 模板 2: 均值回归策略实现\n\n")
        f.write("```python\n")
        f.write("import backtrader as bt\n")
        f.write("import numpy as np\n\n")
        f.write("class MeanReversionStrategy(bt.Strategy):\n")
        f.write("    params = (\n")
        f.write("        ('period', 20),\n")
        f.write("        ('std', 2.0),  # 标准差倍数\n")
        f.write("    )\n\n")
        f.write("    def __init__(self):\n")
        f.write("        self.dataclose = self.datas[0].close\n")
        f.write("        self.mean = bt.indicators.SMA(self.dataclose, period=self.params.period)\n")
        f.write("        self.std = bt.indicators.StdDev(self.dataclose, period=self.params.period)\n")
        f.write("\n")
        f.write("    def next(self):\n")
        f.write("        if not self.position:\n")
        f.write("            # 计算上边界和下边界\n")
        f.write("            upper_band = self.mean[0] + self.std[0] * self.params.std\n")
        f.write("            lower_band = self.mean[0] - self.std[0] * self.params.std\n")
        f.write("            \n")
        f.write("            # 当前价格超过上边界，卖出\n")
        f.write("            if self.dataclose[0] > upper_band:\n")
        f.write("                self.sell()\n")
        f.write("            # 当前价格低于下边界，买入\n")
        f.write("            elif self.dataclose[0] < lower_band:\n")
        f.write("                self.buy()\n")
        f.write("\n")
        f.write("    # TODO: 实现具体的均值回归策略逻辑\n")
        f.write("    pass\n")
        f.write("```\n")
        f.write("\n---\n\n")
        
        f.write("## 📝 模板 3: 突破策略实现\n\n")
        f.write("```python\n")
        f.write("import backtrader as bt\n")
        f.write("import talib\n\n")
        f.write("class BreakoutStrategy(bt.Strategy):\n")
        f.write("    params = (\n")
        f.write("        ('period', 20),\n")
        f.write("        ('mult', 2.0),  # 通道宽度倍数\n")
        f.write("    )\n\n")
        f.write("    def __init__(self):\n")
        f.write("        self.dataclose = self.datas[0].close\n")
        f.write("        self.datahigh = self.datas[0].high\n")
        f.write("        self.datalow = self.datas[0].low\n")
        f.write("        self.atr = bt.indicators.ATR(self.dataclose, period=self.params.period)\n")
        f.write("\n")
        f.write("    def next(self):\n")
        f.write("        if not self.position:\n")
        f.write("            # 计算 Donchian 通道\n")
        f.write("            upper_band = self.dataclose[-self.params.period-1:].max()\n")
        f.write("            lower_band = self.dataclose[-self.params.period-1:].min()\n")
        f.write("            channel_width = upper_band - lower_band\n")
        f.write("            \n")
        f.write("            # 突破上边界，买入\n")
        f.write("            if self.dataclose[0] > upper_band:\n")
        f.write("                self.buy()\n")
        f.write("            # 跌破下边界，卖出\n")
        f.write("            elif self.dataclose[0] < lower_band:\n")
        f.write("                self.sell()\n")
        f.write("\n")
        f.write("    # TODO: 实现具体的突破策略逻辑\n")
        f.write("    pass\n")
        f.write("```\n")
        f.write("\n---\n\n")
        
        f.write("## 📝 模板 4: 机器学习策略实现框架\n\n")
        f.write("```python\n")
        f.write("import backtrader as bt\n")
        f.write("import numpy as np\n")
        f.write("from sklearn.ensemble import RandomForestClassifier\n\n")
        f.write("class MLStrategy(bt.Strategy):\n")
        f.write("    params = (\n")
        f.write("        ('lookback', 20),\n")
        f.write("        ('retrain', 100),\n")
        f.write("    )\n\n")
        f.write("    def __init__(self):\n")
        f.write("        self.dataclose = self.datas[0].close\n")
        f.write("        self.model = RandomForestClassifier()\n")
        f.write("        self.features = []\n")
        f.write("        self.labels = []\n")
        f.write("\n")
        f.write("    def next(self):\n")
        f.write("        # 提取特征\n")
        f.write("        features = self.extract_features()\n")
        f.write("        \n")
        f.write("        # 训练模型或预测\n")
        f.write("        if len(self.labels) > 0:\n")
        f.write("            prediction = self.model.predict([features])[0]\n")
        f.write("            if prediction == 1:  # 买入信号\n")
        f.write("                self.buy()\n")
        f.write("            elif prediction == -1:  # 卖出信号\n")
        f.write("                self.sell()\n")
        f.write("        \n")
        f.write("    def extract_features(self):\n")
        f.write("        # TODO: 实现特征提取\n")
        f.write("        return []\n")
        f.write("```\n")
    
    print(f"✅ 生成策略模板: {template_path}")
    print()
    
    # 第5步：生成 backtrader 项目集成指南
    print("📋 步骤 5：生成项目集成指南")
    print("-"*70)
    print()
    
    integration_path = STRATEGIES_DIR / "04_PROJECT_INTEGRATION.md"
    with open(integration_path, 'w', encoding='utf-8') as f:
        f.write("# 🚀 Backtrader Web 项目集成指南\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("---\n\n")
        
        f.write("## 📂 项目结构\n\n")
        f.write("```\n")
        f.write("backtrader_web/\n")
        f.write("├── backend/\n")
        f.write("│   ├── app/\n")
        f.write("│   │   ├── strategies/  ← 策略文档目录\n")
        f.write("│   │   │   ├── 01_STRATEGY_OVERVIEW.md\n")
        f.write("│   │   │   ├── 02_STRATEGY_ANALYSIS.md\n")
        f.write("│   │   │   ├── 03_STRATEGY_TEMPLATES.md\n")
        f.write("│   │   │   └── 04_PROJECT_INTEGRATION.md\n")
        f.write("│   │   ├── models/  ← 添加策略模型\n")
        f.write("│   │   ├── services/\n")
        f.write("│   │   │   └── strategy_service.py  ← 策略服务\n")
        f.write("│   │   ├── api/\n")
        f.write("│   │   │   └── strategy.py  ← 策略 API\n")
        f.write("│   └── ...\n")
        f.write("```\n")
        f.write("\n---\n\n")
        
        f.write("## 📝 实现步骤\n\n")
        f.write("### 1. 复制策略模板\n")
        f.write("```bash\n")
        f.write("# 从文档中复制策略逻辑\n")
        f.write("# 创建新的策略文件\n")
        f.write(f"cd {BACKTRADER_DIR}/backend/app/strategies/\n")
        f.write("# 创建策略文件\n")
        f.write("touch my_momentum_strategy.py\n")
        f.write("```\n")
        f.write("\n---\n\n")
        
        f.write("### 2. 添加策略服务\n")
        f.write("```python\n")
        f.write("# 在 app/services/strategy_service.py 中添加:\n")
        f.write("\n")
        f.write("from fastapi import HTTPException\n")
        f.write("from typing import List, Dict, Any\n")
        f.write("\n")
        f.write("def analyze_strategy(code: str, params: Dict[str, Any]) -> Dict[str, Any]:\n")
        f.write("    \"\"\"分析策略代码和参数\"\"\"\n")
        f.write("    \n")
        f.write("    # 1. 验证代码语法\n")
        f.write("    import ast\n")
        f.write("    try:\n")
        f.write("        ast.parse(code)\n")
        f.write("    except SyntaxError as e:\n")
        f.write("        raise HTTPException(status_code=400, detail=f\"策略代码语法错误: {str(e)}\")\n")
        f.write("    \n")
        f.write("    # 2. 分析策略类型\n")
        f.write("    strategy_type = identify_strategy_type(code)\n")
        f.write("    \n")
        f.write("    # 3. 检查参数有效性\n")
        f.write("    required_params = get_required_params(strategy_type)\n")
        f.write("    for param in required_params:\n")
        f.write("        if param not in params:\n")
        f.write("            raise HTTPException(status_code=400, detail=f\"缺少必要参数: {param}\")\n")
        f.write("    \n")
        f.write("    return {\n")
        f.write("        \"strategy_type\": strategy_type,\n")
        f.write("        \"params_valid\": True,\n")
        f.write("        \"risk_score\": calculate_risk(params),\n")
        f.write("        \"expected_return\": estimate_return(strategy_type, params),\n")
        f.write("    }\n")
        f.write("```\n")
        f.write("\n---\n\n")
        
        f.write("### 3. 添加策略 API\n")
        f.write("```python\n")
        f.write("# 在 app/api/strategy.py 中添加:\n")
        f.write("\n")
        f.write("@router.post('/strategies/{id}/backtest', summary='回测策略')\n")
        f.write("async def backtest_strategy(\n")
        f.write("    strategy_id: str,\n")
        f.write("    request: Dict[str, Any]\n")
        f.write("    current_user=Depends(get_current_user),\n")
        f.write("    service: StrategyService=Depends(get_strategy_service),\n")
        f.write("):\n")
        f.write("    \"\"\"回测策略并生成报告\"\"\"\n")
        f.write("    \n")
        f.write("    # 1. 获取策略\n")
        f.write("    strategy = await service.get_strategy(current_user.sub, strategy_id)\n")
        f.write("    \n")
        f.write("    # 2. 准备参数\n")
        f.write("    backtest_params = request.get('params', {})\n")
        f.write("    \n")
        f.write("    # 3. 运行回测\n")
        f.write("    cerebro = bt.Cerebro()\n")
        f.write("    cerebro.addstrategy(bt.Strategy)\n")
        f.write("    # cerebro.adddata(bt.feeds...\n")
        f.write("    # cerebro.run()\n")
        f.write("    \n")
        f.write("    # 4. 生成报告\n")
        f.write("    report = generate_backtest_report(cerebro)\n")
        f.write("    \n")
        f.write("    return {\n")
        f.write("        \"task_id\": task_id,\n")
        f.write("        \"report_id\": report_id,\n")
        f.write("        \"metrics\": report['metrics'],\n")
        f.write("        \"equity_curve\": report['equity_curve'],\n")
        f.write("    }\n")
        f.write("```\n")
        f.write("\n---\n\n")
    
    print(f"✅ 生成项目集成指南: {integration_path}")
    print()
    
    # 最终总结
    print("="*70)
    print("✅ 量化交易策略学习和文档生成完成！")
    print("="*70)
    print()
    
    print("📊 统计摘要：")
    print(f"  - 总策略文档数: {len(html_files)}")
    print(f"  - 已处理文档数: {len(strategies)}")
    print(f"  - 已生成文档数: 4")
    print()
    
    print("📂 生成的文档：")
    print(f"  1. 策略总览: 01_STRATEGY_OVERVIEW.md")
    print(f"  2. 策略分析: 02_STRATEGY_ANALYSIS.md")
    print(f"  3. 策略模板: 03_STRATEGY_TEMPLATES.md")
    print(f"  4. 项目集成: 04_PROJECT_INTEGRATION.md")
    print()
    
    print(f"文档保存位置: {STRATEGIES_DIR}")
    print()
    print("🚀 下一步：")
    print("  1. 查看策略总览和分类")
    print("  2. 阅读策略分析和有效性原因")
    print("  3. 使用策略模板实现 backtrader 策略")
    print("  4. 按照集成指南添加到 backtrader_web 项目")
    print()
    print("="*70)

if __name__ == "__main__":
    main()
