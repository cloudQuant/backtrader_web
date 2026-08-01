# 迭代190：单股分析信号闭环与预测质量验证验收计划

## 1. 验收目标

验收的目标不是证明某个信号“必然赚钱”，而是证明单股分析的 `BUY/SELL/WATCH`：

1. 基于生成时点可得的结构化数据；
2. 有可复现的版本、特征、质量状态和持久化记录；
3. 能在未来真实行情到齐后被客观评分；
4. 能让用户在单股页面看到过去预测、样本量和正确率；
5. 夜间批量运行和开盘建议动作不会产生任何订单副作用。

所有“通过”均需保留命令、关键响应或截图证据。测试中的行情、新闻和交易日历必须是固定夹具或受控 mock，不能依赖当天外部数据偶然成功。

本次代码验收以 v1 已实现接口为准：预测查询、成绩单、最新批次状态与只读开盘建议预览已实现；管理员批次重试接口和任何交易执行接口均不在验收范围内。

## 2. 验收环境与前置条件

| 项目 | 必要条件 |
| --- | --- |
| 后端 | 使用 `/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python` 对应的 Anaconda `base` 环境；测试数据库可升级 Alembic。 |
| 前端 | 依赖已安装，`npm run typecheck` 可运行。 |
| 外部行情 | 单元/集成验收全部 mock；手工演练允许调用 AkShare，但只作为附加观察，不作为可重复通过条件。 |
| 配置 | `STOCK_SIGNAL_SCHEDULE_ENABLED=false`；成本与成功阈值在测试 fixture 中显式配置。 |
| 权限 | 普通用户与另一普通用户两个测试身份可用；开盘建议预览只读，不需要管理员身份。 |

任何验收环境若缺少 AkShare、数据库或阈值配置，系统必须保持任务禁用或产生明确失败状态，不能生成默认“中性”信号。

---

## 3. 存储、迁移与审计验收

### A1. 表结构和迁移

- [ ] 在空测试数据库执行 `alembic upgrade head` 后，存在 `stock_signal_predictions` 和 `stock_signal_runs`。
- [ ] 主表有 `prediction_key` 唯一约束，运行表有 `run_key` 唯一约束，且计划规定的查询索引存在。
- [ ] `stock_signal_predictions` 保存 `as_of_date`、`available_at`、`next_trading_date`、`signal_action`、资格/原因、所有版本、特征/策略快照哈希和 1/5/20 日结果字段。
- [ ] `alembic downgrade -1` 与再次 `upgrade head` 在独立测试库成功；已有库升级不会损坏现存单股分析表。

命令：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic upgrade head
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q tests/test_stock_signal_service.py
```

### A2. 幂等与隔离

- [ ] 同一 `source + owner_scope + universe + symbol + as_of_date + feature/policy/model version` 只能写入一条预测；重复调用返回原预测 ID。
- [ ] 策略或模型版本变化会生成新记录，旧记录的特征和评分不会被覆盖。
- [ ] `system` 公共批次可被所有已登录用户读取；用户 A 不能读取用户 B 的 `manual` 记录；v1 不提供批次重试接口。
- [ ] 数据库拒绝两个进程领取相同 `run_key`；测试中第二领取方没有重复处理股票。

---

## 4. 数据、特征与策略验收

### B1. 交易日和上证 50 成分股

- [ ] 已知周末、节假日、正常交易日 fixture 下，`is_trading_day()` 和 `next_trading_day()` 返回预期结果。
- [ ] `as_of_date` 后的第一个交易日才可作为 `next_trading_date`，不能把自然日或当日作为入场日。
- [ ] 成分股解析去重、规范化代码并冻结在运行快照中；返回 49、51、非法代码或来源错误时，运行被标记降级或失败，原因可查询。

### B2. 特征和质量门控

- [ ] 固定 OHLCV 夹具正确计算 1/5/20/60 日收益、均线偏离、RSI(14)、ATR(14)、20 日波动率、成交量 z-score 和价格区间。
- [ ] 关键特征缺失返回 `None` 与原因；不能用 `0` 代替缺失动量、波动率或反转因子。
- [ ] 最新行情日期不等于 `as_of_date`、K 线不足 60、价格/成交量无效会得到 `rejected` 与 `WATCH`，并且没有 `BUY/SELL`。
- [ ] 财务或新闻过期/为空时得到 `degraded` 和明确原因；系统不会把空新闻转换为 `NEUTRAL/LOW` 后继续给方向信号。

### B3. 信号权威和中文标签

- [ ] `SignalPolicy` 在固定输入下有稳定输出和稳定的策略快照哈希。
- [ ] 合格数据的买入、卖出、观望，以及风险/质量否决的观望均有单测。
- [ ] 注入与结构化信号相反的 LLM 文本后，API 和页面最终 action 仍等于 `SignalDecision.action`。
- [ ] `WATCH` 在所有 API、报告和页面上显示为“观望”，不再被映射为“持有”。

命令：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/test_stock_signal_calendar.py \
  tests/test_stock_signal_universe.py \
  tests/test_stock_signal_features.py \
  tests/test_stock_signal_authority.py
```

---

## 5. 预测结果和绩效统计验收

### C1. 前瞻性与结果补齐

- [ ] 创建预测时的 `feature_snapshot_json` 不包含下一交易日及之后的开盘、收盘、收益或新闻。
- [ ] 评分器在下一交易日实际开盘价存在时填入 `entry_date/entry_price`；不得用前收盘价或任意替代价。
- [ ] 在第 1、5、20 个可交易日收盘数据到齐时，分别填入收益、基准和超额收益；到期前保持 `pending/partial`，而非提前评分。
- [ ] 停牌、开盘价缺失、基准缺失等情形标记 `unscorable` 并保留原因；它们不计入成功或失败分母。
- [ ] 对同一预测多次执行评分器不改变已评分结果，也不重复扣除成本。

### C2. 成功率和样本口径

用以下固定行情夹具验证：一笔满足买入阈值的 `BUY`、一笔未满足买入阈值的 `BUY`、一笔满足规避下跌条件的 `SELL`、一笔不满足该条件的 `SELL`、一笔 `WATCH`、一笔未成熟记录和一笔不可评分记录。

- [ ] `BUY` 和 `SELL` 的成功计数分别正确；`WATCH`、未成熟、不可评分均不进入 `actioned_success_rate` 分母。
- [ ] 汇总结果显示 `BUY`、`SELL` 各自的可评分数、成功数、成功率，以及总行动信号成功率。
- [ ] 成本、买入阈值和卖出阈值从预测时的 `policy_snapshot_json` 读取；修改当前配置不会改变历史统计。
- [ ] 无可评分行动信号时，成功率为 `null` 且状态为“样本不足”，页面不显示 `0%`。
- [ ] 统计还同时显示平均/中位净收益、平均超额收益、覆盖率、成熟率和置信度分箱，不能只显示一个胜率数字。

命令：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/test_stock_signal_service.py \
  tests/test_stock_signal_outcomes.py
```

---

## 6. 夜间批次、调度和开盘建议动作验收

### D1. 调度与批次运行

- [ ] 在 `Asia/Shanghai` 虚拟时钟的交易日 19:10，任务只触发一次；在非交易日、任务开关关闭、配置不完整、迁移未完成或数据能力不可用时不生成预测。
- [ ] 批次使用冻结的上证 50 成分股清单，成功处理的股票均有一条 `nightly_sse50/system` 预测，局部失败不会丢失其他股票结果。
- [ ] 运行表准确记录期望数、成功数、降级数、失败数、开始/结束时间和错误摘要。
- [ ] 同一个 `run_key` 重复触发、重启或多实例竞争时不创建重复预测；v1 不暴露批次重试接口。
- [ ] 批次不调用 LLM、经纪商、订单、持仓写服务或 paper execution 服务。用 mock 断言这些依赖零调用。

### D2. 开盘建议动作

使用某个已发布交易日的固定预测数据，调用只读预览接口：

- [ ] 空仓 + `BUY` 返回 `BUY_AT_OPEN`；持仓 + `SELL` 返回 `SELL_AT_OPEN`。
- [ ] 空仓 + `SELL`、持仓 + `BUY`、任意 `WATCH` 以及信号数据降级时均返回 `NO_ACTION`。
- [ ] 每项建议都带预测 ID、`as_of_date`、`next_trading_date`、信号版本和 `execution_disabled=true`。
- [ ] 请求体只接受股票代码/持仓布尔信息，日志和数据库均不保存账户、资金、密钥或订单。
- [ ] 已登录用户只能调用只读预览；接口不接受账户凭据、不保存持仓、不创建订单或调用执行服务。

命令：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/test_stock_signal_batch.py \
  tests/test_stock_signal_scheduler.py \
  tests/test_stock_signal_api.py
```

---

## 7. 单股分析页面验收

### E1. 当前结论和历史预测

- [ ] 打开单股分析后，当前信号显示 `买入/卖出/观望`、生成时间、数据资格、质量原因、策略/模型版本；结论与 API 的结构化字段一致。
- [ ] 历史面板按日期倒序显示当时预测、置信度、资格、1/5/20 日状态、实际收益、相对上证 50 超额收益和版本。
- [ ] 没有启用后预测记录时，显示“尚无可审计预测”，不把旧自然语言报告伪装为历史预测。
- [ ] 分页/游标切换不会重复、遗漏或跨用户显示手工记录。

### E2. 质量成绩单

- [ ] 成绩单按 `BUY`、`SELL` 分项显示样本数、可评分数、成功率；总行动成功率明确写明其分母。
- [ ] `WATCH` 只展示覆盖率、成熟率和后续收益分布，不计入行动成功率。
- [ ] 样本不足、结果未成熟、不可评分、数据降级和批次部分失败均有中文解释、图标/文本和无障碍标签。
- [ ] API 失败、加载中和空状态不会使页面崩溃，也不会显示虚假的 `0%` 或空白卡片。

命令：

```bash
cd src/frontend
npm run typecheck
npm run test -- --run \
  src/__tests__/api/stockAnalysis.test.ts \
  src/__tests__/views/StockAnalysisPage.test.ts
```

---

## 8. 回归、静态检查和证据包

以下命令全部通过后，才可勾选本迭代验收完成：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/test_stock_signal_*.py \
  tests/test_stock_analysis_data_collector.py \
  tests/test_stock_analysis_tradingagents_compat.py
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check app tests

cd ../../src/frontend
npm run typecheck
npm run test

cd ../..
git diff --check
```

验收证据包必须包含：

- [ ] Alembic 升级成功输出和表/索引断言；
- [ ] 一个 50 成分股模拟批次的运行统计及至少一个降级样例；
- [ ] 一条预测从创建、待评分到 20 日评分完成的 API 响应链；
- [ ] `BUY`、`SELL`、`WATCH` 各一条页面展示截图或稳定前端测试断言；
- [ ] 无订单副作用的 mock 断言；
- [ ] 完整测试、类型检查、Ruff 与 `git diff --check` 输出。

## 9. 验收结论边界

通过本验收仅表示信号质量可以被诚实记录和度量，绝不表示已经证明投资收益、批准自动交易或完成真实/模拟盘执行验证。是否启用夜间影子任务由需求方在查看证据包后单独决定；真实/模拟开盘执行、持仓和订单验证必须在独立迭代中评审。
