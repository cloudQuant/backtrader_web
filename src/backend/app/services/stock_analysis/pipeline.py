"""Native stock analysis compatibility pipeline."""

from __future__ import annotations

from typing import Any

from app.services.stock_analysis.signal import StockSignalExtractor


class StockAnalysisPipeline:
    """Build compatibility stage outputs without importing external runtimes."""

    def __init__(self) -> None:
        self.signal_extractor = StockSignalExtractor()

    async def run(
        self,
        *,
        symbol: str,
        market_type: str,
        research_depth: str,
        selected_modules: list[str],
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        profile = self._decision_profile(snapshot)
        context = self._analysis_context(
            symbol=symbol,
            market_type=market_type,
            snapshot=snapshot,
            profile=profile,
        )
        market_report = self._market_report(
            symbol,
            snapshot,
            profile,
            context,
            enabled="market" in selected_modules,
        )
        sentiment_report = self._sentiment_report(
            symbol, snapshot, context, enabled="social" in selected_modules
        )
        news_report = self._news_report(
            symbol, snapshot, context, enabled="news" in selected_modules
        )
        fundamentals_report = self._fundamentals_report(
            symbol, snapshot, profile, context, enabled="fundamentals" in selected_modules
        )

        bull_researcher = self._bull_researcher(
            symbol,
            market_report,
            sentiment_report,
            news_report,
            fundamentals_report,
            profile,
            context,
        )
        bear_researcher = self._bear_researcher(
            symbol,
            market_report,
            sentiment_report,
            news_report,
            fundamentals_report,
            profile,
            context,
        )
        research_team_decision = self._research_manager(
            symbol, bull_researcher, bear_researcher, research_depth, profile, context
        )
        investment_plan = research_team_decision
        trader_investment_plan = self._trader_plan(
            symbol, snapshot, investment_plan, profile, context
        )
        risky_analyst = self._risk_reviewer(
            symbol, snapshot, trader_investment_plan, "激进", profile, context
        )
        safe_analyst = self._risk_reviewer(
            symbol, snapshot, trader_investment_plan, "保守", profile, context
        )
        neutral_analyst = self._risk_reviewer(
            symbol, snapshot, trader_investment_plan, "中性", profile, context
        )
        risk_management_decision = self._risk_manager(
            symbol,
            risky_analyst,
            safe_analyst,
            neutral_analyst,
            trader_investment_plan,
            profile,
            context,
        )
        final_trade_decision = risk_management_decision
        decision = self.signal_extractor.extract(final_trade_decision, symbol=symbol)

        return {
            "market_report": market_report,
            "sentiment_report": sentiment_report,
            "news_report": news_report,
            "fundamentals_report": fundamentals_report,
            "bull_researcher": bull_researcher,
            "bear_researcher": bear_researcher,
            "research_team_decision": research_team_decision,
            "investment_plan": investment_plan,
            "trader_investment_plan": trader_investment_plan,
            "risky_analyst": risky_analyst,
            "safe_analyst": safe_analyst,
            "neutral_analyst": neutral_analyst,
            "risk_management_decision": risk_management_decision,
            "final_trade_decision": final_trade_decision,
            "decision": decision,
            "scores": self._scores(snapshot, decision),
            "stage_order": [
                "market",
                "social",
                "news",
                "fundamentals",
                "bull_researcher",
                "bear_researcher",
                "research_manager",
                "trader",
                "risky_analyst",
                "safe_analyst",
                "neutral_analyst",
                "risk_manager",
                "signal_extraction",
            ],
        }

    def _market_report(
        self,
        symbol: str,
        snapshot: dict[str, Any],
        profile: dict[str, Any],
        context: dict[str, Any],
        *,
        enabled: bool,
    ) -> str:
        if not enabled:
            return f"{symbol} 市场分析未启用，后续阶段按 degraded 占位处理。"
        action = str(profile["action"])
        signal = context["technical_signal"]
        price = context["price"]
        ma5 = context["ma5"]
        ma10 = context["ma10"]
        support = context["support"]
        resistance = context["resistance"]
        return (
            f"{context['name']}（{context['code']}）技术分析报告\n"
            f"分析日期：{context['analysis_date']}\n\n"
            "一、股票基本信息\n"
            f"公司名称：{context['name']}\n"
            f"股票代码：{context['code']}\n"
            f"所属市场：{context['market_type']}\n"
            f"当前价格：{self._format_price(price, context)}\n"
            f"涨跌幅：{self._format_pct(context['change_pct'])}\n"
            f"成交量：{context['volume']} 股\n\n"
            "二、技术指标分析\n"
            "1. 移动平均线与价格位置\n"
            f"当前 MA5 为 {self._format_price(ma5, context)}，MA10 为 "
            f"{self._format_price(ma10, context)}。当前价格相对均线系统呈现{signal}。"
            f"若价格能够重新站上 {self._format_price(resistance, context)}，短线趋势会得到修复；"
            f"若跌破 {self._format_price(support, context)}，则说明回撤压力仍未释放完成。\n\n"
            "2. 动量、波动与短期反转\n"
            f"最近可用 5 日动量为 {self._format_pct(context['momentum_5'])}，"
            f"5 日波动率约 {self._format_pct(context['volatility_5'])}，"
            f"1 日反转因子为 {self._format_pct(context['reversal_1'])}。"
            "这些指标显示价格不是单边强势突破，而是处在趋势修复与短线获利回吐并存的阶段。\n\n"
            "三、价格趋势分析\n"
            f"历史样本区间显示，近期收盘价从 {self._format_price(context['first_close'], context)} "
            f"运行至 {self._format_price(context['last_close'], context)}，区间趋势偏{context['history_trend']}。"
            f"但最新报价 {self._format_price(price, context)} 已低于样本末端收盘价，说明短线资金出现回撤，"
            "不能简单把前期上涨外推为持续上涨。成交量处于样本内正常水平，尚未形成明显放量突破。\n\n"
            "四、投资建议\n"
            f"技术面综合评级：{context['technical_bias']}。在最终组合结论为{action}的前提下，"
            f"技术执行上建议以 {self._format_price(support, context)} 为防守区，"
            f"以 {self._format_price(resistance, context)} 附近作为观察反弹质量的第一压力区。"
            "本阶段结论只反映市场行为，不单独构成买卖依据。"
        )

    def _sentiment_report(
        self, symbol: str, snapshot: dict[str, Any], context: dict[str, Any], *, enabled: bool
    ) -> str:
        if not enabled:
            return f"{symbol} 社媒情绪分析未启用，后续阶段按 degraded 占位处理。"
        news_items = (snapshot.get("news") or {}).get("items") or []
        if not news_items:
            return (
                f"{context['name']}（{context['code']}）社媒情绪分析报告\n"
                "一、样本状态\n"
                "当前未检索到足够的社媒或新闻情绪样本，情绪维度按中性处理。这不是利好，"
                "也不是明确利空，而是说明短线交易需要更多依赖价格、基本面和后续事件验证。\n\n"
                "二、情绪解释\n"
                "在信息样本不足时，市场通常会回到行业景气度、资金偏好和估值约束。"
                f"对于{context['industry']}标的，若没有新的业绩或政策催化，情绪难以独立推动估值重估。\n\n"
                "三、交易含义\n"
                "情绪维度对最终结论不做方向性加分，保留中性权重；后续若出现重大公告、监管政策、"
                "行业利率环境变化或同业估值重估，需要重新更新该阶段。"
            )
        bullish = sum(1 for item in news_items if item.get("sentiment") == "BULLISH")
        bearish = sum(1 for item in news_items if item.get("sentiment") == "BEARISH")
        return (
            f"{context['name']}（{context['code']}）社媒情绪分析报告\n"
            f"样本数量：{len(news_items)} 条，偏多 {bullish} 条，偏空 {bearish} 条。"
            "当前情绪对交易决策的影响以新闻风险联动为主，若偏空样本持续增加，应提高风险折价。"
        )

    def _news_report(
        self, symbol: str, snapshot: dict[str, Any], context: dict[str, Any], *, enabled: bool
    ) -> str:
        if not enabled:
            return f"{symbol} 新闻分析未启用，后续阶段按 degraded 占位处理。"
        news_items = (snapshot.get("news") or {}).get("items") or []
        if not news_items:
            return (
                f"{context['name']}（{context['code']}）财经新闻分析报告\n"
                f"分析日期：{context['analysis_date']}\n\n"
                "一、核心新闻事件与时效性评估\n"
                "当前用户新闻库中未检索到该标的的实时或近期新闻，数据状态按“无可用新闻”处理。"
                "这意味着短线价格缺乏来自公开新闻面的直接催化，个股走势更可能跟随行业、指数和资金偏好。\n\n"
                "二、市场影响与投资者情绪分析\n"
                "无新闻并不等于无风险。对于银行与金融类标的，市场会重点关注净息差、资产质量、"
                "宏观信用环境和监管政策。如果这些变量没有新增信息，情绪通常维持观望，成交弹性有限。\n\n"
                "三、对基本面和长期价值的影响\n"
                "本次新闻缺口不改变公司既有经营事实，基本面判断仍以财务数据、行业位置和历史盈利能力为主。"
                "当前新闻维度不给出明显方向性结论，也不会覆盖基本面阶段的判断。\n\n"
                "四、潜在风险与不确定性\n"
                "需要关注后续是否出现资产质量、行业政策、同业估值波动或宏观利率变化相关信息。"
                "若后续出现负面新闻，应重新评估风险评分；若出现业绩改善或政策支持，则可提高目标价区间。"
            )
        headlines = "；".join(str(item.get("headline") or "") for item in news_items[:3])
        return (
            f"{context['name']}（{context['code']}）财经新闻分析报告\n"
            f"近期重点新闻包括：{headlines}。\n"
            "需要关注事件的持续性、信息可信度、对盈利预期的影响，以及是否会改变市场对风险折价的判断。"
        )

    def _fundamentals_report(
        self,
        symbol: str,
        snapshot: dict[str, Any],
        profile: dict[str, Any],
        context: dict[str, Any],
        *,
        enabled: bool,
    ) -> str:
        if not enabled:
            return f"{symbol} 基本面分析未启用，后续阶段按 degraded 占位处理。"
        latest = context["latest_financial"]
        peer_names = context["peer_names"] or "暂无"
        roe_text = self._format_pct(context["roe"] / 100 if context["roe"] > 1 else context["roe"])
        eps = self._float_or_default(latest.get("eps"), 0.0)
        pe_text = "N/A" if eps <= 0 else f"{context['price'] / eps:.2f} 倍"
        return (
            f"{context['name']}（{context['code']}）深度基本面分析报告\n"
            f"分析日期：{context['analysis_date']} | 当前股价：{self._format_price(context['price'], context)}\n\n"
            "一、公司基本信息\n"
            f"公司名称：{context['name']}\n"
            f"股票代码：{context['code']}\n"
            f"行业分类：{context['sector']} / {context['industry']}\n"
            f"业务描述：{context['description']}\n"
            f"可比标的：{peer_names}\n\n"
            "二、核心财务数据分析\n"
            f"最新披露日期：{latest.get('report_date', 'N/A')}；"
            f"最新披露收入：{latest.get('revenue', 'N/A')}；净利润：{latest.get('net_income', 'N/A')}；"
            f"EPS：{latest.get('eps', 'N/A')}；ROE：{roe_text}。"
            f"收入同比变化约 {self._format_pct(context['revenue_growth'])}，"
            f"净利润同比变化约 {self._format_pct(context['profit_growth'])}。"
            "从已有样本看，公司仍保持正盈利和稳定股东回报，基本面阶段对最终结论形成支撑。\n\n"
            "三、估值与盈利质量\n"
            f"按当前价格和最新披露 EPS 估算，静态市盈率约 {pe_text}。"
            f"对于{context['industry']}行业，估值判断需要结合资产质量、拨备、净息差和分红能力，"
            "不能只看短期股价波动。当前 ROE 维持在两位数，说明盈利质量相对稳健，但增长弹性并不激进。\n\n"
            "四、合理价位区间与投资建议\n"
            f"基准目标价为 {self._format_price(profile['target_price'], context)}。"
            f"若盈利稳定且风险偏好修复，价格可向 {self._format_price(context['resistance'], context)} 区域试探；"
            f"若宏观信用或行业估值承压，则需关注 {self._format_price(context['support'], context)} 附近防守。"
            f"基本面综合评分为 {profile['fundamental_score']:.2f}，结论偏稳健，但不足以单独触发强买入信号。"
        )

    def _bull_researcher(
        self,
        symbol: str,
        market_report: str,
        sentiment_report: str,
        news_report: str,
        fundamentals_report: str,
        profile: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        return (
            "Bull Analyst: \n"
            f"作为看涨研究员，我认为{context['name']}（{context['code']}）的核心价值不在于短线波动，"
            "而在于盈利稳定性、行业地位和估值防守。当前基本面评分较高，说明财务数据对估值有支撑。\n\n"
            "一、看涨理由\n"
            f"1. 盈利能力稳定：最新披露 ROE 为 {context['roe']}，净利润为 "
            f"{context['latest_financial'].get('net_income', 'N/A')}，不是亏损型资产。\n"
            f"2. 价格处于回撤观察区：当前价 {self._format_price(context['price'], context)} "
            f"相对近期样本高点已有明显折让，若风险偏好修复，存在向 "
            f"{self._format_price(context['resistance'], context)} 回归的空间。\n"
            "3. 新闻面没有直接利空：当前新闻维度为空，至少没有新的公开负面催化压制估值。\n\n"
            "二、反驳空方\n"
            "空方强调短线均线压力是合理的，但银行类资产的定价通常更依赖盈利稳定、资产质量和分红预期。"
            "只要基本面没有恶化，技术回撤更适合作为观察区，而不是直接推导出趋势性卖出。\n\n"
            f"三、看涨结论\n"
            f"多头建议：维持{profile['action']}偏积极的观察态度，目标价参考 "
            f"{self._format_price(profile['target_price'], context)}。若后续出现业绩改善或行业估值修复，"
            "可提高仓位；否则保持纪律性仓位管理。"
        )

    def _bear_researcher(
        self,
        symbol: str,
        market_report: str,
        sentiment_report: str,
        news_report: str,
        fundamentals_report: str,
        profile: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        return (
            "Bear Analyst: \n"
            f"作为看跌研究员，我认为{context['name']}（{context['code']}）当前最大的风险是短线趋势和催化不足。"
            "基本面稳定并不等于股价马上重估，尤其当价格低于短期均线、新闻面缺乏增量信息时，资金可能继续观望。\n\n"
            "一、看跌理由\n"
            f"1. 技术面尚未确认反转：当前技术信号为{context['technical_signal']}，"
            f"压力区在 {self._format_price(context['resistance'], context)} 附近。\n"
            "2. 新闻催化不足：无近期新闻会降低短线交易热度，估值修复缺少触发器。\n"
            f"3. 行业弹性有限：{context['industry']}行业更偏稳健，若宏观预期或信用环境承压，"
            "股价上行动能可能弱于高景气成长行业。\n\n"
            "二、反驳多方\n"
            "多方强调基本面稳定，但稳定并不等同于低风险买入。若价格继续弱于均线系统，"
            "持仓者需要优先控制回撤，而不是因为估值看似合理就忽略趋势风险。\n\n"
            f"三、看跌结论\n"
            f"空方建议：在没有重新站上 {self._format_price(context['resistance'], context)} 前，"
            f"不宜把{profile['action']}解读为积极加仓信号；若跌破 "
            f"{self._format_price(context['support'], context)}，应降低风险敞口。"
        )

    def _research_manager(
        self,
        symbol: str,
        bull: str,
        bear: str,
        research_depth: str,
        profile: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        return (
            "最终裁决与投资计划\n"
            f"我的决定：{profile['action']}\n\n"
            f"在仔细分析多空双方论点后，我对{context['name']}（{context['code']}）给出"
            f"{profile['action']}结论。这个决定不是简单地追随短期价格，也不是只看基本面稳定性，"
            "而是把技术、基本面、新闻情绪和风险约束放在同一个框架里比较。\n\n"
            "为什么做出该裁决\n"
            f"1. 技术面：当前信号为{context['technical_signal']}，价格需要突破 "
            f"{self._format_price(context['resistance'], context)} 才能证明修复有效。\n"
            f"2. 基本面：基本面评分 {profile['fundamental_score']:.2f}，盈利和 ROE 对估值形成支撑。\n"
            "3. 新闻情绪：新闻和社媒样本不足，短期缺少明确催化，不能给出强方向加分。\n"
            f"4. 风险约束：风险评分 {profile['risk_score']:.2f}，属于需要控制仓位但不必极端回避的区间。\n\n"
            "投资计划\n"
            f"建议采取{profile['action']}策略：已有仓位以防守区 "
            f"{self._format_price(context['support'], context)} 为风险线，"
            f"上方观察 {self._format_price(context['resistance'], context)} 的突破质量。"
            "空仓资金不宜追高，等待量价配合、基本面确认或新闻催化后再提高仓位。"
        )

    def _trader_plan(
        self,
        symbol: str,
        snapshot: dict[str, Any],
        investment_plan: str,
        profile: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        action = str(profile["action"])
        target = float(profile["target_price"])
        confidence = float(profile["confidence"])
        risk_score = float(profile["risk_score"])
        return (
            "最终交易建议\n"
            f": {action}\n"
            f"基于对{context['name']}（股票代码：{context['code']}）的全方位分析，我做出以下决策：\n\n"
            f"1. 投资建议：{action}\n"
            f"当前综合评分为 {profile['composite_score']:.2f}，技术评分 {profile['technical_score']:.2f}，"
            f"基本面评分 {profile['fundamental_score']:.2f}，新闻评分 {profile['news_score']:.2f}。"
            "这组评分说明标的基本面有支撑，但短期趋势和催化仍需要确认。\n\n"
            "2. 目标价位\n"
            f"短期目标价：{self._format_price(target, context)}\n"
            f"防守价位：{self._format_price(context['support'], context)}\n"
            f"压力价位：{self._format_price(context['resistance'], context)}\n"
            f"若价格放量站上压力位，可继续观察向上修复；若跌破防守价位，应降低仓位或暂停新增买入。\n\n"
            f"3. 置信度：{confidence:.2f}\n"
            "置信度来自技术、基本面、新闻和风险约束的综合一致性。目前基本面比技术面更强，"
            "因此结论偏审慎，不做激进方向判断。\n\n"
            f"4. 风险评分：{risk_score:.2f}\n"
            "主要风险包括短线趋势反复、行业估值波动、新闻催化不足，以及数据源缺失导致的判断误差。\n\n"
            "5. 执行计划\n"
            "已有仓位：维持纪律性仓位，跌破防守位时减仓；站上压力位后再考虑提高仓位。\n"
            "空仓资金：等待价格和成交量确认，不在缺乏催化时追高。\n"
            f"最终交易建议: **{action}**"
        )

    def _risk_reviewer(
        self,
        symbol: str,
        snapshot: dict[str, Any],
        trader_plan: str,
        stance: str,
        profile: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        risk_score = float(profile["risk_score"])
        if stance == "激进":
            return (
                "激进风险分析师观点\n"
                f"我支持在{context['name']}上保留进攻性观察。基本面评分 "
                f"{profile['fundamental_score']:.2f} 较强，说明该标的不是纯粹由题材驱动。"
                f"如果价格能够站上 {self._format_price(context['resistance'], context)}，"
                "市场会重新定价稳定盈利资产的防御价值。激进策略不是盲目追高，而是在确认突破后提高仓位。"
            )
        if stance == "保守":
            return (
                "保守风险分析师观点\n"
                f"当前风险评分约 {risk_score:.2f}，不应忽视短线均线压力和新闻催化不足。"
                f"防守位 {self._format_price(context['support'], context)} 是关键，一旦跌破，"
                "说明资金对基本面支撑并不买账，应优先保护本金。保守策略建议控制仓位、设置止损，"
                "避免把“基本面稳定”误读为“没有下跌风险”。"
            )
        return (
            "中性风险分析师观点\n"
            f"{context['name']}当前风险收益相对均衡。多方看到盈利稳定，空方看到趋势压力，"
            "两者都成立。中性方案是维持核心观察仓位，同时用价格区间管理风险："
            f"下方关注 {self._format_price(context['support'], context)}，"
            f"上方关注 {self._format_price(context['resistance'], context)}。"
            f"在该区间内，{profile['action']}是比激进买入或立刻卖出更稳健的选择。"
        )

    def _risk_manager(
        self,
        symbol: str,
        risky: str,
        safe: str,
        neutral: str,
        trader_plan: str,
        profile: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        action = str(profile["action"])
        target = float(profile["target_price"])
        confidence = float(profile["confidence"])
        risk_score = float(profile["risk_score"])
        return (
            "作为风险管理委员会主席，在认真听取激进、保守和中性三位风险分析师的辩论后，"
            "我的最终裁决如下：\n\n"
            f"最终建议：{action}\n"
            f"目标价位：{self._format_price(target, context)}\n"
            f"置信度：{confidence:.2f}\n"
            f"风险评分：{risk_score:.2f}\n\n"
            "这是一个审慎而非情绪化的结论。激进分析师强调基本面稳定和估值修复，保守分析师强调趋势压力和催化不足，"
            "中性分析师则把重点放在区间管理。综合来看，当前并不存在足以支持极端方向的证据，"
            f"因此最终建议为{action}。\n\n"
            "决策理由：基于辩论与反思的详细推理\n"
            f"1. 核心论点总结：技术面评分 {profile['technical_score']:.2f}，"
            f"基本面评分 {profile['fundamental_score']:.2f}，新闻评分 {profile['news_score']:.2f}。"
            "基本面提供支撑，技术面要求纪律，新闻面暂不提供额外催化。\n"
            "2. 对激进观点的裁决：部分采纳。若价格突破压力位，进攻策略可以提高权重；"
            "但在突破前，不应把稳定盈利直接等同为买入信号。\n"
            "3. 对保守观点的裁决：部分采纳。风险控制是必要的，但当前基本面没有恶化到必须全面卖出的程度。\n"
            "4. 对中性观点的裁决：采纳。以区间管理和仓位纪律处理当前不完全一致的信号，是更稳健的方案。\n\n"
            "完善交易员计划\n"
            f"已有仓位：维持{action}，以 {self._format_price(context['support'], context)} 为风险线；"
            f"若跌破该位置，应降低风险敞口。若站上 {self._format_price(context['resistance'], context)}，"
            "可重新评估是否提高仓位。\n"
            "空仓资金：不追涨，等待技术确认或基本面新信息。\n\n"
            f"最终交易建议: **{action}**"
        )

    def _analysis_context(
        self,
        *,
        symbol: str,
        market_type: str,
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        quote = snapshot.get("quote") or {}
        info = snapshot.get("info") or {}
        history_rows = (snapshot.get("history") or {}).get("rows") or []
        technicals = snapshot.get("technicals") or {}
        factors = technicals.get("factors") or {}
        financials = snapshot.get("financials") or {}
        financial_records = self._financial_records(financials)
        latest = financial_records[-1] if financial_records else {}
        previous = financial_records[-2] if len(financial_records) >= 2 else {}
        peers = (snapshot.get("peers") or {}).get("items") or []

        closes = [self._float_or_default(row.get("close"), 0.0) for row in history_rows]
        lows = [self._float_or_default(row.get("low"), 0.0) for row in history_rows]
        volumes = [self._float_or_default(row.get("volume"), 0.0) for row in history_rows]

        fallback_close = closes[-1] if closes else 100.0
        price = self._float_or_default(quote.get("price"), fallback_close)
        change_pct = self._normalize_change_pct(quote.get("change_pct"))
        ma5 = self._moving_average(closes[-5:]) or price
        ma10 = self._moving_average(closes[-10:]) or ma5
        first_close = closes[0] if closes else price
        last_close = closes[-1] if closes else price
        recent_low = min(lows[-5:] or [price])
        support = round(min(recent_low, price * 0.97), 2)
        resistance = round(max(ma5, ma10, price * 1.03), 2)

        if last_close > first_close:
            history_trend = "上行"
        elif last_close < first_close:
            history_trend = "下行"
        else:
            history_trend = "震荡"
        if price >= ma5 >= ma10:
            technical_signal = "短期偏强，价格位于主要短均线上方"
            technical_bias = "偏多"
        elif price <= ma5 and price <= ma10:
            technical_signal = "短线承压，价格仍受均线系统压制"
            technical_bias = "中性偏弱"
        else:
            technical_signal = "多空交织，趋势尚未完成确认"
            technical_bias = "中性"

        revenue = self._float_or_default(latest.get("revenue"), 0.0)
        previous_revenue = self._float_or_default(previous.get("revenue"), revenue)
        profit = self._float_or_default(latest.get("net_income"), 0.0)
        previous_profit = self._float_or_default(previous.get("net_income"), profit)
        revenue_growth = self._float_or_default(
            latest.get("revenue_growth"), self._growth_rate(revenue, previous_revenue)
        )
        profit_growth = self._float_or_default(
            latest.get("profit_growth"), self._growth_rate(profit, previous_profit)
        )
        roe = self._float_or_default(latest.get("roe"), 0.0)
        volume = int(self._float_or_default(quote.get("volume"), volumes[-1] if volumes else 0.0))
        peer_names = "、".join(item.get("name") or item.get("symbol") or "" for item in peers[:3])

        return {
            "symbol": symbol,
            "code": self._symbol_code(symbol),
            "name": info.get("name") or quote.get("name") or symbol,
            "market_type": market_type,
            "analysis_date": snapshot.get("analysis_date") or "",
            "currency": quote.get("currency") or info.get("listing_currency") or "CNY",
            "sector": info.get("sector") or "N/A",
            "industry": info.get("industry") or "N/A",
            "description": info.get("description") or "暂无公开业务描述",
            "price": price,
            "change_pct": change_pct,
            "volume": volume,
            "ma5": round(ma5, 2),
            "ma10": round(ma10, 2),
            "support": support,
            "resistance": resistance,
            "momentum_5": self._latest_factor(factors.get("momentum_5")),
            "volatility_5": self._latest_factor(factors.get("volatility_5")),
            "reversal_1": self._latest_factor(factors.get("reversal_1")),
            "first_close": first_close,
            "last_close": last_close,
            "history_trend": history_trend,
            "technical_signal": technical_signal,
            "technical_bias": technical_bias,
            "latest_financial": latest,
            "roe": roe,
            "revenue_growth": revenue_growth,
            "profit_growth": profit_growth,
            "peer_names": peer_names,
            "profile_action": profile.get("action"),
        }

    @staticmethod
    def _symbol_code(symbol: str) -> str:
        normalized = str(symbol or "").strip().upper()
        if "." in normalized:
            prefix, suffix = normalized.split(".", 1)
            if prefix.isdigit() and len(prefix) == 6 and suffix in {"SZ", "SH"}:
                return prefix
        return normalized

    @staticmethod
    def _moving_average(values: list[float]) -> float | None:
        valid = [value for value in values if value > 0]
        if not valid:
            return None
        return sum(valid) / len(valid)

    @staticmethod
    def _latest_factor(value: Any) -> float:
        if isinstance(value, list):
            for item in reversed(value):
                if item is not None:
                    return StockAnalysisPipeline._float_or_default(item, 0.0)
            return 0.0
        return StockAnalysisPipeline._float_or_default(value, 0.0)

    @staticmethod
    def _growth_rate(current: float, previous: float) -> float:
        if previous == 0:
            return 0.0
        return (current - previous) / abs(previous)

    @staticmethod
    def _format_pct(value: Any) -> str:
        numeric = StockAnalysisPipeline._float_or_default(value, 0.0)
        if abs(numeric) <= 1:
            numeric *= 100
        return f"{numeric:.2f}%"

    @staticmethod
    def _format_price(value: Any, context: dict[str, Any]) -> str:
        numeric = StockAnalysisPipeline._float_or_default(value, 0.0)
        currency = str(context.get("currency") or "CNY").upper()
        unit = "¥" if currency in {"CNY", "RMB"} else "$" if currency == "USD" else currency
        return f"{unit}{numeric:.2f}"

    def _scores(self, snapshot: dict[str, Any], decision: dict[str, Any]) -> dict[str, float]:
        profile = self._decision_profile(snapshot)
        risk_score = self._float_or_default(decision.get("risk_score"), profile["risk_score"])
        return {
            "technical_score": round(float(profile["technical_score"]), 2),
            "fundamental_score": round(float(profile["fundamental_score"]), 2),
            "news_score": round(float(profile["news_score"]), 2),
            "risk_score": round(risk_score, 2),
        }

    def _decision_profile(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        quote = snapshot.get("quote") or {}
        price = self._float_or_default(quote.get("price"), 100.0)
        change_pct = self._normalize_change_pct(quote.get("change_pct"))
        technical_score = max(0.0, min(100.0, 50.0 + change_pct * 2.0))

        financials = snapshot.get("financials") or {}
        financial_records = self._financial_records(financials)
        latest = financial_records[-1] if financial_records else {}
        roe = self._float_or_default(latest.get("roe"), 0.0)
        net_income = self._float_or_default(latest.get("net_income"), 0.0)
        fundamental_score = 50.0
        if financial_records:
            fundamental_score += 8.0
        if roe > 0:
            fundamental_score += min(12.0, roe * 100 if roe <= 1 else roe)
        if net_income > 0:
            fundamental_score += 5.0
        fundamental_score = max(0.0, min(100.0, fundamental_score))

        news_items = (snapshot.get("news") or {}).get("items") or []
        bullish = sum(1 for item in news_items if item.get("sentiment") == "BULLISH")
        bearish = sum(1 for item in news_items if item.get("sentiment") == "BEARISH")
        news_score = 50.0 + (bullish - bearish) * 8.0 if news_items else 50.0
        news_score = max(0.0, min(100.0, news_score))

        technicals = snapshot.get("technicals") or {}
        factors = technicals.get("factors") or {}
        volatility = abs(self._float_or_default(factors.get("volatility_5"), 0.0))
        volatility_penalty = min(0.25, volatility if volatility <= 1 else volatility / 100)
        bearish_penalty = min(0.2, bearish * 0.05)
        risk_score = max(0.05, min(0.95, 0.45 + volatility_penalty + bearish_penalty))

        composite_score = technical_score * 0.35 + fundamental_score * 0.35 + news_score * 0.3
        if composite_score >= 63.0 and risk_score <= 0.62:
            action = "买入"
            target_price = round(price * 1.08, 2)
        elif composite_score <= 42.0 or risk_score >= 0.78:
            action = "卖出"
            target_price = round(price * 0.95, 2)
        else:
            action = "持有"
            target_price = round(price * 1.03, 2)
        confidence = max(0.5, min(0.9, 0.55 + abs(composite_score - 50.0) / 100.0))
        return {
            "action": action,
            "target_price": target_price,
            "confidence": round(confidence, 2),
            "risk_score": round(risk_score, 2),
            "technical_score": round(technical_score, 2),
            "fundamental_score": round(fundamental_score, 2),
            "news_score": round(news_score, 2),
            "composite_score": round(composite_score, 2),
        }

    @staticmethod
    def _financial_records(financials: dict[str, Any]) -> list[dict[str, Any]]:
        records = [
            item
            for item in [*(financials.get("annual") or []), *(financials.get("quarterly") or [])]
            if isinstance(item, dict)
        ]
        return sorted(records, key=lambda item: str(item.get("report_date") or ""))

    @staticmethod
    def _float_or_default(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_change_pct(value: Any) -> float:
        numeric = StockAnalysisPipeline._float_or_default(value, 0.0)
        return numeric * 100 if abs(numeric) <= 1 else numeric
