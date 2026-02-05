#!/usr/bin/env python3
"""
批量策略学习系统

一次处理 10 个策略（提高处理速度）
"""
import sys
import os
from pathlib import Path
from datetime import datetime
import json
import traceback

# ==================== 路径设置 ====================
STRATEGY_DIR = Path("/home/yun/Downloads/论文/论文")
STRATEGIES_DIR = Path("/home/yun/Documents/backtrader_web/strategies")

# 创建策略目录
STRATEGIES_DIR.mkdir(exist_ok=True)

# 进度文件
PROGRESS_FILE = STRATEGIES_DIR / "99_PROGRESS.json"

# ==================== 策略类型定义 ====================

STRATEGY_TYPES = {
    "momentum": {
        "name": "动量策略",
        "name_cn": "动量策略",
        "keywords": ["momentum", "trend", "price action", "price momentum", "momentum effect", "time series momentum"],
        "summary": "基于价格趋势延续性进行交易",
        "data_requirements": [
            "OHLC 数据（开、高、低、收）",
            "价格数据（用于计算动量）",
            "成交量数据",
            "时间序列数据",
            "移动平均数据",
            "技术指标（RSI, MACD, 动量指标）",
        ],
        "effectiveness_reasons": [
            "市场动量效应：大量学术研究表明，资产价格在短期到中期内往往延续现有趋势",
            "行为金融学：投资者对信息的反应不足，导致趋势的滞后反应",
            "机构资金：机构资金的大量流入流出往往推动价格沿趋势方向运行",
        ]
    },
    "mean_reversion": {
        "name": "均值回归",
        "name_cn": "均值回归",
        "keywords": ["mean reversion", "mean", "reversion", "dollar cost", "average", "regression"],
        "summary": "利用价格回归到均值的特性进行交易",
        "data_requirements": [
            "历史价格数据",
            "移动平均数据",
            "标准差数据",
            "Z-Score 数据",
            "支撑/阻力数据",
            "相关资产价格数据（配对交易）",
        ],
        "effectiveness_reasons": [
            "均值回归理论：价格围绕其长期均值波动，极端价格最终会回归",
            "超买超卖：极端的估值（超买或超卖）往往会回归到合理水平",
            "价值投资：价值投资策略本质上是一种长期均值回归策略",
            "统计套利：基于统计关系，价格偏离均值会回归",
        ]
    },
    "breakout": {
        "name": "突破策略",
        "name_cn": "突破策略",
        "keywords": ["breakout", "channel", "donchian", "breakthrough", "resistance", "support"],
        "summary": "当价格突破关键位置时进行交易",
        "data_requirements": [
            "价格数据",
            "波动率数据（ATR）",
            "历史高点/低点",
            "成交量数据",
            "价格通道数据（如 Donchian 通道）",
            "支撑/阻力位",
        ],
        "effectiveness_reasons": [
            "价格惯性：突破重要位置往往伴随价格的惯性运行",
            "流动性吸收：突破重要位置时，通常会有大量的流动性被吸收",
            "技术分析：多数技术交易者关注关键支撑和阻力位，突破时集体行动",
            "成交量确认：突破往往伴随着成交量的放大",
        ]
    },
    "machine_learning": {
        "name": "机器学习/AI 策略",
        "name_cn": "机器学习/AI 策略",
        "keywords": ["machine learning", "neural", "ai", "lstm", "deep learning", "random forest", "gradient boosting"],
        "summary": "使用机器学习或 AI 模型预测市场方向",
        "data_requirements": [
            "历史 OHLC 数据",
            "技术指标数据",
            "市场情绪数据",
            "新闻/事件数据",
            "订单簿数据",
            "宏观经济数据",
            "衍生数据",
        ],
        "effectiveness_reasons": [
            "模式识别：AI 能发现人类无法发现的非线性模式",
            "大数据分析：机器学习能够处理和分析海量数据，发现复杂关系",
            "自适应性强：模型可以随着新数据的出现而不断更新，适应市场变化",
            "多因子融合：能够同时考虑价格、成交量、技术指标、新闻等多个因子",
        ]
    },
    "pairs_trading": {
        "name": "配对交易/套利",
        "name_cn": "配对交易/套利",
        "keywords": ["pairs", "arbitrage", "cointegration", "statistical arbitrage", "pairs trading"],
        "summary": "基于两种资产之间的统计相关性进行交易",
        "data_requirements": [
            "两种资产的价格数据",
            "协整关系数据",
            "相关性数据",
            "价差数据",
            "历史价差数据",
            "波动率数据",
        ],
        "effectiveness_reasons": [
            "协整关系：当两种资产的价格关系偏离历史正常水平时，该策略会同时做多便宜的资产和做空昂贵的资产，等待关系回归",
            "统计套利：利用统计关系进行套利，有理论支撑",
            "风险分散：配对交易策略通常具有较低的市场风险",
            "绝对收益：配对交易策略的收益往往是绝对收益（不受市场方向影响）",
        ]
    },
    "volatility": {
        "name": "波动率策略",
        "name_cn": "波动率策略",
        "keywords": ["volatility", "atr", "std", "vix", "volatility index", "implied volatility"],
        "summary": "基于市场波动率的特性进行交易",
        "data_requirements": [
            "历史价格数据",
            "收益率数据",
            "波动率指标",
            "VIX 指数",
            "期权链数据",
            "隐含波动率数据",
        ],
        "effectiveness_reasons": [
            "波动率聚集：市场波动率不是恒定的，而是呈现聚集现象",
            "风险溢价：投资者承担波动率风险会获得相应的风险溢价",
            "期权定价：期权的价值与波动率直接相关，基于波动率交易策略有其理论基础",
            "均值回归：波动率往往具有均值回归特性，可以交易",
        ]
    },
    "portfolio_optimization": {
        "name": "投资组合优化",
        "name_cn": "投资组合优化",
        "keywords": ["optimization", "portfolio", "optimizer", "mean-variance", "efficient frontier"],
        "summary": "优化资产配置",
        "data_requirements": [
            "多个资产的历史收益率数据",
            "协方差矩阵",
            "风险模型",
            "收益预期",
            "投资限制",
            "交易成本",
        ],
        "effectiveness_reasons": [
            "风险分散化：通过优化资产配置，可以最大化收益并最小化风险",
            "现代投资组合理论：基于马科维茨、CAPM 等现代投资组合理论",
            "数据驱动：基于历史数据的统计优化",
            "灵活性强：可以根据投资者风险偏好进行调整",
        ]
    },
    "risk_management": {
        "name": "风险管理",
        "name_cn": "风险管理",
        "keywords": ["risk", "drawdown", "sharpe", "crash", "protection", "edge"],
        "summary": "风险控制和对冲",
        "data_requirements": [
            "价格数据",
            "波动率数据",
            "相关性数据",
            "衍生品价格（对冲）",
            "风险指标",
        ],
        "effectiveness_reasons": [
            "风险控制：有效的风险管理是长期交易成功的关键",
            "资本保护：通过对冲可以保护资本免受重大损失",
            "降低回撤：风险管理可以降低最大回撤，提高收益稳定性",
            "心理优势：有风险控制策略的交易者更自信，可以避免情绪化交易",
        ]
    },
    "option_strategy": {
        "name": "期权策略",
        "name_cn": "期权策略",
        "keywords": ["iron", "condor", "option", "straddle", "call", "put", "butterfly"],
        "summary": "使用期权作为交易工具",
        "data_requirements": [
            "期权链数据（不同到期月份的期权价格）",
            "希腊字母数据（Delta、Gamma、Theta、Vega、Rho）",
            "隐含波动率数据",
            "标的价格数据",
            "买卖价差（Bid-Ask Spread）",
            "成交量数据（Open Interest）",
        ],
        "effectiveness_reasons": [
            "非线性收益：期权策略具有非线性的收益特征（有限损失、无限收益）",
            "时间价值衰减：期权的时间价值随着到期临近而衰减",
            "波动率微笑：实际市场波动率与理论模型存在差异，可以套利",
            "希腊字母交易：通过交易希腊字母可以对冲风险，构建中性策略",
        ]
    },
    "other": {
        "name": "其他策略",
        "name_cn": "其他策略",
        "keywords": [],
        "summary": "其他交易策略",
        "data_requirements": [
            "基础 OHLC 数据",
            "成交量数据",
            "技术指标",
        ],
        "effectiveness_reasons": [
            "数据驱动：该策略基于对历史数据的分析",
            "学术研究：有相应的学术研究或理论支撑",
            "实战验证：在实盘交易中有成功的案例",
            "持续优化：能不断优化参数",
        ]
    }
}


# ==================== 工具函数 ====================

def classify_strategy(content: str, filename: str) -> tuple:
    """
    分类策略类型（快速版）
    
    Returns:
        tuple: (strategy_type_key, confidence)
    """
    content_lower = content.lower()
    filename_lower = filename.lower()
    
    # 定义策略关键词和权重
    strategy_scores = {}
    
    # 为每种策略类型打分
    for type_key, type_info in STRATEGY_TYPES.items():
        score = 0
        for keyword in type_info['keywords']:
            if keyword in content_lower:
                score += 1
            if keyword in filename_lower:
                score += 2  # 文件名中的关键词权重更高
        strategy_scores[type_key] = score
    
    # 找到得分最高的策略类型
    if strategy_scores:
        max_score = max(strategy_scores.values())
        for type_key, score in strategy_scores.items():
            if score == max_score:
                # 计算置信度（0-1）
                confidence = min(1.0, max_score / 5.0)  # 假设最多 5 个关键词匹配
                return (type_key, confidence)
    
    # 默认返回"其他策略"
    return ("other", 0.5)


def extract_key_info(content: str, filename: str) -> dict:
    """
    提取关键信息
    """
    # 分类策略
    strategy_type_key, confidence = classify_strategy(content, filename)
    strategy_type = STRATEGY_TYPES[strategy_type_key]
    
    # 提取标题
    title = filename.replace('.html', '').replace('_', ' ')
    
    # 提取摘要
    summary = strategy_type['summary']
    
    return {
        "title": title,
        "filename": filename,
        "strategy_type": strategy_type['name'],
        "strategy_type_cn": strategy_type['name_cn'],
        "strategy_type_key": strategy_type_key,
        "confidence": confidence,
        "summary": summary,
        "data_requirements": strategy_type['data_requirements'],
        "effectiveness_reasons": strategy_type['effectiveness_reasons'],
    }


def load_progress():
    """加载进度"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "current_index": 0}


def save_progress(progress):
    """保存进度"""
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def generate_simple_md(index: int, key_info: dict) -> Path:
    """
    生成简单的 MD 文档（快速版）
    """
    # 生成安全的文件名
    title = key_info['title']
    safe_name = title.replace(' ', '_').replace('/', '_').replace('\\', '_')
    safe_name = safe_name.replace(')', '').replace('(', '')
    safe_name = safe_name.replace('[', '').replace(']', '')
    safe_name = safe_name[:100]  # 限制长度
    
    # 过滤非法字符
    safe_name = ''.join(c if c.isalnum() or c in ('_', '-') for c in safe_name)
    
    filename = f"{index:03d}_{safe_name}.md"
    md_file = STRATEGIES_DIR / filename
    
    with open(md_file, 'w', encoding='utf-8') as f:
        # 标题
        f.write("# " + key_info['title'] + "\n\n")
        
        # 元数据
        f.write("## 📋 元数据\n\n")
        f.write("**文件名**: `" + key_info['filename'] + "`\n")
        f.write("**策略类型**: " + key_info['strategy_type'] + "\n")
        f.write("**策略类型（中文）**: " + key_info['strategy_type_cn'] + "\n")
        f.write("**分类置信度**: " + f"{key_info['confidence']:.2f}" + "\n")
        f.write("\n---\n\n")
        
        # 策略概述
        f.write("## 📋 策略概述\n\n")
        f.write(key_info['summary'] + "\n\n")
        f.write("---\n\n")
        
        # 需要的数据
        f.write("## 📊 需要的数据\n\n")
        f.write("基于策略类型 `" + key_info['strategy_type'] + "`，需要以下数据：\n\n")
        for i, req in enumerate(key_info['data_requirements'], 1):
            f.write(f"{i}. {req}\n")
        f.write("\n---\n\n")
        
        # 策略有效性原因
        f.write("## ✅ 策略有效性原因\n\n")
        f.write("该策略可能有效的原因：\n\n")
        for i, reason in enumerate(key_info['effectiveness_reasons'], 1):
            f.write(f"{i}. {reason}\n")
        f.write("\n---\n\n")
        
        # 实施步骤（简化版）
        f.write("## 🧪 实施步骤\n\n")
        f.write("### 1. 策略理解\n")
        f.write("- 仔细阅读策略文档\n")
        f.write("- 理解策略的核心逻辑\n")
        f.write("- 识别策略的关键参数\n")
        f.write("\n---\n\n")
        
        f.write("### 2. 数据准备\n")
        f.write(f"- 获取 `{key_info['strategy_type']}` 所需的数据\n")
        f.write("- 清洗和预处理数据\n")
        f.write("- 计算所需的技术指标\n")
        f.write("- 确保数据质量\n")
        f.write("\n---\n\n")
        
        f.write("### 3. 策略实现\n")
        f.write("- 在 backtrader 中实现策略逻辑\n")
        f.write("- 设置策略参数\n")
        f.write("- 实现买入/卖出逻辑\n")
        f.write("- 添加风险控制\n")
        f.write("\n---\n\n")
        
        f.write("### 4. 回测验证\n")
        f.write("- 使用历史数据回测策略\n")
        f.write("- 分析回测结果\n")
        f.write("- 计算关键指标（收益率、夏普比率、最大回撤、胜率、盈亏比）\n")
        f.write("- 评估策略稳定性\n")
        f.write("\n---\n\n")
        
        f.write("### 5. 参数优化\n")
        f.write("- 使用网格搜索优化参数\n")
        f.write("- 使用贝叶斯优化参数\n")
        f.write("- 考虑不同市场环境\n")
        f.write("- 避免过拟合\n")
        f.write("\n---\n\n")
        
        f.write("### 6. 模拟交易\n")
        f.write("- 在模拟交易环境中测试策略\n")
        f.write("- 验证策略在实时情况下的表现\n")
        f.write("- 检查滑点和手续费影响\n")
        f.write("\n---\n\n")
        
        f.write("### 7. 实盘验证\n")
        f.write("- 使用小资金实盘验证\n")
        f.write("- 持续监控策略表现\n")
        f.write("- 根据市场变化调整策略\n")
        f.write("- 做好风险控制\n")
        f.write("- 避免情绪化交易\n")
        f.write("\n---\n\n")
        
        # 风险和注意事项（简化版）
        f.write("## ⚠️ 风险和注意事项\n\n")
        f.write("实施 `" + key_info['title'] + "` 策略时，需要注意：\n\n")
        f.write("### 市场风险\n")
        f.write("- 市场环境变化可能导致策略失效\n")
        f.write("- 黑天鹅事件可能对策略造成重大损失\n")
        f.write("- 市场流动性不足可能导致无法执行\n")
        f.write("\n---\n\n")
        
        f.write("### 策略风险\n")
        f.write("- 历史回测不代表未来表现\n")
        f.write("- 过拟合风险：对历史数据的过度拟合\n")
        f.write("- 参数敏感性：参数的微小变化可能对结果产生重大影响\n")
        f.write("- 样本外推：在不同市场和时间段测试\n")
        f.write("\n---\n\n")
        
        f.write("### 执行风险\n")
        f.write("- 滑点风险：实际成交价格与预期价格有偏差\n")
        f.write("- 手续费风险：高频交易可能导致手续费过高\n")
        f.write("- 延迟风险：网络延迟可能导致错过交易机会\n")
        f.write("- 订单执行风险：订单可能无法成交或部分成交\n")
        f.write("- 流动性风险：大额订单可能对价格产生冲击\n")
        f.write("\n---\n\n")
        
        f.write("### 技术风险\n")
        f.write("- 系统故障风险：服务器崩溃、网络中断\n")
        f.write("- 数据风险：历史数据缺失或错误\n")
        f.write("- API 风险：第三方 API 服务中断或限制\n")
        f.write("- 代码 bug：策略代码存在逻辑错误\n")
        f.write("- 数据一致性：不同数据源的数据不一致\n")
        f.write("\n---\n\n")
        
        f.write("### 合规风险\n")
        f.write("- 遵守交易规则和法规\n")
        f.write("- 了解相关市场的交易限制\n")
        f.write("- 避免内幕交易和市场操纵\n")
        f.write("- 做好税务申报\n")
        f.write("- 确保符合反洗钱法规\n")
        f.write("\n---\n\n")
        
        # 参数配置（简化版）
        f.write("## ⚙️ 参数配置\n\n")
        f.write("```python\n")
        f.write(f"# {key_info['title']} 策略参数\n")
        f.write("params = (\n")
        f.write(f"    # 策略类型: {key_info['strategy_type_key']}\n")
        f.write(f"    # TODO: 根据具体策略添加参数\n")
        f.write(f"    # 例如：\n")
        
        # 根据策略类型添加参数
        if key_info['strategy_type_key'] == 'momentum':
            f.write(f"    ('lookback_period', 20),  # 动量周期\n")
            f.write(f"    ('momentum_threshold', 0.02),  # 动量阈值\n")
            f.write(f"    ('risk_per_trade', 0.02),  # 每笔交易风险\n")
        elif key_info['strategy_type_key'] == 'mean_reversion':
            f.write(f"    ('lookback_period', 20),  # 均值周期\n")
            f.write(f"    ('std_dev_multiplier', 2.0),  # 标准差倍数\n")
            f.write(f"    ('entry_threshold', 2.0),  # 入场阈值（标准差倍数）\n")
            f.write(f"    ('exit_threshold', 0.0),  # 退场阈值\n")
            f.write(f"    ('risk_per_trade', 0.02),  # 每笔交易风险\n")
        elif key_info['strategy_type_key'] == 'breakout':
            f.write(f"    ('lookback_period', 20),  # 突破周期\n")
            f.write(f"    ('multiplier', 2.0),  # 通道宽度倍数\n")
            f.write(f"    ('volume_threshold', 1.2),  # 成交量确认倍数\n")
            f.write(f"    ('risk_per_trade', 0.02),  # 每笔交易风险\n")
        elif key_info['strategy_type_key'] == 'machine_learning':
            f.write(f"    ('lookback_period', 60),  # 特征提取周期\n")
            f.write(f"    ('model_type', 'random_forest'),  # 模型类型\n")
            f.write(f"    ('retrain_interval', 30),  # 重训练间隔\n")
            f.write(f"    ('prediction_threshold', 0.6),  # 预测阈值\n")
            f.write(f"    ('risk_per_trade', 0.01),  # 每笔交易风险\n")
        elif key_info['strategy_type_key'] == 'option_strategy':
            f.write(f"    ('days_to_expiry', 80),  # 到期日数\n")
            f.write(f"    ('strike_interval', 10),  # 行权价间距\n")
            f.write(f"    ('delta_neutral', True),  # 是否 Delta 中性\n")
            f.write(f"    ('long_put', False),  # 是否使用额外长 Put\n")
            f.write(f"    ('risk_per_trade', 0.03),  # 每笔交易风险\n")
        else:
            f.write(f"    ('param_1', 1.0),  # 参数 1\n")
            f.write(f"    ('param_2', 2.0),  # 参数 2\n")
            f.write(f"    ('risk_per_trade', 0.02),  # 每笔交易风险\n")
        
        f.write(")\n")
        f.write("```\n")
        f.write("\n---\n\n")
        
        # Backtrader 实现框架（简化版）
        f.write("## 🧩 Backtrader 实现框架\n\n")
        f.write("```python\n")
        f.write("import backtrader as bt\n")
        f.write("import numpy as np\n")
        f.write("\n")
        
        # 生成安全的类名
        class_safe_name = title.replace(' ', '').replace('/', '_').replace('\\', '_')
        class_safe_name = class_safe_name.replace(')', '').replace('(', '')
        class_safe_name = class_safe_name.replace('[', '').replace(']', '')
        class_safe_name = ''.join(c if c.isalnum() or c in ('_', '-') for c in class_safe_name)
        
        f.write(f"class {class_safe_name}Strategy(bt.Strategy):\n")
        f.write(f"    \"\"\"\n")
        f.write(f"    {key_info['title']} 策略\n")
        f.write(f"    \n")
        f.write(f"    策略类型: {key_info['strategy_type']}\n")
        f.write(f"    策略子类: {key_info['strategy_type_cn']}\n")
        f.write(f"    \n")
        f.write(f"    实现步骤:\n")
        f.write(f"    1. 准备所需数据\n")
        f.write(f"    2. 计算技术指标\n")
        f.write(f"    3. 生成交易信号\n")
        f.write(f"    4. 执行交易并管理风险\n")
        f.write(f"    \"\"\"\n")
        f.write(f"\n")
        f.write(f"    params = (\n")
        f.write(f"        # 策略类型: {key_info['strategy_type_key']}\n")
        f.write(f"        # TODO: 根据具体策略添加参数\n")
        f.write(f"        # 例如：\n")
        
        # 根据策略类型添加参数
        if key_info['strategy_type_key'] == 'momentum':
            f.write(f"        ('lookback_period', 20),  # 动量周期\n")
            f.write(f"        ('threshold', 0.02),  # 动量阈值\n")
            f.write(f"        ('risk', 0.02),  # 每笔交易风险\n")
        elif key_info['strategy_type_key'] == 'mean_reversion':
            f.write(f"        ('lookback_period', 20),  # 均值周期\n")
            f.write(f"        ('std', 2.0),  # 标准差倍数\n")
            f.write(f"        ('entry_std', 2.0),  # 入场标准差倍数\n")
            f.write(f"        ('exit_std', 0.0),  # 退场标准差倍数\n")
            f.write(f"        ('risk', 0.02),  # 每笔交易风险\n")
        elif key_info['strategy_type_key'] == 'breakout':
            f.write(f"        ('period', 20),  # 突破周期\n")
            f.write(f"        ('multiplier', 2.0),  # 通道宽度倍数\n")
            f.write(f"        ('volume_multiplier', 1.2),  # 成交量确认倍数\n")
            f.write(f"        ('risk', 0.02),  # 每笔交易风险\n")
        elif key_info['strategy_type_key'] == 'option_strategy':
            f.write(f"        ('days_to_expiry', 80),  # 到期日数\n")
            f.write(f"        ('strike_interval', 10),  # 行权价间距\n")
            f.write(f"        ('delta_neutral', True),  # 是否 Delta 中性\n")
            f.write(f"        ('long_put', False),  # 是否使用额外长 Put\n")
            f.write(f"        ('risk', 0.03),  # 每笔交易风险\n")
        else:
            f.write(f"        ('param_1', 1.0),  # 参数 1\n")
            f.write(f"        ('param_2', 2.0),  # 参数 2\n")
            f.write(f"        ('risk', 0.02),  # 每笔交易风险\n")
        
        f.write("    )\n")
        f.write(f"\n")
        f.write(f"    def __init__(self):\n")
        f.write(f"        super().__init__()\n")
        f.write(f"        \n")
        f.write(f"        # TODO: 初始化指标\n")
        f.write(f"        self.dataclose = self.datas[0].close\n")
        f.write(f"        self.datahigh = self.datas[0].high\n")
        f.write(f"        self.datalow = self.datas[0].low\n")
        f.write(f"        self.dataopen = self.datas[0].open\n")
        f.write(f"        self.datavolume = self.datas[0].volume\n")
        f.write(f"\n")
        f.write(f"    def next(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        核心策略逻辑\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        \n")
        f.write(f"        # TODO: 实现具体的 {key_info['strategy_type']} 逻辑\n")
        f.write(f"        # 这里的逻辑应该根据 {key_info['strategy_type_cn']} 的具体规则实现\n")
        f.write(f"        \n")
        f.write(f"        # 示例框架（需要根据具体策略调整）\n")
        f.write(f"        if not self.position:\n")
        f.write(f"            # 计算指标\n")
        f.write(f"            # TODO: 计算 {key_info['strategy_type']} 的相关指标\n")
        f.write(f"            \n")
        f.write(f"            # 生成交易信号\n")
        f.write(f"            if self.dataclose[0] > self.dataclose[-1]:  # 买入信号\n")
        f.write(f"                self.buy()\n")
        f.write(f"            elif self.dataclose[0] < self.dataclose[-1]:  # 卖出信号\n")
        f.write(f"                self.sell()\n")
        f.write(f"            else:\n")
        f.write(f"                # 持有现有仓位\n")
        f.write(f"                # TODO: 管理现有仓位\n")
        f.write(f"                pass\n")
        f.write(f"\n")
        f.write(f"        # 风险控制\n")
        f.write(f"        # TODO: 实现止损止盈逻辑\n")
        f.write(f"        # TODO: 实现仓位管理\n")
        f.write(f"        # TODO: 实现风险控制\n")
        f.write(f"        pass\n")
        f.write(f"```\n")
        f.write("\n---\n\n")
        
        # 参考链接
        f.write("## 🔗 参考链接\n\n")
        f.write(f"- 原始文档: `{key_info['filename']}`\n")
        f.write(f"- 策略类型: {key_info['strategy_type']}\n")
        f.write(f"- 策略子类: {key_info['strategy_type_cn']}\n")
        f.write("\n")
    
    return md_file


# ==================== 主循环 ====================

def main():
    """主函数"""
    print("="*70)
    print("📚 批量策略学习系统（一次处理 10 个）")
    print("="*70)
    print()
    
    # 1. 获取所有 HTML 文件
    html_files = sorted(list(STRATEGY_DIR.glob("*.html")))
    total = len(html_files)
    
    print(f"📊 总文档数: {total}")
    print()
    
    # 2. 加载进度
    progress = load_progress()
    completed_files = set(progress.get("completed", []))
    current_index = progress.get("current_index", 0)
    
    print(f"📊 已完成: {len(completed_files)}/{total}")
    print(f"📊 当前索引: {current_index}/{total}")
    print()
    
    # 3. 处理接下来的 10 个文件
    processed_count = 0
    batch_size = 10
    
    print(f"📋 批量处理: {batch_size} 个策略")
    print("-"*70)
    print()
    
    for i in range(current_index, min(current_index + batch_size, total)):
        html_file = html_files[i]
        
        print(f"📋 [{i+1}/{total}] 正在处理: {html_file.name}")
        print("-"*70)
        print()
        
        try:
            # 读取 HTML 文件
            with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            print(f"✅ 文件读取成功")
            print(f"   文件大小: {len(content)} 字符")
            print()
            
            # 提取关键信息
            print(f"🔍 分析策略内容...")
            key_info = extract_key_info(content, html_file.name)
            
            print(f"✅ 策略类型: {key_info['strategy_type']}")
            print(f"✅ 策略子类: {key_info['strategy_type_cn']}")
            print(f"✅ 分类置信度: {key_info['confidence']:.2f}")
            print()
            
            # 生成 MD 文档（快速版）
            print(f"📝 生成 MD 文档...")
            md_file = generate_simple_md(i + 1, key_info)
            
            # 更新进度
            completed_files.add(html_file.name)
            progress = {
                "completed": list(completed_files),
                "current_index": i + 1,
                "total": total,
                "progress": f"{(i + 1) * 100 // total}%"
            }
            save_progress(progress)
            
            processed_count += 1
            print(f"✅ [{i+1}/{total}] 完成: {html_file.name}")
            print(f"   生成的文档: {md_file.name}")
            print(f"   策略类型: {key_info['strategy_type']}")
            print()
            print("="*70)
            print()
            
        except Exception as e:
            print(f"❌ [{i+1}/{total}] 失败: {html_file.name}")
            print(f"   错误: {e}")
            traceback.print_exc()
            print()
            print("="*70)
            print()
    
    # 4. 生成最终报告
    print("="*70)
    print("📊 批量策略学习进度报告")
    print("="*70)
    print()
    print(f"✅ 本次处理: {processed_count} 个文档")
    print(f"✅ 累计完成: {len(completed_files)}/{total}")
    print(f"📊 总进度: {len(completed_files) * 100 // total}%")
    print()
    
    # 生成统计报告
    stats_file = STRATEGIES_DIR / "00_STRATEGY_STATS.md"
    with open(stats_file, 'w', encoding='utf-8') as f:
        f.write("# 📊 策略学习统计报告\n\n")
        f.write(f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**总文档数**: {total}\n")
        f.write(f"**已完成**: {len(completed_files)}\n")
        f.write(f"**进度**: {len(completed_files) * 100 // total}%\n")
        f.write("\n---\n\n")
        
        f.write("## 下一步\n")
        print(f"继续处理剩余 {total - len(completed_files)} 个文档")
        print(f"运行相同的脚本继续：")
        print(f"  cd {sys.path[0]}")
        print(f"  python3 batch_process_strategies.py")
    
    print(f"📝 生成的统计报告: {stats_file.name}")
    print()
    
    # 提示
    if len(completed_files) < total:
        print("="*70)
        print("🔄 继续处理下一个批次（10 个）")
        print("="*70)
        print()
        print("📊 进度已保存")
        print(f"📊 总进度: {len(completed_files)}/{total} ({len(completed_files) * 100 // total}%)")
        print()
        print("运行相同的脚本继续处理下一批文档：")
        print(f"  cd {sys.path[0]}")
        print(f"  python3 batch_process_strategies.py")
        print("="*70)
        print()
    else:
        print("="*70)
        print("✅ 所有文档处理完成！")
        print("="*70)
        print()
        print(f"📊 总文档数: {total}")
        print(f"✅ 已完成: {total}")
        print(f"📊 生成的文档数: {total}")
        print(f"📂 策略目录: {STRATEGIES_DIR}")
        print()


if __name__ == "__main__":
    main()
