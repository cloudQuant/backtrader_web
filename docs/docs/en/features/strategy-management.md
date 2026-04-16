# Strategy Management

## Overview

Backtrader Web provides comprehensive strategy management with version control, similar to Git.

## Built-in Templates

118 built-in strategy templates covering:

### Trend Following
- Dual Moving Average
- MACD
- Turtle Trading
- Supertrend

### Mean Reversion
- Bollinger Bands Reversal
- KDJ
- RSI
- Stochastic

### Arbitrage
- Spot-Futures Arbitrage
- Calendar Spread

### Options
- VIX Panic Index
- Put-Call Ratio

### High Frequency
- R-Breaker
- Dual Thrust
-菲阿里四价 (Fairy Four Prices)

## API Endpoints

### Strategy CRUD

```http
# Create strategy
POST /api/v1/strategy/
Content-Type: application/json

{
  "name": "My Strategy",
  "description": "Custom mean reversion strategy",
  "code": "...",
  "parameters": {"period": 20}
}

# List strategies
GET /api/v1/strategy/

# Get strategy
GET /api/v1/strategy/{id}

# Update strategy
PUT /api/v1/strategy/{id}

# Delete strategy
DELETE /api/v1/strategy/{id}
```

### Templates

```http
GET /api/v1/strategy/templates
```

## Version Control

### Create Version

```http
POST /api/v1/strategy-versions/versions
{
  "strategy_id": 1,
  "version_name": "v1.0",
  "message": "Initial version"
}
```

### List Versions

```http
GET /api/v1/strategy-versions/strategies/{strategy_id}/versions
```

### Compare Versions

```http
POST /api/v1/strategy-versions/versions/compare
{
  "strategy_id": 1,
  "version_a": "v1.0",
  "version_b": "v1.1"
}
```

### Rollback

```http
POST /api/v1/strategy-versions/versions/rollback
{
  "strategy_id": 1,
  "target_version": "v1.0"
}
```

## Branch Management

```http
# Create branch
POST /api/v1/strategy-versions/branches
{
  "strategy_id": 1,
  "branch_name": "experiment",
  "base_version": "v1.0"
}
```
