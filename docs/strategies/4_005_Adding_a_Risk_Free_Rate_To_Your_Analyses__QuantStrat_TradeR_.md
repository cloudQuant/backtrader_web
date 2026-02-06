This is a prompt template for generating a quantitative trading strategy documentation in Chinese. It's designed to take an HTML file about a trading strategy and convert it into a structured Markdown document with 10 specific sections.

The prompt describes:

**Input:** An HTML file about "Adding a Risk-Free Rate To Your Analyses" from QuantStrat TradeR

**Required Output:** A detailed Markdown strategy document with:
1. Title (H1)
2. Strategy Overview (H2)
3. Strategy Logic (H2)
4. Required Data (H2)
5. Why the Strategy Works (H2)
6. Risks and Considerations (H2)
7. Implementation Steps (H2)
8. Parameter Configuration (H2)
9. Backtrader Implementation Framework (H2)
10. Reference Links (H2)

**Strategy Type Classification:** The prompt includes a keyword-based classification system to categorize strategies (momentum, mean reversion, breakout, machine learning, options, volatility, statistical arbitrage, portfolio optimization, risk management, earnings estimates, comprehensive strategies, etc.)

**Content:** The HTML content discusses an Elastic Asset Allocation (EAA) strategy that incorporates a risk-free rate using the 13-week treasury bill (IRX index) to calculate excess returns rather than absolute returns.

**Key insight from the content:** Despite the theoretical appeal of using risk-free rates, the backtest comparison showed that using excess returns over the risk-free rate didn't improve performance compared to using absolute returns in the EAA strategy.
