# backtrader_web 模拟交易压测监控记录

更新时间：2026-06-25 16:47 CST

## 当前监控结论

- CTP 压测在 `2026-06-25 14:44 CST` 出现一次真实数据停写：holder 日志记录 `OnSessionDisconnected[...][8193]` 后，监控变为 `data_log=5 data_stale=45 alerts=data_log_stale`。已新增 `--skip-fresh-data-logs` 定向滚动重启能力，先恢复 45 个 stale-data 单元，再用新 CTP holder 全量重整接管。
- 当前 holding supervisor：CTP PID `1324657`（`reports/ctp_reconsolidate_rolling_supervisor.log`），MT5 PID `992775`，长期只读 monitor PID `889932`，后端 uvicorn PID `1379305`，前端 Vite PID `1379375`。严格 `/proc` 复验为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个 `workspace_units/.../run.py` 子进程；旧 CTP holder `906679` 和临时恢复 holder `1319947` 已不在进程表。
- 最新 `ensure_dual_stress_running.sh status`（`2026-06-25 16:46:24 CST`）：CTP `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=0 data_stale=0 data_missing=0 data_quiet=50 alerts=- cpu=1.7% max_cpu=0.0% rss=2510.0MB pss=1599.6MB uss=1591.1MB log=0.4MB`；MT5 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=- cpu=4.0% max_cpu=0.1% rss=2556.6MB pss=1646.7MB uss=1638.3MB log=32.9MB`。CTP 的 `data_quiet=50` 为 15:00 后期货合约进入安静窗口，非 stale。
- 上一轮修复持续生效：`/api/v1/portfolio/trades` 的 `datetime` 字段已保留完整 `dtclose` 时间；本轮真实 `limit=1000` 为 `date_only_datetime=0 bad_iso_datetime=0`，最新 `datetime=2026-06-25T08:45:00.000+00:00`。
- 活动日志深扫（`2026-06-25 16:46 CST`）：MT5 50 个活动 `bar.log` 最新 `datetime` 全部为 `2026-06-25T08:45:00.000+00:00`，`future_gt_120s=0`；CTP 50 个活动 `bar.log` 分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，`future_gt_120s=0`。CTP 最新业务时间停在收盘附近，当前仍记录为期货安静窗口内的 post-session 行为，不作为新缺陷处理。
- 认证后 API 最新验收：`/api/v1/portfolio/overview` 返回 `strategy_count=100 running_count=100 total_assets=50499999.27 total_pnl=-0.73`；`/portfolio/equity` 为 `dates=534 strategies=100 latest=2026-06-25T08:45:00.000+00:00 future_gt_120s=0`；`/portfolio/positions` 为 `total=100 items=100 latest_update=2026-06-25T16:46:00.903+08:00`；`/portfolio/trades?limit=1000` 为 `total=1861 returned=1000 date_only_datetime=0 bad_iso_datetime=0 latest=2026-06-25T08:45:00.000+00:00`。
- 成交/订单/信号日志质量复验：MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T08:45:00.000+00:00`，最新订单到 `2026-06-25T08:44:00.000+00:00`；CTP 全量重整后当前 `trade/order/signal` 为空文件，属于重启后且安静窗口内尚无新成交/信号输出，`bad_json=0 bad_1970=0`。
- 活动错误日志复扫：100 个活动单元的 `error.log/subprocess.stderr.log/gateway.stderr.log` 均无 `Traceback/ERROR/CRITICAL/Exception/ModuleNotFoundError/Address already in use` 命中；后端 `logs/backend.log` 从 PID `1379305` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，此前一次 401 来自巡检脚本误用本地 env 中与当前数据库不一致的管理员密码，不属于服务异常；`GET /health` 和前端 `/` 均返回 200。
- 资源与离群检查：CTP 新 holder 在 14:59-16:46 短窗口 PSS `1591.3 -> 1599.6MB`；MT5 从 11:32 到 16:46 PSS `1616.0 -> 1646.7MB`，日志 `10.4 -> 32.9MB`。单进程 RSS：CTP `49.8-50.5MB`，MT5 `50.7-51.6MB`，线程最大 5、FD 最大 22。
- 最近代码验收：`python -m py_compile src/backend/app/services/log_parser_service.py src/backend/tests/test_log_parser.py` 通过；`python -m pytest src/backend/tests/test_log_parser.py src/backend/tests/test_log_parser_extended.py -q` 结果 `49 passed in 3.81s`；`python -m pytest src/backend/tests/test_portfolio_api.py -q` 结果 `28 passed in 2.35s`。已执行 `PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/restart_app.sh`，重启后后端/前端分别返回 200；本轮 16:21-16:22 为只读巡检，未新增代码改动。

## 已确认并修复的问题

### 1. 组合风控混入历史实例

现象：`/api/v1/portfolio/overview` 曾返回 `strategy_count=223`，混入大量历史或已停止的 manager 实例，导致组合风控总资产、持仓和权益曲线不是当前 50 个 CTP 压测单元的数据。

原因：`LiveTradingManager` 是进程内状态，压测 supervisor 与网站后端是不同 Python 进程。组合 API 只按 manager 聚合时，容易读到后端进程恢复出的旧实例，或者读不到独立 supervisor 的当前运行数据。

修复：组合 API 现在优先从当前用户数据库中的活跃交易工作区单元读取，并解析对应 `workspace_units/{workspace_id}/{unit_id}/logs`。只有没有活跃交易工作区单元时，才回退到原 manager 实例聚合路径。

验收：真实接口从 `strategy_count=223` 收敛为 `strategy_count=50`，并且 `running_count=50`。

### 2. 后端重启会把交易工作区 running 状态重置为 idle

现象：网站后端重启后，50 个 CTP 子进程仍在运行，但数据库中的 50 个交易单元被 startup reconcile 改成 `idle`，导致组合页的运行工作区筛选为空。

原因：启动修复逻辑按回测任务规则处理所有 `queued/running` 的 `StrategyUnit`。交易工作区单元通常没有 `last_task_id`，而是通过 `trading_instance_id` 和 runtime 日志表示运行状态，因此不能套用回测任务修复规则。

修复：`reconcile_orphaned_run_statuses()` 现在只处理非交易工作区，跳过 `workspace_type='trading'` 的策略单元。

验收：新增回归测试保证 trading workspace 的 running 单元不会被重置；当前 DB 中 CTP 50 个单元重启后仍为 `running`。

### 3. 压测 supervisor 到达 hold-seconds 后静默驻留

现象：`run_dual_exchange_simulation.py --hold-seconds 900` 到达 30 次状态输出后，50 个子进程仍在运行，supervisor 进程也仍驻留，但不再输出状态。线程采样显示 supervisor 中存在大量等待子进程退出的 `proc.wait()` 任务。

原因：live trading manager 会为每个子进程创建后台 `wait_process` 任务。对 API 服务这是合理的；对压测脚本而言，如果目标策略仍在运行，主协程到达 hold deadline 后会失去状态输出，而进程仍因子进程等待任务继续存活。

修复：`run_dual_exchange_simulation.py` 增加两项能力：

- `--monitor-only`：只读监控已有目标单元，不 seed、不 stop、不 start。
- 默认在 `hold-seconds` 到期且目标仍 running 时继续输出状态；如确实需要旧行为，可使用 `--no-monitor-after-hold`。

验收：`reports/ctp_monitor_latest.log` 已出现 `hold elapsed; target units still running, continuing status monitor`，并在 hold 到期后继续输出 `status: 期货模拟工作区 running=50 failed=0 idle=0 missing=0`。只读监控进程继续运行且不影响现有 50 个 CTP 策略。

### 4. 监控只看数据库状态，不能识别假 running

现象：数据库中的 `running=50` 不能单独证明 50 个策略真的还在运行。若子进程退出但状态未回写，或者日志停止增长，旧监控仍可能显示正常。

修复：`run_dual_exchange_simulation.py` 的状态汇总增加运行时健康检查：

- `process`: 当前目标单元对应的 `workspace_units/.../run.py` 子进程数。
- `heartbeat`: 最近 180 秒内有任意日志文件更新的单元数。
- `stale`: 有日志文件但超过 180 秒未更新的单元数。
- `no_log`: 没有日志心跳的单元数。

验收：只读快照输出 `monitor: 期货模拟工作区 running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0`，说明数据库状态、真实子进程和日志心跳一致。

### 5. pytest 退出阶段出现 Loguru/aiosqlite 关闭后写日志噪声

现象：部分后端测试通过后，进程退出阶段偶发 `Logging error in Loguru Handler` 与 `ValueError: I/O operation on closed file`。退出码为 0，但验收输出被污染。

原因：测试导入 `app.main` 后，项目的日志配置会把 stdlib logging 转发给 Loguru。测试 session 结束时关闭共享 aiosqlite 引擎，aiosqlite worker thread 仍可能发 DEBUG 日志，此时 pytest 捕获流已经关闭，Loguru sink 写入失败。

修复：测试配置 `src/backend/tests/conftest.py` 将 `aiosqlite` / `aiosqlite.core` 日志级别降到 WARNING，并在 `pytest_sessionfinish` dispose 引擎前禁用这两个 logger。该修复只影响测试环境，不改变生产日志策略。

验收：重新运行组合测试后输出无 `Logging error`、无 `I/O operation on closed file`、无 `aiosqlite.core` 噪声，结果 `27 passed`。

### 6. 网关模拟策略缺少 live qcheck，50 进程压测 CPU 偏高

现象：50 个 CTP 策略子进程全部正常运行并持续写入 tick，但 `ps` 采样显示单个 `workspace_units/.../run.py` 进程约 30% CPU。与此同时 `tick.log` 约 2 tick/s/策略，tick 频率本身不足以解释该 CPU 占用。

原因：通用网关策略模板创建 `BtApiFeed` 时没有传入 `qcheck`，backtrader live 模式默认 `qcheck=0.0`。当没有新 bar 可加载时，engine 会以 0 秒间隔轮询 live feed，形成忙等。50 个策略并发时会放大 CPU 消耗，影响压测对真实业务问题的观察。

修复：

- `strategies/simulate/gateway_dual_ma/run.py` 与 `strategies/simulate/gateway_boll_breakout/run.py` 增加 `_resolve_feed_qcheck()`，并把 `qcheck` 传给 `BtApiFeed`。
- 两个策略模板的 `config.yaml` 在 `live` 段显式加入 `qcheck: 0.5`。
- `workspace_unit_runtime` 在生成交易单元运行目录时默认写入 `live.qcheck=0.5`，并允许 `unit_settings.qcheck`、`unit_settings.live_qcheck`、`unit_settings.qcheck_seconds` 覆盖。
- `seed_simulated_workspaces.py` 的压测单元默认 `unit_settings.qcheck=0.5`。

验收策略：当前 50 个策略不强制重启，以免中断正在积累的压测数据；本轮先通过语法检查和单元测试证明新模板和新同步逻辑正确。下一次新启动或重启 CTP/MT5 压测单元时，继续对比同样 50 进程规模下的 CPU 基线。

### 7. 组合概览把净敞口当作持仓市值，空头集中时显示负数

现象：本轮 50 个 CTP 策略多数为空头，真实接口返回：

- `/api/v1/portfolio/overview`: `total_position_value=-759805.3`
- `/api/v1/portfolio/positions.summary`: `gross_market_value=765673.3`, `net_market_value=-759805.3`

组合页卡片文案是“持仓市值”，行业口径应显示 gross market value，不应因为空头占优而为负。负数应作为“净敞口”单独表达。

原因：overview 原先用 `total_assets - total_cash` 计算 `total_position_value`。该值在有空头时是 signed net exposure，不是总持仓市值。

修复：

- `get_portfolio_overview()` 复用持仓解析和 `_build_position_summary()`，将 `total_position_value` 改为 gross market value。
- 新增 `net_position_value` 字段保留 signed net exposure。
- 没有持仓日志时仍回退到原资产/现金差额，保持空数据和旧日志场景可用。
- 前端 `PortfolioOverview` 类型和初始值补充 `net_position_value`。

验收：新增回归测试覆盖空头持仓：`cash=120000`、`equity=99000`、空头市值 `10000` 时，overview 返回 `total_position_value=10000`、`net_position_value=-10000`。

### 8. 逐 tick 明细默认落盘，长时间 50 策略压测日志膨胀

现象：本轮采样显示 50 个 CTP 单元日志约 `443 MB`，其中 `tick.log` 约 `427 MB`，占总量 96% 以上；最大的单策略 `tick.log` 已超过 `8 MB`。交易、持仓、bar、value 等日志体量很小，逐 tick JSON 明细是主要增长源。

风险：长时间压测时，逐 tick 明细会造成磁盘写放大、备份/归档成本上升，并让日志扫描和故障排查噪声增加。压测目标是发现交易链路和组合风控问题，默认保留订单、成交、持仓、bar、权益和系统日志已经足够；逐 tick 明细应作为诊断开关，而不是默认开启。

修复：

- `strategies/simulate/gateway_dual_ma/run.py` 与 `strategies/simulate/gateway_boll_breakout/run.py` 增加 `_resolve_log_ticks()`，并将结果传入 `TradeLogger(log_ticks=...)`。
- 两个通用网关模板 `config.yaml` 在 `live` 段加入 `log_ticks: false`。
- `workspace_unit_runtime` 生成交易单元运行目录时默认写入 `live.log_ticks=false`，并允许 `unit_settings.log_ticks` / `unit_settings.live_log_ticks` 覆盖。
- `seed_simulated_workspaces.py` 的压测单元默认 `unit_settings.log_ticks=False`。
- 两个通用网关 runner 模板改为向上查找 `backtrader_web` 根目录，并在启动时优先加载本地 `/home/yun/Documents/backtrader` fork，避免测试进程或其他宿主进程先导入 conda 版 `backtrader` 后找不到 `backtrader.feeds.btapifeed`。

验收策略：当前 50 个策略不强制重启，以免中断正在积累的压测数据；本轮先通过语法检查和单元测试证明新模板、新 seed 和新 runtime 同步逻辑正确。下一次重启压测单元后，观察 `tick.log` 不再持续增长，同时确认 heartbeat 仍可由 bar/value/position/system 等日志维持。

### 9. 只读监控缺少资源压力指标，无法提前暴露 CPU 和日志风险

现象：状态监控已经能证明 `running=50`、真实进程数和日志心跳一致，但它原先不输出 CPU、内存、总日志体量、tick 日志体量。当前 50 个老进程仍在运行旧配置，人工采样显示单进程约 34% CPU、逐 tick 日志继续增长；这种资源压力如果不进入持续监控日志，后续很难从 `reports/ctp_monitor_latest.log` 里复盘。

风险：压测目标是暴露 backtrader_web/backtrader/bt_api_py 的真实瓶颈。只看进程和心跳会把“高 CPU 忙等”“日志写放大”“单进程内存异常增长”误判为健康运行，等到系统变慢或磁盘紧张时才发现。

修复：

- `run_dual_exchange_simulation.py` 增加 `/proc` 级别的进程资源采样，不引入新依赖。
- `runtime_health_counter()` 现在同时统计 `cpu_pct_total`、`cpu_pct_max`、`rss_mb_total`、`rss_mb_max`、`log_mb_total`、`tick_log_mb_total`、`tick_log_mb_max`。
- `print_status()` 把这些字段输出到 monitor/status 行，便于长期日志直接观察资源趋势。
- 新增回归测试覆盖资源统计与日志体量汇总。

验收：只读快照输出 `cpu=1694.2% max_cpu=35.4% rss=12783.9MB log=401.3MB tick=390.0MB tick_max=9.6MB`，同时保留 `process=50 heartbeat=50 stale=0 no_log=0`。

### 10. 资源监控只有数值没有阈值告警，长期日志不利于自动筛查

现象：新版监控已经输出 CPU、RSS 和日志体量，但长期监控日志仍需要人工判断这些数值是否异常。本轮采样显示 50 个旧进程仍约 `1694%` 总 CPU、单进程约 `35.5%` CPU、总 RSS 超过 `12 GB`、tick 日志超过 `405 MB`。如果没有稳定告警字段，后续只能靠人工阅读数值发现资源异常。

风险：行业压测监控通常需要同时记录 metrics 和 health/alert 状态。只记录原始数值不方便日志检索、自动巡检或后续 CI/运维脚本判断，也容易让“运行中但资源不健康”的状态被误解为完全正常。

修复：

- `run_dual_exchange_simulation.py` 增加 `resource_alerts()`。
- `print_status()` 输出 `alerts=` 字段；无告警时为 `alerts=-`。
- 当前默认阈值覆盖进程缺失、心跳异常、单进程 CPU、总 RSS、总日志体量和 tick 日志体量。
- 新增测试覆盖告警列表和 `print_status()` 输出。

验收：真实只读快照输出 `alerts=cpu_high,rss_high,tick_log_high`，同时保留资源数值和 `process=50 heartbeat=50 stale=0 no_log=0`。

### 11. workspace_units 进程未被实例恢复扫描，真实进程被误判为失败

现象：受控重启后一度出现 `process=50`，但系统状态随后变为 `running=0 failed=48 idle=2`。OS 里仍然能看到大量 `workspace_units/.../run.py` 进程，说明策略并没有真实退出。

原因：`process_supervisor.scan_running_strategy_pids()` 只识别命令行中包含 `strategies` 的 `run.py`，没有识别交易工作区运行目录 `workspace_units`。因此 `LiveTradingManager.get_instance()` / `list_instances()` 无法把外部仍存活的工作区子进程恢复成 running，导致 DB 和组合风控读取到错误状态。

修复：

- `process_supervisor.scan_running_strategy_pids()` 同时识别 `strategies` 与 `workspace_units` 路径。
- `live_trading/instance.py:get_instance()` 在实例非 running 时，会按 `runtime_dir/run.py` 扫描真实 PID，找到后恢复 `status=running`、`pid`，并清空旧 error。
- `LiveTradingManager.get_instance()` 注入进程扫描依赖。
- 新增测试覆盖 `workspace_units/.../run.py` 扫描和非 running 实例恢复。

验收：修复后 monitor-only 能把真实运行中的 CTP 工作区进程恢复到实例状态；最终全量 CTP 输出 `running=50 failed=0 idle=0 process=50`。

### 12. 已运行实例重复启动会把工作区单元误写成 failed

现象：重启脚本启动 50 个 CTP 单元时，部分单元已经在跑，底层返回 `Strategy is already running`。`TradingWorkspaceService.start_units()` 把该异常当作启动失败，导致单元 `run_status=failed`，组合风控也随之丢失该单元数据。

原因：工作区启动接口不具备幂等性；它在发现已有实例后仍直接调用 `manager.start_instance()`，没有把“已经运行”作为成功状态处理。

修复：

- `TradingWorkspaceService.start_units()` 发现已有实例处于 running 时直接刷新快照并返回 running。
- 如果并发启动过程中底层抛出 `Strategy is already running`，服务会重新读取实例；确认实例为 running 后按成功处理。
- 重复启动不再增加 `run_count`。
- 新增回归测试 `test_start_units_keeps_already_running_instance_running`。

验收：相关后端测试 `50 passed`；真实 CTP DB 状态恢复为 `Counter({'running': 50})`。

### 13. 实例 JSON 记录丢失时，已有 PID 需要重挂而不是重复启动

现象：`CTP压测08` 的 `workspace_units/.../run.py` 进程真实存在，但实例 JSON 里找不到旧 `task_id=bd9b3f6b`，DB 显示 `idle`，组合风控缺少该单元数据。

原因：工作区启动路径在实例记录缺失时会新建 instance，但新建后没有立即按 runtime 目录扫描已有 PID；下一步如果直接启动，会有重复进程风险。

修复：

- `TradingWorkspaceService.start_units()` 在 `add_instance()` 后立即调用 `manager.get_instance()`，利用 runtime 目录扫描重挂已有 PID。
- 新增回归测试 `test_start_units_reattaches_missing_instance_record_to_running_pid`。
- `run_dual_exchange_simulation.py` 增加 `--unit-ids`，支持只恢复指定异常单元，不影响已运行的 48 个策略。

现场处置：

- `CTP压测08` 从旧实例 `bd9b3f6b` 重挂到新实例 `853eb984`，状态改为 running，`run_count` 未重复增加。
- `CTP压测37/50` 使用定向 supervisor 启动，PID `1839199`，日志 `reports/ctp_recover_37_50.log`，首次状态 `running=2 process=2 heartbeat=2`。
- 后端重启加载最新修复，PID `1842303`；前端 Vite 进程保持运行。

验收：

- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures --no-hold`
- 最新输出：`期货模拟工作区 running=50 failed=0 idle=0 missing=0 process=50 heartbeat=10 stale=40 no_log=0 alerts=heartbeat_stale,cpu_high,rss_high,tick_log_high`
- 组合风控接口复测：overview `strategies=50 total_assets=49998363.47 total_position_value=626166.76`，positions `total=50`，trades `total=274`，allocation `items=50`。
- 网站复测：`GET /health` healthy，前端 `http://127.0.0.1:3000/` 返回 200。

备注：MT5 模拟工作区当前仍为 `running=0 failed=50`，需要单独继续排查；本轮修复聚焦 CTP 50 个策略和组合风控数据恢复。

### 14. BtApiFeed 将 pending tick 当成 live bar，导致 qcheck 失效和 CPU 忙等

现象：50 个 CTP 工作区全部处于 running，组合风控数据也正常，但真实 5 秒增量采样显示总 CPU 仍约 `1727%`，单进程最高超过 `60%`。配置和 runtime 目录已经写入 `qcheck: 0.5`，说明 CPU 高不是配置没有下发，而是 live feed/run loop 没有进入等待。

排查：

- 运行目录 `config.yaml` 和 `run.py` 已确认传入 `BtApiFeed(..., qcheck=0.5)`。
- `backtrader.Cerebro._runnext()` 会在 `data.haslivedata()` 返回 True 时跳过 qcheck。
- `BtApiFeed.haslivedata()` 原先把 `store.has_pending_tick()` / `store.has_pending_orderbook()` 也视为 True。
- 这些 pending tick/orderbook 只是实时原始事件，不一定形成完整 bar；在 1m bar 模式下，`_load()` 会反复 drain tick、返回 `None`，策略时钟没有推进，但 Cerebro 下一轮仍因 pending tick 跳过 qcheck，从而高频空转。

修复：

- 在 `/home/yun/Documents/backtrader/backtrader/feeds/btapifeed.py` 中调整 `BtApiFeed.haslivedata()`：只在 `_live` 或 store 的 completed live bar cache 中有 bar 时返回 True。
- pending tick/orderbook 仍由 `_check()` / `_load()` drain 并聚合，但不再让 Cerebro 误以为已有可推进策略时钟的数据。
- `BtApiFeed._load()` 在没有完整 bar 可交付时，按 `self._qcheck` 执行短等待；否则 `DataBase.do_qcheck()` 只是设置 `_qcheck` 字段，实际没有任何 sleep/wait 使用它。
- 更新 `/home/yun/Documents/backtrader/tests/unit/feeds/test_btapifeed.py` 中相关测试预期：实时源存在仍由 `islive()` 表达；`haslivedata()` 只表达 completed bar 是否可立即读取。
- 新增测试覆盖“有实时 tick 但未形成完整 1m bar 时必须按 qcheck 等待”，防止再次空转。

验收：

- `python -m py_compile backtrader/feeds/btapifeed.py tests/unit/feeds/test_btapifeed.py`
- `python -m pytest tests/unit/feeds/test_btapifeed.py -q`，结果 `40 passed`。

现场验收计划：需要重启 50 个 CTP 工作区，让新进程加载修复后的本地 `backtrader`。重启后继续用 5 秒增量 CPU 采样和 monitor-only 输出验证 CPU 是否显著下降，同时确认 `running=50 process=50` 和组合风控接口仍有 50 个策略数据。

### 15. 外部策略 PID 只发 SIGTERM 不等待退出，旧进程会被重新重挂

现象：修复 `BtApiFeed` 后完整重启 50 个 CTP 单元，绝大多数新进程 CPU 降到约 `0.2%`，但仍有两个旧 PID 持续占用约一个 CPU 核：

- `CTP压测07`：旧 PID `1819165`，父进程 `1816776`，仍显示 `started_at=2026-06-24 00:02:28`
- `CTP压测50`：旧 PID `1839557`，父进程 `1839199`，仍显示 `started_at=2026-06-24 00:02:29`

原因：`LiveTradingManager.stop_instance()` 对不在当前 manager `_processes` 字典里的外部 PID 只能调用 `_kill_pid()`。原 `_kill_pid()` 在 Unix 上只发 `SIGTERM`，不等待也不升级 `SIGKILL`。如果旧策略进程没有及时退出，后续 `start_units()` 会通过 runtime 目录扫描把仍存活的旧 PID 重新重挂为 running，导致完整重启并没有真正换成新代码。

修复：

- `process_supervisor.kill_pid()` 增加 `force_after_seconds` 参数；默认仍只发 `SIGTERM`，保持轻量调用兼容。
- `LiveTradingManager._kill_pid()` 使用 `force_after_seconds=1.0`：先 `SIGTERM`，短等待后如果 PID 仍存活则 `SIGKILL`。
- 新增测试覆盖 SIGTERM 后仍存活时升级 SIGKILL。

验收：

- `python -m py_compile src/backend/app/services/process_supervisor.py src/backend/app/services/live_trading/manager.py src/backend/tests/test_process_supervisor.py`
- `python -m pytest src/backend/tests/test_process_supervisor.py src/backend/tests/test_live_instance_service.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `43 passed`。

现场验收计划：定向重启 `CTP压测07` 和 `CTP压测50`，确认旧 PID 不再存活，新 PID 加载 qcheck sleep 修复后 5 秒增量 CPU 不再出现单进程 100%。

### 16. 同一 workspace runtime 会残留多个 running 实例记录，API 重启后重复计数

现象：API 重启并扫描运行中策略进程后，`LiveTradingManager.list_instances()` 一度返回同一 `workspace_units/.../01a175ce...` runtime 对应 3 条 running instance，且 PID 都是同一个 `1854030`。这会污染实例列表、组合聚合 fallback 和后续 start/stop 判断。

原因：`add_instance(runtime_dir=...)` 只创建新记录，没有检查同一 runtime 目录是否已有运行实例。旧实例记录在 DB `trading_instance_id` 变化、手工重挂或异常重启后会留在 `live_trading_instances.json` 中；后续扫描 `runtime_dir/run.py` 时会把这些旧记录全部恢复为 running。

修复：

- `live_trading/instance.py` 增加 runtime_dir 归一化 key。
- `list_instances()` 扫描后按 runtime_dir 对 running 记录去重；优先保留无 error、较新的实例记录。
- `add_instance()` 在同一 runtime_dir 已有 running 实例时复用该记录，并删除同 runtime 的重复旧记录，避免重复创建。
- 新增测试覆盖列表扫描去重和 `add_instance()` 复用已运行 runtime。

验收：

- `python -m py_compile src/backend/app/services/live_trading/instance.py src/backend/tests/test_live_instance_service.py`
- `python -m pytest src/backend/tests/test_live_instance_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_process_supervisor.py -q`，结果 `45 passed`。
- 现场文件 `src/backend/data/live_trading_instances.json` 复核：`running_entries=50 unique_runtime_dirs=50 duplicates={}`。

### 17. 组合页“交易记录”表使用每日汇总伪造交易行，导致看起来没有真实成交数据

现象：后端 `/api/v1/portfolio/trades` 已返回 CTP 真实交易明细，但前端组合页的“交易记录”tab 没有使用该接口，而是调用 `/workspace/{id}/trading/daily-summary`，再把每日汇总映射成 `TradeItem`。表格列是开仓、平仓、价格、手续费、净盈亏等交易明细字段，填入日报数据会让用户误以为组合风控没有交易数据。

原因：`PortfolioPage.vue` 为了支持工作区选择，把持仓和交易都改走 workspace 聚合接口；但 workspace 日报不是成交明细。

修复：

- 组合页持仓继续按选中工作区调用 `workspaceApi.getTradingPositions()`。
- 交易记录改为调用真实明细接口 `portfolioApi.getTrades(1000)`，再按 `strategy_name` 中的工作区前缀过滤到当前选中的运行工作区。
- 删除日报到交易明细的伪映射函数。
- 更新前端测试，覆盖只保留选中工作区的真实交易明细。

验收：

- `npm test -- PortfolioPage.test.ts --run`，结果 `16 passed`。
- `npm test -- portfolio.test.ts --run`，结果 `6 passed`。
- `npm run build` 成功。
- 真实 API 验收：`/api/v1/portfolio/trades` 返回 `total=274`，组合页数据源不再依赖日报伪交易。

### 18. 压测单元默认运行 7200 秒，不符合“持续监控、不用停止”

现象：完成 qcheck 修复和去重修复后再次验收，CTP 工作区突然变为 `running=0 idle=50 process=0`，组合概览也退化为 historical/fallback 聚合。日志和配置显示 50 个压测单元的 `duration_seconds=7200`，从 00:02 左右启动到 02:40 以后自然到期退出。

原因：`seed_simulated_workspaces.py` 的 CTP/MT5 stress unit 固定 `duration_seconds=7200`、`session_timeout=7260`。这适合短验收，不适合长期压测和持续监控。

修复：

- 新增 `DEFAULT_STRESS_DURATION_SECONDS = 7 * 24 * 60 * 60`。
- 新增 `stress_duration_seconds()`，允许通过 `SIM_STRESS_DURATION_SECONDS` 环境变量覆盖。
- CTP/MT5 stress unit 的 `session_timeout` 自动设为 `duration_seconds + 60`。
- 新增测试覆盖默认 7 天和环境变量覆盖。

现场处置：

- 启动长时 CTP supervisor：PID `2084699`，日志 `reports/ctp_long_stress_7d.log`。
- 重新 seed 后 50 个 CTP unit 均更新为 `duration_seconds=604800`、`session_timeout=604860`。
- 当前 CTP 验收：`running=50 failed=0 idle=0 process=50 heartbeat=50 stale=0 no_log=0`。
- 当前组合风控验收：overview `strategy_count=50 running_count=50 total_assets=50000000.0 total_position_value=45071.6`；positions `total=50`。
- 5 秒即时 CPU 采样：`unique_pids=50 instant_cpu_total_pct=3.8`，最高单进程约 `0.2%`。

备注：`http://127.0.0.1:5173/` 当前被另一个 `WoniuNote API v2.0.0 (C++)` 服务占用；本项目 Vite 前端固定运行在 `http://127.0.0.1:3000/`，组合页为 `http://127.0.0.1:3000/portfolio/overview`。

### 19. MT5 50 个单元失败：缺少 demo 账号且导入了错误的 `pymt5` 包

现象：MT5 工作区已 seed 出 50 个压测单元，但运行全部失败。最初错误为 `gateway_command_endpoint is required`，进一步检查发现 MT5 网关配置没有 login/password，`build_mt5_gateway_runtime_kwargs()` 抛出 `MT5 gateway requires login and password` 后被运行链路降级为直连模式，导致策略进程里才报 endpoint 缺失。

处理：

- 使用 `/home/yun/Documents/pymt5` 的 `open_demo_account()` 在 `MetaQuotes-Demo` 上创建新的 demo 账号。
- 验证该账号可登录，账户信息可读：USD、balance `100000.0`、leverage `100`、`is_demo=True`。
- 验证行情可用：`load_symbols()` 返回 `162` 个品种，`EURUSD` 最近 1 小时 M1 bar 返回 `60` 根。
- 将 demo 凭据写入项目根 `.env` 的 `MT5_LOGIN/MT5_PASSWORD/MT5_WS_URI` 和 `MT5_DEMO_*`；密码不写入本记录。
- 发现当前 Python 环境原先安装的 `pymt5 1.4.0` 没有 `MT5WebClient`，`bt_api_mt5` 运行时导入到错误包后报 `AttributeError: module 'pymt5' has no attribute 'MT5WebClient'`。
- 执行 `/home/yun/anaconda3/bin/python -m pip install -e /home/yun/Documents/pymt5`，确认 `import pymt5` 指向 `/home/yun/Documents/pymt5/pymt5/__init__.py` 且 `has_MT5WebClient=True`。

现场运行：

- 后端重启后健康检查正常：`GET /health -> healthy`。
- 启动 MT5 长时 supervisor：PID `2103135`，日志 `reports/mt5_long_stress_7d.log`。
- CTP 长时 supervisor 继续运行：PID `2084699`，日志 `reports/ctp_long_stress_7d.log`。
- 当前双交易所只读监控：CTP `running=50 failed=0 process=50 heartbeat=50`；MT5 `running=50 failed=0 process=50 heartbeat=50`。
- 当前组合风控验收：overview `strategy_count=100 running_count=100 total_assets=50499792.68 total_position_value=313329.92 total_pnl=-207.32`；positions `count=100`；trades `count=941`，其中按 `strategy_name` 前缀统计 MT5 `667`、CTP `274`。

### 20. 双交易所监控把日志静默误判为心跳失效，并把旧 `tick.log` 计入当前压测

现象：CTP 与 MT5 各 50 个策略进程都正常存活，组合风控也能看到 100 个策略的持仓和交易，但 `run_dual_exchange_simulation.py --monitor-only` 一度输出 CTP `heartbeat=5 stale=45 tick_log_high`、MT5 `heartbeat=0 stale=50`。这会把安静但正常的策略误报成系统异常。

原因：

- 监控把普通日志文件的最近 mtime 当成心跳；策略在没有订单或行情日志可写时，进程仍然健康但日志可能长时间不更新。
- 日志压力统计直接扫描 workspace 的所有 `*.log` 和 `tick.log`，没有区分当前进程启动时间；旧 session 遗留的 CTP `tick.log` 会继续污染当前压测的日志体积。

修复：

- `ProcessResource` 增加 `started_at_epoch`，从 `/proc/{pid}/stat` 与 `/proc/uptime` 推导进程启动时间。
- `runtime_health_counter()` 对仍在运行的策略进程直接计为 `heartbeat_fresh`，不再依赖普通日志 mtime。
- `log_bytes()` 与 `latest_log_age_seconds()` 支持 `since_timestamp`，当前 session 的日志压力只统计进程启动之后更新的日志文件。
- 保留非运行进程的日志 mtime 检查，用于辅助定位退出后最后一次日志活动。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `9 passed`。
- 修复后只读监控：CTP `running=50 failed=0 idle=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=- log=17.5MB tick=0.0MB`；MT5 `running=50 failed=0 idle=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=- log=18.2MB tick=0.0MB`。
- 组合风控接口复核：overview `strategy_count=100 running_count=100 total_position_value=538043.8 total_pnl=-267.21`；positions `total=100`，MT5 `50`、CTP `50`；trades `total=1003`，最近 1000 条中 MT5 `710`、CTP `290`；allocation `items=100`。
- 新增只读双交易所监控进程：PID `2391254`，日志 `reports/dual_monitor_fixed_7d.log`。该进程不负责启停策略，只持续输出修复后的监控口径。

### 21. 长压测 supervisor 退出后缺少幂等恢复入口

现象：17:27 之前的长压测日志显示 CTP 与 MT5 各 50 个单元均曾达到 `running=50 process=50 heartbeat=50 alerts=-`，但 21:55 复查时系统中已经没有 `workspace_units/.../run.py`、`run_dual_exchange_simulation.py`、后端或前端进程。只读快照显示 CTP `running=0 idle=50 process=0`，MT5 `running=0 idle=50 process=0`。这说明压测 supervisor 或宿主会话结束后，现场会回到非监控状态。

风险：持续压测依赖人工命令驻留，不符合长时间运行任务的可恢复性要求。后续如果终端会话、Codex 会话或宿主桌面进程中断，50 个工作区不会自动恢复，运行数据会出现空窗。

改进：

- 新增 `scripts/ops/ensure_dual_stress_running.sh`，提供幂等后台启动入口。
- 默认使用当前 `PYTHON_BIN` 启动 `run_dual_exchange_simulation.py --no-stop-existing --targets futures,mt5 --hold-seconds 604800 --status-interval 30`。
- PID 写入 `.pids/dual_stress_watchdog.pid`，日志写入 `reports/dual_stress_watchdog_7d.log`。
- 支持 `start`、`status`、`restart`；`status` 会同时运行一次 `--monitor-only --no-hold` 现场快照。
- 默认不跳过 seed，确保目标工作区缺失时能补齐；如只想复用现有 50+50 单元，可设置 `SKIP_SEED=1`。

验收：

- `bash -n scripts/ops/ensure_dual_stress_running.sh` 通过。
- `PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/ensure_dual_stress_running.sh start` 启动双交易所 supervisor，PID `19233`，日志 `reports/dual_stress_watchdog_7d.log`。
- 进程验收：`pgrep -fc '/workspace_units/.*/run.py'` 返回 `100`。
- supervisor 首轮稳定状态：CTP `running=50 failed=0 idle=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`，MT5 `running=50 failed=0 idle=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。
- 独立 `status` 快照确认 supervisor 存活；最新快照 CTP 仍为 `running=50 process=50 heartbeat=50 alerts=-`，MT5 仍为 `running=50 process=50 heartbeat=50`，但 RSS 已超过默认阈值，继续列入后续监控。

### 22. bt_api_py 旧插件入口不兼容当前 PluginLoader，污染长压测日志

现象：重新拉起双交易所长压测时，策略启动没有被阻断，但 supervisor 日志出现多段插件加载 traceback：

- `buda` / `btcturk`: `register_plugin() takes 0 positional arguments but 2 were given`
- `bitvavo`: `PluginInfo.__init__() got an unexpected keyword argument 'description'`
- `bitfinex`: `module 'bt_api_bitfinex.plugin' has no attribute 'register_plugin'`

原因：`bt_api_base.plugins.PluginLoader` 当前按隔离加载协议调用 `register_plugin(registry, runtime)`，并要求返回完整 `PluginInfo(core_requires, supported_exchanges, supported_asset_types)`。上述插件仍停留在旧协议：无参入口、导入时全局注册、不返回 metadata，或只有 metadata 没有 entry point 函数。

风险：这些错误当前不影响 CTP/MT5 目标插件运行，但会让长期监控日志反复出现无关 traceback，掩盖真正的交易链路异常，也会使插件健康状态不可判断。

修复：

- `/home/yun/Documents/bt_api_py` 中的 `bt_api_buda`、`bt_api_btcturk`、`bt_api_bitvavo`、`bt_api_bitfinex` 已统一改为当前插件协议。
- 四个插件的 `register_plugin()` 现在都在传入的隔离 registry 上注册 feed/exchange/balance，并返回当前协议的 `PluginInfo`。
- `buda` 与 `bitvavo` 的 `registry_registration.py` 去掉导入即注册的副作用；旧调用方仍可显式调用 `register_buda()` / `register_bitvavo()`。
- `btcturk` 的旧 `BTCTurkPlugin.get_plugin_info()` 返回当前协议 metadata，`register_btcturk()` 改为使用显式 registry API。
- `bitfinex` 新增缺失的 `register_plugin()`，entry point 不再指向不存在的函数。
- 新增 `tests/test_plugin_entrypoints_compat.py`，用 fake entry point 走真实 `PluginLoader`，验证四个插件 `loader.failed == {}` 且目标 exchange 已注册。

验收：

- `python -m py_compile ...` 覆盖四个插件、四个 registry helper 和新增测试，通过。
- `python -m pytest tests/test_plugin_entrypoints_compat.py -q`，结果 `1 passed`。
- `python -m pytest bt_api/bt_api_base/tests/plugins/test_loader.py tests/test_plugin_entrypoints_compat.py -q`，结果 `7 passed`。
- `python -m pytest bt_api/bt_api_buda/tests/exchange_registers/test_register_buda.py bt_api/bt_api_bitvavo/tests/exchange_registers/test_register_bitvavo.py bt_api/bt_api_bitfinex/tests/exchange_registers/test_register_bitfinex.py -q`，结果 `3 passed`。

### 23. 资源监控用 RSS 累加导致共享内存重复计数，MT5 被误报 `rss_high`

现象：双交易所长压测稳定运行后，CTP 与 MT5 均保持 `running=50 process=50 heartbeat=50`，但 MT5 持续输出 `rss_high`。当前采样：

- CTP 50 进程 RSS `8103.2MB`，PSS `3510.0MB`，USS `3462.3MB`。
- MT5 50 进程 RSS `12823.7MB`，PSS `8229.4MB`，USS `8181.5MB`。

原因：监控原先直接累加 `/proc/{pid}/statm` 的 RSS。RSS 会把 Python 解释器、动态库、只读 mmap 等共享页在每个策略进程里重复计算；50 个独立进程时，这会显著放大总内存压力。行业监控通常用 PSS（Proportional Set Size）评估多进程总内存，因为共享页按比例分摊；USS（Unique Set Size）用于观察真正独占内存。

修复：

- `run_dual_exchange_simulation.py` 增加 `/proc/{pid}/smaps_rollup` 解析，采集 PSS 和 USS。
- `ProcessResource`、`runtime_health_counter()`、`print_status()` 增加 `pss` / `uss` 输出，同时保留 `rss` 便于排查。
- `resource_alerts()` 在 PSS 可用时优先用 `pss_mb_total` 判断总内存压力；只有 PSS 不可用时才回退到 RSS 并输出 `rss_high`。
- `scripts/ops/ensure_dual_stress_running.sh` 增加 `monitor` 动作，启动不负责启停策略的只读长监控进程，避免当前 supervisor 未重启时仍使用旧 RSS 口径。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `10 passed`。
- 新口径现场快照：CTP `running=50 process=50 heartbeat=50 alerts=- rss=7434.5MB pss=2840.6MB uss=2793.3MB`；MT5 `running=50 process=50 heartbeat=50 alerts=- rss=13213.9MB pss=8619.3MB uss=8571.7MB`。
- 启动只读 PSS 监控：`PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/ensure_dual_stress_running.sh monitor`，PID `35022`，日志 `reports/dual_stress_monitor_7d.log`。
- `./scripts/ops/ensure_dual_stress_running.sh status` 确认 supervisor PID `19233` 与只读 monitor PID `35022` 均在运行。

### 24. MT5 网关 tick/event 队列无背压，50 进程长压测触发真实 `pss_high`

现象：切换到 PSS 口径后，MT5 最初不再被 RSS 误报，但长时监控继续显示真实内存爬升。22:18 左右现场快照：CTP `running=50 process=50 heartbeat=50 alerts=- pss=1629.0MB`；MT5 `running=50 process=50 heartbeat=50 alerts=pss_high pss=10379.7MB`。按进程拆分后，MT5 不是单一进程异常，而是 50 个策略进程整体每个约 166-275MB PSS，符合每个进程都在累积网关行情队列的形态。

原因：

- `bt_api_py.gateway.client.GatewayClient` 的 `_tick_queues` 与 `_event_queue` 使用无界 `collections.deque`。
- `poll_tick()` / `poll_broker_update()` 每次先从 ZMQ socket drain 新消息，再消费本地队列；当 MT5 行情推送速度高于 backtrader feed 聚合消费速度时，会进一步扩大积压。
- ZMQ SUB socket 没有显式接收高水位，进程内队列和 socket 侧缓冲都缺少统一背压边界。

修复：

- `/home/yun/Documents/bt_api_py/bt_api_py/gateway/client.py` 新增 `DEFAULT_MAX_TICKS_PER_SYMBOL=1000`、`DEFAULT_MAX_EVENTS=1000`、`DEFAULT_DRAIN_MAX_MESSAGES=250`、`DEFAULT_SOCKET_RCVHWM=1000`。
- tick/event 队列改为有界 deque，超过上限时丢弃最旧消息，避免慢消费者无限增长。
- `poll_tick()` 与 `poll_broker_update()` 改为优先消费已有队列，只有队列为空时才 drain socket。
- `_drain_socket()` 增加单次消息数上限，`connect()` 为 market/event SUB socket 设置 `RCVHWM`。
- 新增 `/home/yun/Documents/bt_api_py/tests/test_gateway_client_backpressure.py`，覆盖有界队列丢弃最旧消息、优先消费已有队列、单次 drain 上限。
- `scripts/ops/ensure_dual_stress_running.sh` 新增 `NO_STOP_EXISTING` 环境开关，默认仍为 `1`；设置 `NO_STOP_EXISTING=0` 时可对指定 `TARGETS` 做专项停启，便于只滚动 MT5 而不影响 CTP。

验收：

- `python -m py_compile bt_api_py/gateway/client.py tests/test_gateway_client_backpressure.py` 通过。
- `python -m pytest tests/test_gateway_client_backpressure.py -q`，结果 `5 passed`。
- 第一次使用 5000 条队列上限后，MT5 仍从 `pss=8791.1MB` 爬升到 `pss=10965.4MB` 并触发 `pss_high`，因此将默认上限收紧到 1000。
- MT5 专项 supervisor 已重启并加载 1000 上限版本：PID `49693`，日志 `reports/dual_stress_mt5_backpressure_7d.log`。CTP supervisor PID `19233` 保持运行。
- 1000 上限版本连续采样：MT5 PSS `8791.9 -> 9052.3 -> 9305.1 -> 9528.0 -> 9627.7 -> 9705.3 -> 9769.2 -> 9794.2 -> 9801.0 -> 9809.9 -> 9819.0 -> 9828.1MB`，未再触发 `pss_high`。
- 最新现场快照：CTP `running=50 process=50 heartbeat=50 alerts=- cpu=8.8% pss=1768.2MB`；MT5 `running=50 process=50 heartbeat=50 alerts=- cpu=39.0% max_cpu=1.0% pss=9846.4MB uss=9789.9MB`。

### 25. Hyperliquid 插件缺少可选依赖时被记为 import failure，污染 MT5 启动日志

现象：MT5 专项 supervisor 每次启动时都会出现一条无关日志：`[bt_api_base.plugins] plugin hyperliquid import failed: ModuleNotFoundError: No module named 'eth_account'`。该问题不影响 MT5 插件注册和策略运行，但会让长压测启动日志混入其它交易所的可选依赖错误。

原因：

- `bt_api_hyperliquid.plugin` 顶层导入 `registry_registration`，后者继续导入 `feeds.live_hyperliquid.request_base`。
- `request_base` 依赖 `eth_account`，但当前压测环境没有安装该可选依赖。
- `bt_api_base.plugins.PluginLoader` 只有 `loaded` / `failed` 两类状态，缺少“插件因可选依赖缺失被干净跳过”的语义。

修复：

- `/home/yun/Documents/bt_api_py/bt_api/bt_api_base` 新增 `PluginOptionalDependencyError`。
- `PluginLoader` 新增 `skipped` 字典；捕获 `PluginOptionalDependencyError` 时输出 `plugin ... skipped`，不再进入 `failed`。
- `/home/yun/Documents/bt_api_py/bt_api/bt_api_hyperliquid/src/bt_api_hyperliquid/__init__.py` 改为懒加载公开对象，避免包导入阶段拉起 feed 依赖。
- `bt_api_hyperliquid.plugin.register_plugin()` 改为注册时延迟导入 `registry_registration`；缺少 `eth_account` 时抛 `PluginOptionalDependencyError`。
- `bt_api_hyperliquid/pyproject.toml` 补充真实依赖 `eth-account>=0.10`，避免正式安装插件时漏装依赖。
- 新增 `bt_api_hyperliquid/tests/test_plugin_optional_dependency.py`，验证 entry point load 不导入可选依赖，缺依赖时 loader 记入 `skipped`。

验收：

- `python -m py_compile src/bt_api_base/plugins/errors.py src/bt_api_base/plugins/__init__.py src/bt_api_base/plugins/loader.py tests/plugins/test_loader.py` 通过。
- `python -m pytest tests/plugins/test_loader.py -q`，结果 `7 passed`。
- `python -m py_compile src/bt_api_hyperliquid/__init__.py src/bt_api_hyperliquid/plugin.py tests/test_plugin_optional_dependency.py` 通过。
- `python -m pytest tests/test_plugin_optional_dependency.py -q`，结果 `2 passed`。
- 组合验证：`python -m pytest bt_api/bt_api_base/tests/plugins/test_loader.py bt_api/bt_api_hyperliquid/tests/test_plugin_optional_dependency.py -q`，结果 `9 passed`。
- 真实 `PluginLoader.load_all()` 验证：发现 `26` 个 entry points；`hyperliquid_failed=False`，`hyperliquid_skipped=True`，`failed_keys=[]`，`skipped_keys=['hyperliquid']`。
- 最新现场快照仍稳定：CTP `running=50 process=50 heartbeat=50 alerts=- pss=2202.0MB`；MT5 `running=50 process=50 heartbeat=50 alerts=- cpu=25.1% max_cpu=0.6% pss=9702.1MB`。

### 26. 压测 supervisor `restart` 只等待 3 秒，旧进程未退出时会静默复用旧 PID

现象：滚动 MT5 专项压测 supervisor 时，`restart` 对旧 PID 发送 `SIGTERM` 后只固定等待 3 秒。旧 supervisor 仍在清理 50 个子进程时，`start_supervisor()` 立即看到 PID 还存活并输出 `dual stress supervisor already running`，导致本次 `restart` 命令表面成功，但实际上没有启动新 supervisor，也没有加载新代码。

原因：`scripts/ops/ensure_dual_stress_running.sh` 的 `restart` 分支没有区分“旧进程仍在退出中”和“已有可复用 supervisor 正常运行”，也没有在停机超时后返回非零状态。长压测 supervisor 负责回收多个策略子进程，3 秒固定等待不足以覆盖真实停机场景。

修复：

- 新增 `STOP_TIMEOUT_SECONDS` 环境变量，默认 `60` 秒。
- 新增 `stop_supervisor()`，发送 `SIGTERM` 后持续等待旧 PID 消失；旧 PID 退出后删除 PID 文件再启动新 supervisor。
- 如果超时后旧 PID 仍存活，脚本输出 `dual stress supervisor still running after ...` 并返回非零状态，避免把“未完成重启”伪装成成功。
- 新增 `src/backend/tests/test_ensure_dual_stress_running_script.py`，用忽略 `SIGTERM` 的假 supervisor 复现旧 PID 卡住场景，验收 `restart` 会明确失败且不会输出 `already running` 或 `started dual stress supervisor`。

验收：

- `bash -n scripts/ops/ensure_dual_stress_running.sh` 通过。
- `python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `1 passed`。
- 未对当前真实 CTP/MT5 supervisor 执行重启；测试只使用临时 PID 文件和 `/bin/true` 作为假 Python 命令。
- 最新现场快照确认压测未受影响：CTP `running=50 process=50 heartbeat=50 alerts=- cpu=7.4% max_cpu=0.2% pss=3182.3MB`；MT5 `running=50 process=50 heartbeat=50 alerts=- cpu=20.0% max_cpu=0.5% pss=7858.8MB`。

### 27. 会话日志过滤隐藏了历史 `tick.log` 磁盘占用，长压测状态无法提示清理风险

现象：当前 CTP 50 个策略进程均正常运行，实时状态显示 `tick=0.0MB`，但运行目录实际存在上一轮会话遗留的 `logs/tick.log`：`workspace_units/b9e23899-eaad-4dd6-a973-ac47196f86a5` 总占用 `453M`，其中 50 个 `tick.log` 合计 `426.5MB`，单文件最大约 `10.4MB`。这些文件的 mtime 是 `2026-06-24 01:31`，当前 CTP 子进程启动时间是 `2026-06-24 21:57`，因此被会话过滤排除。

原因：`runtime_health_counter()` 为避免旧日志误判当前进程心跳和当次会话增长，只统计 `mtime >= process_started_at` 的 `log` / `tick`。这个口径适合判断当前进程是否正在产生日志风暴，但无法暴露 runtime 目录累计磁盘占用；长压测反复重启后，历史 `tick.log` 会持续留在同一个 unit 目录里，状态输出看起来健康但磁盘风险已存在。

修复：

- 保留原有会话口径：`log`、`tick`、`tick_max` 仍只统计当前进程启动后的日志。
- 新增累计磁盘口径：`log_disk`、`tick_disk`、`tick_disk_max`，不受进程启动时间过滤影响。
- 新增 `log_disk_high` / `tick_log_disk_high` 告警，分别复用现有总日志阈值和 tick 日志阈值。
- 新增测试覆盖“活进程晚于旧 `tick.log` 启动”的场景，验收会话 `tick=0.0MB` 但累计 `tick_disk` 仍记录旧文件大小。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `11 passed`。
- 最新现场快照：CTP `running=50 process=50 heartbeat=50 alerts=tick_log_disk_high cpu=6.9% max_cpu=0.2% pss=3615.6MB log=14.6MB log_disk=447.4MB tick=0.0MB tick_disk=426.5MB tick_disk_max=10.4MB`；MT5 `running=50 process=50 heartbeat=50 alerts=- cpu=17.3% max_cpu=0.4% pss=6452.5MB log=75.2MB log_disk=75.2MB tick_disk=0.0MB`。
- 只滚动后台只读 monitor 加载新口径，未重启 CTP/MT5 supervisor 或策略进程；新 monitor PID `73939`，日志 `reports/dual_stress_monitor_7d.log` 已输出 `tick_log_disk_high` 和 `tick_disk=426.5MB`。

### 28. 压测 supervisor 停机时按 `TARGETS` 全量停止单元，可能误停其它 supervisor 接管的工作区

现象：当前现场有两个 supervisor：旧主 supervisor PID `19233` 仍以 `--targets futures,mt5 --no-stop-existing` 运行并监控 CTP；MT5 已由专项 supervisor PID `49693` 接管。`run_dual_exchange_simulation.py` 旧逻辑在收到 `SIGTERM` 时直接调用 `stop_targets(workspaces, specs_by_key, target_unit_ids)`，会按 `TARGETS` 停止所有目标单元，而不是只停止本进程实际启动的单元。如果旧主 supervisor 被优雅终止，它可能把 MT5 专项 supervisor 正在管理的 50 个单元一起停掉。

原因：

- `WorkspaceService.run_units()` 返回的结果只有 `unit_id` / `task_id` / `status`，没有说明该单元是本次新启动，还是调用前已经在运行。
- 压测脚本没有记录本 supervisor 的 owned unit set；收到停机信号时只能按目标集合全量清理。
- `--no-stop-existing` 的语义只影响启动前是否停旧单元，没有延伸到 supervisor 退出清理阶段。

修复：

- `TradingWorkspaceService.start_units()` 返回 `already_running` 字段；已在运行的实例保持 `run_count` 不变，并标记为 `already_running=True`。
- `start_targets()` 返回 `(summaries, owned_unit_ids_by_key)`；只有 `status=running` 且 `already_running=False` 的单元会进入 owned 集合。
- 新增 `stop_owned_targets()`，收到停机信号时只停止 owned unit IDs；空 owned 集合的目标不会调用 `stop_units()`。
- 保留启动和状态输出格式，避免影响现有运维命令。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/app/services/trading_workspace_service.py src/backend/tests/test_trading_workspace_service.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `21 passed`。
- 本轮未对旧主 supervisor PID `19233` 执行 SIGTERM；该旧进程仍是老代码，后续不要用优雅终止触发它的全量 `TARGETS` 清理。
- 最新现场快照：CTP `running=50 process=50 heartbeat=50 alerts=tick_log_disk_high cpu=6.1% max_cpu=0.1% pss=4560.5MB log_disk=448.0MB tick_disk=426.5MB`；MT5 `running=50 process=50 heartbeat=50 alerts=- cpu=13.8% max_cpu=0.3% pss=5356.0MB log_disk=76.4MB`。

### 29. 全局标准库日志拦截把第三方 DEBUG/INFO 噪声写入应用日志，导致 `logs/app_*.log` 膨胀

现象：压测工作区自身日志已受控，但主应用日志目录仍异常膨胀。`logs/app_2026-06-22.log` 达到约 `3.6GB`，当前 `logs/app_2026-06-24.log` 约 `133MB`。抽样发现主要不是业务错误，而是第三方库噪声：`faker.factory` 的本地化 DEBUG、`aiosqlite.core` 的 execute/cursor/commit/rollback DEBUG、`asyncio.selector_events` 的 `Using selector: EpollSelector` DEBUG，以及 `slowapi.extension` 的 storage reset INFO。

原因：`setup_logger()` 使用 `logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)` 将标准库 logging 全量转发到 loguru；在 DEBUG=true 或测试环境下，app 文件 sink 级别也是 DEBUG。这个组合会把依赖库的高频 DEBUG/INFO 一并写入 `app_*.log`，与应用自身调试日志没有隔离。

修复：

- 在 `setup_logger()` 安装标准库拦截器后，显式将已确认高噪声第三方 logger 降到 `WARNING`：`aiosqlite`、`aiosqlite.core`、`asyncio`、`faker`、`faker.factory`、`slowapi`、`slowapi.extension`。
- 保留根 logger 的 `level=0`，应用自身 `app.*` logger 在 DEBUG 模式下仍可输出 DEBUG，避免影响本项目调试能力。
- 新增单元测试覆盖：应用 logger 仍启用 DEBUG；上述第三方 logger 的 DEBUG/INFO 被禁用，且有效级别为 `WARNING`。
- 未清理或截断既有大日志文件；本次只修复后续增长源。

验收：

- `python -m py_compile src/backend/app/utils/logger.py src/backend/tests/test_enhanced_logger.py` 通过。
- `python -m pytest src/backend/tests/test_enhanced_logger.py -q`，结果 `23 passed, 3 skipped`。
- `python -m pytest src/backend/tests/test_audit_and_logging.py -q`，结果 `32 passed, 6 warnings`。
- logger 聚焦测试输出中不再出现此前每轮 pytest 末尾常见的 `asyncio.selector_events DEBUG Using selector: EpollSelector` 噪声。

### 30. 工作区 unit 重启前不清理旧 `logs/`，新会话会继承历史 tick/trade 日志和磁盘告警

现象：当前 CTP 50 单元正在正常运行，且本会话 `tick=0.0MB`，但状态仍报 `tick_log_disk_high`，因为同一批 unit runtime 目录下保留了上一轮会话的 `logs/tick.log`。这些旧文件累计约 `426.5MB`，单文件最大约 `10.4MB`。如果后续复用相同 unit runtime 启动新进程，旧 `trade.log` / `position.log` / `tick.log` 也可能短暂混入快照解析和磁盘统计。

原因：`TradingWorkspaceService.start_units()` 会复用 `workspace_units/<workspace>/<unit>/`，启动前只同步 `run.py` 和 `config.yaml`，没有清理上一轮 `logs/`。此前为了保护 running 实例，不能在 runtime 同步阶段直接删除日志；但在确认实例不是 `running`、即将调用 `manager.start_instance()` 前清理是安全的。

修复：

- 新增 `_clear_runtime_logs_before_start(runtime_dir)`，删除该 unit runtime 下旧 `logs/` 后重新创建空目录。
- 只在 `already_running=False` 且即将启动新子进程时调用；已运行实例不清理，避免误删当前进程输出。
- 测试覆盖两个关键分支：running 实例保留旧日志文件；stopped 实例启动前清空旧 `tick.log` / `trade.log`。
- 本轮未对当前 CTP/MT5 运行中单元做文件删除或重启；现有 `tick_log_disk_high` 会保留到下一轮安全重启或明确执行人工清理。

验收：

- `python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/tests/test_trading_workspace_service.py` 通过。
- `python -m pytest src/backend/tests/test_trading_workspace_service.py -q`，结果 `9 passed`。
- `python -m pytest src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_seed_simulated_workspaces.py src/backend/tests/test_gateway_strategy_runner_config.py -q`，结果 `28 passed, 1 warning`。

### 31. `--monitor-only` 运维输出反复写入默认 admin 密码 `UserWarning`，污染长期监控日志

现象：每次执行 `ensure_dual_stress_running.sh status` 或启动只读 monitor 时，输出最前面都会出现：
`Insecure default admin password detected. Change ADMIN_PASSWORD before shared or production use.` 该警告不是交易运行错误，但会进入 `reports/dual_stress_monitor_7d.log`，影响异常扫描，也让人工查看状态时更难聚焦真正的 CTP/MT5 告警。

原因：`run_dual_exchange_simulation.py` 即使只做 `--monitor-only`，也会导入后端数据库和 workspace 服务，从而构造 `Settings`。在本地未显式配置 `ADMIN_PASSWORD` 时，config 的非生产保护会发出 `UserWarning`。但只读 monitor 不会创建默认管理员，也不会启动 Web 服务，这条 warning 对该模式没有操作价值。

修复：

- 在 `run_dual_exchange_simulation.py` 顶部新增 `_suppress_default_admin_warning_for_monitor_only()`。
- 仅当命令行包含 `--monitor-only` 时，忽略这一条精确匹配的默认 admin 密码 `UserWarning`。
- 普通 seed/start 路径不启用过滤；如果可能创建默认 admin 或运行服务，默认密码风险仍会提示。
- 新增测试覆盖 monitor-only 会抑制该 warning，start 模式仍保留 warning。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `15 passed`。
- `PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/ensure_dual_stress_running.sh status` 实测输出不再包含该 `UserWarning`；最新状态仍为 CTP `running=50 process=50 heartbeat=50 alerts=tick_log_disk_high`，MT5 `running=50 process=50 heartbeat=50 alerts=-`。

### 32. Gateway live runner 未启用 Backtrader 内存受限模式，长时间运行会累积 data/indicator line buffers

现象：最新监控显示 CTP 50 个子进程全数存活且心跳正常，但总 PSS/USS 持续增长；最近采样约为 `pss=5335.7MB uss=5298.5MB`，子进程增长较均匀。MT5 已从此前高位回落，当前约 `pss=3532.2MB`。CTP 的 `tick` 本会话为 `0.0MB`，`GatewayClient` tick 队列也已有 `maxlen`，因此更符合 Backtrader live runner 自身 line buffer 随 bar 数持续累积的特征。

原因：

- 压测模板 `strategies/simulate/gateway_dual_ma/run.py` 和 `gateway_boll_breakout/run.py` 使用 `bt.Cerebro(quicknotify=True)`，未设置 `exactbars`。
- Backtrader live feed 会关闭 preload/runonce，但 `exactbars=False` 时 data、indicator 和 observer 的 line buffers 仍会保留完整历史，适合回测/绘图，不适合 7x24 headless live 压测。
- 默认 `stdstats=True` 还会加载标准 observer，对无界 line buffer 和 headless 运行都没有必要。

修复：

- Gateway live runner 支持 `live.exactbars` / `simulate.exactbars` / `cerebro.exactbars`，默认 `True`，可显式设为 `0`/`false` 回退完整历史。
- Gateway live runner 支持 `live.stdstats` / `simulate.stdstats` / `cerebro.stdstats`，默认 `False`。
- 工作区 trading runtime 同步配置时默认写入 `live.exactbars=True`、`live.stdstats=False`，并允许 `unit_settings` 覆盖。
- seed 生成的 50+50 压测单元显式带上这些 live 内存配置，便于后续 re-seed 和人工审计。
- 不强行重启当前 CTP/MT5 运行中子进程；修复会在后续安全重启或新启动单元时生效。

验收：

- `python -m py_compile strategies/simulate/gateway_dual_ma/run.py strategies/simulate/gateway_boll_breakout/run.py src/backend/app/services/workspace_unit_runtime.py src/backend/scripts/seed_simulated_workspaces.py src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_seed_simulated_workspaces.py src/backend/tests/test_trading_workspace_service.py` 通过。
- `python -m pytest src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_seed_simulated_workspaces.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `17 passed, 1 warning`。

### 33. Live 子进程仍导入过重的 backtrader/bt_api_py 模块，MT5 50 进程 PSS 被放大

现象：`exactbars=True`、`stdstats=False`、tick dispatch 关闭后，MT5 50 个策略仍在启动后快速爬升。关闭 indicator 日志前的同窗口采样约为：35 秒 `pss=3953.3MB`、3 分钟 `pss=4763.1MB`，单进程中位数从约 `79.0MB` 升到 `95.1MB`。样本进程 smaps 显示主要是私有 `[anon]` 与 `[heap]`，并且 MT5 子进程中仍映射了 `bt_api_ctp` 扩展库。

原因：

- backtrader 顶层导入原先会急切加载 analyzers、observers、talib、profiles 和大量 indicator 模块；live runner 只需要 `Cerebro`、`Strategy`、少量 indicators、`BtApiFeed`、`BtApiStore`。
- `bt_api_py.gateway.client` 的子模块导入会先执行 `bt_api_py/__init__.py`；顶层包又急切导入 `BtApi`，从而把 `bt_api_ctp` 等非 MT5 gateway 所需模块带进每个 MT5 策略进程。
- `TradeLogger(log_indicators=True)` 会在每个 bar 枚举并写入 indicator 数据，带来不必要的 CPU、对象分配和 `indicator.log` 磁盘增长。

修复：

- backtrader sibling repo 增加 `BACKTRADER_LIGHT_IMPORT=1` 模式，顶层、`indicators`、`observers`、`feeds`、`stores`、`brokers` 只导入 live runner 所需对象；普通模式不变。
- `bt_api_py` sibling repo 增加 `BT_API_PY_LIGHT_IMPORT=1`，light 模式下 `BtApi` 改为按需导入；直接导入 `bt_api_py.gateway.client.GatewayClient` 不再加载 `bt_api_ctp`。
- live 子进程默认环境增加 `BACKTRADER_LIGHT_IMPORT=1`、`BT_API_PY_LIGHT_IMPORT=1` 和线程上限变量。
- Gateway 与 5 个 MT5 专用 runner 新增 `log_positions/log_indicators/log_signals` 配置解析；默认保留 positions/signals，关闭 indicators。
- `workspace_unit_runtime.py` 与 `seed_simulated_workspaces.py` 默认写入 `log_positions=True`、`log_indicators=False`、`log_signals=True`。
- 已滚动重启 MT5 专项 supervisor 和 CTP 专项 supervisor，使 100 个当前压测子进程全部加载新 runtime。

验收：

- `BACKTRADER_LIGHT_IMPORT=1 import backtrader` 的轻量导入 PSS 约 `20.9MB`，未加载 analyzers/talib/profiles。
- `BT_API_PY_LIGHT_IMPORT=1 from bt_api_py.gateway.client import GatewayClient` 的 PSS 约 `21.5MB`；普通 `import bt_api_py` 仍约 `62.7MB` 且保持 `BtApi` 兼容。
- 同时启用两个 light import 后，`backtrader` store/feed/gateway client 导入 PSS 约 `29.0MB`，heavy modules 计数为 `0`。
- MT5 重启后：35 秒 `pss=1890.6MB`、3 分钟 `pss=2600.3MB`、延长窗口稳定在约 `pss=2889.8MB`，单进程中位数约 `58.0MB`；较修复前同窗口降低约 `2.1GB`。
- CTP 重启后最新：`pss=1855.0MB`，单进程中位数约 `34.9MB` 至 `35MB`，线程数从旧现场的 250 降到 200。
- 最新 100 子进程合计：`count=100 threads=400 rss=6567.7MB pss=4745.2MB uss=4728.3MB`，CTP/MT5 均 `alerts=-`。
- CTP 与 MT5 两个压测目录均无新 `indicator.log`，100 个 config 均为 `log_indicators: false`。
- 测试通过：
  - `cd /home/yun/Documents/backtrader && python -m pytest tests/unit/test_light_import.py tests/unit/feeds/test_btapifeed.py -q`，结果 `42 passed`。
  - `PYTHONPATH=/home/yun/Documents/bt_api_py python -m pytest /home/yun/Documents/bt_api_py/tests/test_light_import.py -q`，结果 `1 passed`。
  - `python -m pytest src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_seed_simulated_workspaces.py -q`，结果 `18 passed, 1 warning`。
  - `python -m pytest src/backend/tests/test_live_trading_manager.py -k build_subprocess_env -q`，结果 `2 passed, 63 deselected`。
  - `python -m pytest src/backend/tests/test_extracted_modules.py -k GatewayRuntimeService -q`，结果 `10 passed, 103 deselected`。

### 34. GatewayClient 未按订阅过滤 tick，单策略进程会缓存全市场队列

现象：light import、`exactbars=True`、indicator 日志关闭后，CTP 新启动 50 个子进程仍在早期窗口持续增长。修复前同一轮日志显示 CTP PSS 从 `1601.2MB` 逐步升到 `1909.3MB`，随后继续到约 `1986MB`；但策略日志极小，`tick.log` 为 `0.0MB`，样本进程也没有再映射 `bt_api_ctp` 或 `pandas`。

原因：

- `GatewayClient.connect()` 对 ZMQ market socket 使用 `SUBSCRIBE b""`，实际会接收共享 gateway 发布的全部 symbol。
- `GatewayClient.subscribe()` 只向 gateway 发送订阅命令，没有在 client 侧记录 `self.subscribed`。
- `_store_tick()` 对每条 market payload 都按 `symbol` 与 `instrument_id` 建队列；在 50 策略共享 gateway 时，每个单策略子进程都会为其他 symbol 填充 `gateway_max_ticks_per_symbol` 队列。

修复：

- `bt_api_py.gateway.client.GatewayClient.subscribe()` 成功后记录规范化后的订阅 symbol，并过滤空字符串。
- `_store_tick()` 只保留当前 client 已订阅的 `symbol` / `instrument_id`；没有显式订阅时保留旧的全市场兼容行为。
- 新增单测覆盖：订阅后记录 symbol、未订阅 tick 不创建队列、未订阅状态保持旧行为。

验收：

- `PYTHONPATH=/home/yun/Documents/bt_api_py /home/yun/anaconda3/bin/python -m py_compile bt_api_py/gateway/client.py tests/test_gateway_client_backpressure.py` 通过。
- `PYTHONPATH=/home/yun/Documents/bt_api_py /home/yun/anaconda3/bin/python -m pytest tests/test_gateway_client_backpressure.py tests/test_light_import.py -q`，结果 `9 passed`。
- 重启 CTP/MT5 后 3 分钟复采：CTP `pss=1565.7MB`，MT5 `pss=1631.3MB`，均为 `running=50 process=50 heartbeat=50 alerts=-`。
- `/proc` 复核：100 个子进程合计 `rss=5020.6MB pss=3197.6MB uss=3180.6MB`；CTP 单进程 PSS 中位数约 `31.3MB`，MT5 单进程 PSS 中位数约 `32.6MB`。

### 35. 多个 supervisor 并发写 live_trading_instances.json，导致 MT5 单元启动丢状态

现象：在一次 CTP 与 MT5 相邻重启后，MT5 supervisor 报 `MT5模拟工作区 first error: Instance does not exist`，随后长期处于 `running=49 idle=1 process=49 heartbeat=49 no_log=1 alerts=heartbeat_missing`。数据库定位到 idle 单元为 `83f651bf-431d-46f3-9e7d-d752a1322444`，对应实例 `64db8610` 在 JSON 中为 `stopped`。

原因：`LiveTradingManager` 的实例状态持久化使用 `src/backend/data/live_trading_instances.json`。此前 `InstanceStore` 是“读取整份 JSON -> 修改内存 -> 写回整份 JSON”，只受单进程内锁保护。CTP 与 MT5 两个独立 supervisor 并发 stop/start 时，会互相覆盖对方刚写入的实例状态，从而让某个 `trading_instance_id` 在启动窗口内短暂缺失或回退到旧状态。

修复：

- `InstanceStore` 增加跨进程文件锁 `live_trading_instances.json.lock`，`put/delete/update_fields` 在锁内完成读改写。
- `InstanceStore.save_all()` 改为临时文件写入后 `replace()`，避免写半截 JSON。
- `LiveTradingManager` 的 `sync_status_on_boot/list/add/remove/get/start/stop/wait_process` 等会写实例状态的路径接入同一个跨进程锁。
- `start_instance/stop_instance` 仍保留进程内 async 锁，并在跨进程锁获取异常时释放 async 锁，避免后续启停卡住。

验收：

- 重新滚动重启 CTP supervisor PID `208001` 与 MT5 supervisor PID `209032` 后，MT5 `64db8610` 正常重新 acquire，启动结果恢复为 `running=50 failed=0 idle=0`。
- `src/backend/data/live_trading_instances.json` 当前为 `running=100 stopped=100`。
- 最新 direct monitor：CTP 与 MT5 均 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。
- 测试通过：
  - `python -m py_compile src/backend/app/services/instance_store.py src/backend/app/services/live_trading/manager.py`。
  - `python -m pytest src/backend/tests/test_instance_store.py src/backend/tests/test_instance_store_and_ws.py src/backend/tests/test_extracted_modules.py -k InstanceStore -q`，结果 `23 passed, 143 deselected`。
  - `python -m pytest src/backend/tests/test_live_instance_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_live_trading_manager.py -k "test_save_instances or add_instance or remove_instance or get_instance or start_instance or stop_instance or build_subprocess_env or start_units" -q`，结果 `25 passed, 73 deselected`。

### 36. live instance 跨进程锁粒度过粗，重启不同 supervisor 时会互相长时间阻塞

现象：修复 JSON 丢写后，CTP 与 MT5 相邻重启时，后启动的 supervisor 会等待前一个 supervisor 完成较长一段 gateway acquire / 子进程启动流程。实测 MT5 restart 命令曾等待约 30 秒才返回 `started dual stress supervisor`。这说明跨进程文件锁不仅保护 JSON 写入，也覆盖了慢 I/O 和 subprocess 启动阶段。

原因：`LiveTradingManager.start_instance()` / `stop_instance()` 外层直接持有 `_AsyncInstanceStoreLock`。该锁内部同时持有进程内 async lock 与 `live_trading_instances.json.lock` 文件锁，导致一个 supervisor 启动 50 个单元时，另一个无关 supervisor 的实例状态更新被长时间阻塞。

修复：

- `start_instance()` / `stop_instance()` 外层只保留进程内 async lock，避免同一 manager 内并发启停打架。
- 跨进程文件锁改为通过 `instance_lock=_AsyncInstanceStoreLock()` 传给 `live_execution`，仅在最终 `load latest -> update one instance -> save` 的 JSON 改写小段进入。
- `wait_process()` 仍使用带 async lock 的 `_AsyncInstanceStoreLock(self._instance_op_lock)`，保证子进程退出回写与同进程启停互斥。
- 移除生产代码中为兼容旧测试加入的 `unittest.mock.Mock` 判断；`test_save_instances` 改用真实临时文件验证原子写入结果。
- 新增回归测试 `test_start_instance_delegates_file_lock_to_execution_layer`，防止以后把文件锁重新扩大到整个启动过程。

验收：

- `python -m py_compile src/backend/app/services/instance_store.py src/backend/app/services/live_trading/manager.py src/backend/tests/test_live_trading_manager.py` 通过。
- `python -m pytest src/backend/tests/test_instance_store.py src/backend/tests/test_instance_store_and_ws.py src/backend/tests/test_extracted_modules.py -k InstanceStore -q`，结果 `23 passed, 143 deselected`。
- `python -m pytest src/backend/tests/test_live_instance_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_live_trading_manager.py -k "test_save_instances or delegates_file_lock or add_instance or remove_instance or get_instance or start_instance or stop_instance or build_subprocess_env or start_units" -q`，结果 `26 passed, 73 deselected`。
- 重新滚动重启后：CTP supervisor PID `219002`，MT5 supervisor PID `219420`；MT5 restart 约 `7s` 返回，不再被 CTP 的 50 单元启动阶段长时间阻塞。
- 3 分钟复采 direct monitor：CTP 与 MT5 均 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。
- `/proc` 复核：100 个子进程合计 `rss=5009.6MB pss=3187.7MB uss=3170.7MB`；CTP 单进程 PSS 中位数约 `31.4MB`，MT5 单进程 PSS 中位数约 `32.5MB`。

### 37. live trading manager 测试读取真实压测现场，且进程终止测试仍按旧语义断言

现象：扩大回归到完整 `src/backend/tests/test_live_trading_manager.py -q` 后出现 3 个失败：

- `test_get_gateway_health_subprocess_ready` 与 `test_get_gateway_health_subprocess_fatal_error` 期望只返回 1 个手工构造的 subprocess gateway snapshot，但实际返回 101 个 snapshot，因为测试在调用 `get_gateway_health()` 时读到了当前真实的 100 个压测实例。
- `test_kill_pid_success` 仍断言 `os.kill()` 只调用一次；当前实现为了更可靠清理策略子进程，`_kill_pid()` 会先发 SIGTERM，然后在 `force_after_seconds=1.0` 内轮询 `os.kill(pid, 0)`，必要时再 SIGKILL。

原因：

- gateway health 测试只在构造 `LiveTradingManager()` 时 patch 了 `_load_instances`，但真正调用 `get_gateway_health()` 时底层 `gateway_health_service.get_gateway_health()` 仍可读取真实 `live_trading_instances.json`。
- 进程终止测试没有跟随之前的 owned stop 修复更新，仍按老的无强制清理行为写断言。

修复：

- 两个 gateway health 测试改为 mock `gateway_health_service.get_gateway_health` 返回空列表，只验证 manager 对 `_gateways` 中 subprocess gateway override 的合并逻辑，避免依赖现场状态。
- `test_kill_pid_success` 改为模拟 SIGTERM 后进程已退出：允许一次 SIGTERM 和一次 `pid, 0` 探活，并断言不会发送 SIGKILL。

验收：

- `python -m pytest src/backend/tests/test_live_trading_manager.py -q`，结果 `66 passed`。

### 38. 压测状态行缺少时间戳，长期告警复盘难以定位时间窗口

现象：`reports/dual_stress_monitor_7d.log`、CTP/MT5 supervisor 日志中的核心 `status:` / `monitor:` 行原先没有时间戳。长期日志里混有多次重启窗口期的 `process_missing`、`heartbeat_missing`、`pss_high` 等历史告警时，只看行内容很难判断它们发生在何时，也难以和代码变更、重启、资源采样做精确关联。

原因：`run_dual_exchange_simulation.py:print_status()` 直接输出 `{prefix}: ...`，虽然部分第三方 logger 行有时间戳，但压测健康快照本身没有结构化时间前缀。持续巡检和事后审计需要每条健康快照都自带本地时区时间。

修复：

- 新增 `status_timestamp()`，使用本地时区输出 `YYYY-MM-DD HH:MM:SS TZ`。
- `print_status()` 统一输出 `{timestamp} {prefix}: ...`，覆盖 `monitor`、`status`、`started`、`hold elapsed` 等健康快照行。
- 回归测试固定 `2026-06-25 01:35:00 CST`，验证输出行以时间戳开头，并继续保留资源告警字段断言。
- 仅重启无副作用的 `monitor-only` 进程，让新格式立即进入 `reports/dual_stress_monitor_7d.log`；CTP/MT5 实际 supervisor 和 100 个策略子进程保持运行。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `15 passed`。
- 新 monitor PID `236913` 已写入 `2026-06-25 01:32:55 CST monitor: ... alerts=-`。
- 最新 direct monitor：CTP 与 MT5 均 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 39. 压测脚本普通运维行仍无时间戳，和健康快照混排时不利于审计

现象：第 38 项修复后，`monitor:` / `status:` 健康快照已有时间戳，但同一个 `reports/dual_stress_monitor_7d.log` 中仍有 `期货模拟工作区 target prefix: CTP压测`、`monitor holding for 604800s`、启动/停止摘要、错误摘要等裸文本行。长期日志按时间窗口检索时，这些行仍无法可靠排序或归属到具体重启窗口。

原因：脚本里健康快照走 `print_status()`，普通运维行仍直接 `print()`。行业压测日志应保证同一日志源的所有脚本输出都具备同一时间前缀。

修复：

- 新增 `print_log()`，复用 `status_timestamp()`，给普通 stdout/stderr 运维行统一添加本地时区时间戳。
- `seed_targets()`、`stop_targets()`、`start_targets()`、`stop_owned_targets()`、`hold_monitor()`、`main()` 中的脚本级普通输出改用 `print_log()`。
- `print_log()` 默认在调用时读取当前 `sys.stdout`，避免导入时绑定旧 stdout，保证 pytest 捕获和进程重定向都正常。
- 新增回归测试 `test_print_log_includes_timestamp`，固定 `2026-06-25 01:36:00 CST` 验证普通运维行格式。
- 仅重启无副作用的 `monitor-only` 进程，让新格式立即进入只读监控日志；实际 CTP/MT5 supervisor 与 100 个策略子进程未重启。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `16 passed`。
- 新 monitor PID `241305` 已写入：
  - `2026-06-25 01:37:01 CST 期货模拟工作区 target prefix: CTP压测`
  - `2026-06-25 01:37:02 CST monitor holding for 604800s`
  - `2026-06-25 01:37:10 CST monitor: ... alerts=-`
- 最新 direct monitor：CTP 与 MT5 均 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 40. 压测 CPU 指标是启动以来平均值，长跑后会稀释当前负载

现象：`run_dual_exchange_simulation.py` 的 `cpu=` / `max_cpu=` 原先使用 `/proc/{pid}/stat` 中累计 CPU 时间除以进程启动以来 elapsed time。对短时启动尖峰有参考价值，但长时间运行后会逐步变成全生命周期平均值，无法反映当前 30 秒巡检窗口的 CPU 压力；如果后续出现短时忙等或 gateway 回调风暴，指标可能被历史低负载稀释。

原因：`read_process_resource()` 每次独立计算 `process_seconds / elapsed_seconds`，没有保存上一次采样的 CPU 时间和墙钟时间。

修复：

- 新增 `_PROCESS_CPU_SAMPLES`，按 PID 保存上一轮 `(sample_time, total_cpu_seconds)`。
- 新增 `process_cpu_pct()`：同一 monitor 进程第二轮开始使用 `delta_cpu / delta_time * 100` 计算窗口 CPU；首轮、PID 新出现或 CPU 计数回退时仍回退到启动以来平均值。
- `runtime_health_counter()` 在同一轮采样中复用统一 `sample_time` 和 `/proc/uptime`，减少每个 PID 重复读取并保证同一轮 CPU 比例一致。
- 新增 `prune_process_cpu_samples()`，每轮清理已退出 PID 的缓存，避免长期 monitor 内存增长。
- 新增回归测试覆盖首轮回退、后续窗口 delta 和退出 PID 缓存清理。
- 重启无副作用的 `monitor-only` 进程，让长期巡检进入窗口 CPU 采样；实际 CTP/MT5 supervisor 与 100 个策略子进程未重启。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `18 passed`。
- 短时只读验证 `--monitor-only --hold-seconds 6 --status-interval 5 --no-monitor-after-hold` 输出第二轮 `status`，CTP/MT5 均 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。
- 长期只读 monitor PID `245746` 已写入 `2026-06-25 01:41:49 CST status: ... alerts=-`。

### 41. TradeLogger 会把 session_started 事件时间写成 Unix epoch

现象：抽样检查 CTP 与 MT5 工作区的 `logs/system.log` 时，所有新启动策略的第一条 `session_started` 结构化日志都类似：

- `log_time`: `2026-06-25T01:15:06.793+08:00`
- `event_time`: `1970-01-01 00:00:00`
- `event_type`: `session_started`

这不是运行故障，但会污染长期压测审计时间线。按 `event_time` 排序或聚合系统事件时，所有 session start 都会落到 epoch，和真实启动窗口脱节，也会影响后续从日志构造生命周期视图。

原因：`backtrader.observers.TradeLogger.start()` 在第一根 bar 之前写 `session_started`。`TradeLogger._base_event()` 未传显式 `event_time` 时默认读取 `self._owner.datetime.datetime()`，此时 backtrader 数据时间尚未推进，返回 epoch。

修复：

- 修改 `/home/yun/Documents/backtrader/backtrader/observers/trade_logger.py` 的 `_base_event()`：没有显式 `event_time` 时使用当前 wall-clock `log_time`。
- 对 store/gateway 转发事件仍保留显式 `event_time`，例如 `store_connected` 的 gateway timestamp 不会被替换。
- 新增单元测试覆盖默认事件时间等于 `log_time`、显式事件时间保持不变。
- 新增运行时集成断言，确保 `session_started.event_time == session_started.log_time` 且不再以 `1970-01-01` 开头。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py tests/integration/test_trade_logger_runtime.py` 通过。
- `/home/yun/anaconda3/bin/python -m pytest tests/unit/observers/test_trade_logger_edge_cases.py -q`，结果 `23 passed`。
- `/home/yun/anaconda3/bin/python -m pytest tests/integration/test_trade_logger_runtime.py -q`，结果 `8 passed`。
- 当前 100 个压测子进程未重启，旧日志不会被回写；下一次新启动或滚动重启策略时验证 `session_started.event_time` 不再是 epoch。

### 42. live trading 元数据补齐触发测试污染，真实运行态被写成 idle/stopped

现象：运行 live trading API 回归测试后，真实 `src/backend/data/live_trading_instances.json` 被覆盖成只有两个测试夹具实例：

- `inst1`: `user_id=user1`、`status=stopped`
- `inst2`: `user_id=user2`、`status=stopped`

随后 direct monitor 显示 CTP/MT5 均 `running=0 idle=50 process=50 heartbeat=50`。这是假 idle：`/proc` 中 100 个策略子进程仍在，日志心跳也正常，但持久化 JSON 与 DB `strategy_units.run_status` 已被测试写坏。

原因：

- 新增的 live instance 元数据补齐会在 `LiveTradingManager()` 初始化或 `list_instances()` 时给旧记录补 `id`、`gateway_type`、`updated_at`，并在有变更时保存。
- `src/backend/tests/test_live_trading_api.py::TestLiveTradingManager::test_list_instances_filters_by_user` 只 mock 了 `_load_instances`，没有 mock `_save_instances`。
- 测试环境没有把 live trading 的真实 JSON 文件重定向到临时目录，因此保存动作直接写入生产压测状态文件。
- CTP API 预设测试仍按旧的一字段断言，和当前已支持 `ctp_env`、front、timeout 等 7 个可编辑字段的实现漂移。

恢复：

- 扫描 `/proc` 中 `workspace_units/{workspace_id}/{unit_id}/run.py`，确认两个压力 workspace 各 50 个真实子进程，provider 分别为 `ctp_gateway` 和 `mt5_gateway`。
- 从 MySQL `strategy_units` 读取 100 个 unit 的 `trading_instance_id`、策略信息、owner、gateway config，并与 `/proc` 的 `(workspace_id, unit_id)` 一一校验。
- 用真实 PID、runtime/log 目录和进程启动时间重建 100 个 JSON 实例，全部标记为 `status=running`，并写入 `gateway_type`。
- 将 100 条 `strategy_units.run_status` 恢复为 `running`，同步 `trading_snapshot.instance_status=running`、`started_at`、`updated_at`。
- 恢复过程中未停止、重启或替换任何 CTP/MT5 supervisor 和策略子进程。

修复：

- 新增 `app.services.live_trading.metadata`，集中处理 `gateway_type` 推断、`updated_at` 和旧实例元数据补齐。
- `live_trading.instance` / `live_trading.execution` 在 add/list/get/start/stop/wait 等路径统一维护 `updated_at` 与 `gateway_type`，让 API 列表和前端类型可直接读取这些字段。
- `LiveInstanceInfo`、前端 `LiveInstance` 类型补齐 `updated_at`、`gateway_type`、`gateway_key`。
- `tests/conftest.py` 的 autouse fixture 现在把 `live_trading_manager._INSTANCES_FILE`、`_MANUAL_GATEWAYS_FILE` 和 `instance_store._INSTANCES_FILE` 重定向到每个测试自己的 `tmp_path`，测试不再接触真实运行态文件。
- CTP gateway preset API 测试改为断言当前 7 个可编辑字段：`account_id`、`ctp_env`、`set1_group`、`td_front`、`md_front`、`startup_timeout_sec`、`command_timeout_sec`。

验收：

- 恢复后 direct monitor：CTP 与 MT5 均 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。
- `src/backend/data/live_trading_instances.json` 当前 `instances=100`、`running=100`、`gateway_type` 为 `ctp_gateway=50`、`mt5_gateway=50`。
- DB 复核：两个 workspace 的 `strategy_units` 均 `run_status=running` 各 50 条，抽样 `trading_snapshot.instance_status=running`。
- 污染复现测试前后真实 JSON sha256 不变：`8cc461c0e7b0d7fb0b07e70e6de5ae901751ca655883e711ac42bf0aeeb9574b`。
- `python -m py_compile src/backend/app/services/live_trading/metadata.py src/backend/app/services/live_trading/instance.py src/backend/app/services/live_trading/execution.py src/backend/app/schemas/live_trading_instance.py src/backend/tests/conftest.py src/backend/tests/test_live_instance_service.py src/backend/tests/test_live_trading_api.py src/backend/tests/test_extracted_modules.py` 通过。
- `python -m pytest src/backend/tests/test_live_instance_service.py -q`，结果 `25 passed`。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k LiveExecutionService`，结果 `7 passed, 1 skipped, 105 deselected`。
- `python -m pytest src/backend/tests/test_live_trading_manager.py -q`，结果 `66 passed`。
- `python -m pytest src/backend/tests/test_live_trading_api.py -q`，结果 `39 passed`。

### 43. 长期只读 monitor 按 DB running 判断退出，假 idle 时停止监控真实子进程

现象：测试污染发生后，`reports/dual_stress_monitor_7d.log` 最后一行停在：

- `2026-06-25 01:59:15 CST status: ... running=0 idle=50 process=50 heartbeat=50 ... alerts=-`

随后长期只读 monitor PID `245746` 已不存在，CTP supervisor PID `219002` 与 MT5 supervisor PID `219420` 也已不存在，但 `/proc` 中 100 个策略子进程仍存活、日志心跳仍正常，父进程变为 `systemd --user` PID `1584`。也就是说 supervisor/monitor 在最需要继续提示“DB 状态与真实进程不一致”的时候退出了。

原因：

- `hold_monitor()` 同时服务启动 supervisor 和只读 monitor，它的退出条件调用 `any_targets_running()`。
- `any_targets_running()` 只看 DB 派生的 `running` 计数，不看 runtime 健康计数。
- 当 DB 被外部污染成 `idle`，但子进程仍在时，`running=0 process_alive=50 heartbeat_fresh=50` 会被误判为“目标已停止”，于是长期 monitor 返回。
- `resource_alerts()` 只检查 `running > process_alive` 的 `process_missing`，没有检查 `process_alive > running`，因此假 idle 行还显示 `alerts=-`。

修复：

- `any_targets_running()` 保持函数名兼容，但活跃判定扩展为 `running > 0 or process_alive > 0`。
- `resource_alerts()` 新增 `process_orphaned`：当真实子进程数大于 DB running 数时报警。
- 新增回归测试覆盖：
  - `idle=50 process_alive=50` 仍被认为需要继续监控。
  - `resource_alerts()` 对假 idle 输出 `process_orphaned`。
  - `hold_monitor()` 在 DB idle 但真实进程仍活跃时不会退出。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `19 passed`。
- 人工验证：`resource_alerts(Counter({'idle': 50, 'process_alive': 50, 'heartbeat_fresh': 50})) == ['process_orphaned']`，`any_targets_running(...) is True`。
- 启动新长期只读 monitor PID `282193`；当前不重启 100 个策略子进程，也无法在不重启的情况下把已运行子进程重新挂回原 supervisor 父进程：
  - `setsid ... run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --hold-seconds 604800 --status-interval 30`
  - 日志已写入 `2026-06-25 02:16:49 CST monitor: ... running=50 ... process=50 heartbeat=50 ... alerts=-`
  - 后续已继续写入 `2026-06-25 02:17:20 CST status` 与 `2026-06-25 02:17:51 CST status`，PID 仍存活。

### 44. ensure 脚本只信 PID 文件，无法发现已运行的 monitor 进程

现象：新长期只读 monitor 通过 `setsid` 直接启动后，真实 PID `282193` 持续运行并写日志，但：

- `.pids/dual_stress_monitor.pid` 不存在或为空。
- `scripts/ops/ensure_dual_stress_running.sh status` 输出 `dual stress monitor not running`。
- 如果此时执行 `monitor` 动作，脚本会再次启动一个只读 monitor，造成重复监控进程和重复日志行。

原因：

- `ensure_dual_stress_running.sh` 只读取 PID 文件并用 `ps -p` 判断，不扫描已经存在的 `run_dual_exchange_simulation.py` 进程。
- 实际进程命令行可能使用相对脚本路径 `src/backend/scripts/run_dual_exchange_simulation.py`，原先即使后续补扫描，如果只匹配绝对路径也会漏掉。

修复：

- 新增 `cmdline_for_pid()`，优先读取 `/proc/{pid}/cmdline`，兼容 fallback 到 `ps`。
- 新增 `find_existing_process(mode)`，按脚本路径、`--targets`、`--monitor-only`、`--no-hold` 区分长期 monitor / supervisor。
- 新增 `current_or_discovered_pid(mode, pid_file)`，PID 文件失效时扫描真实进程，找到后回写 PID 文件。
- `start`、`monitor`、`status`、`restart/stop` 路径统一使用发现逻辑，避免重复启动已存在的长期进程。
- 匹配脚本路径时同时支持绝对路径和相对路径。

验收：

- `bash -n scripts/ops/ensure_dual_stress_running.sh` 通过。
- `python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `3 passed`。
- 真实环境验证：
  - `TARGETS=futures,mt5 PYTHON_BIN=/home/yun/anaconda3/bin/python scripts/ops/ensure_dual_stress_running.sh status`
  - 输出 `dual stress monitor running: pid=282193`。
  - `.pids/dual_stress_monitor.pid` 已回写为 `282193`。
  - 同次只读快照仍为 CTP/MT5 双目标 `running=50 process=50 heartbeat=50 alerts=-`。

### 45. runtime health 把“进程存活”误当成“日志心跳正常”

现象：当前 100 个策略进程全部存活，但直接按进程启动时间过滤当前 session 日志后，100 个 runtime 目录的最新日志 mtime 都已经超过 4300 秒：

- `fresh_count<=180 0`
- `stale>180 100`
- `missing 0`

旧 direct monitor 却持续输出 `heartbeat=50 stale=0 alerts=-`。这会掩盖“进程还在但策略主循环/行情/日志输出已经停住”的真实状态。

原因：`runtime_health_counter()` 原先只要 `process_alive` 就直接 `counter["heartbeat_fresh"] += 1`，没有调用 `latest_log_age_seconds()` 检查日志 mtime。`heartbeat` 实际上成了第二个 `process` 指标。

修复：

- `process` 仍只表示目标 `run.py` 进程是否存在。
- `heartbeat` / `stale` / `no_log` 统一基于 `latest_log_age_seconds(log_dir, since_timestamp=session_since)` 计算。
- 对活进程也检查当前 session 日志 mtime：
  - `age is None` -> `heartbeat_missing`
  - `age <= stale_heartbeat_seconds` -> `heartbeat_fresh`
  - `age > stale_heartbeat_seconds` -> `heartbeat_stale`
- 保留当前 session 日志过滤，避免旧 session 遗留日志让新进程误判为有心跳。
- 新增回归测试：活进程 + 600 秒未写日志时必须得到 `process_alive=1 heartbeat_stale=1`。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `20 passed`。
- 修复后 direct monitor 输出：
  - CTP `running=50 process=50 heartbeat=0 stale=50 alerts=heartbeat_stale`
  - MT5 `running=50 process=50 heartbeat=0 stale=50 alerts=heartbeat_stale`
- 仅重启只读 monitor，不触碰 100 个策略子进程；新 monitor PID `307323` 已写入修复后的首轮快照：
  - `2026-06-25 02:28:42 CST monitor: ... heartbeat=0 stale=50 ... alerts=heartbeat_stale`
  - 后续 `2026-06-25 02:30:15 CST status` 持续保持同一口径。

### 46. gateway runner 缺少独立心跳文件，安静运行期无法证明主循环健康

现象：修复 runtime health 口径后，当前 CTP/MT5 各 50 个策略进程仍全部存活，但 direct monitor 正确显示 `heartbeat=0 stale=50 alerts=heartbeat_stale`。这说明现有旧进程的 `logs` 目录已经长时间没有当前 session 文件更新。旧 runner 只依赖 TradeLogger、交易、行情或系统事件写日志，没有一个独立于市场事件的进程心跳，因此监控无法区分“进程正常安静等待行情”和“主循环/日志路径已经停住”。

原因：

- `strategies/simulate/gateway_dual_ma/run.py` 与 `strategies/simulate/gateway_boll_breakout/run.py` 只在创建 `BtApiFeed` / `TradeLogger` 后由 backtrader 事件驱动写日志。
- 独立示例 `strategies/simulate/mt5_eurusd_ma_cross/run.py` 也没有 runner 自身心跳。
- 新版 monitor 已不再把 `process_alive` 当成 `heartbeat_fresh`，因此旧 runner 暴露出真实的可观测性缺口。

修复：

- 三个 runner 新增 `logs/heartbeat.json`，字段包含 `pid`、`status`、`timestamp`、`started_at`。
- 心跳线程在 `BtApiStore(...).start()` 前启动，覆盖网关启动等待阶段。
- 默认心跳间隔 30 秒；可通过 `live` / `simulate` / `logging` / `gateway` 下的 `heartbeat_interval_seconds` 或 `heartbeat_interval` 覆盖，配置路径最小 1 秒。
- 写入采用临时文件加 `os.replace()` 原子替换，避免 monitor 读到半写文件。
- 退出路径先停止 store，再停止心跳线程并写入 `status=stopped`。
- `runtime_health_counter()` 已扫描 `logs` 目录下任意文件的 mtime，因此无需再改 monitor；`heartbeat.json` 不是 `*.log`，不会计入日志体积指标。

验收：

- `python -m py_compile strategies/simulate/gateway_dual_ma/run.py strategies/simulate/gateway_boll_breakout/run.py strategies/simulate/mt5_eurusd_ma_cross/run.py src/backend/tests/test_gateway_strategy_runner_config.py` 通过。
- `python -m pytest src/backend/tests/test_gateway_strategy_runner_config.py -q`，结果 `7 passed, 1 warning`。
- `python -m pytest src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `30 passed, 1 warning`。
- `python -m pytest src/backend/tests/test_trading_workspace_service.py -q`，结果 `10 passed`；新增覆盖已有旧 `run.py` 会被模板刷新。
- `python -m pytest src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_ensure_dual_stress_running_script.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `40 passed, 1 warning`。
- 现场不重启当前 100 个策略子进程；direct monitor 仍为 CTP/MT5 双目标 `running=50 process=50 heartbeat=0 stale=50 alerts=heartbeat_stale`，这是旧进程未加载新 runner 的预期状态。
- 长期只读 monitor PID 仍为 `307323`，`reports/dual_stress_monitor_7d.log` 持续输出相同 stale 心跳口径。

### 47. start 模式 `--no-hold` 会取消 wait_process，误改新启动实例状态

现象：用 `run_dual_exchange_simulation.py --skip-seed --targets futures --unit-ids 0b64cdc5-b443-496c-ace4-eeb66a50bba2 --no-hold` 尝试滚动重启 CTP01 canary 时，脚本先输出 `running=1`，随后父脚本退出码为 `139`，新子进程没有持续存活。第一次 canary 后实例 `d88dea3a` 被回写成 `status=error pid=None error="Process exit code: None"`；第二次修复前后又出现 `status=stopped pid=None`。这说明 `--no-hold` 对“本进程刚启动的 asyncio subprocess”并不安全。

原因：

- `start_instance()` 通过 `asyncio.create_subprocess_exec()` 启动策略，并创建后台 `wait_process()` 任务。
- start 模式遇到 `--no-hold` 立即让 `asyncio.run(main())` 结束，事件循环会取消后台 `wait_process()`。
- 旧 `wait_process()` 的 `finally` 在 `proc.returncode is None` 时仍继续清 `pid`、写 `stopped_at`、保存实例，导致刚启动但尚未被稳定监护的策略被误标为 error/stopped。
- 对真正新启动的单元，`--no-hold` 还会让父进程无法继续持有 subprocess watcher，不适合作为滚动重启方式。

修复：

- `wait_process()` 显式处理 `asyncio.CancelledError`。
- 当 `proc.returncode is None` 且实例不是显式 stopping 时，将该 wait 回调视为 stale/cancelled callback：不写 error/stopped、不清 pid、不 pop `processes`、不释放 gateway。
- `run_dual_exchange_simulation.py` 新增 `has_owned_started_units()`；start 模式下如果 `--no-hold` 但本轮确实启动了新单元，则忽略立即退出，继续进入 hold，保证 subprocess watcher 仍附着。
- 后续滚动重启必须使用持有型 supervisor；本轮 CTP01 使用 detached canary supervisor PID `347458` 持有。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/app/services/live_trading/execution.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_extracted_modules.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `22 passed`。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k LiveExecutionService`，结果 `8 passed, 1 skipped, 105 deselected`。
- 取消路径隔离验证：`CancelledError + returncode=None` 后 `saved == {}`、`released == []`，实例仍为 `status=running pid=12345`。
- 现场恢复：CTP01 实例 `d88dea3a` 当前 `status=running pid=347600 error=None`，由 supervisor PID `347458` 持有。

### 48. 无 live process 的旧 heartbeat/log 文件不应计入当前心跳

现象：CTP01 首次 canary 失败后，单元级 direct monitor 输出 `running=0 failed=1 process=0 heartbeat=1 stale=0 alerts=-`；随后心跳文件变旧后又输出 `process=0 stale=1`。这会让已失败或已停止的单元因为残留 `heartbeat.json`/日志 mtime 被计入 heartbeat/stale，混淆“当前进程健康”和“旧文件存在”。

原因：`runtime_health_counter()` 对每个目标单元都会扫描 `logs` mtime，无论该单元当前是否有 live `run.py` 进程。修复进程存活不等于心跳之后，这个细节暴露出来：没有进程的单元仍可因为旧文件得到 `heartbeat_fresh` 或 `heartbeat_stale`。

修复：

- `process` 仍按当前 `workspace_units/.../run.py` 进程统计。
- `heartbeat` / `stale` / `no_log` 只对 `process_alive` 的单元统计。
- 当前 session 的 `log` / `tick` 体积也只对 live process 统计；累计磁盘口径 `log_disk` / `tick_disk` 仍保留所有目标单元的历史文件大小。
- 新增测试覆盖无 live process 但旧日志 mtime 很新时，`heartbeat_fresh/stale/missing` 均为 0，`log_mb_total=0.0`，但 `log_disk_mb_total` 仍记录历史文件。

验收：

- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `22 passed`。
- CTP01 canary 持有型 supervisor 输出 `running=1 failed=0 idle=0 missing=0 process=1 heartbeat=1 stale=0 no_log=0 alerts=-`。
- 全局 direct monitor 输出：CTP `running=50 process=50 heartbeat=1 stale=49 alerts=heartbeat_stale`；MT5 `running=50 process=50 heartbeat=0 stale=50 alerts=heartbeat_stale`。

### 49. 滚动重启需要脚本级分批编排和真实完成汇总

现象：CTP01 canary 证明新版 runner 有效后，需要把剩余旧进程逐步切到新版心跳 runner。但直接手工按单元执行 start/stop 容易重复踩中 `--no-hold` watcher 取消问题；全量 stop/start 又会一次性扰动 50 个 CTP 或 MT5 单元。CTP02 现场滚动重启还暴露一个日志问题：`rolling batch 1 check` 已显示 `process=1 heartbeat=1 alerts=-`，但随后的 `rolling restarted` 使用启动结果计数，误报 `process=0 alerts=process_missing`。

原因：

- 原脚本只有全量 stop/start 和只读 monitor，没有“按批 stop/start、每批等待、每批检查”的操作模式。
- 需要跳过已加载新版 runner 且心跳新鲜的 canary，否则重复重启会增加无意义扰动。
- `print_status()` 需要运行时健康计数；单纯的 `run_units()` 返回值只包含 DB/start 状态，不包含 `/proc` 进程、heartbeat、日志体量和资源指标。

修复：

- `run_dual_exchange_simulation.py` 新增 `--rolling-restart`、`--rolling-batch-size`、`--rolling-batch-wait-seconds`、`--skip-fresh-heartbeats`。
- 新增 `unit_heartbeat_state()`、`filter_units_for_rolling_restart()`、`chunked_units()`、`restart_target_batch()`、`rolling_restart_targets()`，支持按目标和单元过滤分批滚动重启。
- 每个 batch stop/start 后按 `target_keys=(key,)` 只打印当前目标的 health check，避免单目标滚动时输出另一个工作区的噪声。
- start/rolling 完成后的 `started` / `rolling restarted` 汇总改为重新调用 `status_summary()`，保证输出包含真实 `process/heartbeat/stale/alerts`，不再把纯 start counter 当作健康状态。

验收：

- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `26 passed`。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k LiveExecutionService`，结果 `8 passed, 1 skipped, 105 deselected`。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `46 passed, 1 warning`。
- CTP02 现场滚动重启命令：`setsid /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --unit-ids 92524351-3681-4495-8663-e9cc29f091bb --rolling-restart --rolling-batch-size 1 --rolling-batch-wait-seconds 35 --skip-fresh-heartbeats --hold-seconds 604800 --status-interval 30 > reports/ctp02_rolling_supervisor.log 2>&1 &`，实际 supervisor PID `369784`。
- CTP02 子进程 PID `369914` 当前由 PID `369784` 持有，`reports/ctp02_rolling_supervisor.log` 持续输出 `running=1 process=1 heartbeat=1 stale=0 no_log=0 alerts=-`。
- 补丁后的 no-op 验证：对 CTP02 再执行 `--rolling-restart --skip-fresh-heartbeats --no-hold` 时，脚本输出 `rolling restart: no units selected`，并正确输出 `rolling restarted: ... process=1 heartbeat=1 stale=0 alerts=-` 后退出。
- 剩余 CTP 现场滚动重启命令：`setsid /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --rolling-restart --rolling-batch-size 4 --rolling-batch-wait-seconds 35 --skip-fresh-heartbeats --hold-seconds 604800 --status-interval 30 > reports/ctp_remaining_rolling_supervisor.log 2>&1 &`，实际 supervisor PID `379969`。
- `reports/ctp_remaining_rolling_supervisor.log` 完成 `rolling batch 1/12` 到 `rolling batch 12/12`，每批均为 `running=4 failed=0 process=4 heartbeat=4 stale=0 alerts=-`；最终 `rolling restarted` 为 CTP `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。
- MT5 现场滚动重启命令：`setsid /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets mt5 --rolling-restart --rolling-batch-size 4 --rolling-batch-wait-seconds 35 --skip-fresh-heartbeats --hold-seconds 604800 --status-interval 30 > reports/mt5_remaining_rolling_supervisor.log 2>&1 &`，实际 supervisor PID `388891`。
- `reports/mt5_remaining_rolling_supervisor.log` 完成 `rolling batch 1/13` 到 `rolling batch 13/13`，前 12 批为 `running=4 failed=0 process=4 heartbeat=4 stale=0 alerts=-`，最后一批为 `running=2 failed=0 process=2 heartbeat=2 stale=0 alerts=-`；最终 `rolling restarted` 为 MT5 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。
- 全局长期 monitor 已从 CTP `heartbeat=1 stale=49`、MT5 `heartbeat=0 stale=50` 逐步变为双目标 `heartbeat=50 stale=0 alerts=-`。

### 50. 压测 start/rolling supervisor 日志仍写入默认 admin 密码 warning

现象：`--monitor-only` 早前已经过滤默认 admin 密码 `UserWarning`，但本轮 CTP/MT5 持有型 rolling supervisor 日志开头仍出现 `Insecure default admin password detected. Change ADMIN_PASSWORD before shared or production use.`。这条 warning 不是策略或网关错误，却会进入 `reports/ctp_remaining_rolling_supervisor.log`、`reports/mt5_remaining_rolling_supervisor.log`，影响长期日志异常筛查。

原因：`run_dual_exchange_simulation.py` 顶部只在 `--monitor-only` 时安装 warning filter；start/rolling 模式同样只是压测运维脚本，不运行 Web 服务，但导入后端配置时仍会触发默认 admin warning。

修复：

- 将过滤函数改为 `_suppress_default_admin_warning_for_stress_script()`，对该压测脚本所有模式生效。
- 过滤规则仍只匹配默认 admin 密码这条精确 `UserWarning`；普通 `UserWarning` 仍会显示，避免吞掉真实运维告警。
- 更新回归测试：覆盖压测脚本全模式抑制默认 admin warning，以及 unrelated warning 不被抑制。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `26 passed`。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `46 passed, 1 warning`。
- no-op rolling 验证：`python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --rolling-restart --rolling-batch-size 1 --rolling-batch-wait-seconds 0 --skip-fresh-heartbeats --no-hold 2>&1 | head -n 5`，输出以 `期货模拟工作区 target prefix` 开头，不再包含默认 admin 密码 warning。
- 修复后 direct monitor 仍稳定：CTP/MT5 均为 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。

### 51. store/gateway 运行事件写入无时区 UTC event_time

现象：抽样检查当前 CTP/MT5 压测单元的 `logs/system.log` 时，`store_connecting`、`store_connected` 等运行事件的 `log_time` 是带 `+08:00` 的本地时间，但 `event_time` 是无时区 UTC 字符串，例如：

- `log_time=2026-06-25T03:24:19.970+08:00`
- `event_time=2026-06-24T19:24:18.843`

这不是交易中断，但会污染审计时间线。无时区 ISO 字符串被不同消费者按本地时间或 UTC 解释时，会产生 8 小时偏移；按 `event_time` 聚合生命周期事件时也会和 `log_time` 混用出错。

原因：

- `BtApiStore.emit_runtime_event()` 用 `datetime.now(timezone.utc).replace(tzinfo=None).isoformat(...)` 生成 UTC 时间，刻意去掉了 `+00:00`。
- `TradeLogger._base_event()` 对显式传入的字符串 `event_time` 原样落盘，因此继承了上游无时区格式。

修复：

- `/home/yun/Documents/backtrader/backtrader/stores/btapistore.py`：`emit_runtime_event()` 直接输出带 `+00:00` 的 UTC ISO 字符串。
- `/home/yun/Documents/backtrader/backtrader/observers/trade_logger.py`：新增 `_event_time_str()`，对 datetime、epoch 数字、`Z` 后缀和遗留无时区 ISO 字符串统一落成带 offset 的 ISO 时间；无效字符串仍原样保留，避免吞掉异常来源信息。
- 更新单元和集成测试，锁定 store runtime timestamp 为 UTC aware，且 `system.log` 中的 `store_connected.event_time` 可解析出 UTC offset。

验收：

- `python -m py_compile backtrader/stores/btapistore.py backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py tests/unit/stores/test_btapistore_notifications.py tests/integration/test_trade_logger_runtime.py` 通过。
- `python -m pytest tests/unit/observers/test_trade_logger_edge_cases.py -q tests/unit/stores/test_btapistore_notifications.py -q tests/integration/test_trade_logger_runtime.py -q`，结果 `47 passed`。
- `python -m pytest tests/unit/stores/test_btapistore.py -q`，结果 `90 passed, 1 skipped`。
- 直接样例输出：`store_connecting 2026-06-24T19:52:48.229+00:00`。
- 现有 100 个长跑子进程没有重启，旧 `system.log` 不会回写；下一次新启动或滚动重启后再抽样确认 `store_connected.event_time` 带 `+00:00`。

### 52. CTP gateway 原生 stderr 污染 supervisor 日志

现象：CTP canary/rolling supervisor 日志在首次 acquire gateway 后出现以下原生输出：

- `WARNING: you should run this program as super-user.`
- `WARNING: output may be incomplete or inaccurate, you should run this program as super-user.`
- `/sys/firmware/dmi/tables/smbios_entry_point: Permission denied`
- `Can't read memory from /dev/mem`

这些行不是策略错误，也不会进入单元 `logs/error.log`，但它们落在 `reports/ctp*_supervisor.log` 后，会干扰 `WARNING|ERROR|Traceback` 异常检索。精确搜索 Python 源码和 site-packages 未找到这些字符串，判断为 CTP 原生库在硬件指纹/授权探测时直接写进当前进程 stderr。

原因：当前 CTP/MT5 gateway runtime 是 in-process thread，不是单独 `Popen`。策略子进程已有 `subprocess.stdout.log` / `subprocess.stderr.log` 隔离，但 gateway 原生库与 supervisor 共用进程 fd 1/2，因此原生 stderr 会直接污染 supervisor 日志。

修复：

- `src/backend/app/services/gateway/runtime.py` 新增 `_redirect_gateway_native_stdio()`，在 gateway `start_in_thread()` 和 `wait_gateway_runtime_ready()` 的短窗口内临时把 fd 1/2 重定向到当前策略单元 `logs/gateway.stdout.log`、`logs/gateway.stderr.log`。
- 使用全局 `RLock` 支持同线程嵌套重定向；异常路径会恢复已替换的 fd，避免测试或生产环境出现半重定向。
- 保留正常 `Gateway acquire ...` Python 日志在 supervisor 中输出，只隔离原生启动/ready 探测噪声。

验收：

- `python -m py_compile src/backend/app/services/gateway/runtime.py src/backend/tests/test_extracted_modules.py` 通过。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k GatewayRuntimeService`，结果 `12 passed, 104 deselected`。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k "LiveExecutionService or GatewayRuntimeService"`，结果 `20 passed, 1 skipped, 95 deselected`。
- `python -m pytest src/backend/tests/test_live_trading_manager.py -q`，结果 `66 passed`。
- 当前 100 个长跑子进程没有重启；下一次 CTP gateway 新启动或滚动重启后，再抽样确认 `reports/ctp*_supervisor.log` 不再出现上述原生 warning，相关内容进入对应单元 `logs/gateway.stderr.log`。

### 53. ensure_dual_stress_running status 不认识拆分 supervisor

现象：当前 100 个策略子进程已经由四个持有型 supervisor 管理，但 `TARGETS=futures,mt5 scripts/ops/ensure_dual_stress_running.sh status` 只输出 `dual stress supervisor not running` 和 monitor PID。这会让运维人员误以为没有 supervisor 持有策略子进程，尤其是在主 dual supervisor 被拆分为 canary/rolling supervisor 后。

原因：脚本原先只维护一个 `DUAL_STRESS_PID_FILE`，并且发现 supervisor 时要求命令行完全匹配 `--targets ${TARGETS}`。当前现场 supervisor 分别是 `--targets futures`、`--targets mt5`，部分还带 `--unit-ids` 或 `--rolling-restart`，因此不会被旧 status 识别。

修复：

- `scripts/ops/ensure_dual_stress_running.sh` 新增 `find_existing_supervisor_processes()`，从 `/proc` 中发现所有非 `--monitor-only`、非 `--no-hold` 的 `run_dual_exchange_simulation.py` 长驻进程。
- 新增 `status_split_supervisors()`，优先读取 `.pids/*supervisor.pid`，再补充 `/proc` 发现结果并去重。
- `start` 默认检测到任意拆分 supervisor 存活时直接复用并退出，避免在四个持有型 supervisor 已经接管 100 个子进程后再启动一个新的 dual supervisor；如确需并行启动，可显式设置 `NO_START_IF_SPLIT_SUPERVISOR=0`。
- 保留旧的 `dual stress supervisor` 输出和 `restart` 行为，不自动 stop 当前拆分 supervisor，避免误杀正在持有子进程的长跑 supervisor。

验收：

- `bash -n scripts/ops/ensure_dual_stress_running.sh` 通过。
- `python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `5 passed`。
- 真实 `start` 保护验证：`TARGETS=futures,mt5 PYTHON_BIN=/bin/false scripts/ops/ensure_dual_stress_running.sh start` 输出 `split stress supervisor already running: pid=347458; not starting dual stress supervisor`，未启动新进程。
- 真实 status 输出已列出：
  - `split stress supervisor running: pid=347458 file=ctp01_canary_supervisor.pid`
  - `split stress supervisor running: pid=369784 file=ctp02_rolling_supervisor.pid`
  - `split stress supervisor running: pid=379969 file=ctp_remaining_rolling_supervisor.pid`
  - `split stress supervisor running: pid=388891 file=mt5_remaining_rolling_supervisor.pid`
  - `dual stress monitor running: pid=307323`
- 同次 direct monitor 仍为双目标 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。

### 54. 后端 API 进程缺失导致组合接口不可用

现象：压测策略和四个 supervisor 均健康，但 `.pids/backend.pid` 指向的进程已不存在，端口 8000/8080 均无 uvicorn 监听。前端 5173 仍返回 200，但组合 API 无法访问。

处理：

- 没有调用 `stop_app.sh`，避免误停当前前端或影响 100 个压测子进程。
- 手动只启动后端 uvicorn，并刷新 `.pids/backend.pid`。
- 后续在异常日志、安全头、aiomysql 降噪、call_logger 脱敏和历史日志清洗后，再次只重启后端，当前后端 PID 为 `470775`。

验收：

- `GET /` 返回 200。
- 未认证 `GET /api/v1/portfolio/overview` 返回 401。
- 认证后组合 API 返回：
  - overview `strategy_count=100 running_count=100 total_assets=50499419.39 total_pnl=-580.61`
  - positions `total=100`
  - equity 200
  - allocation 200
- 后端重启前后真实策略子进程仍为 100 个，四个拆分 supervisor 与 monitor PID 未变化。

### 55. HTTPException 日志格式、request_id 关联和 X-Powered-By 暴露

现象：后端恢复后的未认证探针在 `logs/backend.log` 中输出：

- `ERROR | app.middleware.exception_handling:handle_http_exception | HTTP exception: %s - %s`
- 同一请求的 request middleware 日志与 exception handler 日志使用不同 request_id。
- 安全头测试显示 DEBUG 下响应会带 `X-Powered-By: AI for Trader`。

原因：

- `app.middleware.exception_handling` 使用 loguru logger，但仍按 stdlib logging 方式传 `%s` 参数，因此占位符不会展开。
- `LoggingMiddleware.__call__()` 只把 request_id 写到响应头，没有写入 `scope["state"]`；FastAPI exception handler 读取不到时会重新生成 request_id。
- `SecurityHeadersMiddleware` 在 DEBUG 下主动追加 `X-Powered-By`，与安全头测试和“不暴露服务实现信息”的目标冲突。

修复：

- `src/backend/app/middleware/exception_handling.py`：新增 request-scoped logger 绑定；validation、application、HTTP 和 generic exception 日志均使用 loguru `{}` 格式；HTTP 4xx 记 WARNING，HTTP 5xx 仍记 ERROR。
- `src/backend/app/middleware/logging.py`：`dispatch()` 和 ASGI `__call__()` 均把同一个 request_id 写入 request/scope state，使异常日志、请求日志和响应头可关联。
- `src/backend/app/middleware/security_headers.py`：移除 DEBUG 下的 `X-Powered-By` 响应头。

验收：

- `python -m py_compile src/backend/app/middleware/exception_handling.py src/backend/app/middleware/security_headers.py src/backend/app/middleware/logging.py src/backend/tests/test_middleware.py src/backend/tests/test_logging_middleware.py` 通过。
- `python -m pytest src/backend/tests/test_middleware.py -q`，结果 `20 passed, 6 warnings`。
- `python -m pytest src/backend/tests/test_logging_middleware.py -q`，结果 `7 passed`。
- `python -m pytest src/backend/tests/test_middleware.py src/backend/tests/test_logging_middleware.py -q`，结果 `27 passed, 6 warnings`。
- `python -m pytest src/backend/tests/test_security.py -q`，结果 `33 passed, 13 warnings`。
- 真实未认证请求返回 401，响应头 `X-Request-ID=311b944b`，日志同时出现：
  - `Request started: GET /api/v1/portfolio/overview` request_id `311b944b`
  - `WARNING ... HTTP exception: 401 - Not authenticated` request_id `311b944b`
  - `Request completed: GET /api/v1/portfolio/overview -> 401` request_id `311b944b`
- 真实 `GET /` 响应头中 `X-Powered-By` 为 absent。

### 56. aiomysql DEBUG 认证日志污染后端日志

现象：后端每次启动、登录或组合 API 查询都会输出多条：

- `DEBUG | aiomysql.connection:caching_sha2_password_auth | caching sha2: succeeded by fast path.`

这些行不是业务错误，但在 DEBUG 环境下会把后端日志中的真正业务事件冲淡；此前项目已经对 `aiosqlite`、`asyncio`、`faker`、`slowapi` 做了第三方 logger 降噪。

修复：

- `src/backend/app/utils/logger.py` 的 `_NOISY_THIRD_PARTY_LOGGERS` 增加 `aiomysql` 和 `aiomysql.connection`，统一降到 WARNING。
- `src/backend/tests/test_enhanced_logger.py` 扩展现有第三方降噪测试，锁定 `aiomysql.connection` 不再启用 DEBUG/INFO。

验收：

- `python -m py_compile src/backend/app/utils/logger.py src/backend/tests/test_enhanced_logger.py` 通过。
- `python -m pytest src/backend/tests/test_enhanced_logger.py -q`，结果 `23 passed, 3 skipped`。
- 后端重启到 PID `465990` 后，登录和组合接口均返回 200。
- 从 `Started server process [465990]` 起过滤 `logs/backend.log`，`rg 'aiomysql|caching sha2'` 无匹配。

### 57. call_logger 泄漏登录密码和 JWT token

现象：真实登录探针在 `logs/backend.log` 中出现敏感内容：登录参数里包含默认管理员密码字段，登录返回摘要里包含 JWT access token 字段。

原因：`app.utils.call_logger` 只按顶层参数名过滤敏感字段。`user_login` 本身不是敏感参数名，因此 Pydantic `UserLogin.__repr__()` 会把内部 `password` 写入日志；返回值 `Token` 也直接按 repr 截断，导致 JWT 前缀进入日志。

修复：

- `src/backend/app/utils/call_logger.py` 新增 `_sanitize_for_log()`，递归处理 dict/list/tuple/set 和 Pydantic `model_dump()`，对 `password`、`token`、`secret`、`api_key`、`authorization`、`credential` 等字段统一写 `***`。
- 调用参数摘要省略 `self`/`cls`，避免 bound method 对象 repr 污染日志。
- `src/backend/tests/test_audit_and_logging.py` 增加 Pydantic 参数/返回值脱敏、嵌套 mapping 脱敏和 `self` 省略测试。

验收：

- `python -m py_compile src/backend/app/utils/call_logger.py src/backend/tests/test_audit_and_logging.py` 通过。
- `python -m pytest src/backend/tests/test_audit_and_logging.py -q -k CallLogger`，结果 `12 passed, 23 deselected`。
- `python -m pytest src/backend/tests/test_audit_and_logging.py -q`，结果 `35 passed, 6 warnings`。
- 后端重启到 PID `465990` 后，真实登录和 overview 均返回 200。
- 从 `Started server process [465990]` 起过滤 `logs/backend.log`，明文默认管理员密码、`self` 对象 repr、JWT 前缀和 `caching sha2` 均无匹配。
- 同段真实日志显示：
  - `CALL ... AuthService.login args={'user_login': {'username': 'admin', 'password': '***'}}`
  - `OK ... AuthService.login ... result={'access_token': '***', 'token_type': '***', 'expires_in': 604800}`

### 58. 修复前 backend.log 中已落盘的敏感片段仍需清洗

现象：`call_logger` 脱敏修复上线后，新日志不再写明文密码和 JWT，但 `logs/backend.log` 中仍保留修复前的密码字段和 access token 字段。这意味着即使代码已修复，当前工作目录的主后端日志仍然含有敏感信息。

处理：

- 对 `logs/backend.log` 做机械脱敏，替换历史密码字段、access token 字段和默认管理员密码字符串。
- 清洗后发现运行中的 uvicorn 可能仍持有旧文件描述符，因此只重启后端一次，让 PID `470775` 重新打开当前已清洗的 `logs/backend.log`。
- 后续复扫发现当前实际 Loguru sink 文件 `src/backend/logs/app_2026-06-25.log` 和旧 `logs/backend_runtime.log` 也保留了同类修复前敏感片段；已短停后端，机械脱敏这两个文件，再按原后端工作目录和命令重启 uvicorn 到 PID `505420`。

验收：

- 明文默认管理员密码、JWT 前缀、bearer token、旧 MT5 明文值复扫均无真实匹配；zip 归档内同样无这些敏感模式匹配。
- 触发 `GET /` 后，当前 `logs/backend.log` 尾部出现 04:28 后的新请求日志，证明后端正在写入当前文件。
- 认证后组合 API 仍返回 overview 200、`strategy_count=100 running_count=100`，positions 200、`total=100`。
- 策略子进程仍为 100 个，长期 monitor PID `307323` 不变。

### 59. MT5/CTP 压测配置和 live instance JSON 落盘明文密码

现象：继续扫描运行态配置时发现，当前 MT5 压测工作区 50 个活动 `config.yaml` 在 `gateway.password` 和 `mt5.password` 中保留了真实 MT5 密码；`src/backend/data/live_trading_instances.json` 的实例参数中也保留同一密码副本。进一步检查发现 5 个独立 `strategies/simulate/mt5_*` 模板配置也写入了真实 MT5 密码。

原因：

- `seed_simulated_workspaces.py` 会把手动网关或 settings 中的 CTP/MT5 密码写进 `gateway_config`。
- `workspace_unit_runtime._apply_gateway_runtime_config()` 会把 `gateway_config.params` 原样合并到每个 runtime `config.yaml`。
- `gateway_dual_ma`、`gateway_boll_breakout` 与独立 MT5 runner 对 MT5 密码的读取顺序是配置文件优先，导致后续即使 `.env` 中有凭据，也会继续依赖落盘明文。
- `build_mt5_gateway_runtime_kwargs()` 和 CTP 密码解析同样允许旧 `gateway_params.password` 覆盖环境值。

修复：

- `src/backend/scripts/seed_simulated_workspaces.py`：新生成的 CTP/MT5 gateway config 不再写 `password` 字段，账号、front、ws_uri 等非敏感连接字段保持不变。
- `src/backend/app/services/gateway/launch_builder.py`：CTP/MT5 运行时参数改为优先使用环境/.env 凭据；MT5 同时保留 `MT5_PASS` legacy alias。
- `src/backend/app/services/workspace_unit_runtime.py`：合并 gateway runtime config 前递归剥离 `password`、token、API key、secret、authorization、passphrase 等敏感键，防止 UI/数据库里已有的敏感字段被复制到每个 runtime 目录。
- `strategies/simulate/gateway_dual_ma/run.py`、`strategies/simulate/gateway_boll_breakout/run.py` 和 5 个 `strategies/simulate/mt5_*` runner：MT5 连接配置优先读取 `MT5_LOGIN`、`MT5_ACCOUNT`、`MT5_PASSWORD`、`MT5_PASS`、`MT5_WS_URI` 等环境变量，再回退配置文件。
- 5 个独立 MT5 模板 `config.yaml` 的 `mt5.password` 已清空。
- 已清空当前 MT5 活动 workspace 50 个 runtime `config.yaml` 和 `src/backend/data/live_trading_instances.json` 中已经落盘的旧明文密码副本。清理前确认 repo `.env` 中存在 CTP/MT5 必需凭据，后续重启仍可由 `load_strategy_env()` 读取。

验收：

- `python -m py_compile` 覆盖 seed、gateway launch、workspace runtime、两个 gateway runner、5 个独立 MT5 runner 和相关测试文件，结果通过。
- `python -m pytest src/backend/tests/test_seed_simulated_workspaces.py src/backend/tests/test_gateway_preset_and_launch.py src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `97 passed, 1 warning`。
- `python -m json.tool src/backend/data/live_trading_instances.json` 通过；两个活动压测目录共 100 个 `config.yaml` 均可被 `yaml.safe_load()` 解析。
- 对旧 MT5 明文密码值、MT5 模板旧密码值、历史 admin/JWT 模式复扫，`strategies/simulate`、`workspace_units`、`logs/backend.log`、`src/backend/data/live_trading_instances.json` 均无匹配。
- 对两个活动压测目录、MT5 模板和 live instance JSON 扫描非空 `password` 字段无匹配；更宽的敏感字段扫描仅剩 CTP 默认 `auth_code=0000000000000000` 占位值。
- 清理运行态文件后策略子进程仍为 100 个；direct monitor 显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。
- 认证后 `/api/v1/portfolio/overview` 返回 200，`strategy_count=100 running_count=100 total_assets=50499466.28 total_pnl=-533.72`；`/api/v1/portfolio/positions` 返回 200，`total=100`。

### 60. 根应用日志遗留大文件没有启动归档，单日文件缺少大小上限

现象：根 `logs/` 目录达到约 `3.6G`。其中 `logs/app_2026-06-22.log` 单文件约 `3.4G`，`logs/app_2026-06-24.log` 约 `128M`，而 `logs/app_2026-06-23.log.zip` 已经正常压缩。抽样显示 6 月 22 日和 6 月 24 日的大文件主要是旧 DEBUG 噪声，包含大量 `faker.factory`、`aiosqlite.core`、`asyncio.selector_events` 行。

原因：

- `setup_logger()` 原本只配置 Loguru `rotation="00:00"` 和 `compression="zip"`。Loguru 只有在运行中的 sink 触发后续 rotation 时才会压缩旧文件；如果某天进程退出或重启后没有再触发对应文件的 rotation，遗留 `app_YYYY-MM-DD.log` 会一直原样保留。
- 单个日期日志没有大小上限；即使前面已经修复第三方 DEBUG 降噪，未来某个业务 DEBUG 风暴仍可能在同一天内把 `app_YYYY-MM-DD.log` 写到数百 MB 或 GB。

修复：

- `src/backend/app/utils/logger.py` 新增启动期遗留归档：`setup_logger()` 在注册新 sink 前会压缩非当天、非空、且最近 60 秒没有写入的 `app/errors/audit/backtest_YYYY-MM-DD.log`，跳过当前日志、非日期日志和可能仍活跃的文件。
- `src/backend/app/utils/logger.py` 新增组合 rotation 条件：日志跨天或预计写入后超过配置大小时都会触发 Loguru rotation，继续使用 zip 压缩和既有 retention。
- `src/backend/app/config.py` 新增 `LOG_ROTATION_MAX_MB`，默认 `100`，设为 `0` 可关闭大小上限。
- 使用新归档函数清理当前历史文件：`logs/app_2026-06-22.log` 归档为约 `108M` zip，`logs/app_2026-06-24.log` 归档为约 `4M` zip，`logs/` 总体从约 `3.6G` 降为 `110M`；当前后端实际 Loguru sink 目录 `src/backend/logs/` 的旧 `app/errors/audit_YYYY-MM-DD.log` 也已归档，目录约 `320K`。
- 只针对 uvicorn 做短重启，使用原后端工作目录 `src/backend` 和原启动命令，stdout/stderr 继续追加到根 `logs/backend.log`；新 PID 为 `496706`，未触碰前端和 CTP/MT5 压测 supervisor。

验收：

- `python -m py_compile src/backend/app/utils/logger.py src/backend/app/config.py src/backend/tests/test_enhanced_logger.py src/backend/tests/test_audit_and_logging.py` 通过。
- `python -m pytest src/backend/tests/test_enhanced_logger.py src/backend/tests/test_audit_and_logging.py -q`，结果 `64 passed, 3 skipped, 6 warnings`。
- `git diff --check -- src/backend/app/utils/logger.py src/backend/app/config.py src/backend/tests/test_enhanced_logger.py src/backend/tests/test_audit_and_logging.py` 无输出。
- `du -sh logs src/backend/logs` 当前为根 `logs=110M`、`src/backend/logs=320K`；两个目录的历史日期日志已变为 zip，当前 `src/backend/logs/app_2026-06-25.log` 约 `45K`。
- 策略子进程仍为 100 个；长期监控最新 tail 显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。
- 后端重启后 `GET /` 返回 200；认证后 `/api/v1/portfolio/overview` 返回 200，`strategy_count=100 running_count=100 total_assets=50500312.95 total_pnl=312.95`；`/api/v1/portfolio/positions` 返回 200，持仓数 `100`。

### 61. pytest 预期异常写入真实应用日志，污染压测异常扫描

现象：继续扫描当前 `logs/` 时，根 `logs/errors_2026-06-25.log` 和 `logs/app_2026-06-25.log` 中出现大量测试用例预期异常，包括测试 RuntimeError、模拟磁盘错误、测试 request id 和测试失败函数名等特征。这些不是运行中的后端或策略错误，但普通异常扫描会把它们和真实压测故障混在一起。

原因：`src/backend/tests/conftest.py` 在导入 `app.main` 前设置了测试数据库和默认密码，但没有设置 `LOG_DIR`。因此 `app.main` 导入时执行 `setup_logger()`，会把 pytest 期间触发的预期异常写入仓库真实日志目录。后续即使测试通过，长期压测巡检仍会在根 `logs/*.log` 中看到测试异常残留。

修复：

- `src/backend/tests/conftest.py` 在任何 `app.*` 导入之前创建 `/tmp/backtrader_web_pytest_logs_*`，并无条件设置 `LOG_DIR` 指向该目录。
- `src/backend/tests/test_enhanced_logger.py` 新增回归测试，确认 pytest 会话中的 `get_settings().LOG_DIR` 不等于仓库根 `logs/`，且目录名带 `backtrader_web_pytest_logs_` 前缀。
- 已将根目录中被测试污染的 `logs/errors_2026-06-25.log`、`logs/app_2026-06-25.log`、`logs/audit_2026-06-25.log` 压缩归档为 `*.pytest-polluted-*.zip`，保留内容但移出常规 `.log` 异常扫描。

验收：

- `python -m py_compile src/backend/tests/conftest.py src/backend/tests/test_enhanced_logger.py` 通过。
- `python -m pytest src/backend/tests/test_enhanced_logger.py src/backend/tests/test_audit_and_logging.py -q`，结果 `64 passed, 3 skipped, 6 warnings`。
- 跑测试前后，根 `logs/errors_2026-06-25.log` 中四类测试特征计数没有增加。
- 归档历史污染日志后，当前 `logs/*.log` 与 `src/backend/logs/*.log` 中四类测试特征命中数均为 0。
- 当前活动 CTP/MT5 两个压测目录的 100 个 `logs/error.log`、`logs/subprocess.stderr.log`、`logs/gateway.stderr.log` 均无非空文件；100 个 `heartbeat.json` 均存在。
- 最新长期监控仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 alerts=-`；认证后组合 API 为 `strategy_count=100 running_count=100 positions_total=100`。

### 62. 策略子进程未继承本地 backtrader 源码路径

现象：继续抽样当前 CTP/MT5 的 `logs/system.log`，发现 `data_status`、`session_started` 已是带时区时间，但 store 生命周期事件仍有大量无时区 `event_time`。当前活动 CTP/MT5 目录各有 `system_events=400 bad_tz=300`，问题集中在 `store_connecting`、`store_connected`、`store_ready`、`store_auth_success`、`store_login_success`、`market_data_subscribe_request` 等事件。

原因：

- `/home/yun/Documents/backtrader` 中的 `TradeLogger._event_time_str()` 与 store runtime timestamp 修复已经存在并有测试覆盖。
- 当前长跑策略子进程的 `/proc/<pid>/environ` 显示 `PYTHONPATH=/home/yun/Documents/bt_api_py/bt_api_py`，没有 `/home/yun/Documents/backtrader`。
- `src/backend/app/services/live_trading/service.py` 只把本地 `backtrader` 插入后端主进程 `sys.path`；`LiveTradingManager._build_subprocess_env()` 传给策略子进程的环境此前只追加 `_BT_API_PY_DIR`。因此新启动策略可能继续加载环境里的 installed `backtrader`，而不是本地源码树。

修复：

- `src/backend/app/services/gateway/runtime.py` 新增 `_prepend_python_paths()`，构建策略子进程环境时按 `backtrader -> bt_api_py -> existing PYTHONPATH` 顺序合并路径，并跳过不存在路径和重复项。
- `build_subprocess_env()` 新增可选 `backtrader_dir` 参数，保持旧调用兼容。
- `src/backend/app/services/live_trading/manager.py` 新增 `_BACKTRADER_DIR`，优先使用项目同级 `/home/yun/Documents/backtrader`，不存在时回退到 `~/Documents/backtrader`，并传给 gateway runtime env builder。
- `src/backend/tests/test_extracted_modules.py` 和 `src/backend/tests/test_live_trading_manager.py` 增加回归测试，锁定路径顺序、去重和 manager 参数传递。

验收：

- `python -m py_compile src/backend/app/services/gateway/runtime.py src/backend/app/services/live_trading/manager.py src/backend/tests/test_extracted_modules.py src/backend/tests/test_live_trading_manager.py` 通过。
- `python -m pytest src/backend/tests/test_extracted_modules.py::TestGatewayRuntimeService src/backend/tests/test_live_trading_manager.py::TestGatewayLifecycle::test_build_subprocess_env_prefers_local_source_paths src/backend/tests/test_live_trading_manager.py::TestGatewayLifecycle::test_build_subprocess_env_with_gateway -q`，结果 `15 passed`。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k GatewayRuntimeService`，结果 `13 passed, 104 deselected`。
- `python -m pytest src/backend/tests/test_live_trading_manager.py -q -k "build_subprocess_env"`，结果 `3 passed, 64 deselected`。
- `git diff --check -- src/backend/app/services/gateway/runtime.py src/backend/app/services/live_trading/manager.py src/backend/tests/test_extracted_modules.py src/backend/tests/test_live_trading_manager.py` 无输出。
- 已只重启 uvicorn 后端从 PID `505420` 到 PID `521327`，使后续 Web/API 侧启动路径加载本轮修复；`.pids/backend.pid` 已修正为实际 uvicorn PID，`GET /` 返回 `200`。
- 当前未重启 100 个长跑策略子进程，样本 PID `347600`、`369914` 的 `PYTHONPATH` 仍只有 `/home/yun/Documents/bt_api_py/bt_api_py`，符合“现有进程不热更新环境变量”的预期。下一次新启动或滚动重启后，再复验子进程 `PYTHONPATH` 与 `system.log` 中 store 事件时间戳。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold` 当前仍为 CTP/MT5 双目标 `running=50 process=50 heartbeat=50 stale=0 alerts=-`；认证后组合 API 为 `strategy_count=100 running_count=100 positions_total=100 trades_total=1452`。

### 63. TradeLogger 市场数据日志仍写无时区 datetime

现象：继续扫描当前 CTP/MT5 活动压测目录，发现 `bar.log`、`value.log`、`position.log` 的 `datetime` 字段仍是 `2026-06-23 03:31:00` 这类无 offset 字符串；`bar.log` 中部分网关 bar 事件还把 `local_time` 写成 epoch 浮点数。当前旧进程累计命中：

- CTP：`bar.log total=13086 datetime_bad=13086 local_time_bad=6543`，`value.log total=6543 datetime_bad=6543`，`position.log total=6543 datetime_bad=6543`。
- MT5：`bar.log total=21006 datetime_bad=21006 local_time_bad=5503`，`value.log total=15503 datetime_bad=15503`，`position.log total=15503 datetime_bad=15503`。

原因：

- `TradeLogger._get_datetime_str()` 直接返回 `str(self._owner.datetime.datetime())`，backtrader 内部时间通常是 naive datetime，落盘后无法判断 UTC/本地时区。
- `notify_bar_event()` / `notify_tick_event()` 原样写入 gateway/feed 事件字段；对象里的 `datetime`、`time`、`local_time` 没有日志层归一化。
- `timestamp` epoch 数字仍是有用的机器字段，不能为了解决展示歧义直接改成字符串。

修复：

- `/home/yun/Documents/backtrader/backtrader/observers/trade_logger.py` 的 `_get_datetime_str()` 改为通过 `_event_time_str()` 输出带显式 offset 的 ISO 字符串；读取策略时间失败时回退到带 `+08:00` 的 wall-clock `log_time`。
- 新增 `_normalize_event_time_fields()`，在 tick/bar 日志写出前归一化 `datetime`、`time`、`local_time`；保留 `timestamp` 原数值，避免破坏 epoch 排序和延迟计算消费者。
- `tests/unit/observers/test_trade_logger_edge_cases.py` 增加 naive strategy datetime、bar `datetime/local_time` 归一化与 `timestamp` 保持数值的回归测试。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py tests/integration/test_trade_logger_runtime.py` 通过。
- `/home/yun/anaconda3/bin/python -m pytest tests/unit/observers/test_trade_logger_edge_cases.py -q`，结果 `26 passed`。
- `/home/yun/anaconda3/bin/python -m pytest tests/integration/test_trade_logger_runtime.py -q`，结果 `8 passed`。
- `/home/yun/anaconda3/bin/python -m pytest tests/integration/test_trade_logger.py tests/unit/observers/test_trade_logger_internal_errors.py -q`，结果 `17 passed`。
- `git diff --check -- backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py tests/integration/test_trade_logger_runtime.py` 无输出。
- 当前 100 个长跑策略子进程仍未重启，旧日志继续存在无时区字段是预期状态；下一次新启动或滚动重启后，应抽样确认新 `bar.log`、`value.log`、`position.log` 的 `datetime` 均带 offset，且 `bar.log.local_time` 为 ISO offset 字符串。

### 64. 组合权益曲线把分钟级 live value.log 压缩成日级 3 点

现象：认证后抽样 `/api/v1/portfolio/equity`，当前 100 个长跑策略已经持续写入分钟级 `value.log`，但接口只返回 `dates=3`，即 `2026-06-23` 到 `2026-06-25` 三个日级点。前端权益/回撤图因此看不到日内权益变化，只能显示每天一个聚合点。

原因：

- `parse_value_log()` 对所有 `dt/datetime/event_time/log_time` 都调用 `_normalize_date_text()`，只保留日期部分。
- `/api/v1/portfolio/equity` 直接使用 `value_data["dates"]` 对齐各策略权益曲线；当所有分钟级 bar 被截成同一天，`date_map[dt]` 会不断覆盖，只剩每天最后一个点。
- 旧 backtest 解析依赖日级 `dates`，不能直接把 `dates` 改成完整 datetime，否则会影响既有报表和测试语义。

修复：

- `src/backend/app/services/log_parser_service.py` 的 `parse_value_log()` 保留兼容字段 `dates`，同时新增 `datetimes`，保存完整原始时间文本。
- `src/backend/app/api/portfolio/api.py` 的 `get_portfolio_equity()` 改为优先使用 `value_data["datetimes"]`，不存在时回退到旧 `dates`。
- `src/backend/tests/test_log_parser.py` 增加 `datetimes` 断言，确保旧 `dates` 仍为日级。
- `src/backend/tests/test_portfolio_api.py` 增加 `test_portfolio_equity_prefers_intraday_datetimes`，锁定 live 日内时间轴不会被压缩。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/log_parser_service.py src/backend/app/api/portfolio/api.py src/backend/tests/test_log_parser.py src/backend/tests/test_portfolio_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_log_parser.py src/backend/tests/test_log_parser_extended.py -q`，结果 `48 passed`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `26 passed`。
- `git diff --check -- src/backend/app/services/log_parser_service.py src/backend/app/api/portfolio/api.py src/backend/tests/test_log_parser.py src/backend/tests/test_portfolio_api.py` 无输出。
- 已仅重启后端 uvicorn，从 PID `521327` 切换到 PID `539654`；`GET /` 返回 200。
- 重启后认证调用 `/api/v1/portfolio/equity` 返回 `points=508 first=2026-06-23 03:00:00 last=2026-06-25 08:39:00 total_equity_points=508`，确认当前 live 日内曲线恢复。
- 重启后 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 alerts=-`；四个拆分 supervisor 和长期只读 monitor PID 均未变化。

### 65. 组合持仓 API 丢弃日志更新时间，前端更新时间列为空

现象：认证后抽样 `/api/v1/portfolio/positions`，接口返回 `total=100`，但 100 条持仓全部缺少 `updated_at`。前端 `PortfolioPage.vue` 已有 `updated_at` 列，导致当前持仓表无法展示每条持仓来自哪根 bar/哪次快照。

运行数据证据：

- API 采样：`total=100 missing_updated_at=100`。
- 底层解析器能读出时间：活动 `position.log` 最新行包含 `datetime`，例如 MT5 单元最新为 `2026-06-25 08:42:00`，CTP 单元最新为 `2026-06-23 05:49:00`。
- 因此问题不在日志缺字段，而在组合 API 聚合时丢弃了 `datetime/dt`。

修复：

- `src/backend/app/api/portfolio/api.py` 的 snapshot 持仓转换保留 `updated_at`、`datetime` 或 `dt`。
- `get_portfolio_positions()` 返回每条持仓时新增 `updated_at: p.updated_at || p.datetime || p.dt`。
- `src/backend/tests/test_portfolio_api.py` 的持仓聚合测试增加 `datetime` 与 `dt` 两种来源断言，锁定字段透传。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `26 passed`。
- `git diff --check -- src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py` 无输出。
- 已仅重启后端 uvicorn，从 PID `539654` 切换到 PID `546556`；`GET /` 返回 200。
- 重启后认证调用 `/api/v1/portfolio/positions` 返回 `total=100 missing_updated_at=0`，首条样本为 `data_name=XAUUSD updated_at=2026-06-25 06:58:00`。
- 重启后 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 alerts=-`；四个拆分 supervisor 和长期只读 monitor PID 均未变化。

### 66. 归档报告日志仍保留修复前登录敏感片段

现象：活动日志、后端日志和 live instance JSON 的敏感值复扫已经干净，但把扫描范围扩大到 `reports/` 后，发现 `reports/backend_latest.log` 仍保留旧后端快照中的登录调用记录。该文件是 2026-06-24 的历史归档报告，不属于当前 uvicorn 或策略运行日志；但它仍包含修复前落盘的默认管理员密码字段和 JWT access token 片段。

原因：前几轮清理聚焦在当前运行日志路径 `logs/`、`src/backend/logs/`、runtime config 和 live instance JSON。`reports/backend_latest.log` 是早期诊断快照，位于归档报告目录，未被前一轮敏感值复扫覆盖。

修复：

- 对 `reports/backend_latest.log` 做就地脱敏，把登录参数中的 password 值替换为 `***`，把 `Token(access_token=...)` 中的 token 片段替换为 `***`。
- 没有修改或重启任何 CTP/MT5 supervisor、策略子进程或后端服务；这是归档文本清理，不影响当前 100 个长跑单元。
- 将 `reports/` 纳入后续敏感值复扫口径，避免归档快照继续携带修复前的认证材料。

验收：

- 清理前归档敏感值复扫仅命中 `reports/backend_latest.log:18`。
- 清理后同一组默认密码、JWT 前缀、Bearer-token 和未脱敏 token/password 字段复扫无输出。
- 抽样确认 `reports/backend_latest.log` 中旧登录行已变为 `password='***'` 与 `access_token='***'`。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 67. 工作区持仓接口未返回行级更新时间，组合页仍显示工作区旧更新时间

现象：继续核对前端真实调用路径后发现，`PortfolioPage.vue` 的 positions tab 不直接使用 `/api/v1/portfolio/positions`，而是对每个运行中交易工作区调用 `/api/v1/workspace/{workspace_id}/trading/positions`。该工作区接口返回的 position manager 行只有 `symbol/long_position/short_position/avg_price/latest_price/market_value` 等字段，没有 `updated_at`。前端映射时只能使用 `workspace.updated_at`，当前两个运行中工作区的元数据时间停在 `2026-06-23T14:00:29`，会让“更新时间”列显示工作区记录更新时间，而不是每条持仓快照来自哪根 bar。

运行数据证据：

- 工作区列表中 CTP 与 MT5 为 `status=running`，但 workspace `updated_at` 均为 `2026-06-23T14:00:29`。
- 修复前 `/workspace/{id}/trading/positions` 的 position 行没有 `updated_at` 字段。
- 底层 `position.log` JSON 行已经包含完整 `datetime`；CTP 当前样本最新为 `2026-06-23 06:06:00`，MT5 当前样本最新为 `2026-06-25 08:59:00`。

原因：

- `TradingWorkspaceService._build_snapshot()` 优先读取 `current_position.json`，它通常没有 bar 时间；只有缺失 current position 时才回退 `position.log`。
- `build_positions_response()` 从 unit snapshot 汇总 position manager 行时没有输出 snapshot 或明细持仓中的更新时间。
- 前端 `mapWorkspacePosition()` 固定写 `updated_at: workspace.updated_at`，无法使用真实持仓快照时间。

修复：

- `src/backend/app/services/trading_workspace_service.py` 改为优先使用 `position.log` 的最新行构建工作区 trading snapshot；缺失时再回退 `current_position.json`。
- snapshot 明细持仓新增 `updated_at`，并把最新 position 时间写入 snapshot `updated_at`。
- `PositionManagerItem` 响应新增 `updated_at`，取明细持仓最新时间或 snapshot 更新时间。
- `src/frontend/src/types/workspace.ts` 的 `TradingPositionManagerItem` 增加可选 `updated_at`。
- `src/frontend/src/views/PortfolioPage.vue` 改为 `item.updated_at ?? workspace.updated_at`，优先显示真实持仓快照时间。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/app/schemas/trading.py src/backend/tests/test_workspace_trading_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_workspace_trading_api.py -q`，结果 `6 passed`。
- `npm run typecheck` 初次暴露既有 `src/__tests__/api/stockAnalysis.test.ts` 参数类型不匹配，和本轮 `updated_at` 字段改动无关；已在第 68 节修复并复跑通过。
- 已仅重启后端 uvicorn，从 PID `546556` 切换到 PID `561817`；`GET /` 返回 `200`。
- 重启后认证调用两个运行中工作区持仓接口：CTP `total=50 missing_updated_at=0`，MT5 `total=50 missing_updated_at=0`。
- 重启后 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 68. 前端 stockAnalysis API 测试 payload 推断为 string[]，阻断全量 typecheck

现象：修复工作区持仓更新时间后运行 `npm run typecheck`，`vue-tsc` 在 `src/__tests__/api/stockAnalysis.test.ts` 报错：测试 payload 的 `selected_modules` 被 TypeScript 推断为 `string[]`，不能传给 API 的 `StockAnalysisCreateTaskParams.selected_modules: StockAnalysisModule[]`。

原因：测试中的 `payload` 没有显式类型标注，对象字面量里的字符串数组不会自动收窄为 `StockAnalysisModule[]` 联合类型数组；实际页面代码已通过 `StockAnalysisModule[]` 类型标注规避该问题。

修复：

- `src/frontend/src/__tests__/api/stockAnalysis.test.ts` 引入 `StockAnalysisCreateTaskParams` 类型。
- 将测试 payload 标注为 `StockAnalysisCreateTaskParams`，让 `selected_modules` 使用 API 合约类型，同时保持原有 post 调用断言不变。

验收：

- `npm run typecheck` 通过。
- `npm test -- src/__tests__/api/stockAnalysis.test.ts --run`，结果 `2 passed`。

### 69. 工作区持仓接口重复 hydrate，50 单元请求触发慢请求告警

现象：继续扫描后端日志时发现，组合页实际使用的两个工作区持仓接口在修复 `updated_at` 后仍触发慢请求 warning：CTP 工作区约 `0.55s`，MT5 工作区约 `0.90s`。接口返回 200 且数据正确，但每次打开组合页 positions tab 会按运行中工作区各请求一次，50 单元规模下已经接近或超过当前 500ms 慢请求阈值。

运行数据证据：

- `logs/backend.log` 在 `2026-06-25 06:05:58` 记录 CTP `/api/v1/workspace/{id}/trading/positions took 0.55s`。
- 同一轮 MT5 `/api/v1/workspace/{id}/trading/positions took 0.90s`。
- 活动 runtime 日志 JSON 正常，`error.log` 和 `subprocess.stderr.log` 均为空；性能问题集中在后端聚合路径。

原因：

- `WorkspaceService.get_trading_positions()` 已先调用 `TradingWorkspaceService.hydrate_units()`，用于从运行实例和日志刷新每个 unit 的 trading snapshot。
- 随后 `TradingWorkspaceService.build_positions_response()` 内部又无条件调用一次 `hydrate_units()`。
- 因此单次工作区持仓请求会对 50 个运行单元重复解析日志两遍；刚修复的工作区持仓 `updated_at` 又让这条路径必须读取 `position.log` 最新行，重复 hydrate 的成本在 MT5 50 单元上更明显。

修复：

- `TradingWorkspaceService.build_positions_response()` 增加兼容参数 `hydrate: bool = True`，默认行为保持不变。
- `WorkspaceService.get_trading_positions()` 在已经 hydrate 并提交变更后调用 `build_positions_response(..., hydrate=False)`，避免同一请求重复解析。
- `src/backend/tests/test_trading_workspace_service.py` 增加 `test_build_positions_response_can_skip_hydration`，锁定 `hydrate=False` 不再调用 `hydrate_units()`。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/app/services/workspace_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py -q`，结果 `17 passed`。
- 已仅重启后端 uvicorn，从 PID `561817` 切换到 PID `570248`；`GET /` 返回 `200`。
- 重启后同一工作区持仓接口耗时：CTP `305.6ms`，MT5 `474.0ms`，均未再触发慢请求 warning，且 `positions=50 missing_updated_at=0`。
- 重启后 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 70. 运行实例 log_dir 为空时，工作区 hydrate 可能沿用旧快照

现象：继续追踪工作区持仓更新时间时发现，`src/backend/data/live_trading_instances.json` 中 `CTP压测01` 仍为 `status=running` 且有真实 PID，但持久化字段 `log_dir=null`。该单元的 `runtime_dir/logs/position.log` 实际持续增长，最新行带有本地写入时间和业务 bar 时间；后端重启后，如果工作区交易服务只看 `instance.log_dir`，就会跳过实时日志解析，导致该单元沿用数据库中的旧 snapshot。

运行数据证据：

- 实例存储当前 100 个压测实例均为运行态，其中 CTP 50 个实例里 `missing_log_dir=1`，MT5 为 `missing_log_dir=0`。
- `CTP压测01` 的 `runtime_dir/logs/position.log` 存在且持续更新；抽样尾部包含 `log_time=2026-06-25T06:18:41.316+08:00`、`datetime=2026-06-23 06:25:00`。
- 修复前同一单元工作区持仓样本停在旧 snapshot；修复加载后，认证接口中 `CTP压测01` 持仓时间推进到当前日志业务时间，说明 `runtime_dir/logs` 回退已参与 hydrate。

原因：

- `TradingWorkspaceService._build_snapshot()` 和 `_instance_log_result()` 只读取 live manager 实例字典里的 `log_dir`。
- 某些长跑实例在早期启动或恢复时会留下 `log_dir=null`，但 `runtime_dir/logs` 是交易工作区固定运行目录，日志实际可用。
- 组合 API 的 portfolio 聚合路径已有独立 `runtime_dir` 回退；问题集中在工作区交易服务 hydrate 和日汇总入口。

修复：

- 新增 `_instance_log_dir(instance)` helper：优先使用存在的 `log_dir`，缺失或无效时回退到 `runtime_dir/logs`。
- `_build_snapshot()` 改用该 helper，确保工作区状态 hydrate 能读取实时 `position.log`。
- `_instance_log_result()` 改用同一 helper，确保工作区日汇总在实例 `log_dir` 为空时仍能解析 `value.log/trade.log`。
- 新增两条回归测试，分别覆盖 snapshot hydrate 和日汇总入口的 `runtime_dir/logs` 回退。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py -q`，结果 `19 passed`。
- 已仅重启后端 uvicorn，从 PID `570248` 切换到 PID `579992`；`GET /` 返回 `200`。
- 重启后认证调用组合和工作区持仓接口：组合 positions `total=100 missing_updated_at=0`；CTP 工作区 `positions=50 missing_updated_at=0 elapsed=416.5ms`；MT5 工作区 `positions=50 missing_updated_at=0 elapsed=484.8ms`。
- 后端新 PID 下没有新的慢请求 warning；最新请求日志中 CTP 工作区持仓约 `0.42s`，MT5 工作区持仓约 `0.48s`。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 71. 工作区持仓接口仍全量解析日志，MT5 50 单元接近慢请求阈值

现象：第 69 节去掉重复 hydrate 后，工作区持仓接口不再超过 500ms 慢请求阈值，但 MT5 50 单元请求仍多次在 `0.47s-0.49s` 附近。该接口只需要 position manager 行，却仍在 hydrate 阶段对每个单元执行 `parse_log_dir()`，读取 `value.log/trade.log/order.log/bar.log/position.log` 等全量日志。

运行数据证据：

- 第 70 节修复加载后，CTP 工作区持仓约 `416.5ms`，MT5 工作区持仓约 `484.8ms`。
- 后端新 PID 下没有慢请求 warning，但 MT5 已非常接近当前 500ms 阈值；后续日志增长后仍可能再次触发 warning。
- 活动日志质量正常，`bad_json=0` 且错误日志为空，瓶颈集中在不必要的日志解析量。

原因：

- `WorkspaceService.get_trading_positions()` 为了刷新每个 unit 的 trading snapshot，调用 `TradingWorkspaceService.hydrate_units()`。
- `hydrate_units()` 默认通过 `_build_snapshot()` 执行全量日志解析，适合状态页、日汇总或详情页，但 positions manager 只需要最新持仓、行级更新时间和基础实例状态。
- 第 69 节避免了重复 hydrate，但剩下的一次 hydrate 仍做了超过 positions 接口需求的工作。

修复：

- `_build_snapshot()` 增加 `full_log: bool = True` 参数；默认保持全量行为。
- `hydrate_units()` 增加同名参数并传给 `_build_snapshot()`。
- `WorkspaceService.get_trading_positions()` 改为 `hydrate_units(..., full_log=False)`，只读取 `position.log/current_position` 构建持仓快照。
- 轻量 hydrate 会保留已有 snapshot 里的 `today_pnl/cumulative_pnl/trades` 等摘要字段，避免 positions 请求把其他视图需要的全量数据清空。
- 新增单测确认轻量 hydrate 不调用 `parse_log_dir()`，并能保留已有收益和交易摘要。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/app/services/workspace_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py -q`，结果 `20 passed`。
- 已仅重启后端 uvicorn，从 PID `579992` 切换到 PID `585412`；`GET /` 返回 `200`。
- 轻量 hydrate 后三轮认证请求：CTP 工作区持仓 `153.9ms/136.5ms/134.2ms`；MT5 工作区持仓 `232.4ms/163.4ms/184.1ms`。
- 两个工作区均保持 `positions=50 missing_updated_at=0`；样本 `CTP压测01` 更新时间为 `2026-06-23 06:30:00`，样本 `MT5压测01` 更新时间为 `2026-06-25 09:23:00`。
- 组合 API 仍正常：positions `total=100 missing_updated_at=0`，equity `points=596`，trades `total=1786`。
- 新 PID 下后端日志没有新的慢请求 warning 或 traceback。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 72. portfolio 聚合路径信任失效 log_dir，可能屏蔽 runtime_dir/logs 回退

现象：修复工作区交易服务的 `log_dir=null` 回退后，继续审计组合 API fallback 路径，发现 `_resolve_instance_log_dir()` 对 manager 实例的显式 `log_dir` 只要非空就直接返回。若持久化实例记录里保留了旧路径或已删除路径，组合 API 在没有活跃 trading workspace sources、或回退到 manager 实例聚合时，会解析失效目录并得到空数据，而不会继续尝试 `runtime_dir/logs` 或策略目录最新日志。

运行数据证据：

- 当前运行数据已经出现同类元数据漂移：CTP 50 个实例里 `missing_log_dir=1`，说明 long-running 实例记录可与真实 runtime 日志位置不一致。
- portfolio 路径此前对显式 `log_dir` 没有 `is_dir()` 检查；workspace trading service 则已改为只信任存在目录并回退 `runtime_dir/logs`。
- 新增单测构造 stale explicit `log_dir` 和 active `runtime_dir/logs/value.log`，验证应回退到 runtime logs。

原因：

- `_resolve_instance_log_dir()` 直接 `return explicit_log_dir`，没有验证目录是否存在。
- manager 实例聚合是 workspace sources 为空时的 fallback，容错逻辑不应比主路径更脆弱。

修复：

- `src/backend/app/api/portfolio/api.py` 中显式 `log_dir` 只有在 `is_dir()` 为真时才返回。
- 否则继续 `runtime_dir -> find_latest_log_dir(runtime_dir)`，再回退策略目录。
- 新增回归测试 `test_resolve_instance_log_dir_falls_back_when_explicit_log_dir_is_stale`。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `27 passed`。
- 已仅重启后端 uvicorn，从 PID `585412` 切换到 PID `589926`；`GET /` 返回 `200`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499892.33 total_pnl=-107.67 total_position_value=487863.16 net_position_value=11604.64`；positions `total=100 missing_updated_at=0`；trades `total=1822`；equity `points=606 first=2026-06-23 03:00:00 last=2026-06-25 09:28:00`；allocation `items=100`。
- 工作区持仓接口仍正常：CTP `139.9ms positions=50 missing_updated_at=0`；MT5 `182.9ms positions=50 missing_updated_at=0`。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`，错误日志为空。
- 后端 PID `589926` 下没有新的慢请求 warning 或 traceback。

### 73. 默认管理员密码提示由 Settings 发出非结构化 warning，后端启动日志重复告警

现象：继续复扫后端重启日志时发现，每次 uvicorn 启动都会先由 Pydantic `Settings` 构造路径向 stdout/stderr 写一条 Python `UserWarning`，随后 `app.startup.security_check` 又输出一条结构化 WARNING。两条提示表达的是同一个默认管理员密码风险，但前者没有项目日志格式、request_id、模块字段，也会污染长期运行日志和敏感/异常扫描。

运行数据证据：

- 后端 PID `589926` 启动前，`logs/backend.log` 中先出现来自 `pydantic/main.py` 的非结构化 `UserWarning`，随后才出现 `app.startup.security_check` 的结构化 WARNING。
- 新 PID `600788` 启动后，从 `Started server process [600788]` 之后复扫，仅保留 `app.startup.security_check` 的结构化 WARNING，没有新的 Pydantic `UserWarning`。
- 这个问题与交易子进程无关；CTP/MT5 direct monitor 在修复前后均保持 `running=50 process=50 heartbeat=50 alerts=-`。

原因：

- `Settings.validate_runtime_security_guards()` 在非生产环境遇到默认管理员密码时调用 `warnings.warn()`。
- 同一风险已经由 startup security check 在应用生命周期中输出结构化日志，导致重复且口径不一致。
- 配置单测还把类默认值与本机 `.env` 覆盖后的运行配置混在一起，导致验证过程中出现与本轮逻辑无关的失败。

修复：

- `src/backend/app/config.py` 去掉非生产分支的 `warnings.warn()`；生产环境默认密码仍通过 `ValueError` 阻止启动。
- 保留 `app.startup.security_check` 的结构化 WARNING，风险提示不消失。
- `src/backend/tests/test_config_validation.py` 新增/调整测试：配置构造不再产生 Python warning；生产环境安全校验显式传入被测默认 secret；默认 DEBUG 断言改为检查字段定义；需要隔离本机 `.env` 的测试使用 `_env_file=None`。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/config.py src/backend/app/startup/security_check.py src/backend/tests/test_config_validation.py src/backend/tests/test_main_lifespan_and_websocket.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_config_validation.py src/backend/tests/test_main_lifespan_and_websocket.py -q`，结果 `29 passed, 3 skipped, 1 warning`；剩余 warning 是既有未知 pytest mark。
- 直接构造 `Settings(DEBUG=True, ADMIN_PASSWORD=<default>)` 的 Python warning 计数为 `0`。
- 后端已仅重启到 uvicorn PID `600788`，`GET /` 返回 `200`，进程使用独立 session 持续存活。
- 新 PID 启动段只保留结构化默认管理员密码 WARNING，没有新的 Pydantic `UserWarning`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499687.2 total_pnl=-312.8 total_position_value=482803.43 net_position_value=37542.65`；positions `total=100 missing_updated_at=0`；trades `total=1893`；equity `points=624 first=2026-06-23 03:00:00 last=2026-06-25 09:37:00`；allocation `items=100`。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 74. 空闲交易工作区持仓接口继续展示旧日志持仓，容易误判为当前持仓

现象：继续复扫工作区持仓接口时发现，两个旧的 CTP SimNow 7x24 工作区在数据库中已经是 `run_status_counts={'idle': 50}`，但 `/api/v1/workspace/{workspace_id}/trading/positions` 仍会读取历史 runtime `position.log`，默认返回 50 条持仓。当前组合 API 没有混入这些 idle 工作区，但工作区列表或人工排查时，idle 工作区会看起来仍有当前持仓。

运行数据证据：

- 当前目标压测工作区 `期货模拟工作区`、`MT5模拟工作区` 均为 `running=50`，默认持仓接口分别返回 50 条。
- 两个旧 CTP 工作区 `CTP SimNow 7x24 模拟交易运营 ...` 均为 `idle=50`，修复前默认持仓接口也返回 50 条，且 `updated_at` 来自历史日志。
- 这类历史持仓不应作为工作区级“当前持仓”展示；真正需要排查历史单元时，可以显式指定 `unit_ids`。

原因：

- `WorkspaceService.get_trading_positions()` 对整个工作区所有 unit 执行 hydrate 和 positions response 构建。
- `TradingWorkspaceService.build_positions_response()` 只看 snapshot/日志中的持仓值，不区分该 unit 当前是否 `running/queued`。
- 空闲工作区的旧 runtime 日志仍可读，因此被当作当前 position manager 行输出。

修复：

- `WorkspaceService.get_trading_positions()` 保持先 hydrate，以便 DB 状态滞后但实例真实运行时仍能纠正。
- 默认未传 `unit_ids` 时，仅把 `run_status` 或 snapshot `instance_status` 为 `queued/running` 的单元交给 position manager 聚合。
- 显式传 `unit_ids` 时保留原有行为，仍可查看指定历史单元快照，便于人工排查。
- 新增 API 回归测试：stopped 实例 + 历史 `position.log` 默认返回空持仓；带 `unit_ids` 查询仍返回该单元历史快照。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/workspace_service.py src/backend/tests/test_workspace_trading_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_workspace_trading_api.py -q`，结果 `7 passed`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_trading_workspace_service.py -q`，结果 `14 passed`。
- 已仅重启后端 uvicorn 到 PID `613349`；`GET /` 返回 `200`，进程 `SID=613349` 持续存活。
- 真实 API 复验：`期货模拟工作区` positions `50 missing_updated_at=0`，`MT5模拟工作区` positions `50 missing_updated_at=0`；两个 idle 旧 CTP 工作区默认 positions 均为 `0`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499507.74 total_pnl=-492.26 total_position_value=512403.85 net_position_value=285373.35`；positions `total=100 missing_updated_at=0`；trades `total=1954`；equity `points=639 first=2026-06-23 03:00:00 last=2026-06-25 09:44:00`；allocation `items=100`。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 75. 组合持仓明细缺少带符号市值，无法从 positions 行复算净敞口

现象：继续复扫真实组合接口时发现，`/api/v1/portfolio/overview` 返回 `net_position_value=718172.48`，但 `/api/v1/portfolio/positions` 的 100 行 `market_value` 直接求和为 `749299.78`，等同于毛市值而不是净敞口。positions summary 自身能区分 long/short，但明细行没有带符号市值字段，前端或外部调用方很容易把空头持仓也当正向敞口累加。

运行数据证据：

- 修复前 positions 返回 `total=100`，其中有 29 个空头和 16 个 flat，但每行 `market_value` 都是正数。
- overview 的 `total_position_value` 表示毛市值，`net_position_value` 表示净敞口；positions 明细缺少能直接复算 `net_position_value` 的字段。
- 真实空头样例中 `direction=short`、`size=-0.01`，但 `market_value=39.97455`，缺少 `-39.97455` 这类 signed value。

原因：

- `get_portfolio_positions()` 为了兼容前端毛市值展示，对每行 `market_value` 使用 `abs(market_value)`。
- `_build_position_summary()` 依赖 `size` 判断 long/short，因此 summary 的 `net_market_value` 是正确的；但行级 API 没有暴露同一口径的 signed value。

修复：

- 保留既有 `market_value` 正数语义，避免破坏前端毛市值展示和已有测试。
- 新增 `signed_market_value` 字段：多头为正、空头为负、flat 为 0。
- 前端 `PositionItem` 类型声明同步新增可选 `signed_market_value`。
- 回归测试覆盖空头行 `market_value` 保持正数、`signed_market_value` 为负，并验证明细 signed 求和可复算 summary net。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `27 passed`。
- `npm run typecheck`，结果通过。
- 已仅重启后端 uvicorn 到 PID `625336`；`GET /` 返回 `200`。
- 真实 API 复验：positions `total=100 missing_signed=0 shorts=35 wrong_short_signed=0 gross_sum=749461.11 signed_sum=712358.90 summary_net=712358.90 overview_net=712358.85`；overview `strategy_count=100 running_count=100 total_assets=50499962.98 total_pnl=-37.02 total_position_value=749461.17 net_position_value=712358.85`；equity `points=654 first=2026-06-23 03:00:00 last=2026-06-25 09:52:00 strategies=100`。
- 新 PID 下 5 个交易工作区持仓复验：IB idle `0`，CTP `50 missing_updated_at=0`，MT5 `50 missing_updated_at=0`，两个旧 CTP idle 工作区均 `0`。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 76. 组合页按工作区筛选交易时先全局截断，CTP 交易被 MT5 最近交易挤掉

现象：真实运行数据里 `/api/v1/portfolio/trades?limit=1000` 返回 `total=2023 rows=1000`，但前 1000 条全部来自 `MT5模拟工作区`。组合页在工作区视图中先请求全局最近 1000 条 trades，再用前端按工作区名称过滤；当用户只选择 CTP 工作区时，CTP 的较早交易会在后端全局截断前就被 MT5 最近交易挤掉，前端可能显示空交易列表或不完整交易列表。

运行数据证据：

- 修复前真实 API 采样：`trades total=2023 rows=1000 prefixes=[('MT5模拟工作区 / MT5', 1000)]`。
- 同一时刻 CTP 50 个策略仍在运行且有 trade.log，组合页 positions 能显示 CTP 50 条持仓，说明问题不是 CTP 无数据，而是 trades 的全局 limit 先于工作区过滤。
- 修复后真实 API 采样：全局 `limit=5` 仍全为 MT5；传 MT5 工作区 ID 得到 `total=1405 rows=5 prefixes={'MT5模拟工作区': 5}`；传 CTP 工作区 ID 得到 `total=654 rows=5 prefixes={'期货模拟工作区': 5}`。

原因：

- 后端 `get_portfolio_trades()` 只支持全局聚合和全局 `limit`。
- 前端 `PortfolioPage.loadWorkspaceAggregates()` 调用 `portfolioApi.getTrades(1000)` 后再做本地 `strategy_name` 前缀过滤，导致后端已丢弃选中工作区之外时间排序较后的明细。

修复：

- `_PortfolioSource` 增加 `workspace_id`，活跃交易工作区来源使用真实 `Workspace.id`，manager fallback 若实例包含 `workspace_id` 也会透传。
- `/api/v1/portfolio/trades` 和 `/api/v1/portfolio/simulation/trades` 新增可选 `workspace_ids` 查询参数，支持逗号分隔和重复 query 值；后端先过滤来源，再聚合排序并应用 `limit`。
- 前端 `portfolioApi.getTrades(limit, workspaceIds)` 会在选中工作区非空时传 `workspace_ids=...`。
- 组合页 `loadWorkspaceAggregates()` 传入当前选中工作区 ID，保留原本本地前缀过滤作为防御。
- 新增后端回归测试覆盖“全局最新交易属于另一个工作区，但传 CTP 工作区后 limit=1 仍返回 CTP 交易”；新增前端 API 和页面测试覆盖 `workspace_ids` 参数。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `28 passed`。
- `npm test -- --run src/__tests__/api/portfolio.test.ts src/__tests__/views/PortfolioPage.test.ts`，结果 `2 files passed, 25 tests passed`。
- `npm run typecheck`，结果通过。
- 已仅重启后端 uvicorn 到 PID `639121`；`GET /health` 返回 `200`。
- 真实 API 复验：全局 trades `total=2059 rows=5 prefixes={'MT5模拟工作区': 5}`；MT5 工作区过滤 `total=1405 rows=5 prefixes={'MT5模拟工作区': 5}`；CTP 工作区过滤 `total=654 rows=5 prefixes={'期货模拟工作区': 5}`。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。
- 新 PID 日志从 `Started server process [639121]` 后无 ERROR、Traceback、UserWarning 或 slow request；仅保留既有结构化默认管理员密码 WARNING。

### 77. 组合页默认全选交易仍按合并后 limit 截断，CTP 交易不出现在默认列表

现象：第 76 项修复后，单独选择 CTP 工作区时 trades 已正确返回 CTP 交易；但组合页默认会同时选中 CTP 与 MT5 两个运行工作区。此时前端传两个工作区 ID 一次请求，后端仍按“选中集合整体最近 1000 条”返回。真实数据中 MT5 最近交易数量超过 1000，默认全选交易表仍只会看到 MT5，不利于同时对比两个工作区。

运行数据证据：

- 新接口修复后继续采样：`/api/v1/portfolio/trades?limit=1000&workspace_ids=<ctp>,<mt5>` 的前 1000 条仍全部为 `MT5模拟工作区`。
- 分别查询单工作区时，MT5 当前 `total=1429 rows=1000`，CTP 当前 `total=673 rows=673`。
- 按新前端策略模拟合并后，默认全选可得到 `merged_rows=1673 prefixes={'MT5模拟工作区': 1000, '期货模拟工作区': 673}`。

原因：

- 第 76 项解决的是“工作区过滤先于 limit”，但多个工作区作为一个过滤集合时，`limit` 仍对集合整体生效。
- 组合页的默认视图语义更像“展示当前选中每个工作区的近期交易”，不是“只展示选中集合全局最近 1000 条交易”。

修复：

- `PortfolioPage.loadWorkspaceAggregates()` 改为对每个选中工作区分别调用 `portfolioApi.getTrades(1000, [workspace.id])`。
- 前端将每个工作区返回的 trades 做工作区名称防御过滤后合并，并按 `dtclose/datetime/dtopen` 降序排序。
- 新增页面测试，验证两个选中工作区时会分别发起 `getTrades(1000, ['ws-running'])` 与 `getTrades(1000, ['ws-mt5'])`。

验收：

- `npm test -- --run src/__tests__/views/PortfolioPage.test.ts`，结果 `17 passed`；随后方向显示测试加入后同文件为 `18 passed`。
- `npm run typecheck`，结果通过。
- 真实 API 模拟新前端路径：MT5 单工作区 `rows=1000 total=1429`，CTP 单工作区 `rows=673 total=673`，合并后 `merged_rows=1673 prefixes={'MT5模拟工作区': 1000, '期货模拟工作区': 673}`。

### 78. 交易表只识别 long/short，真实 buy/sell 方向被反向显示

现象：继续复扫真实 trades 明细时发现，后端 `parse_trade_log()` 输出的交易方向是 `buy/sell`。组合页交易表模板只判断 `row.direction === 'long'`，因此真实 `buy` 会走到 else 分支，被显示成空头文案和绿色样式。

运行数据证据：

- 真实 `/api/v1/portfolio/trades?limit=20` 当前方向计数为 `{'sell': 10, 'buy': 10}`。
- 样例：`('MT5模拟工作区', 'USDCAD', 'buy')` 和 `('MT5模拟工作区', 'USDJPY', 'buy')` 都会被旧模板按空头显示。

原因：

- positions 使用 `long/short/flat`，trades 使用 `buy/sell`；前端交易表复用了只适合 positions 的方向判断。

修复：

- 新增 `tradeDirectionLabel()` 与 `tradeDirectionClass()`，同时兼容 `buy/long` 和 `sell/short`。
- 交易表方向列改用该 helper。
- 新增页面测试，覆盖 `buy -> 多/红色` 与 `sell -> 空/绿色`。

验收：

- `npm test -- --run src/__tests__/views/PortfolioPage.test.ts`，结果 `18 passed`。
- `npm run typecheck`，结果通过。
- 真实 API 方向复扫：工作区 trades 前 20 条均为 `buy/sell`，新 helper 已覆盖该口径。

### 79. 交易表开平仓时间列宽不足，真实分钟级时间容易被截断

现象：真实 trades API 的 `dtopen/dtclose` 是完整分钟级时间，例如 `2026-06-25 10:10:00`，但组合页交易表开仓/平仓时间列宽为 `100`。在 Element Plus 表格中该宽度更适合日期，不适合 19 位日期时间，容易截断关键信息。

修复：

- 将交易表 `dtopen` 与 `dtclose` 两列宽度从 `100` 调整为 `150`，与持仓更新时间列保持一致。

验收：

- `npm test -- --run src/__tests__/views/PortfolioPage.test.ts`，结果 `18 passed`。
- `npm run typecheck`，结果通过。

### 80. 持仓更新时间混用行情业务时间，历史回放中的活跃 CTP 看起来像停更

现象：继续复扫真实运行日志时发现，CTP 50 个单元的 `value.log/position.log/trade.log` 业务 `datetime` 仍停在历史行情回放时间 `2026-06-23 07:25` 附近，但日志 `log_time`、文件 mtime 和 heartbeat 都在 `2026-06-25` 当前时间持续推进。组合页和工作区持仓页此前把 `datetime` 当 `updated_at` 展示，会让正在运行的历史回放 CTP 看起来像两天前已经停更。

运行数据证据：

- CTP 样例 `value.log`：`log_time=2026-06-25T07:18:41.365+08:00`，但 `datetime=2026-06-23 07:25:00`。
- MT5 样例则两者都接近当前业务时间：`log_time=2026-06-25T07:19:00.921+08:00`，`datetime=2026-06-25 10:18:00`。
- 修复前 API 只能返回一个 `updated_at`，无法区分“这条持仓什么时候刷新”和“这条持仓对应哪根行情 K 线”。

原因：

- `parse_position_log()` 解析 JSON/pipe/TSV position 日志时没有保留 `log_time`。
- 组合 API 与工作区 position manager 都使用 `updated_at/datetime/dt` 的兜底顺序，因此历史回放数据会把业务时间误当刷新时间。

修复：

- `parse_position_log()` 对 JSON、pipe key-value 和 TSV 三种格式都保留 `log_time`；TSV 同时保留完整 `datetime`，`dt` 继续保留日期口径。
- 组合持仓 API 与工作区 position manager 的 `updated_at` 优先使用 `updated_at/log_time/datetime/dt`，新增 `data_time` 字段保留行情业务时间。
- `PositionManagerItem`、前端 `PositionItem` 和 `TradingPositionManagerItem` 类型同步新增 `data_time`。
- 组合页映射工作区持仓时保留 `data_time`，现有“更新时间”列继续展示 `updated_at`，因此会显示真实刷新时间。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/log_parser_service.py src/backend/app/api/portfolio/api.py src/backend/app/services/trading_workspace_service.py src/backend/app/schemas/trading.py src/backend/tests/test_log_parser_extended.py src/backend/tests/test_portfolio_api.py src/backend/tests/test_trading_workspace_service.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_log_parser_extended.py src/backend/tests/test_portfolio_api.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `77 passed`。
- `npm test -- --run src/__tests__/api/portfolio.test.ts src/__tests__/views/PortfolioPage.test.ts`，结果 `2 files passed, 25 tests passed`。
- `npm run typecheck` 和 `npm run build` 均通过；build 仅保留既有 Vite 大 chunk warning。
- 已仅重启后端 uvicorn 到 PID `675412`；`GET /health` 返回 `200`。
- 真实 API 复验：组合 positions `total=100 missing_updated_at=0 missing_data_time=0 updated_prefixes={'2026-06-25': 100} data_prefixes={'2026-06-25': 50, '2026-06-23': 50}`；CTP 工作区 positions `updated_prefixes={'2026-06-25': 50} data_prefixes={'2026-06-23': 50}`；MT5 工作区 positions `updated_prefixes={'2026-06-25': 50} data_prefixes={'2026-06-25': 50}`。
- 新 PID 日志从 `Started server process [675412]` 后无 ERROR、Traceback、UserWarning 或 slow request；仅保留既有结构化默认管理员密码 WARNING。
- 最新 direct monitor 仍显示 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 no_log=0 alerts=-`。

### 81. 压测 supervisor 未注入本地源码路径，滚动重启后仍可能加载不到 backtrader 修复

现象：修复 live trading 子进程环境后继续复扫 `/proc/<pid>/environ`，发现通过 `run_dual_exchange_simulation.py` 启动的压测 supervisor 仍只把 `/home/yun/Documents/bt_api_py/bt_api_py` 放进策略子进程 `PYTHONPATH`，没有 `/home/yun/Documents/backtrader`。这会导致 `/home/yun/Documents/backtrader` 中已修复的 `TradeLogger` / store 时间戳逻辑在滚动重启策略后仍不生效。

原因：

- `run_dual_exchange_simulation.py` 作为独立运维入口，在导入 `app` 和创建子进程环境前没有统一补齐本地源码路径。
- 先前的环境修复覆盖了网站后端通过 live trading manager 启动的路径，但没有覆盖压测 supervisor 自身直接拉起的策略。

修复：

- 在 `run_dual_exchange_simulation.py` 中新增 `configure_local_source_paths()`，按 `backtrader -> bt_api_py -> existing PYTHONPATH` 顺序更新 `os.environ["PYTHONPATH"]`。
- 同一函数也把本地源码路径插到 `sys.path` 前端，保证 supervisor 进程自身在后续导入 `app` 相关模块时也优先使用工作区源码。
- 新增回归测试 `test_configure_local_source_paths_prepends_local_sources`，覆盖环境变量顺序、重复路径去重和 `sys.path` 插入顺序。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `27 passed`。
- 无副作用导入验证输出 `PYTHONPATH=/home/yun/Documents/backtrader:/home/yun/Documents/bt_api_py/bt_api_py:src/backend`。
- 先用 CTP01 canary 验证新子进程环境，再对 CTP 与 MT5 各 50 单元做全量 rolling restart；最终 CTP `rolling restarted: running=50 process=50 heartbeat=50 stale=0 alerts=-`，MT5 `rolling restarted: running=50 process=50 heartbeat=50 stale=0 alerts=-`。
- `/proc` 精确匹配 100 个 `workspace_units/.../run.py` 子进程后，`missing_local_count=0`、`missing_light_count=0`。

### 82. MT5 异常权益尖峰让状态采样触发 numpy overflow warning

现象：MT5 rolling restart 和 `ensure_dual_stress_running.sh status` 曾反复输出：

- `/home/yun/anaconda3/lib/python3.13/site-packages/numpy/_core/_methods.py:197: RuntimeWarning: overflow encountered in multiply`

运行数据证据：

- 逐个捕获 `parse_log_dir()` warning 后定位到单个 MT5 单元 `2811635c-38b7-44f3-8525-fc43a02aa71a/logs/value.log`。
- 该 `value.log` 在正常 `broker_value` 约 `10000` 的序列中夹杂 19 条 `-5.53e201` 到 `-5.56e201` 的异常权益值，`broker_cash` 同期约 `10039.85`，后续权益又回到 `10000` 附近。

原因：

- `parse_value_log()` 原样接收极端有限浮点值；`parse_log_dir()` 再用这些点计算收益序列和 `np.std()`。
- `5e201` 级别尖峰转换成收益率后，numpy 方差计算中的平方操作溢出，虽然最终策略仍 running，但监控日志被 warning 污染，风险指标也可能被异常点拉坏。

修复：

- `parse_value_log()` 对权益曲线加入小作用域合理性过滤：拒绝非有限值、绝对值超过 `1e15`、相对现金超过 `1000x`、或相邻权益跳变超过 `1000x` 的点。
- `parse_log_dir()` 的 total/annual return 和 Sharpe 计算增加有限值保护；Sharpe 收益序列只使用有限且绝对收益不超过 `10x` 的点，避免坏 tick 继续污染风险指标。
- 新增回归测试构造正常权益序列中混入 `-5.538e201`，断言解析不会产生 warning，且会跳过坏点保留正常最终权益。

验收：

- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_log_parser_extended.py -q`，结果 `36 passed`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_log_parser_extended.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_portfolio_api.py -q`，结果 `105 passed`。
- 对真实 MT5 50 个 `logs/` 逐个 `warnings.catch_warnings()` 解析，结果 `overflow_warning_dirs=0`。
- 重启 monitor-only 到 PID `717756` 后，`ensure_dual_stress_running.sh status` 在 `2026-06-25 07:54:21 CST` 输出双目标 `running=50 process=50 heartbeat=50 stale=0 alerts=-`，无 numpy warning。
- 仅重启后端 uvicorn 到 PID `722265`；`GET /health` 返回 200，认证后组合 overview `strategy_count=100 running_count=100 total_assets=50500146.42 total_pnl=146.42`，positions `total=100 missing_updated_at=0 missing_data_time=0`。
- 后端日志从 `Started server process [722265]` 后复扫 `ERROR/Traceback/RuntimeWarning/overflow encountered` 均为 0。

### 83. 通用进程扫描使用 ps 文本拆词，存在误匹配非策略命令的风险

现象：继续做 `/proc` 侧验证时，最初用简单字符串包含 `workspace_units` 与 `run.py` 的扫描脚本得到 101 个进程，其中 1 个没有本地源码路径和轻量导入环境变量。复查发现该额外进程其实是当前扫描命令的 shell 自身，命令文本中包含这些字符串，并不是策略子进程。`run_dual_exchange_simulation.py` 自己已按 `/proc/<pid>/cmdline` 的 argv 分段精确匹配，因此运行监控没有误报；但通用 `process_supervisor.scan_running_strategy_pids()` 在 Linux/macOS fallback 中仍使用 `ps -eo pid,args` 文本拆词，边界不如 argv 级匹配稳。

原因：

- `ps args` 是格式化后的整行命令文本，无法天然区分脚本内容、shell 参数和真实 argv 路径。
- 原实现只要某个拆出的 token 以 `run.py` 结尾且包含 `strategies` 或 `workspace_units` 就记录 PID，缺少对绝对路径和 argv 边界的约束。

修复：

- `process_supervisor` 新增 `_scan_running_strategy_pids_procfs()`，Linux 下优先读取 `/proc/<pid>/cmdline`，只接受单个 argv item 中的绝对 `.../strategies/.../run.py` 或 `.../workspace_units/.../run.py`。
- `ps` / Windows WMIC fallback 复用同一个 `_strategy_run_py_arg()` 校验函数，拒绝非绝对路径或非策略目录 token。
- 新增回归测试构造 fake procfs：真实 argv path 会被识别，shell heredoc 文本中出现的 `workspace_units/.../run.py` 不会被识别。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/process_supervisor.py src/backend/tests/test_process_supervisor.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_process_supervisor.py -q`，结果 `14 passed`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python - <<'PY' ... scan_running_strategy_pids()` 在真实现场返回 `total=100 workspace_units=100`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_process_supervisor.py src/backend/tests/test_live_instance_service.py src/backend/tests/test_extracted_modules.py -q`，结果 `154 passed, 2 skipped`。

### 84. 手动 CTP 前置被 .env 自动环境选择覆盖，08:xx 会从 30001/30011 跳到 set2 40001/40011

现象：组合回归测试暴露手动连接 CTP 时，即使调用方显式传入 `td_front=tcp://182.254.243.31:30001`、`md_front=tcp://182.254.243.31:30011`，`connect_gateway()` 仍会把 runtime kwargs 改成 `tcp://182.254.243.31:40001/40011`。同时“当前三组 SimNow 前置均不可达”测试没有在前置探测阶段返回清晰错误，而是继续走到 runtime class import 并返回 `TypeError`。

原因：

- `_resolve_manual_ctp_env_credentials()` 会把 `.env` 中的 `CTP_ENV` 纳入 `resolve_ctp_front_selection()`。
- 当环境为 `auto` 且当前时间为 `2026-06-25 08:xx CST`、不在 CTP 日盘/夜盘交易时段内时，自动选择逻辑会切到 set2 `40001/40011`。
- 对“手动传入前置”的 API 调用来说，这破坏了显式参数优先级，也绕过了 `_resolve_ctp_front_pair()` 对当前三组 SimNow 前置的可达性切换/错误提示。

修复：

- `_resolve_manual_ctp_env_credentials()` 现在检测调用方是否显式传入 `td_front/td_address/md_front/md_address`。
- 当显式前置存在且调用方没有显式传 `ctp_env` 时，内部按 `ctp_env=manual` 处理，让显式前置保持手动语义，不再被 `.env` 的 `CTP_ENV=auto` 覆盖。
- 保留显式 `ctp_env` 的优先级；如果调用方明确指定 `auto/set1/set2`，仍按该选择执行。
- 网关健康快照测试同步覆盖新增的 CTP 诊断字段，避免 API 字段扩展未被测试契约记录。

验收：

- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_extracted_modules.py -q -k 'connect_gateway_reuses_existing_shared_session_and_promotes_manual or connect_gateway_switches_to_reachable_current_simnow_front or connect_gateway_returns_clear_error_when_all_current_simnow_fronts_unreachable or connect_gateway_keeps_requested_simnow_front_when_proxy_tunnel_available or get_gateway_health_returns_runtime_snapshot'`，结果 `5 passed, 112 deselected`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_process_supervisor.py src/backend/tests/test_live_instance_service.py src/backend/tests/test_extracted_modules.py -q`，结果 `154 passed, 2 skipped`。
- 后端已用 `setsid` 重启到 PID `752932`；`GET /health` 返回 200，认证后组合 overview `strategy_count=100 running_count=100 total_assets=50500010.08 total_pnl=10.08`，positions `total=100 missing_updated_at=0 missing_data_time=0`。
- 后端日志从 `Started server process [752932]` 后复扫 `ERROR/Traceback/RuntimeWarning/overflow encountered/ModuleNotFoundError/Address already in use` 均为 0。

### 85. CTP/MT5 tick 到 bar 的业务时间把交易所/本地墙钟时间标成 UTC

现象：继续复扫当前活动压测日志时，发现日志 `log_time` 与文件 mtime 都在 `2026-06-25 08:24 CST` 附近持续推进，但业务 `datetime` 仍有两类时间语义风险：

- CTP 是历史行情回放，最新样本 `value.log/position.log/bar.log` 为 `datetime=2026-06-23T08:31:00.000+00:00`、`log_time=2026-06-25T08:24:41.325+08:00`；这说明进程活跃时间和业务回放时间分离，监控不能只看日志心跳。
- MT5 最新样本为 `datetime=2026-06-25T11:23:00.000+00:00`、`log_time=2026-06-25T08:24:00.630+08:00`；结合早前带 `timestamp=1782357359.0` 的样本可复算为 `2026-06-25T03:15:59+00:00` / `2026-06-25T11:15:59+08:00`，表明交易所/本地墙钟时间容易被当作 UTC 字符串落盘。

原因：

- `backtrader.feeds.btapifeed._tick_datetime()` 对 aware datetime/ISO 只做 `replace(tzinfo=None)`，没有换算到 UTC；timestamp fallback 使用本机时区 `datetime.fromtimestamp()`。
- `_tick_timestamp()` 对 naive datetime 调用 `.timestamp()`，会受运行机器时区影响。
- `BtApiStore._normalize_datetime()` 注释写的是 UTC naive，但实现同样只是丢弃 tzinfo。
- `bt_api_ctp.gateway.adapter` 用 CTP 的 `TradingDay + UpdateTime` 构造 naive datetime，再调用 `.timestamp()`，依赖本机时区恰好是 `Asia/Shanghai`。
- 后续确认运行时实际导入的 CTP 包不是 `/home/yun/Documents/bt_api_py/bt_api/bt_api_ctp` 子模块，而是独立仓库 `/home/yun/Documents/bt_api_ctp/src/bt_api_ctp`。只改子模块副本不会影响当前策略进程。

修复：

- `BtApiFeed` 新增 UTC 归一化辅助：tick 有 `timestamp` 时优先 epoch；带时区 datetime/ISO 先转 UTC 再去 tzinfo；numeric timestamp 用 UTC fromtimestamp；naive datetime 按已归一化 UTC 处理。
- `BtApiStore._normalize_datetime()` 改为真正的 UTC naive 归一化；`_normalize_bar()` 在 dict 同时包含 `timestamp` 和 `datetime` 时优先 epoch，避免 provider datetime 被错误标注时继续污染 bar。
- CTP wrapper 的 `event.datetime` 改为 `_normalize_datetime(tick_dt)`，不再直接剥离 `+08:00`。
- `bt_api_ctp.gateway.adapter` 新增 `_ctp_tick_timestamp_datetime()`，CTP 交易所时间显式使用 `UTC+8` aware datetime，fallback 使用 UTC aware datetime，避免依赖本机时区；该修复已同步到实际运行导入源 `/home/yun/Documents/bt_api_ctp/src/bt_api_ctp/gateway/adapter.py`。

验收：

- `/home/yun/anaconda3/bin/python -m py_compile backtrader/feeds/btapifeed.py backtrader/stores/btapistore.py tests/unit/feeds/test_btapifeed.py tests/unit/stores/test_btapistore.py` 通过。
- `/home/yun/anaconda3/bin/python -m pytest tests/unit/feeds/test_btapifeed.py tests/unit/stores/test_btapistore.py -q`，结果 `138 passed, 1 skipped`。
- `PYTHONPATH=/home/yun/Documents/bt_api_ctp/src:/home/yun/Documents/bt_api_py/bt_api/bt_api_base/src python -m py_compile src/bt_api_ctp/gateway/adapter.py tests/test_gateway_adapter_datetime.py`，在 `/home/yun/Documents/bt_api_ctp` 通过。
- `PYTHONPATH=/home/yun/Documents/bt_api_ctp/src:/home/yun/Documents/bt_api_py/bt_api/bt_api_base/src pytest -q tests/test_gateway_adapter_datetime.py`，结果 `2 passed in 0.15s`。
- 实际导入复验：`bt_api_ctp.gateway.adapter.__file__` 指向 `/home/yun/Documents/bt_api_ctp/src/bt_api_ctp/gateway/adapter.py`，`20260623 08:22:00.500 +08` 转换为 epoch `1782174120.5` 和 UTC `2026-06-23T00:22:00.500000+00:00`。
- 已用 `reports/ctp_timefix_rolling_supervisor.log` 与 `reports/mt5_timefix_rolling_supervisor.log` 完成一轮时间修复 rolling restart：CTP `2026-06-25 08:43:39 CST rolling restarted ... running=50 failed=0 process=50 heartbeat=50 stale=0 alerts=-`；MT5 `2026-06-25 08:43:41 CST rolling restarted ... running=50 failed=0 process=50 heartbeat=50 stale=0 alerts=-`。
- 时间修复后样例：CTP `datetime=2026-06-23T00:51:00.000+00:00 log_time=2026-06-25T08:44:41.664+08:00`；MT5 `datetime=2026-06-25T03:44:00.000+00:00 log_time=2026-06-25T08:45:00.974+08:00`，已不再出现旧的 `08:xx+00:00` / `11:xx+00:00` 墙钟误标。
- env 默认值修复后再次 rolling restart，最新全量分布为 CTP 50/50 `bar/value/position` 前缀 `2026-06-23T01`，MT5 50/50 前缀 `2026-06-25T04`；最终 direct monitor `2026-06-25 09:01:09 CST` 仍为双目标 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。

### 86. 当前运行导入源是独立 `/home/yun/Documents/bt_api_ctp`

现象：最初把 CTP 时间修复写入 `/home/yun/Documents/bt_api_py/bt_api/bt_api_ctp` 后，进一步用当前策略同类 `PYTHONPATH` 检查发现运行时导入路径实际为：

- `bt_api_ctp`: `/home/yun/Documents/bt_api_ctp/src/bt_api_ctp/__init__.py`
- `bt_api_ctp.gateway.adapter`: `/home/yun/Documents/bt_api_ctp/src/bt_api_ctp/gateway/adapter.py`
- `bt_api_mt5`: `/home/yun/Documents/bt_api_py/bt_api/bt_api_mt5/src/bt_api_mt5/__init__.py`
- `bt_api_base`: `/home/yun/Documents/bt_api_py/bt_api/bt_api_base/src/bt_api_base/__init__.py`

风险：子模块副本里的修复和测试会通过，但当前 CTP 策略进程不会加载它，导致 rolling restart 后仍使用旧时间语义。

修复：把 `_ctp_tick_timestamp_datetime()` 和对应测试同步到独立仓库 `/home/yun/Documents/bt_api_ctp`，并用实际导入路径复验 helper 行为。

验收：`/home/yun/Documents/bt_api_ctp` 下 `py_compile` 与 `pytest -q tests/test_gateway_adapter_datetime.py` 均通过；完成全量 rolling restart 后 50 个 CTP 单元最新日志全部从旧 `2026-06-23T08:*+00:00` 变为真实 UTC `2026-06-23T00/01:*+00:00`。

### 87. 替换 holding supervisor 时 SIGTERM 会误停 owned 单元

现象：全量 rolling restart 后的 supervisor 会进入长时间 hold。若为了替换 holder 对旧进程发送普通 SIGTERM，旧实现会在 finally 中停止它认为自己 owned 的目标单元。这样清理旧 holder 可能把刚重启好的 50 个策略单元也停掉。

修复：

- `run_dual_exchange_simulation.py` 增加 `--no-stop-owned-on-signal`。
- 新增 `handle_stop_signal(..., stop_owned_on_signal=True)`，默认保持旧行为；显式传入该 flag 时，收到 stop signal 只记录并退出 holder，不停止 owned 单元。
- 新增测试覆盖默认会停 owned 单元，以及 flag 打开时保留 owned 单元运行。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `PYTHONPATH=src/backend pytest -q src/backend/tests/test_run_dual_exchange_simulation.py`，结果 `29 passed in 2.15s`。
- 新 holder 命令均带 `--no-stop-owned-on-signal`；旧 holder `785202/785203` 已 SIGTERM 清理，随后 direct monitor 仍为 CTP/MT5 各 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。

### 88. 新策略子进程未带本地时区和轻量列默认 env

现象：完成时间修复 rolling restart 后，`/proc` 精确匹配 100 个 `workspace_units/.../run.py` 进程均存在，但抽样环境只有网关相关 `BT_*` 和 `BT_API_PY_LIGHT_IMPORT=1`，没有 `BT_STORE_LOCAL_TIMEZONE=Asia/Shanghai` 与 `BT_FEED_ENABLE_LIGHT_COLUMNS=1`。

风险：时间日志这次已由代码层修复，但后续新启动路径缺少统一 env 默认值，容易让 store/feed 的可配置运行口径与压测预期不一致。

修复：在 `src/backend/app/services/gateway/runtime.py` 的 `_LIVE_SUBPROCESS_THREAD_DEFAULTS` 中加入：

- `BT_STORE_LOCAL_TIMEZONE=Asia/Shanghai`
- `BT_FEED_ENABLE_LIGHT_COLUMNS=1`

实现继续使用 `setdefault`，外部显式 env 仍可覆盖。

验收：

- `python -m py_compile src/backend/app/services/gateway/runtime.py src/backend/tests/test_extracted_modules.py src/backend/tests/test_live_trading_manager.py` 通过。
- `PYTHONPATH=src/backend pytest -q src/backend/tests/test_extracted_modules.py::TestGatewayRuntimeService::test_build_subprocess_env_without_gateway src/backend/tests/test_extracted_modules.py::TestGatewayRuntimeService::test_build_subprocess_env_with_gateway`，结果 `2 passed`。
- `PYTHONPATH=src/backend pytest -q src/backend/tests/test_live_trading_manager.py::TestGatewayLifecycle::test_build_subprocess_env_prefers_local_source_paths src/backend/tests/test_live_trading_manager.py::TestGatewayLifecycle::test_build_subprocess_env_with_gateway src/backend/tests/test_live_trading_manager.py::TestGatewayLifecycle::test_build_subprocess_env_with_ib_web_gateway`，结果 `3 passed`。
- 已用 `reports/ctp_envfix_rolling_supervisor.log` 与 `reports/mt5_envfix_rolling_supervisor.log` 再做一轮全量 rolling restart：CTP `2026-06-25 09:00:12 CST rolling restarted ... running=50 failed=0 process=50 heartbeat=50 stale=0 alerts=-`；MT5 `2026-06-25 09:00:15 CST rolling restarted ... running=50 failed=0 process=50 heartbeat=50 stale=0 alerts=-`。
- 最终 `/proc` 精确匹配两个目标目录下 `run.py` 进程 `50+50=100`，`missing_local=0`、`missing_light=0`。

### 89. MT5 open trade 的 `datetime` 写成 Unix epoch 0

现象：继续扫真实 `trade.log` 时发现 MT5 单元 `2811635c-38b7-44f3-8525-fc43a02aa71a` 有 open trade 行写出 `datetime=1970-01-01T00:00:00.000+00:00`，但同一行 `log_time=2026-06-25T08:55:34.013+08:00` 且行情/持仓日志正常。

原因：`backtrader` `TradeLogger._format_trade()` 只从 observer owner datetime 取事件时间。open trade 的 `trade.dtopen` 可能为 `0`，owner datetime 在模拟启动窗口也可能返回平台零值，最终被格式化成 epoch 0。

修复：`/home/yun/Documents/backtrader/backtrader/observers/trade_logger.py` 新增 trade 时间字段归一化 helper：

- closed trade 优先使用 `trade.dtclose`，open trade 优先使用 `trade.dtopen`。
- 通过 `trade.data.num2date()` 转换 backtrader numdate，而不是按 Unix timestamp 解释。
- 零值或缺失时回退当前 data datetime、owner datetime、最后回退 `log_time`。
- JSON/text 两种 trade 输出都写入一致的 `datetime/dtopen/dtclose`。

验收：`/home/yun/Documents/backtrader` 下新增 open/closed trade 时间字段测试；`py_compile` 通过，`pytest tests/unit/observers/test_trade_logger_edge_cases.py -q` 结果 `28 passed`，`pytest tests/integration/test_trade_logger_runtime.py -q` 结果 `8 passed`，`pytest tests/unit/observers/test_trade_logger_monitoring.py tests/unit/observers/test_trade_logger_internal_errors.py -q` 结果 `5 passed`。全量 TradeLogger rolling restart 后复扫当前日志：CTP `trade_rows=8 open_rows=6 bad_1970=0`，MT5 `trade_rows=1448 open_rows=747 bad_1970=0`。

### 90. gateway 原生 stdio 重定向 contextmanager 掩盖 CTP ready 原始错误

现象：CTP TradeLogger rolling restart 第一批有 1 个单元失败，真实 native traceback 是 `RuntimeError: ctp market not ready`，但工作区快照里最终错误变成 `generator didn't stop after throw()`。

原因：`backtrader_web` 的 `_redirect_gateway_native_stdio()` 用 `@contextmanager` 时把 setup 失败 fallback 的 `yield` 放在覆盖整个 `yield` 的 `except OSError` 中。若被包裹代码抛错且 fd restore 又触发异常，contextmanager 会在 exception throw 路径二次 yield，掩盖原始 gateway ready 错误。

修复：`src/backend/app/services/gateway/runtime.py` 将 fd setup 失败和正常 `yield/finally` 分开；restore 阶段只 suppress `OSError` 并关闭 fd/handle，不再在 exception throw 路径 yield。新增回归测试断言 `build_subprocess_env()` 在 gateway ready 失败时保留原始 `runtime: ctp market not ready`。

验收：`python -m py_compile src/backend/app/services/gateway/runtime.py src/backend/tests/test_extracted_modules.py` 通过；`PYTHONPATH=src/backend pytest -q` 三个 gateway runtime 目标测试结果 `3 passed`。随后单工作区恢复日志已不再出现 `generator didn't stop after throw()`，失败原因能保留为真实 `ctp market not ready`。

### 91. CTP gateway 启动只尝试一次，瞬时 market 未 ready 会让单元长期 failed

现象：修复 contextmanager 后，失败 CTP 单元 `0b64cdc5-b443-496c-ace4-eeb66a50bba2` 的真实错误是 `ctp market not ready`。第一次单工作区恢复仍失败并进入 hold：`running=0 failed=1 process=0`。

原因：`/home/yun/Documents/bt_api_ctp/src/bt_api_ctp/gateway/adapter.py` 的 `CtpGatewayAdapter.connect()` 启动 market/trade stream 后只等待一次；任一 stream 在超时窗口内未 ready 就直接抛错，且失败路径没有明确清理半启动的 stream。在 50 单元 rolling restart 压力下，CTP market 连接存在瞬时未 ready 的运行窗口。

修复：适配器保留原默认语义，但在较长 `gateway_startup_timeout_sec` 下默认启用有限重试：

- 保存 stream kwargs，失败后 `_stop_startup_streams()` 并重建 market/trade/feed。
- `gateway_startup_timeout_sec>=30` 时默认 `startup_attempts=3`，每个 stream 的等待窗口按总预算拆分；也支持显式 `gateway_startup_attempts` 与 `gateway_startup_retry_backoff_sec`。
- 最终失败时抛出包含尝试次数和最后原因的 `RuntimeError`。

验收：`/home/yun/Documents/bt_api_ctp` 下 `py_compile` 通过；`pytest tests/test_gateway_adapter_startup.py tests/test_gateway_adapter_datetime.py -q` 结果 `3 passed`。重新启动单 CTP 工作区恢复 holder PID `836573` 后，`reports/ctp01_retryfix_recover_supervisor.log` 显示 `2026-06-25 09:27:40 CST started: ... running=1 failed=0 process=1 heartbeat=1`。全量 direct monitor `2026-06-25 09:29:37 CST` 恢复为 CTP/MT5 双目标 `running=50 failed=0 process=50 heartbeat=50 stale=0 alerts=-`。

### 92. runtime health 未检查交易数据日志，进程和心跳正常时可能漏报空策略

现象：继续复扫 CTP01 后发现，该单元在恢复 holder 下 `process=1 heartbeat=1 stale=0 no_log=0 alerts=-`，但 `bar.log`、`value.log`、`position.log`、`trade.log`、`order.log`、`signal.log` 均为 0 字节。也就是说策略主循环和独立 `heartbeat.json` 都正常更新，但当时还没有任何交易数据日志写出。

原因：`run_dual_exchange_simulation.py` 旧的 `runtime_health_counter()` 只用 `heartbeat.json` 和“任意日志 mtime”判断存活。`system.log`、`gateway.stderr.log` 或 heartbeat 自身增长时，`latest_log_age_seconds()` 会让 `no_log=0/stale=0`，但这不能证明策略已经产出 bar/value/position 这类核心交易数据。

修复：压测脚本新增交易数据日志健康口径：

- 只把 `bar.log`、`value.log`、`position.log` 纳入 `DATA_ACTIVITY_LOG_NAMES`。
- `latest_data_log_age_seconds()` 忽略缺失、空文件、目录和早于当前 session 的旧文件。
- `runtime_health_counter()` 在 session 预热窗口后统计 `data_log_fresh/data_log_stale/data_log_missing`。
- 状态行输出 `data_log=... data_stale=... data_missing=...`，并在 `resource_alerts()` 中加入 `data_log_stale` 与 `data_log_missing`。

验收：`py_compile` 通过；`PYTHONPATH=src/backend pytest src/backend/tests/test_run_dual_exchange_simulation.py -q` 结果 `31 passed`。修复后的 direct monitor 先准确暴露当时 CTP 全量 `data_log=49 data_missing=1 alerts=data_log_missing`；随后单 CTP01 rolling recovery holder PID `848678` 在 09:42:48 后输出 `data_log=1 data_missing=0 alerts=-`。最新全量 direct monitor `2026-06-25 09:45:17 CST` 已恢复为 CTP/MT5 双目标 `data_log=50 data_stale=0 data_missing=0 alerts=-`；长期只读 monitor 已重启到 PID `854273`，首次输出也包含 `data_log=50 data_missing=0 alerts=-`。

### 93. `--no-stop-owned-on-signal` 会让 gateway-backed 子策略失去进程内 gateway

现象：清理 CTP01 临时数据日志恢复 holder PID `848678` 后，CTP01 子策略 PID `848890` 仍存活，`heartbeat.json` 继续更新，但 `bar.log/value.log/position.log` 停在 `2026-06-25 09:45:02 +0800`。长期 monitor 随后显示 CTP `data_log=49 data_stale=1 alerts=data_log_stale`；其它 IF2609 单元仍继续写 bar，说明不是合约行情全局空窗。

原因：CTP/MT5 压测的 gateway runtime 是 supervisor 进程内线程，策略子进程通过 `BT_GATEWAY_*_ENDPOINT` 连接该 runtime。旧的 `--no-stop-owned-on-signal` 在 SIGTERM 时让 holder 退出但保留 owned 子策略，等价于关闭子策略依赖的进程内 gateway，同时留下还会写 heartbeat 的孤儿策略。旧 monitor 还没有把 `failed/idle/missing` 计入 alerts，导致后续 CTP01 重启失败时出现 `running=0 failed=1 process=0 alerts=-`。

修复：

- `--no-stop-owned-on-signal` 保留为兼容参数，但帮助文本标记为 deprecated。
- `handle_stop_signal()` 现在即使收到该参数，也会停止 owned target units，避免 gateway-backed 子策略在 owner supervisor 退出后继续空转。
- `resource_alerts()` 新增 `unit_failed/unit_idle/unit_missing`，失败或缺失目标单元不再显示 `alerts=-`。
- rolling restart 新增 `--rolling-batch-start-attempts` 与 `--rolling-batch-retry-wait-seconds`；每个 batch 只 stop 一次，后续只重试未成功 running 的 unit，避免单个 CTP market 瞬时未 ready 直接让该单元长期 failed。

验收：`py_compile` 通过；`PYTHONPATH=src/backend pytest src/backend/tests/test_run_dual_exchange_simulation.py -q` 结果 `32 passed`。先前失败 holder `reports/ctp01_gateway_holder_supervisor.log` 记录 `running=0 failed=1 ... alerts=-`，证明旧口径漏报；新版 holder PID `865311` 使用 `--rolling-batch-start-attempts 3` 启动，`reports/ctp01_gateway_holder_supervisor_v2.log` 显示 `rolling batch start attempt 1/3: running=1, failed=0`，并在 `2026-06-25 09:59:52 CST` 恢复为 `data_log=1 data_missing=0 alerts=-`。最新全量 direct monitor `2026-06-25 10:00:43 CST` 恢复 CTP/MT5 双目标 `data_log=50 data_stale=0 data_missing=0 alerts=-`。

注意：当前 CTP 全量 holder PID `822940` 与 MT5 全量 holder PID `823052` 是修复前用旧 `--no-stop-owned-on-signal` 参数启动的进程。不要直接对它们 SIGTERM；后续如需替换，应先用新版 rolling supervisor 接管对应 units，再清理旧 holder。

### 94. 旧 holder 停机只按 unit id，会误停已被新 holder 接管的子策略

现象：为了替换旧 holder，CTP 全量单元已用新版 rolling supervisor PID `875885` 重新接管。但旧 holder PID `822940`、CTP01 专项 holder PID `865311` 仍在自己的内存状态里记录了相同的 owned unit id。若此时对旧 holder 发送 SIGTERM，旧实现会按 unit id 调用 `stop_units()`，有可能停止已经由新 holder 持有的当前 `run.py` 子进程。

原因：`stop_owned_targets()` 旧口径只校验“这个 supervisor 曾启动过哪些 unit id”，没有校验“这些 unit id 当前的 live `run.py` 进程是否仍然是当前 supervisor 的子进程”。跨 supervisor rolling takeover 后，unit id 所有权和当前进程父子关系已经分离，单靠 unit id 不足以安全执行 stop。

修复：

- 新增 `process_parent_pid()` 与 `unit_has_process_owned_by_pid()`，从 `/proc/<pid>/status` 读取当前 `PPid`。
- `stop_owned_targets()` 接收当前 `owner_pid` 与 live process map，只停止当前 `run.py` PID 的父进程仍等于该 supervisor PID 的 unit。
- 若 owned unit id 都已被别的 holder 接管，则输出 `owned stop skipped: no current owned processes`，不再调用 `stop_units()`。
- 新增回归测试覆盖“同一 unit id 已被另一个 supervisor 重新持有时，旧 holder 不会 stop”。

验收：`py_compile` 通过；`PYTHONPATH=src/backend pytest src/backend/tests/test_run_dual_exchange_simulation.py -q` 结果 `35 passed`。CTP 新 holder `875885` 完成 13 批接管后，`/proc` 父进程校验显示 CTP 50 个 `run.py` 全部归 `875885`；旧 CTP holder PID `822940/865311` 已清理且未误停当前策略。

### 95. CTP 数据日志健康检查未区分交易小节静默窗口

现象：CTP 全量接管在 `2026-06-25 10:20 CST` 完成后，monitor 一度显示 `data_log=16 data_stale=16 data_missing=8 alerts=data_log_stale,data_log_missing`。同时 `running=50 process=50 heartbeat=50` 正常，且 CFFEX 日盘品种仍有新数据；告警集中出现在商品期货 `10:15-10:30` 小节休市窗口内。

原因：第 92 节新增的交易数据日志健康检查把任何 `bar/value/position` 停写都视为异常，但 CTP 不同品种存在交易时段差异。商品期货在 `10:15-10:30`、午休和日夜盘间隔内没有新 bar 是预期行为；CFFEX 股指/国债日盘品种的静默窗口又与商品期货不同。MT5 外汇符号则不应套用 CTP 静默规则。

修复：

- 从当前 unit 的 runtime `config.yaml` 读取 `live.symbol`，并用 `letters+digits` 规则识别 CTP 合约前缀。
- 新增 `is_ctp_data_quiet_time()`：`IF/IC/IH/IM/T/TF/TS/TL` 按 CFFEX 日盘窗口处理，其它 CTP 商品合约按商品期货日内小节、午休、日夜盘间隔处理。
- `runtime_health_counter()` 在 CTP 静默窗口内把 data log missing/stale 计入 `data_log_quiet`，不触发 `data_log_missing` 或 `data_log_stale`。
- `print_status()` 输出 `data_quiet=...`，便于区分“预期无行情”和“策略实际停写”。

验收：`PYTHONPATH=src/backend pytest src/backend/tests/test_run_dual_exchange_simulation.py -q` 结果 `35 passed`。修复后的长期 monitor 在 `2026-06-25 10:26:13 CST` 输出 CTP `data_log=20 data_stale=0 data_missing=0 data_quiet=30 alerts=-`；小节恢复后 direct monitor 在 `2026-06-25 10:31:19 CST` 输出 CTP `data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=-`。

### 96. CTP holding supervisor 进程仍运行旧监控口径，会继续写小节假告警

现象：代码和长期 monitor 已加载第 95 节的 `data_quiet` 修复，但 CTP holding supervisor PID `875885` 是该修复之前启动的进程。继续 tail `reports/ctp_all_ownerfix_rolling_supervisor.log` 可见它的 status 行仍没有 `data_quiet=...` 字段，并且在 `2026-06-25 10:15-10:30 CST` 商品期货小节里持续输出 `alerts=data_log_stale,data_log_missing`。同一时段新版长期 monitor 已正确输出 `data_quiet=30 alerts=-`，说明这是 holder 自监控进程版本漂移，而不是策略或行情异常。

原因：压测 holder 是长生命周期 Python 进程，脚本修复不会热加载进已运行的 holder。上一轮只重启了长期 monitor 和 MT5 holder；CTP holder 已经拥有 50 个 CTP gateway-backed 子策略，不能直接退出，否则会关闭进程内 gateway，因此必须用最新版脚本再次 rolling takeover。

修复：

- 启动新的 CTP 全量 rolling supervisor，使用当前 `run_dual_exchange_simulation.py`，参数继续保持 `--rolling-batch-start-attempts 3 --rolling-batch-retry-wait-seconds 30 --rolling-batch-wait-seconds 45`。
- 新 holder 分批 stop/start 并接管全部 50 个 CTP 子策略后，再按当前进程所有权校验清理旧 holder `875885`。
- 后续验收以新 holder 自身 status 行、长期 monitor、direct monitor 和 `/proc` 父进程归属共同确认。

验收：新 CTP holder PID `906679` 在 `reports/ctp_all_quietfix_rolling_supervisor.log` 完成 13 批 rolling takeover；第 1 批首轮 1 个 unit 因 `ctp market not ready` 失败，30 秒后重试成功，后续批次均 `failed=0`。新 holder 自身从每批 check 到 holding status 都输出 `data_quiet=...`；`2026-06-25 10:55:54 CST rolling restarted` 为 `running=50 process=50 heartbeat=50 data_log=40 data_quiet=0 alerts=-`，数据日志暖机后在 `2026-06-25 10:58:25 CST` 与 `10:58:56 CST` 连续输出 `data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=-`。严格 `/proc` 父进程复验为 CTP `{'906679': 50}`，旧 CTP holder `875885` 不在进程表；`2026-06-25 10:59:07 CST` direct monitor 中 CTP/MT5 均为 `data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=-`，认证后 API 仍为 CTP/MT5 各 50 running、各 50 positions、组合 `strategy_count=100 running_count=100`。

### 97. split supervisor pidfile 只校验 PID 存活，PID 复用时可能误报 holder

现象：第 96 节完成后，`.pids/` 中只有 `ctp_all_quietfix_rolling_supervisor.pid` 与 `mt5_all_ownerfix_rolling_supervisor.pid` 对应真实 holder，但历史滚动重启遗留了大量 `*supervisor.pid` 文件。旧 `ensure_dual_stress_running.sh status` 在扫描 split supervisor pidfile 时只用 `ps -p` 判断 PID 是否存在；如果旧 PID 被系统复用给无关进程，脚本可能误报该无关进程为 split supervisor，`start` 路径也可能因此拒绝启动必要的 dual supervisor。

原因：`status_split_supervisors()` 与 `first_split_supervisor_pid()` 只调用 `is_running()`，没有校验 `/proc/<pid>/cmdline` 是否为 `run_dual_exchange_simulation.py`，也没有清理 stale split pidfile。主 supervisor/monitor pidfile 的复用校验同样偏弱。

修复：

- 新增 `pid_matches_mode()`，对 pidfile 中的 PID 同时校验 cmdline 包含 `src/backend/scripts/run_dual_exchange_simulation.py`、mode 匹配 supervisor/monitor、不是 `--no-hold` 临时进程；主 dual supervisor/monitor 还要求 `--targets ${TARGETS}` 匹配。
- split supervisor pidfile 校验不强制匹配 `TARGETS`，以兼容当前 CTP/MT5 拆分 holder；但若 PID 不存在或 cmdline 不匹配，会删除该 stale/invalid pidfile。
- 设置 `DUAL_STRESS_SUPERVISOR_PID_FILES` 时只检查显式给出的 pidfile，不再额外发现环境中的真实 split holder，避免测试和定向运维命令被现场其它 holder 干扰。

验收：`bash -n scripts/ops/ensure_dual_stress_running.sh` 通过；`PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q` 结果 `7 passed`。真实执行 `TARGETS=futures,mt5 PYTHON_BIN=/home/yun/anaconda3/bin/python scripts/ops/ensure_dual_stress_running.sh status` 输出 CTP split PID `906679`、MT5 split PID `889556`、monitor PID `889932`，并在 `2026-06-25 11:09:40 CST` 保持 CTP/MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；执行后 `.pids/*supervisor.pid` 只剩两个 live 文件：`ctp_all_quietfix_rolling_supervisor.pid` 与 `mt5_all_ownerfix_rolling_supervisor.pid`。

### 98. MT5 broker server wall time 仍被当成 UTC epoch，组合时间轴未来 3 小时

现象：继续抽样当前压测日志时，CTP 已正常把交易所本地时间转成 UTC，但 MT5 仍把 broker 服务器墙钟时间标成 UTC。`2026-06-25 11:12 CST` 附近，当前 UTC 为 `2026-06-25T03:12:45Z`，CTP 最新 bar 为 `datetime=2026-06-25T03:11:00.000+00:00 log_time=2026-06-25T11:12:01+08:00`，而 MT5 最新 bar 为 `datetime=2026-06-25T06:11:00.000+00:00 log_time=2026-06-25T11:12:00+08:00`。组合权益 API 的最新点也推进到 `2026-06-25T06:11:00.000+00:00`，相对真实 UTC 未来约 3 小时。

原因：`bt_api_mt5` 适配器把 `pymt5` 返回的 `rate.time` 与实时 `tick_time/tick_time_ms` 直接作为 Unix UTC epoch 输出；`backtrader` store/feed 再按 UTC epoch 正常解析。`pymt5` 账户信息实际暴露 `server_offset_time = timezone_shift + daylight_mode * 3600`，MetaQuotes demo 当前为 UTC+3，但适配器未使用该偏移将 MT5 服务器时间归一为真实 UTC。

修复：在 `/home/yun/Documents/bt_api_py/bt_api/bt_api_mt5/src/bt_api_mt5/gateway/adapter.py` 中连接后读取 `terminal_info()` / `get_account()` 的 `server_offset_time`，并把历史 bar `time`、实时 tick `tick_time_ms/tick_time` 统一减去该偏移后再输出给 `GatewayTick` / `BtApiStore`。该修复保留 `server_offset_time=0` 的 UTC broker 行为，也支持通过适配器 kwargs 显式传入 offset。

验收：

- `/home/yun/Documents/bt_api_py/bt_api/bt_api_mt5` 中 `py_compile` 通过，新增 `tests/test_gateway_adapter_time.py` 结果 `3 passed`；`git diff --check` 无输出。
- 使用 `reports/mt5_all_timefix_rolling_supervisor.log` 只滚动接管 MT5 50 个策略，新 holder PID `992775` 在 `2026-06-25 11:31:38 CST` 输出 `rolling restarted ... running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=40 ... alerts=-`，并在 `2026-06-25 11:34:10 CST` 升至 `data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=-`。
- 严格 `/proc` 父进程复验：CTP `{'906679': 50}`、MT5 `{'992775': 50}`；旧 MT5 holder `889556` 在确认不再拥有子进程后已 SIGTERM 清理。
- 活动日志时间复验：MT5 50 个活动 `bar.log` 最新 `datetime` 全部为 `2026-06-25T03:34:00+00:00`，`future_gt_120s=0`；CTP 50 个活动 `bar.log` 最新为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，午间休市后静默但无告警。
- 认证后 API 复验：`/api/v1/portfolio/equity` 与 `/api/v1/portfolio/simulation/equity` 均为 `dates=260 strategies=100 latest=2026-06-25T03:35:00+00:00 future_gt_120s=0`；`/api/v1/portfolio/positions` 为 `total=100 dated_positions=100 latest=2026-06-25T03:35:00.000+00:00`。

### 99. ensure start 模式只报告首个 split holder，容易误判另一个 holder 状态

现象：继续巡检时直接执行 `bash scripts/ops/ensure_dual_stress_running.sh start`，脚本正确拒绝启动新的 dual supervisor，但输出只有 `split stress supervisor already running: pid=906679; not starting dual stress supervisor`。真实 `/proc` 复验显示 MT5 holder `992775` 同样拥有 50 个子进程，说明运行态正常，但 `start` 输出缺少 MT5 split holder，容易让自动巡检或人工值守误判为只剩 CTP holder。

原因：`start_supervisor()` 调用 `first_split_supervisor_pid()` 后，只输出第一个可复用 split supervisor 并立即返回；完整的 `status_split_supervisors()` 只在 `status` 动作中调用。

修复：`start_supervisor()` 在 `NO_START_IF_SPLIT_SUPERVISOR=1` 且发现 split holder 时，仍保持不启动新的 dual supervisor，但会继续调用 `status_split_supervisors()` 输出所有已运行 split holder pidfile/发现结果。

验收：`PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q` 结果 `8 passed`。真实执行 `bash scripts/ops/ensure_dual_stress_running.sh start && bash scripts/ops/ensure_dual_stress_running.sh status` 输出 CTP split PID `906679`、MT5 split PID `992775`、monitor PID `889932`，未启动新的 dual supervisor；随后 direct monitor `2026-06-25 12:09:43 CST` 保持 CTP/MT5 双目标 `running=50 process=50 heartbeat=50 alerts=-`。

### 100. CTP 交易数据停写但心跳正常时，滚动重启不能定向恢复 stale-data 单元

现象：`2026-06-25 14:44 CST` 继续巡检时，CTP holder 日志出现 `CThostFtdcUserApiImplBase::OnSessionDisconnected[...][8193]`，随后状态从健康变为 `data_log=5 data_stale=45 alerts=data_log_stale`。45 个单元仍有进程和心跳，但 `bar/value/position` 最新业务时间停在 `2026-06-25T06:40:00+00:00`，只有 5 个 `m2609` 单元继续写入。MT5 同期仍为 `running=50 process=50 data_log=50 alerts=-`。

原因：压测脚本已经能用交易数据日志识别 `data_log_stale`，但滚动重启选择器只有 `--skip-fresh-heartbeats`，只按心跳过滤。数据停写但心跳仍新的单元不会被精确挑出；如果直接全量滚动，又会不必要地重启仍在正常写入的单元。

修复：

- `run_dual_exchange_simulation.py` 增加 `--skip-fresh-data-logs`。
- 新增 `unit_data_log_state()`，把单元按交易数据日志状态归为 `not_running/warmup/quiet/missing/fresh/stale`。
- `filter_units_for_rolling_restart()` 在启用该参数时跳过 `fresh/quiet/warmup`，只选择 stale/missing 等需要恢复的单元。
- `rolling_restart_targets()` 与 CLI 参数透传该新过滤条件，并新增回归测试覆盖 fresh data log 会被跳过。

现场处置：

- 用 `--rolling-restart --skip-fresh-data-logs` 定向恢复 stale-data CTP 单元；恢复后状态回到 `running=50 process=50 heartbeat=50 data_stale=0 alerts=-`。
- 由于普通 `nohup &` 子进程会被当前执行环境清理，最终使用 `setsid -f` 启动持久 CTP 全量重整 holder：PID `1324657`，日志 `reports/ctp_reconsolidate_rolling_supervisor.log`。
- 新 holder 完成 13 批接管后，旧 CTP holder `906679` 和临时恢复 holder `1319947` 均已退出；严格 `/proc` 父进程复验为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`。

验收：

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `36 passed in 2.88s`。
- 最新 `ensure_dual_stress_running.sh status` 为 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`。CTP 的 `data_quiet=50` 出现在 15:00 后，属于交易小节安静窗口而非 stale。

### 101. 组合成交 API 的 `datetime` 被截成日期，丢失分钟级成交时间

现象：继续复验真实 `/api/v1/portfolio/trades?limit=1000` 时，返回 `total=1619 returned=1000 date_only_datetime=1000`。每条成交的 `dtopen/dtclose` 都有完整分钟级时间，例如 `2026-06-25T07:34:00+00:00`，但主字段 `datetime` 被降级成 `2026-06-25`。前端当前主要按 `dtclose/dtopen` 排序和展示，因此页面没有立即错乱；但 API 调用方或前端 fallback 使用 `datetime` 时会丢失日内顺序和真实平仓时间。

原因：`parse_trade_log()` 的 JSON/pipe 分支把成交输出中的 `datetime` 设置为 `_normalize_date_text(item.get("dtclose"))`；传统 TSV 分支也对 `dtopen/dtclose/datetime` 使用 `.split(" ")[0]`。该日级归一化适合早期日线回测，但不适合当前 1 分钟级 CTP/MT5 模拟交易日志。

修复：

- `src/backend/app/services/log_parser_service.py` 中 JSON/pipe 成交输出的 `datetime` 改为 `_normalize_dt_text(item.get("dtclose"))`。
- 传统 TSV 成交输出的 `datetime/dtopen/dtclose` 也改为保留完整文本，不再截断到日期。
- `src/backend/tests/test_log_parser.py` 增加 JSON simulate 日志和 TSV 日志的分钟级时间断言。

验收：

- `python -m py_compile src/backend/app/services/log_parser_service.py src/backend/tests/test_log_parser.py` 通过。
- `python -m pytest src/backend/tests/test_log_parser.py src/backend/tests/test_log_parser_extended.py -q`，结果 `49 passed in 3.81s`。
- `python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `28 passed in 2.35s`。
- `PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/restart_app.sh` 已重启后端到 PID `1379305` 并启动前端 PID `1379375`。
- 重启后真实接口验收：`/portfolio/trades?limit=20` 返回 `total=1624 returned=20 date_only_datetime=0`，样例 `datetime=2026-06-25T07:36:00.000+00:00 dtclose=2026-06-25T07:36:00.000+00:00`；`/health` 和前端 `/` 均返回 200。
- 重启未影响压测进程：`ensure_dual_stress_running.sh status` 仍为 CTP `running=50 process=50 heartbeat=50 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`。

## 本轮验收命令（含较早阶段输出）

- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py`，本轮 `--skip-fresh-data-logs` 修复后通过。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，本轮 `--skip-fresh-data-logs` 修复后结果 `36 passed in 2.88s`。
- `/home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --rolling-restart --rolling-batch-size 4 --rolling-batch-wait-seconds 1 --rolling-batch-start-attempts 1 --rolling-batch-retry-wait-seconds 1 --skip-fresh-data-logs --hold-seconds 1`，现场恢复 stale-data CTP 单元，最终输出 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=5 data_stale=0 data_missing=0 data_quiet=0 alerts=-`，随后 warmup 到 `data_log=50 data_stale=0 alerts=-`。
- `setsid -f bash -c 'exec /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --rolling-restart --rolling-batch-size 4 --rolling-batch-wait-seconds 15 --rolling-batch-start-attempts 2 --rolling-batch-retry-wait-seconds 20 --hold-seconds 604800 > reports/ctp_reconsolidate_rolling_supervisor.log 2>&1'`，启动持久 CTP 重整 holder PID `1324657`；最终 `2026-06-25 14:59:09 CST rolling restarted ... running=50 process=50 heartbeat=50 data_stale=0 alerts=-`。
- `scripts/ops/ensure_dual_stress_running.sh status`，最新 `2026-06-25 15:09:57 CST` 结果：CTP `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=0 data_stale=0 data_missing=0 data_quiet=50 alerts=-`；MT5 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=-`。
- 严格 `/proc` 父进程复验：CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 `100` 个 `workspace_units/.../run.py` 子进程。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q`，ensure start split holder 全量报告修复后结果 `8 passed`。
- `bash scripts/ops/ensure_dual_stress_running.sh start && bash scripts/ops/ensure_dual_stress_running.sh status`，最新 `2026-06-25 12:09:43 CST` 结果：CTP split PID `906679`、MT5 split PID `992775`、monitor PID `889932`；CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`，MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`。
- `/home/yun/anaconda3/bin/python -m py_compile src/bt_api_mt5/gateway/adapter.py tests/test_gateway_adapter_time.py`，在 `/home/yun/Documents/bt_api_py/bt_api/bt_api_mt5` 通过。
- `PYTHONPATH=/home/yun/Documents/bt_api_py/bt_api/bt_api_base/src:/home/yun/Documents/bt_api_py/bt_api/bt_api_mt5/src /home/yun/anaconda3/bin/python -m pytest tests/test_gateway_adapter_time.py -q`，结果 `3 passed`。
- `rg -n "self\\.logger\\.(info|warning|debug|error)\\([^\\n]*," src/bt_api_mt5/gateway/adapter.py` 无输出；`git diff --check -- src/bt_api_mt5/gateway/adapter.py tests/test_gateway_adapter_time.py` 无输出。
- `reports/mt5_all_timefix_rolling_supervisor.log` 显示 MT5 timefix holder `992775` 完成 13 批 rolling takeover；最终 `2026-06-25 11:34:10 CST status: MT5模拟工作区 running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=-`。
- `TARGETS=futures,mt5 PYTHON_BIN=/home/yun/anaconda3/bin/python scripts/ops/ensure_dual_stress_running.sh status`，最新 `2026-06-25 11:37:36 CST` 结果：CTP `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=0 data_stale=0 data_missing=0 data_quiet=50 alerts=- cpu=3.0% rss=2518.9MB pss=1604.0MB uss=1595.6MB`；MT5 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=- cpu=5.9% rss=2529.9MB pss=1616.9MB uss=1608.5MB`。
- 活动日志扫描脚本结果：MT5 `active=50 ok=50 bad=0 future_gt_120s=0 latest=2026-06-25T03:34:00+00:00`；CTP `active=50 ok=50 bad=0 future_gt_120s=0 latest_min=2026-06-25T03:28:00+00:00 latest_max=2026-06-25T03:29:00+00:00`。
- 本地 API 登录后复验：`/portfolio/overview status=200 strategy_count=100 running_count=100 total_assets=50499808.27`，`/portfolio/equity status=200 dates=260 strategies=100 latest=2026-06-25T03:35:00+00:00 future_gt_120s=0`，`/portfolio/positions status=200 total=100 dated_positions=100 latest=2026-06-25T03:35:00.000+00:00`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py`，在本仓库通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `35 passed`。
- `bash -n scripts/ops/ensure_dual_stress_running.sh` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `7 passed`。
- `TARGETS=futures,mt5 PYTHON_BIN=/home/yun/anaconda3/bin/python scripts/ops/ensure_dual_stress_running.sh status`，最新 `2026-06-25 11:09:40 CST` 结果：CTP `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=- cpu=3.6% rss=2514.4MB pss=1599.6MB uss=1591.2MB`；MT5 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=- cpu=4.6% rss=2540.5MB pss=1626.8MB uss=1618.4MB`。
- CTP quietfix 新 holder `906679` 使用 `--rolling-batch-start-attempts 3 --rolling-batch-retry-wait-seconds 30` 完成全量 13 批 takeover；首批 1 个临时 `ctp market not ready` 失败在第 2 次尝试恢复，最终 `2026-06-25 10:55:54 CST rolling restarted ... running=50 process=50 heartbeat=50 ... alerts=-`，并在 `10:58:25/10:58:56 CST` 连续 status `data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=-`。
- 严格 `/proc` 父进程复验：`ctp {'906679': 50}`、`mt5 {'889556': 50}`；`ps -p 752932,875885,906679,889556,889932` 只显示后端 `752932`、CTP holder `906679`、MT5 holder `889556` 和长期 monitor `889932`，旧 CTP holder `875885` 不在进程表。
- CTP 新 holder `875885` 使用 `--rolling-batch-start-attempts 3 --rolling-batch-retry-wait-seconds 30` 完成全量 13 批 ownerfix rolling takeover；严格 `/proc` 父进程复验为 `ctp {'875885': 50}`，旧 holder `822940/865311` 不在进程表。
- MT5 新 holder `889556` 使用同样参数完成全量 13 批 ownerfix rolling takeover；`reports/mt5_all_ownerfix_rolling_supervisor.log` 最终输出 `2026-06-25 10:35:49 CST rolling restarted ... running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 ... alerts=-`，严格 `/proc` 父进程复验为 `mt5 {'889556': 50}`，旧 holder `823052` 已 SIGTERM 清理且不在进程表。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，最新 `2026-06-25 10:59:07 CST` 结果：CTP `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=- cpu=4.7% rss=2508.6MB pss=1596.3MB uss=1587.9MB`；MT5 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=50 stale=0 no_log=0 data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=- cpu=4.7% rss=2538.4MB pss=1624.8MB uss=1616.4MB`。
- `reports/dual_stress_monitor_7d.log` 最新 tail 到 `2026-06-25 11:00:22 CST` 已连续输出 CTP/MT5 双目标 `data_log=50 data_stale=0 data_missing=0 data_quiet=0 alerts=-`。
- `curl -fsS http://127.0.0.1:8000/health` 返回 `status=healthy database=connected`。
- 认证后 API 最新验收：CTP `units=50 run_status={'running': 50} errors=0 positions=50 missing_updated_at=0 missing_data_time=0`；MT5 `units=50 run_status={'running': 50} errors=0 positions=50 missing_updated_at=0 missing_data_time=0`；组合 overview `strategy_count=100 running_count=100 total_assets=50499963.53 total_pnl=-36.47`；portfolio positions `total=100 missing_updated_at=0 missing_data_time=0`。
- 活动错误日志复扫：CTP `error.log=0 subprocess.stderr.log=0 gateway.stderr.log=1`，唯一非空 gateway stderr 仍是原生 DMI/`/dev/mem` 权限 warning；MT5 三类错误日志均为 0。
- `git diff --check -- BACKTRADER_WEB_STRESS_MONITORING.md src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py` 无输出；三个未跟踪文件的额外 trailing whitespace 扫描结果为 `whitespace_issues 0`。
- `/home/yun/anaconda3/bin/python -m py_compile backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py`，在 `/home/yun/Documents/backtrader` 通过。
- `/home/yun/anaconda3/bin/python -m pytest tests/unit/observers/test_trade_logger_edge_cases.py -q`，在 `/home/yun/Documents/backtrader` 结果 `28 passed`。
- `/home/yun/anaconda3/bin/python -m pytest tests/integration/test_trade_logger_runtime.py -q`，在 `/home/yun/Documents/backtrader` 结果 `8 passed`。
- `/home/yun/anaconda3/bin/python -m pytest tests/unit/observers/test_trade_logger_monitoring.py tests/unit/observers/test_trade_logger_internal_errors.py -q`，在 `/home/yun/Documents/backtrader` 结果 `5 passed`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/gateway/runtime.py src/backend/tests/test_extracted_modules.py`，在本仓库通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest -q src/backend/tests/test_extracted_modules.py::TestGatewayRuntimeService::test_build_subprocess_env_captures_gateway_wait_native_stderr src/backend/tests/test_extracted_modules.py::TestGatewayRuntimeService::test_build_subprocess_env_preserves_gateway_ready_error src/backend/tests/test_extracted_modules.py::TestGatewayRuntimeService::test_wait_gateway_runtime_ready_raises_runtime_error_detail`，结果 `3 passed`。
- `/home/yun/anaconda3/bin/python -m py_compile src/bt_api_ctp/gateway/adapter.py tests/test_gateway_adapter_startup.py`，在 `/home/yun/Documents/bt_api_ctp` 通过。
- `/home/yun/anaconda3/bin/python -m pytest tests/test_gateway_adapter_startup.py tests/test_gateway_adapter_datetime.py -q`，在 `/home/yun/Documents/bt_api_ctp` 结果 `3 passed`。
- CTP 单工作区恢复：`reports/ctp01_retryfix_recover_supervisor.log` 显示 `2026-06-25 09:27:40 CST started: ... running=1 failed=0 process=1 heartbeat=1`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，最新 `2026-06-25 09:29:37 CST` 结果：CTP `running=50 failed=0 process=50 heartbeat=50 stale=0 alerts=- cpu=3.7% rss=2497.1MB pss=1586.2MB uss=1577.8MB`；MT5 `running=50 failed=0 process=50 heartbeat=50 stale=0 alerts=- cpu=6.3% rss=2533.3MB pss=1620.4MB uss=1612.0MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py`，在本仓库通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `31 passed`。
- `git diff --check -- BACKTRADER_WEB_STRESS_MONITORING.md src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py`，无输出。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures --unit-ids 0b64cdc5-b443-496c-ace4-eeb66a50bba2 --no-hold`，`2026-06-25 09:43:10 CST` 结果：`running=1 process=1 heartbeat=1 no_log=0 data_log=1 data_stale=0 data_missing=0 alerts=-`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，最新 `2026-06-25 09:45:17 CST` 结果：CTP `running=50 failed=0 process=50 heartbeat=50 no_log=0 data_log=50 data_stale=0 data_missing=0 alerts=- cpu=3.1% rss=2508.7MB pss=1594.8MB uss=1586.5MB`；MT5 `running=50 failed=0 process=50 heartbeat=50 no_log=0 data_log=50 data_stale=0 data_missing=0 alerts=- cpu=5.4% rss=2540.0MB pss=1626.9MB uss=1618.7MB`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，新增 holder signal 与 rolling batch retry 修复后结果 `32 passed`。
- `reports/ctp01_gateway_holder_supervisor.log` 记录旧口径失败样例：`rolling batch start: running=0, failed=1`，随后 `running=0 failed=1 process=0 alerts=-`。
- `setsid /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --unit-ids 0b64cdc5-b443-496c-ace4-eeb66a50bba2 --rolling-restart --rolling-batch-size 1 --rolling-batch-start-attempts 3 --rolling-batch-retry-wait-seconds 30 --rolling-batch-wait-seconds 90 --hold-seconds 604800 --status-interval 30 > reports/ctp01_gateway_holder_supervisor_v2.log 2>&1 &`，新版 CTP01 holder PID `865311`。
- `reports/ctp01_gateway_holder_supervisor_v2.log` 显示 `2026-06-25 09:56:51 CST ... rolling batch start attempt 1/3: running=1, failed=0`；`2026-06-25 09:59:52 CST status: ... data_log=1 data_missing=0 alerts=-`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures --unit-ids 0b64cdc5-b443-496c-ace4-eeb66a50bba2 --no-hold`，`2026-06-25 10:00:43 CST` 结果：`running=1 failed=0 process=1 heartbeat=1 no_log=0 data_log=1 data_stale=0 data_missing=0 alerts=-`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，`2026-06-25 10:00:43 CST` 结果：CTP `running=50 failed=0 process=50 heartbeat=50 no_log=0 data_log=50 data_stale=0 data_missing=0 alerts=- cpu=3.0% rss=2513.6MB pss=1599.7MB uss=1591.4MB`；MT5 `running=50 failed=0 process=50 heartbeat=50 no_log=0 data_log=50 data_stale=0 data_missing=0 alerts=- cpu=5.1% rss=2541.8MB pss=1628.9MB uss=1620.5MB`。
- 长期 monitor 已从 PID `854273` 重启到 PID `870009`，`reports/dual_stress_monitor_7d.log` 最新首次输出 `2026-06-25 10:02:41 CST monitor: ... data_log=50 data_missing=0 alerts=-`。
- CTP01 runtime 文件 mtime 验收：`bar.log/value.log/position.log` 均更新到 `2026-06-25 10:03:01 +0800`，`heartbeat.json` 更新到 `2026-06-25 10:02:51 +0800`。
- `curl -fsS http://127.0.0.1:8000/health` 返回 `status=healthy database=connected`。
- 认证后组合 API 验收：overview `strategy_count=100 running_count=100`；positions `total=100 missing_updated_at=0`。
- 长期 monitor 已从旧 PID `717756` 重启到 PID `854273`，`reports/dual_stress_monitor_7d.log` 首次输出 `2026-06-25 09:45:45 CST monitor: ... data_log=50 data_missing=0 alerts=-`；临时 CTP01 数据日志恢复 holder PID `848678` 已 SIGTERM 清理。
- `curl -fsS http://127.0.0.1:8000/health` 返回 `status=healthy database=connected`。
- 认证后组合 API 验收：overview `strategy_count=100 running_count=100`；positions `total=100 missing_updated_at=0`。
- 认证后 API 验收：CTP `status_total=50 {'running': 50} errors=0 positions_total=50`；MT5 `status_total=50 {'running': 50} errors=0 positions_total=50`。
- TradeLogger 运行日志复扫：CTP `trade_rows=8 open_rows=6 bad_1970=0`；MT5 `trade_rows=1448 open_rows=747 bad_1970=0`。
- `/home/yun/anaconda3/bin/python -m py_compile backtrader/feeds/btapifeed.py backtrader/stores/btapistore.py tests/unit/feeds/test_btapifeed.py tests/unit/stores/test_btapistore.py`，在 `/home/yun/Documents/backtrader` 通过。
- `/home/yun/anaconda3/bin/python -m pytest tests/unit/feeds/test_btapifeed.py tests/unit/stores/test_btapistore.py -q`，在 `/home/yun/Documents/backtrader` 结果 `138 passed, 1 skipped`。
- `PYTHONPATH=/home/yun/Documents/bt_api_py/bt_api/bt_api_ctp/src:/home/yun/Documents/bt_api_py/bt_api/bt_api_base/src /home/yun/anaconda3/bin/python -m py_compile bt_api/bt_api_ctp/src/bt_api_ctp/gateway/adapter.py bt_api/bt_api_ctp/tests/test_gateway_adapter_datetime.py`，在 `/home/yun/Documents/bt_api_py` 通过。
- `PYTHONPATH=/home/yun/Documents/bt_api_py/bt_api/bt_api_ctp/src:/home/yun/Documents/bt_api_py/bt_api/bt_api_base/src /home/yun/anaconda3/bin/python -m pytest bt_api/bt_api_ctp/tests/test_gateway_adapter_datetime.py -q`，结果 `2 passed, 1 warning`。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，最新 `2026-06-25 08:23:26 CST` 结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.5% rss=2501.6MB pss=1588.7MB uss=1580.3MB log=3.1MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=4.6% rss=2531.0MB pss=1618.1MB uss=1609.7MB log=12.6MB`。
- `reports/dual_stress_monitor_7d.log` 最新 tail（`2026-06-25 08:26:56 CST`）：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2502.2MB pss=1589.4MB uss=1580.9MB log=3.4MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=4.6% rss=2531.3MB pss=1618.5MB uss=1610.0MB log=12.8MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/process_supervisor.py src/backend/tests/test_process_supervisor.py src/backend/app/services/gateway/manual.py src/backend/app/services/gateway/health.py src/backend/tests/test_extracted_modules.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_process_supervisor.py -q`，结果 `14 passed`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_extracted_modules.py -q -k 'connect_gateway_reuses_existing_shared_session_and_promotes_manual or connect_gateway_switches_to_reachable_current_simnow_front or connect_gateway_returns_clear_error_when_all_current_simnow_fronts_unreachable or connect_gateway_keeps_requested_simnow_front_when_proxy_tunnel_available or get_gateway_health_returns_runtime_snapshot'`，结果 `5 passed, 112 deselected`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_process_supervisor.py src/backend/tests/test_live_instance_service.py src/backend/tests/test_extracted_modules.py -q`，结果 `154 passed, 2 skipped`。
- `scan_running_strategy_pids()` 真实现场复验：`total=100 workspace_units=100`。
- `scripts/ops/ensure_dual_stress_running.sh status`，最新 `2026-06-25 08:11:13 CST` 结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.6% rss=2499.6MB pss=1586.7MB uss=1578.3MB log=2.3MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=4.7% rss=2529.2MB pss=1616.3MB uss=1607.9MB log=11.7MB`。
- 已用 `setsid` 重启后端 uvicorn 到 PID `752932`；`GET /health` 返回 `200`，认证后组合 overview `strategy_count=100 running_count=100 total_assets=50500010.08 total_pnl=10.08`，positions `total=100 missing_updated_at=0 missing_data_time=0`。
- 新 PID 日志复扫：从 `Started server process [752932]` 之后 `ERROR=0 Traceback=0 RuntimeWarning=0 overflow encountered=0 ModuleNotFoundError=0 Address already in use=0`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/log_parser_service.py src/backend/tests/test_log_parser_extended.py` 通过。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_log_parser_extended.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_portfolio_api.py -q`，结果 `105 passed`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python - <<'PY' ...` 逐个解析 MT5 50 个真实 `logs/` 并捕获 warning，结果 `overflow_warning_dirs=0`。
- `/proc` 精确匹配 100 个 `workspace_units/.../run.py` 子进程，结果 `matched_processes=100 missing_local_count=0 missing_light_count=0`。
- `scripts/ops/ensure_dual_stress_running.sh status`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=4.3% rss=2494.0MB pss=1583.6MB uss=1575.2MB log=1.1MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=5.3% rss=2523.3MB pss=1610.4MB uss=1602.0MB log=10.5MB`。
- 已仅重启后端 uvicorn 到 PID `722265`；`GET /health` 返回 `200`，认证后组合 overview `strategy_count=100 running_count=100 total_assets=50500146.42 total_pnl=146.42`，positions `total=100 missing_updated_at=0 missing_data_time=0`。
- 新 PID 日志复扫：从 `Started server process [722265]` 之后 `ERROR=0 Traceback=0 RuntimeWarning=0 overflow encountered=0`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/log_parser_service.py src/backend/app/api/portfolio/api.py src/backend/app/services/trading_workspace_service.py src/backend/app/schemas/trading.py src/backend/tests/test_log_parser_extended.py src/backend/tests/test_portfolio_api.py src/backend/tests/test_trading_workspace_service.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_log_parser_extended.py src/backend/tests/test_portfolio_api.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `77 passed`。
- `npm test -- --run src/__tests__/api/portfolio.test.ts src/__tests__/views/PortfolioPage.test.ts`，结果 `2 files passed, 25 tests passed`。
- `npm run typecheck`，结果通过。
- `npm run build`，结果通过；仅保留既有 Vite 大 chunk warning。
- 已仅重启后端 uvicorn 到 PID `675412`；`GET /health` 返回 `200`，进程 `SID=675412` 持续存活。
- 真实 API 复验：overview `strategy_count=100 running_count=100 total_assets=50500481.77 total_pnl=481.77 total_position_value=709453.74 net_position_value=-687886.94`；组合 positions `total=100 missing_updated_at=0 missing_data_time=0 updated_prefixes={'2026-06-25': 100} data_prefixes={'2026-06-25': 50, '2026-06-23': 50}`。
- 工作区 positions 复验：MT5 `rows=50 missing_updated_at=0 missing_data_time=0 updated_prefixes={'2026-06-25': 50} data_prefixes={'2026-06-25': 50}`；CTP `rows=50 missing_updated_at=0 missing_data_time=0 updated_prefixes={'2026-06-25': 50} data_prefixes={'2026-06-23': 50}`。
- `PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/ensure_dual_stress_running.sh status`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2510.2MB pss=1600.0MB uss=1591.8MB log=16.5MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2545.4MB pss=1634.2MB uss=1626.0MB log=24.8MB`。
- 新 PID 日志复扫：从 `Started server process [675412]` 之后无 ERROR、Traceback、UserWarning 或 slow request；仅保留既有结构化默认管理员密码 WARNING。
- `npm test -- --run src/__tests__/views/PortfolioPage.test.ts`，结果 `18 passed`。
- `npm run typecheck`，结果通过。
- `npm run build`，结果通过；仅保留既有 Vite 大 chunk warning。
- 真实 API 模拟前端默认全选 trades 路径：MT5 工作区 `rows=1000 total=1429 directions={'buy': 11, 'sell': 9}`，CTP 工作区 `rows=673 total=673 directions={'buy': 8, 'sell': 12}`，合并后 `merged_rows=1673 prefixes={'MT5模拟工作区': 1000, '期货模拟工作区': 673}`。
- 真实 `/api/v1/portfolio/trades?limit=20` 方向计数为 `{'sell': 10, 'buy': 10}`，已由前端 helper 覆盖。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `28 passed`。
- `npm test -- --run src/__tests__/api/portfolio.test.ts src/__tests__/views/PortfolioPage.test.ts`，结果 `2 files passed, 25 tests passed`。
- `npm run typecheck`，结果通过。
- 已仅重启后端 uvicorn 到 PID `639121`；`GET /health` 返回 `200`，进程 `SID=639121` 持续存活。
- 认证后组合 trades API 当前结果：全局 `total=2059 rows=5 prefixes={'MT5模拟工作区': 5}`；MT5 工作区过滤 `total=1405 rows=5 prefixes={'MT5模拟工作区': 5}`；CTP 工作区过滤 `total=654 rows=5 prefixes={'期货模拟工作区': 5}`。
- `PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/ensure_dual_stress_running.sh status`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2509.4MB pss=1599.1MB uss=1590.9MB log=15.8MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2543.7MB pss=1632.6MB uss=1624.4MB log=24.1MB`。
- 新 PID 日志复扫：从 `Started server process [639121]` 之后无 ERROR、Traceback、UserWarning 或 slow request；仅保留既有结构化默认管理员密码 WARNING。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `27 passed`。
- `npm run typecheck`，结果通过。
- 已仅重启后端 uvicorn 到 PID `625336`；`GET /` 返回 `200`，进程 `SID=625336` 持续存活。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499962.98 total_pnl=-37.02 total_position_value=749461.17 net_position_value=712358.85`；positions `total=100 missing_updated_at=0 missing_signed=0 signed_sum=712358.90 summary_net=712358.90`；equity `points=654 first=2026-06-23 03:00:00 last=2026-06-25 09:52:00 strategies=100`。
- 新 PID 下认证后 `GET /api/v1/workspace/{ctp_workspace_id}/trading/positions`：`elapsed=141.7ms positions=50 missing_updated_at=0`。
- 新 PID 下认证后 `GET /api/v1/workspace/{mt5_workspace_id}/trading/positions`：`elapsed=179.2ms positions=50 missing_updated_at=0`。
- 新 PID 下三个 idle 工作区默认持仓接口均为 `positions=0 missing_updated_at=0`。
- `PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/ensure_dual_stress_running.sh status`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2508.3MB pss=1598.0MB uss=1589.8MB log=14.3MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.3% rss=2542.7MB pss=1631.6MB uss=1623.3MB log=22.6MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/workspace_service.py src/backend/tests/test_workspace_trading_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_workspace_trading_api.py -q`，结果 `7 passed`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_trading_workspace_service.py -q`，结果 `14 passed`。
- 已仅重启后端 uvicorn 到 PID `613349`；`GET /` 返回 `200`，进程 `SID=613349` 持续存活。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499507.74 total_pnl=-492.26 total_position_value=512403.85 net_position_value=285373.35`；positions `total=100 missing_updated_at=0`；trades `total=1954`；equity `points=639 first=2026-06-23 03:00:00 last=2026-06-25 09:44:00`；allocation `items=100`。
- 新 PID 下认证后 `GET /api/v1/workspace/{ctp_workspace_id}/trading/positions`：`elapsed=132.4ms positions=50 missing_updated_at=0`。
- 新 PID 下认证后 `GET /api/v1/workspace/{mt5_workspace_id}/trading/positions`：`elapsed=184.6ms positions=50 missing_updated_at=0`。
- 新 PID 下两个 idle 旧 CTP 工作区默认持仓接口：`positions=0`、`missing_updated_at=0`，不再展示历史 runtime 持仓作为当前持仓。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2507.9MB pss=1597.7MB uss=1589.4MB log=13.8MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2542.4MB pss=1631.3MB uss=1623.0MB log=22.1MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/config.py src/backend/app/startup/security_check.py src/backend/tests/test_config_validation.py src/backend/tests/test_main_lifespan_and_websocket.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_config_validation.py src/backend/tests/test_main_lifespan_and_websocket.py -q`，结果 `29 passed, 3 skipped, 1 warning`。
- 直接构造 `Settings(DEBUG=True, ADMIN_PASSWORD=<default>)` 的 Python warning 计数为 `0`。
- 已仅重启后端 uvicorn 到 PID `600788`；`GET /` 返回 `200`，进程 `SID=600788` 持续存活。
- 新 PID 启动日志复扫：从 `Started server process [600788]` 之后无新的 Pydantic `UserWarning`，仅保留 `app.startup.security_check` 的结构化默认管理员密码 WARNING；无新 traceback、ERROR 或慢请求 warning。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499687.2 total_pnl=-312.8 total_position_value=482803.43 net_position_value=37542.65`；positions `total=100 missing_updated_at=0`；trades `total=1893`；equity `points=624 first=2026-06-23 03:00:00 last=2026-06-25 09:37:00`；allocation `items=100`。
- 新 PID 下认证后 `GET /api/v1/workspace/{ctp_workspace_id}/trading/positions`：`elapsed=139.3ms positions=50 missing_updated_at=0`。
- 新 PID 下认证后 `GET /api/v1/workspace/{mt5_workspace_id}/trading/positions`：`elapsed=187.4ms positions=50 missing_updated_at=0`。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2507.6MB pss=1597.3MB uss=1589.1MB log=13.3MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2542.0MB pss=1630.9MB uss=1622.6MB log=21.5MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `27 passed`。
- 已仅重启后端 uvicorn 到 PID `589926`；`GET /` 返回 `200`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499892.33 total_pnl=-107.67 total_position_value=487863.16 net_position_value=11604.64`；positions `total=100 missing_updated_at=0`；trades `total=1822`；equity `points=606 first=2026-06-23 03:00:00 last=2026-06-25 09:28:00`；allocation `items=100`。
- 新 PID 下认证后 `GET /api/v1/workspace/{ctp_workspace_id}/trading/positions`：`elapsed=139.9ms positions=50 missing_updated_at=0`。
- 新 PID 下认证后 `GET /api/v1/workspace/{mt5_workspace_id}/trading/positions`：`elapsed=182.9ms positions=50 missing_updated_at=0`。
- 后端日志复扫：06:29 后无新 `Slow request detected`、traceback 或新 ERROR；仅保留 06:05 之前的历史慢请求 warning 和 04:06 的旧 HTTPException 格式记录。
- 活动日志质量复扫：CTP `missing_log_dir=1` 但通过 `runtime_dir/logs` 可读 50 个活动日志目录，MT5 `missing_log_dir=0`；CTP/MT5 的 `bar/value/position/trade/order/signal` 均 `bad_json=0`，100 个 `error.log` 与 `subprocess.stderr.log` 均为空。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2507.2MB pss=1596.9MB uss=1588.7MB log=12.6MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2541.6MB pss=1630.5MB uss=1622.2MB log=20.9MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/app/services/workspace_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py -q`，结果 `20 passed`。
- 已仅重启后端 uvicorn 到 PID `585412`；`GET /` 返回 `200`。
- 轻量 hydrate 后认证请求三轮工作区持仓接口：CTP `153.9ms/136.5ms/134.2ms positions=50 missing_updated_at=0`；MT5 `232.4ms/163.4ms/184.1ms positions=50 missing_updated_at=0`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50500420.87 total_pnl=420.87 total_position_value=707583.96 net_position_value=-698352.78`；positions `total=100 missing_updated_at=0`；trades `total=1786`；equity `points=596 first=2026-06-23 03:00:00 last=2026-06-25 09:23:00`。
- 新 PID 下后端日志复扫：06:24 后无新 `Slow request detected`、traceback 或新 ERROR；仅保留 06:05 之前的历史慢请求 warning 和 04:06 的旧 HTTPException 格式记录。
- 活动日志质量复扫：CTP `missing_log_dir=1` 但通过 `runtime_dir/logs` 可读 50 个活动日志目录，MT5 `missing_log_dir=0`；CTP/MT5 的 `bar/value/position/trade/order/signal` 均 `bad_json=0`，100 个 `error.log` 与 `subprocess.stderr.log` 均为空。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2506.9MB pss=1596.6MB uss=1588.4MB log=12.3MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2541.4MB pss=1630.2MB uss=1622.1MB log=20.6MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py -q`，结果 `19 passed`。
- 已仅重启后端 uvicorn 到 PID `579992`；`GET /` 返回 `200`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50500141.62 total_pnl=141.62 total_position_value=505696.29 net_position_value=-408831.19`；positions `total=100 missing_updated_at=0`；trades `total=1755`；equity `points=584 first=2026-06-23 03:00:00 last=2026-06-25 09:17:00`；allocation `items=100`。
- 新 PID 下认证后 `GET /api/v1/workspace/{ctp_workspace_id}/trading/positions`：`elapsed=416.5ms positions=50 missing_updated_at=0`。
- 新 PID 下认证后 `GET /api/v1/workspace/{mt5_workspace_id}/trading/positions`：`elapsed=484.8ms positions=50 missing_updated_at=0`。
- 活动日志质量复扫：CTP `missing_log_dir=1` 但通过 `runtime_dir/logs` 可读 50 个活动日志目录，MT5 `missing_log_dir=0`；CTP/MT5 的 `bar/value/position/trade/order/signal` 均 `bad_json=0`，100 个 `error.log` 与 `subprocess.stderr.log` 均为空。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2506.8MB pss=1596.5MB uss=1588.3MB log=11.9MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2541.2MB pss=1630.0MB uss=1621.8MB log=20.2MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/app/services/workspace_service.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_workspace_trading_api.py -q`，结果 `17 passed`。
- 已仅重启后端 uvicorn 到 PID `570248`；`GET /` 返回 `200`。
- 新 PID 下认证后 `GET /api/v1/workspace/{ctp_workspace_id}/trading/positions`：`elapsed=305.6ms positions=50 missing_updated_at=0`。
- 新 PID 下认证后 `GET /api/v1/workspace/{mt5_workspace_id}/trading/positions`：`elapsed=474.0ms positions=50 missing_updated_at=0`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50500161.11 total_pnl=161.11 total_position_value=712341.48 net_position_value=-642636.52`；positions `total=100 missing_updated_at=0`；trades `total=1681`；equity `points=566 first=2026-06-23 03:00:00 last=2026-06-25 09:08:00`；allocation `items=100 total=50500161.11`。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2505.9MB pss=1595.6MB uss=1587.4MB log=11.2MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2540.5MB pss=1629.4MB uss=1621.1MB log=19.5MB`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/trading_workspace_service.py src/backend/app/schemas/trading.py src/backend/tests/test_workspace_trading_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_workspace_trading_api.py -q`，结果 `6 passed`。
- `npm run typecheck` 通过。
- `npm test -- src/__tests__/api/stockAnalysis.test.ts --run`，结果 `2 passed`。
- 已仅重启后端 uvicorn 到 PID `561817`；`GET /` 返回 `200`。
- 认证后 `GET /api/v1/workspace/{ctp_workspace_id}/trading/positions` 当前结果：`total=50 missing_updated_at=0 first.updated_at=2026-06-23 06:06:00`。
- 认证后 `GET /api/v1/workspace/{mt5_workspace_id}/trading/positions` 当前结果：`total=50 missing_updated_at=0 first.updated_at=2026-06-25 08:59:00`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499977.66 total_pnl=-22.34 total_position_value=710706.27 net_position_value=-398696.65`；positions `total=100 missing_updated_at=0`；trades `total=1621`；equity `points=549 first=2026-06-23 03:00:00 last=2026-06-25 08:59:00`；allocation `items=100 total=50499977.66`。
- `reports/` 归档敏感值复扫清理后无输出。
- 抽样检查 `reports/backend_latest.log`，确认旧登录行已脱敏为 masked password 和 masked access token。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2505.7MB pss=1595.5MB uss=1587.3MB log=11.0MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.4% rss=2540.3MB pss=1629.2MB uss=1620.9MB log=19.1MB`。
- 认证后组合 API 当前结果：overview `strategy_count=100 running_count=100 total_assets=50499674.93 total_pnl=-325.07 total_position_value=606639.48 net_position_value=-573289.76`；positions `total=100 missing_updated_at=0`；trades `total=1540`；equity `points=528 first=2026-06-23 03:00:00 last=2026-06-25 08:49:00`；allocation `items=100 total=50499674.93`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `26 passed`。
- `git diff --check -- src/backend/app/api/portfolio/api.py src/backend/tests/test_portfolio_api.py` 无输出。
- 已仅重启后端 uvicorn 到 PID `546556`；`GET /` 返回 `200`。
- 认证后 `GET /api/v1/portfolio/positions` 当前结果：`total=100 missing_updated_at=0 first.updated_at=2026-06-25 06:58:00`。
- `/home/yun/anaconda3/bin/python -m py_compile src/backend/app/services/log_parser_service.py src/backend/app/api/portfolio/api.py src/backend/tests/test_log_parser.py src/backend/tests/test_portfolio_api.py`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_log_parser.py src/backend/tests/test_log_parser_extended.py -q`，结果 `48 passed`。
- `PYTHONPATH=src/backend /home/yun/anaconda3/bin/python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `26 passed`。
- `git diff --check -- src/backend/app/services/log_parser_service.py src/backend/app/api/portfolio/api.py src/backend/tests/test_log_parser.py src/backend/tests/test_portfolio_api.py` 无输出。
- 已仅重启后端 uvicorn 到 PID `539654`；`GET /` 返回 `200`。
- 认证后 `GET /api/v1/portfolio/equity` 当前结果：`points=508 first=2026-06-23 03:00:00 last=2026-06-25 08:39:00 total_equity_points=508`。
- `/home/yun/anaconda3/bin/python -m py_compile backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py tests/integration/test_trade_logger_runtime.py`，在 `/home/yun/Documents/backtrader` 通过。
- `/home/yun/anaconda3/bin/python -m pytest tests/unit/observers/test_trade_logger_edge_cases.py -q`，结果 `26 passed`。
- `/home/yun/anaconda3/bin/python -m pytest tests/integration/test_trade_logger_runtime.py -q`，结果 `8 passed`。
- `/home/yun/anaconda3/bin/python -m pytest tests/integration/test_trade_logger.py tests/unit/observers/test_trade_logger_internal_errors.py -q`，结果 `17 passed`。
- `git diff --check -- backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py tests/integration/test_trade_logger_runtime.py`，在 `/home/yun/Documents/backtrader` 无输出。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.0% rss=2504.7MB pss=1594.4MB uss=1586.2MB log=9.3MB`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=- cpu=3.5% rss=2538.5MB pss=1627.4MB uss=1619.2MB log=17.6MB`。
- 认证后 `GET /api/v1/portfolio/overview` 当前结果：`strategy_count=100 running_count=100 total_assets=50500363.56 total_pnl=363.56`。
- 认证后 `GET /api/v1/portfolio/positions` 当前结果：`positions_total=100`。
- 认证后 `GET /api/v1/portfolio/trades?limit=3` 当前结果：`trades_total=1452`。
- 敏感值和测试噪声复扫：`logs/`、`src/backend/logs/`、live instance JSON 与根监控文档中无明文默认管理员密码、JWT/Bearer、旧 MT5 明文值和 pytest 噪声命中；live instance JSON 非空 `password` 数量为 0。
- `python -m py_compile src/backend/app/services/gateway/runtime.py src/backend/app/services/live_trading/manager.py src/backend/tests/test_extracted_modules.py src/backend/tests/test_live_trading_manager.py`
- `python -m pytest src/backend/tests/test_extracted_modules.py::TestGatewayRuntimeService src/backend/tests/test_live_trading_manager.py::TestGatewayLifecycle::test_build_subprocess_env_prefers_local_source_paths src/backend/tests/test_live_trading_manager.py::TestGatewayLifecycle::test_build_subprocess_env_with_gateway -q`，结果 `15 passed`。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k GatewayRuntimeService`，结果 `13 passed, 104 deselected`。
- `python -m pytest src/backend/tests/test_live_trading_manager.py -q -k "build_subprocess_env"`，结果 `3 passed, 64 deselected`。
- `git diff --check -- src/backend/app/services/gateway/runtime.py src/backend/app/services/live_trading/manager.py src/backend/tests/test_extracted_modules.py src/backend/tests/test_live_trading_manager.py`
- 此前只重启 uvicorn 后端到 PID `521327`，`GET /` 返回 `200`；随后本轮又重启到 PID `539654`。
- 策略子进程环境抽样：当前共有 100 个 `workspace_units/.../run.py` 子进程；样本 PID `347600`、`369914` 的 `PYTHONPATH` 仍为 `/home/yun/Documents/bt_api_py/bt_api_py`，确认本轮 env 修复需下次新启动或滚动重启策略后生效。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，当前结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=-`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。
- 认证后 `GET /api/v1/portfolio/overview` 当前结果：`strategy_count=100 running_count=100 total_assets=50500363.56 total_pnl=363.56`。
- 认证后 `GET /api/v1/portfolio/positions` 当前结果：`positions_total=100`。
- 认证后 `GET /api/v1/portfolio/trades?limit=3` 当前结果：`trades_total=1452`。
- 敏感值和测试噪声复扫：`logs/`、`src/backend/logs/`、live instance JSON 与根监控文档中无明文默认管理员密码、JWT/Bearer、旧 MT5 明文值和 pytest 噪声命中。
- `python -m py_compile src/backend/app/utils/logger.py src/backend/app/config.py src/backend/tests/test_enhanced_logger.py src/backend/tests/test_audit_and_logging.py`
- `python -m py_compile src/backend/tests/conftest.py src/backend/tests/test_enhanced_logger.py`
- `python -m pytest src/backend/tests/test_enhanced_logger.py src/backend/tests/test_audit_and_logging.py -q`，结果 `64 passed, 3 skipped, 6 warnings`。
- `git diff --check -- src/backend/app/utils/logger.py src/backend/app/config.py src/backend/tests/test_enhanced_logger.py src/backend/tests/test_audit_and_logging.py`
- `git diff --check -- src/backend/tests/conftest.py src/backend/tests/test_enhanced_logger.py`
- pytest 日志隔离验收：根 `logs/errors_2026-06-25.log` 中四类测试特征计数在测试前后没有增加；归档历史污染日志后，当前 `logs/*.log` 与 `src/backend/logs/*.log` 中上述测试特征命中数均为 0。
- `PYTHONPATH=src/backend python -c "from pathlib import Path; from app.utils.logger import _archive_stale_dated_logs; print(_archive_stale_dated_logs(Path('logs'), min_age_seconds=60))"`，已将根 `logs/` 非当天遗留日期日志归档为 zip。
- `PYTHONPATH=src/backend python -c "from pathlib import Path; from app.utils.logger import _archive_stale_dated_logs; print(_archive_stale_dated_logs(Path('src/backend/logs'), min_age_seconds=60))"`，已将当前后端 Loguru 目录非当天遗留日期日志归档为 zip。
- 只重启 uvicorn 后端到 PID `496706`，`GET /` 返回 `200`。
- `du -sh logs src/backend/logs`，当前结果 `110M logs`、`320K src/backend/logs`。
- `tail -n 12 reports/dual_stress_monitor_7d.log`，最新 CTP/MT5 均 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。
- 活动 CTP/MT5 目录非空错误日志验收：两个当前压测目录下 `logs/error.log`、`logs/subprocess.stderr.log`、`logs/gateway.stderr.log` 均无非空文件；`heartbeat.json` 共 100 个。
- 认证后 `GET /api/v1/portfolio/overview` 当前结果：`strategy_count=100 running_count=100 total_assets=50499840.43 total_pnl=-159.57`。
- 认证后 `GET /api/v1/portfolio/positions` 当前结果：`positions_total=100`。
- `python -m py_compile src/backend/scripts/seed_simulated_workspaces.py src/backend/app/services/gateway/launch_builder.py src/backend/app/services/workspace_unit_runtime.py strategies/simulate/gateway_dual_ma/run.py strategies/simulate/gateway_boll_breakout/run.py strategies/simulate/mt5_audusd_rsi_pullback/run.py strategies/simulate/mt5_eurusd_ma_cross/run.py strategies/simulate/mt5_gbpusd_bb_revert/run.py strategies/simulate/mt5_usdjpy_trend_follow/run.py strategies/simulate/mt5_xauusd_breakout/run.py src/backend/tests/test_seed_simulated_workspaces.py src/backend/tests/test_gateway_preset_and_launch.py src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_trading_workspace_service.py`
- `python -m pytest src/backend/tests/test_seed_simulated_workspaces.py src/backend/tests/test_gateway_preset_and_launch.py src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `97 passed, 1 warning`。
- `python -m json.tool src/backend/data/live_trading_instances.json >/dev/null`；活动 CTP/MT5 共 100 个 runtime `config.yaml` 均通过 `yaml.safe_load()`。
- 敏感值复扫：旧 MT5 明文密码值、旧 MT5 模板密码值、历史 admin/JWT 模式均无匹配；两个活动压测目录、MT5 模板和 live instance JSON 中无非空 `password` 字段。
- `python src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，当前结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=-`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。
- `GET /api/v1/portfolio/overview` 当前认证结果：`strategy_count=100 running_count=100 total_assets=50500363.56 total_pnl=363.56`。
- `GET /api/v1/portfolio/positions` 当前认证结果：`total=100`。
- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/app/services/live_trading/execution.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_extracted_modules.py`
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `26 passed`。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k LiveExecutionService`，结果 `8 passed, 1 skipped, 105 deselected`。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `46 passed, 1 warning`。
- `setsid /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --unit-ids 0b64cdc5-b443-496c-ace4-eeb66a50bba2 --hold-seconds 604800 --status-interval 30 > reports/ctp01_canary_supervisor.log 2>&1 &`，实际 supervisor PID `347458`。
- `setsid /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --unit-ids 92524351-3681-4495-8663-e9cc29f091bb --rolling-restart --rolling-batch-size 1 --rolling-batch-wait-seconds 35 --skip-fresh-heartbeats --hold-seconds 604800 --status-interval 30 > reports/ctp02_rolling_supervisor.log 2>&1 &`，实际 supervisor PID `369784`。
- `setsid /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets futures --rolling-restart --rolling-batch-size 4 --rolling-batch-wait-seconds 35 --skip-fresh-heartbeats --hold-seconds 604800 --status-interval 30 > reports/ctp_remaining_rolling_supervisor.log 2>&1 &`，实际 supervisor PID `379969`。
- `setsid /home/yun/anaconda3/bin/python -u src/backend/scripts/run_dual_exchange_simulation.py --skip-seed --targets mt5 --rolling-restart --rolling-batch-size 4 --rolling-batch-wait-seconds 35 --skip-fresh-heartbeats --hold-seconds 604800 --status-interval 30 > reports/mt5_remaining_rolling_supervisor.log 2>&1 &`，实际 supervisor PID `388891`。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures --unit-ids 0b64cdc5-b443-496c-ace4-eeb66a50bba2 --no-hold`，当前结果：`running=1 failed=0 idle=0 missing=0 process=1 heartbeat=1 stale=0 no_log=0 alerts=-`。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures --unit-ids 92524351-3681-4495-8663-e9cc29f091bb --no-hold`，当前结果：`running=1 failed=0 idle=0 missing=0 process=1 heartbeat=1 stale=0 no_log=0 alerts=-`。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，当前结果：CTP `running=50 process=50 heartbeat=50 stale=0 alerts=-`；MT5 `running=50 process=50 heartbeat=50 stale=0 alerts=-`。
- `python -m py_compile strategies/simulate/gateway_dual_ma/run.py strategies/simulate/gateway_boll_breakout/run.py strategies/simulate/mt5_eurusd_ma_cross/run.py src/backend/tests/test_gateway_strategy_runner_config.py`
- `python -m pytest src/backend/tests/test_gateway_strategy_runner_config.py -q`，结果 `7 passed, 1 warning`。
- `python -m pytest src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `30 passed, 1 warning`。
- `python -m pytest src/backend/tests/test_trading_workspace_service.py -q`，结果 `10 passed`。
- `python -m pytest src/backend/tests/test_gateway_strategy_runner_config.py src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_ensure_dual_stress_running_script.py src/backend/tests/test_trading_workspace_service.py -q`，结果 `40 passed, 1 warning`。
- `TARGETS=futures,mt5 PYTHON_BIN=/home/yun/anaconda3/bin/python scripts/ops/ensure_dual_stress_running.sh status`，输出 `dual stress supervisor not running`、`dual stress monitor running: pid=307323`。
- 以下继续保留本轮较早阶段的验收命令；旧输出中的 `heartbeat=50` 或双目标 `heartbeat=0 stale=50` 是当时口径或当时现场状态，不代表 04:02 当前结论。
- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py`
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `20 passed`。
- `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures,mt5 --no-hold`，当前结果：CTP 与 MT5 均 `running=50 failed=0 idle=0 missing=0 process=50 heartbeat=0 stale=50 no_log=0 alerts=heartbeat_stale`。
- `bash -n scripts/ops/ensure_dual_stress_running.sh`
- `python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `3 passed`。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `23 passed`。
- `TARGETS=futures,mt5 PYTHON_BIN=/home/yun/anaconda3/bin/python scripts/ops/ensure_dual_stress_running.sh status`，输出 `dual stress monitor running: pid=307323` 并回写 `.pids/dual_stress_monitor.pid=307323`。
- `python -m py_compile src/backend/app/services/live_trading/metadata.py src/backend/app/services/live_trading/instance.py src/backend/app/services/live_trading/execution.py src/backend/app/schemas/live_trading_instance.py src/backend/tests/conftest.py src/backend/tests/test_live_instance_service.py src/backend/tests/test_live_trading_api.py src/backend/tests/test_extracted_modules.py`
- `python -m pytest src/backend/tests/test_live_instance_service.py -q`，结果 `25 passed`。
- `python -m pytest src/backend/tests/test_extracted_modules.py -q -k LiveExecutionService`，结果 `7 passed, 1 skipped, 105 deselected`。
- `python -m pytest src/backend/tests/test_live_trading_manager.py -q`，结果 `66 passed`。
- `python -m pytest src/backend/tests/test_live_trading_api.py -q`，结果 `39 passed`。
- 上述 pytest 前后真实 `src/backend/data/live_trading_instances.json` sha256 均为 `8cc461c0e7b0d7fb0b07e70e6de5ae901751ca655883e711ac42bf0aeeb9574b`。
- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/app/api/portfolio/api.py src/backend/app/services/workspace/reconciliation.py`
- `python -m pytest src/backend/tests/test_workspace_reconciliation.py src/backend/tests/test_portfolio_api.py -q`
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `4 passed`。
- `python -m py_compile src/backend/scripts/run_dual_exchange_simulation.py src/backend/tests/test_run_dual_exchange_simulation.py`
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py -q`，结果 `7 passed`。
- `python -m pytest src/backend/tests/test_run_dual_exchange_simulation.py src/backend/tests/test_workspace_reconciliation.py src/backend/tests/test_portfolio_api.py -q`，结果 `27 passed`。
- `python -m py_compile strategies/simulate/gateway_dual_ma/run.py strategies/simulate/gateway_boll_breakout/run.py src/backend/app/services/workspace_unit_runtime.py src/backend/scripts/seed_simulated_workspaces.py`
- `python -m pytest src/backend/tests/test_trading_workspace_service.py src/backend/tests/test_seed_simulated_workspaces.py -q`，结果 `9 passed`。
- `python -m pytest src/backend/tests/test_portfolio_api.py -q`，结果 `23 passed`。
- `npm test -- --run src/__tests__/views/PortfolioPage.test.ts`，结果 `16 passed`。
- `rg "Logging error|I/O operation on closed file|aiosqlite.core" /tmp/backtrader_web_pytest_logging_check.out`，无匹配。
- `PYTHON_BIN=/home/yun/anaconda3/bin/python ./scripts/ops/restart_app.sh`
- 真实 API 验收：
  - `GET /api/v1/portfolio/overview`
  - `GET /api/v1/portfolio/positions`
  - `GET /api/v1/portfolio/trades?limit=3`
  - `GET /api/v1/portfolio/equity`
  - `GET /api/v1/portfolio/allocation`
  - 本轮认证后最新结果：overview `strategy_count=50 running_count=50 total_position_value=484782.4 net_position_value=137078.8`，positions `total=50`，trades `total=248`，equity `strategies=50`，allocation `items=50`。
- 只读监控验收：
  - `python -u src/backend/scripts/run_dual_exchange_simulation.py --monitor-only --skip-seed --targets futures --no-hold`
  - 输出 `process=50 heartbeat=50 stale=0 no_log=0 alerts=cpu_high,rss_high,tick_log_high cpu=1694.6% max_cpu=35.5% rss=12606.4MB log=416.7MB tick=405.1MB tick_max=9.9MB`
- `backtrader` TradeLogger 时间线修复验收：
  - `/home/yun/anaconda3/bin/python -m py_compile backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py tests/integration/test_trade_logger_runtime.py`
  - `/home/yun/anaconda3/bin/python -m pytest tests/unit/observers/test_trade_logger_edge_cases.py -q`，结果 `23 passed`。
  - `/home/yun/anaconda3/bin/python -m pytest tests/integration/test_trade_logger_runtime.py -q`，结果 `8 passed`。
- `backtrader` store runtime event 时间戳修复验收：
  - `python -m py_compile backtrader/stores/btapistore.py backtrader/observers/trade_logger.py tests/unit/observers/test_trade_logger_edge_cases.py tests/unit/stores/test_btapistore_notifications.py tests/integration/test_trade_logger_runtime.py`
  - `python -m pytest tests/unit/observers/test_trade_logger_edge_cases.py -q tests/unit/stores/test_btapistore_notifications.py -q tests/integration/test_trade_logger_runtime.py -q`，结果 `47 passed`。
  - `python -m pytest tests/unit/stores/test_btapistore.py -q`，结果 `90 passed, 1 skipped`。
- `backtrader_web` gateway 原生 stderr 隔离修复验收：
  - `python -m py_compile src/backend/app/services/gateway/runtime.py src/backend/tests/test_extracted_modules.py`
  - `python -m pytest src/backend/tests/test_extracted_modules.py -q -k GatewayRuntimeService`，结果 `12 passed, 104 deselected`。
  - `python -m pytest src/backend/tests/test_extracted_modules.py -q -k "LiveExecutionService or GatewayRuntimeService"`，结果 `20 passed, 1 skipped, 95 deselected`。
  - `python -m pytest src/backend/tests/test_live_trading_manager.py -q`，结果 `66 passed`。
- `ensure_dual_stress_running.sh` 拆分 supervisor 状态修复验收：
  - `bash -n scripts/ops/ensure_dual_stress_running.sh`
  - `python -m pytest src/backend/tests/test_ensure_dual_stress_running_script.py -q`，结果 `5 passed`。
  - `TARGETS=futures,mt5 PYTHON_BIN=/home/yun/anaconda3/bin/python scripts/ops/ensure_dual_stress_running.sh status`，输出四个 `split stress supervisor running`、一个 `dual stress monitor running`，并保持双目标 `alerts=-`。
  - `TARGETS=futures,mt5 PYTHON_BIN=/bin/false scripts/ops/ensure_dual_stress_running.sh start`，输出已复用拆分 supervisor，未启动新 dual supervisor。

## 最近持续巡检快照

- `2026-06-25 16:46-16:47 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；注册运行 PID 复验为 `pids=100 alive=100 missing=0 states={'S': 100}`，父进程分布为 CTP holder `1324657:50`、MT5 holder `992775:50`。
- 活动日志继续正常：MT5 50 个活动 `bar.log` 最新 `datetime` 全部为 `2026-06-25T08:45:00.000+00:00`，`future_gt_120s=0`；MT5 `trade.log/signal.log` 最新到 `2026-06-25T08:45:00.000+00:00`，`order.log` 最新到 `2026-06-25T08:44:00.000+00:00`，均无坏时间或未来时间。CTP 50 个活动 `bar.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.27 total_pnl=-0.73`；equity `dates=534 strategies=100 latest=2026-06-25T08:45:00.000+00:00 future_gt_120s=0`；positions `total=100 items=100 latest_update=2026-06-25T16:46:00.903+08:00`；trades `total=1861 returned=1000 date_only_datetime=0 bad_iso_datetime=0 latest=2026-06-25T08:45:00.000+00:00`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log/subprocess.stderr.log/gateway.stderr.log` 均无错误关键字，其中仅 1 个 `gateway.stderr.log` 非空但无 `ERROR/Traceback/Exception`；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0。CTP holder PSS `1599.6MB`，MT5 holder PSS `1646.7MB`。
- `2026-06-25 16:42-16:43 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；注册运行 PID 复验为 `pids=100 alive=100 missing=0 states={'S': 100}`，父进程分布为 CTP holder `1324657:50`、MT5 holder `992775:50`。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:42:00.000+00:00`，`future_gt_120s=0`；MT5 `trade.log/signal.log` 最新到 `2026-06-25T08:42:00.000+00:00`，`order.log` 最新到 `2026-06-25T08:41:00.000+00:00`，均无坏时间或未来时间。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.36 total_pnl=-0.64`；equity `dates=531 strategies=100 latest=2026-06-25T08:42:00.000+00:00 future_gt_120s=0`；positions `total=100 items=100 latest_update=2026-06-25T16:43:01.143+08:00`；trades `total=1843 returned=1000 date_only_datetime=0 bad_iso_datetime=0 latest=2026-06-25T08:42:00.000+00:00`；allocation `items=100 total=50499999.36`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log/subprocess.stderr.log/gateway.stderr.log` 均无错误关键字，其中仅 1 个 `gateway.stderr.log` 非空但无 `ERROR/Traceback/Exception`；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0。CTP holder PSS `1599.4MB`，MT5 holder PSS `1646.5MB`。
- `2026-06-25 16:38-16:39 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；注册运行 PID 复验为 `pids=100 alive=100 missing=0 states={'S': 100}`，父进程分布为 CTP holder `1324657:50`、MT5 holder `992775:50`。
- 活动日志继续正常：MT5 50 个活动 `bar.log` 最新 `datetime` 全部为 `2026-06-25T08:38:00.000+00:00`，`future_gt_120s=0`；MT5 `trade.log/signal.log` 最新到 `2026-06-25T08:38:00.000+00:00`，`order.log` 最新到 `2026-06-25T08:37:00.000+00:00`，均无坏时间或未来时间。CTP 50 个活动 `bar.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.39 total_pnl=-0.61`；equity `dates=527 strategies=100 latest=2026-06-25T08:38:00.000+00:00 future_gt_120s=0`；positions `total=100 items=100 latest_update=2026-06-25T16:39:00.874+08:00`；trades `total=1828 returned=1000 date_only_datetime=0 bad_iso_datetime=0 latest=2026-06-25T08:38:00.000+00:00`。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log/subprocess.stderr.log/gateway.stderr.log` 均无错误关键字，其中仅 1 个 `gateway.stderr.log` 非空但无 `ERROR/Traceback/Exception`；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0。CTP holder PSS `1599.2MB`，MT5 holder PSS `1646.4MB`。
- `2026-06-25 16:34-16:35 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；注册运行 PID 复验为 `registered_running_pids=100 unique=100 alive=100 missing=0 runpy=100`，父进程分布为 CTP holder `1324657:50`、MT5 holder `992775:50`，100 个子进程均为 `S`。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:34:00.000+00:00`，`future_gt_120s=0`；MT5 `trade.log` 最新到 `2026-06-25T08:34:00.000+00:00`，`order.log/signal.log` 最新到 `2026-06-25T08:33:00.000+00:00`，均无坏时间或未来时间。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.54 total_pnl=-0.46`；equity `dates=523 strategies=100 latest=2026-06-25T08:34:00.000+00:00 future_gt_120s=0 bad_datetime=0`；positions `total=100 items=100 latest_update=2026-06-25T16:35:00.931+08:00`；trades `total=1819 returned=1000 date_only_datetime=0 bad_iso_datetime=0 latest=2026-06-25T08:34:00.000+00:00`；allocation `items=100 total=50499999.54`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log/subprocess.stderr.log/gateway.stderr.log` 均无错误关键字，其中仅 1 个 `gateway.stderr.log` 非空但无 `ERROR/Traceback/Exception`；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0。CTP holder PSS `1599.1MB`，MT5 holder PSS `1646.2MB`。
- `2026-06-25 16:31-16:32 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；注册运行 PID 复验为 `registered_running_pids=100 unique=100 alive_registered=100 missing=0`，父进程分布为 CTP holder `1324657:50`、MT5 holder `992775:50`，100 个子进程均为 `workspace_units/.../run.py` 且状态为 `S`。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:30:00.000+00:00`，`future_gt_120s=0`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T08:30:00.000+00:00`，最新订单到 `2026-06-25T08:29:00.000+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.45 total_pnl=-0.55`；equity `dates=519 strategies=100 latest=2026-06-25T08:30:00.000+00:00 future_gt_120s=0`；positions `total=100 items=100 latest_update=2026-06-25T16:31:00.913+08:00`；trades `total=1806 returned=1000 date_only_datetime=0 bad_iso_datetime=0 latest=2026-06-25T08:30:00.000+00:00`；allocation `items=100 total=50499999.45`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元的 `error.log/subprocess.stderr.log/gateway.stderr.log` 均无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，本轮一次 401 来自巡检脚本误用本地 env 中与当前数据库不一致的管理员密码。CTP holder PSS `1599.0MB`，MT5 holder PSS `1646.1MB`。
- `2026-06-25 16:21-16:22 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 argv `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个真实子进程。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:21:00.000+00:00`，`future_gt_120s=0`，`log_time_age=42.8-43.5s`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T08:21:00.000+00:00`，最新订单到 `2026-06-25T08:20:00.000+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.69 total_pnl=-0.31`；equity/simulation equity 均为 `dates=510 strategies=100 latest=2026-06-25T08:21:00.000+00:00`；positions `total=100 items=100 latest_update=2026-06-25T16:22:01.052+08:00`；trades `total=1788 returned=1000 date_only_datetime=0 latest=2026-06-25T08:21:00.000+00:00`；allocation `items=100 total=50499999.69`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`password` 仅命中 11 条已脱敏登录日志。CTP holder PSS `1598.8MB`，MT5 holder PSS `1645.8MB`。
- `2026-06-25 16:17-16:18 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 argv `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个真实子进程。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:17:00.000+00:00`，`future_gt_120s=0`，`log_time_age=50.9-51.5s`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T08:17:00.000+00:00`，最新订单到 `2026-06-25T08:16:00.000+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.5 total_pnl=-0.5`；equity/simulation equity 均为 `dates=506 strategies=100 latest=2026-06-25T08:17:00.000+00:00`；positions `total=100 items=100 latest_update=2026-06-25T16:18:00.873+08:00`；trades `total=1766 returned=1000 date_only_datetime=0 latest=2026-06-25T08:17:00.000+00:00`；allocation `items=100 total=50499999.5`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`password` 仅命中 10 条已脱敏登录日志。CTP holder PSS `1598.7MB`，MT5 holder PSS `1645.6MB`。
- `2026-06-25 16:14-16:15 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 argv `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个真实子进程。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:14:00.000+00:00`，`future_gt_120s=0`，`log_time_age=1.6-2.1s`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T08:14:00.000+00:00`，最新订单到 `2026-06-25T08:13:00.000+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.6 total_pnl=-0.4`；equity/simulation equity 均为 `dates=503 strategies=100 latest=2026-06-25T08:14:00.000+00:00`；positions `total=100 items=100 latest_update=2026-06-25T16:15:00.951+08:00`；trades `total=1745 returned=1000 date_only_datetime=0 latest=2026-06-25T08:14:00.000+00:00`；allocation `items=100 total=50499999.6`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`password` 仅命中 9 条已脱敏登录日志。CTP holder PSS `1598.7MB`，MT5 holder PSS `1645.5MB`。
- `2026-06-25 16:10-16:11 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 argv `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个真实子进程。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:10:00.000+00:00`，`future_gt_120s=0`，`log_time_age=4.4-5.0s`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T08:10:00.000+00:00`，最新订单到 `2026-06-25T08:09:00.000+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.6 total_pnl=-0.4`；equity/simulation equity 均为 `dates=499 strategies=100 latest=2026-06-25T08:10:00.000+00:00`；positions `total=100 items=100 latest_update=2026-06-25T16:11:00.920+08:00`；trades `total=1725 returned=1000 date_only_datetime=0 latest=2026-06-25T08:10:00.000+00:00`；allocation `items=100 total=50499999.6`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`password` 仅命中 9 条已脱敏登录日志。CTP holder PSS `1598.6MB`，MT5 holder PSS `1644.5MB`。
- `2026-06-25 16:05-16:06 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 argv `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个真实子进程。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:05:00.000+00:00`，`future_gt_120s=0`，`log_time_age=24.7-25.2s`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T08:05:00.000+00:00`，最新订单到 `2026-06-25T08:04:00.000+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.72 total_pnl=-0.28`；equity/simulation equity 均为 `dates=494 strategies=100 latest=2026-06-25T08:05:00.000+00:00`；positions `total=100 items=100 latest_update=2026-06-25T16:06:00.877+08:00`；trades `total=1707 returned=1000 date_only_datetime=0 latest=2026-06-25T08:05:00.000+00:00`；allocation `items=100 total=50499999.72`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`password` 仅命中 7 条已脱敏登录日志。CTP holder PSS `1598.4MB`，MT5 holder PSS `1644.3MB`。
- `2026-06-25 15:59-16:02 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个子进程。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T08:01:00.000+00:00`，`future_gt_120s=0`，`log_time_age=49.5-50.1s`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T08:01:00.000+00:00`，最新订单到 `2026-06-25T08:00:00.000+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00.000+00:00:20`、`2026-06-25T07:00:00.000+00:00:20`、`2026-06-25T07:03:00.000+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.7 total_pnl=-0.3`；equity/simulation equity 均为 `dates=489 strategies=100 latest=2026-06-25T08:00:00.000+00:00`；positions `total=100 items=100 latest_update=2026-06-25T16:01:01.277+08:00`；trades `total=1700 returned=1000 date_only_datetime=0 latest=2026-06-25T08:00:00.000+00:00`；allocation `items=100 total=50499999.7`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`password` 仅命中 7 条已脱敏登录日志。CTP holder PSS `1598.2MB`，MT5 holder PSS `1644.6MB`。
- `2026-06-25 15:50-15:52 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个子进程。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T07:50:00+00:00`，`future_gt_120s=0`，`log_time_age=47.2-47.9s`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T07:50:00+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:00:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.31 total_pnl=-0.69`；equity/simulation equity 均为 `dates=480 strategies=100 latest=2026-06-25T07:51:00+00:00 future_gt_120s=0`；positions `total=100 dated=100 latest=2026-06-25T07:51:00+00:00`；trades `total=1673 returned=1000 date_only_datetime=0`；allocation `items=100`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`password` 仅命中 5 条已脱敏登录日志。CTP holder PSS `1598.1MB`，MT5 holder PSS `1644.4MB`。
- `2026-06-25 15:46-15:48 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，总计 100 个子进程。
- 活动日志继续正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T07:46:00+00:00`，`future_gt_120s=0`，`log_time_age=11.0-11.6s`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T07:46:00+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:00:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，符合 15:00 后期货安静窗口。
- API 与服务健康正常：overview `strategy_count=100 running_count=100 total_assets=50499999.36 total_pnl=-0.64`；equity/simulation equity 均为 `dates=475 strategies=100 latest=2026-06-25T07:46:00+00:00 future_gt_120s=0`；positions `total=100 dated=100 latest=2026-06-25T07:46:00+00:00`；trades `total=1660 returned=1000 date_only_datetime=0`；allocation `items=100`；`/health` 和前端 `/` 均返回 200。
- 元数据、资源和错误日志正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`password` 仅命中 4 条已脱敏登录日志。CTP holder PSS `1597.8MB`，MT5 holder PSS `1644.3MB`。
- `2026-06-25 15:41-15:44 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- 活动日志和成交时间字段正常：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T07:41:00+00:00`，`future_gt_120s=0`；MT5 `trade/order/signal` 尾部 `bad_json=0 bad_1970=0 future_gt_120s=0 date_only_datetime_tail=0`，最新成交/信号到 `2026-06-25T07:41:00+00:00`。CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:00:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，符合 15:00 后期货安静窗口。
- API 与元数据一致：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 bad_pid=0 missing_runtime=0 running_without_pid=0`；overview `strategy_count=100 running_count=100 total_assets=50499999.28 total_pnl=-0.72`；equity/simulation equity 均为 `dates=471 strategies=100 latest=2026-06-25T07:42:00+00:00 future_gt_120s=0`；positions `total=100 dated=100 latest=2026-06-25T07:42:00+00:00`；trades `total=1640 returned=1000 date_only_datetime=0`。
- 资源和错误日志正常：CTP holder 从 `14:59:39` 到 `15:42:00` 的总 PSS 增量约 `+6.1MB`、日志维持 `0.4MB`；MT5 holder 从 `11:32:09` 到 `15:42:00` 的总 PSS 增量约 `+28.1MB`、日志 `10.4 -> 28.2MB`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `1379305` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow` 均为 0，`/health` 和前端 `/` 均返回 200。
- `2026-06-25 15:32-15:38 CST`：本轮巡检发现并修复组合成交 API 主时间字段降级问题。修复前 `/portfolio/trades?limit=1000` 为 `total=1619 returned=1000 date_only_datetime=1000`；修复 `parse_trade_log()` 后，重启后端到 PID `1379305`，真实 `/portfolio/trades?limit=20` 为 `total=1624 returned=20 date_only_datetime=0`，样例 `datetime=2026-06-25T07:36:00.000+00:00 dtclose=2026-06-25T07:36:00.000+00:00`。
- 运行状态保持正常：`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- 活动日志深扫：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T07:32:00+00:00`，`future_gt_120s=0`；CTP 50 个活动 `bar.log/value.log/position.log` 仍分布为 `2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:00:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，`future_gt_120s=0`，与 15:00 后期货安静窗口一致。
- API 与错误日志复验：overview `strategy_count=100 running_count=100 total_assets=50499999.19 total_pnl=-0.81`；equity `dates=465 strategies=100 latest=2026-06-25T07:36:00+00:00 future_gt_120s=0`；positions `total=100 dated=100 latest=2026-06-25T07:36:00+00:00`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；`/health` 和前端 `/` 均返回 200。
- 本轮验收命令：`python -m py_compile src/backend/app/services/log_parser_service.py src/backend/tests/test_log_parser.py` 通过；`python -m pytest src/backend/tests/test_log_parser.py src/backend/tests/test_log_parser_extended.py -q` 结果 `49 passed in 3.81s`；`python -m pytest src/backend/tests/test_portfolio_api.py -q` 结果 `28 passed in 2.35s`。
- `2026-06-25 15:25-15:30 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。最新 `ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- CTP 在 15:24-15:25 曾出现部分 post-session 追加写入，状态短暂为 `data_log=40 data_quiet=10 alerts=-`；到 15:29 已回到 `data_log=0 data_quiet=50 alerts=-`。50 个活动 `bar.log/value.log/position.log` 业务时间分布为 `2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:00:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，`future_gt_120s=0`。该现象当前记录为期货收盘后数据落盘行为，继续观察，不作为新缺陷处理。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T07:26:00+00:00`，`log_time_skew=0.5s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T07:26:00+00:00`，`dates=455 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T07:26:00.000+00:00`。
- 元数据和组合 API 一致：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 stopped=0 bad_pid=0 missing_runtime=0 running_without_pid=0`；overview `strategy_count=100 running_count=100 total_assets=50499999.29 total_pnl=-0.71`。全局 `/portfolio/trades?limit=1000` 当前仍因时间排序返回 MT5 `1000/1000`，这是第 76/77 项已知场景；前端 `PortfolioPage.vue` 当前已按每个选中工作区分别调用 `portfolioApi.getTrades(1000, [workspace.id])`，本轮不新增修复项。
- 资源趋势和错误日志正常：CTP 新 holder 从 `14:59:39` 到 `15:26:50` 的总 PSS 增量 `+4.2MB`、日志 `+0.1MB`；MT5 holder 从 `11:32:09` 到 `15:26:51` 的总 PSS 增量 `+26.4MB`、日志 `+16.9MB`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `752932` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow/password` 均为 0，`GET /health` 返回 200。
- `2026-06-25 15:21-15:23 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T07:22:00+00:00`，`log_time_skew=0.7s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T07:22:00+00:00`，`dates=451 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T07:22:00.000+00:00`。
- CTP 活动日志在 15:00 后安静窗口内保持预期静默：50 个活动 `bar.log/value.log/position.log` 最新分布为 `2026-06-25T06:58:00+00:00:20`、`2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，`future_gt_120s=0`；监控正确输出 `data_quiet=50 alerts=-`，无 `data_stale`。
- 元数据和组合 API 一致：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 stopped=0 bad_pid=0 missing_runtime=0 running_without_pid=0`；overview `strategy_count=100 running_count=100 total_assets=50499999.21 total_pnl=-0.79`。全局 `/portfolio/trades?limit=1000` 当前仍因时间排序返回 MT5 `1000/1000`，这是第 76/77 项已知场景；前端 `PortfolioPage.vue` 当前已按每个选中工作区分别调用 `portfolioApi.getTrades(1000, [workspace.id])`，本轮不新增修复项。
- 资源趋势和错误日志正常：CTP 新 holder 从 `14:59:39` 到 `15:22:48` 的总 PSS 增量 `+3.6MB`、日志 `+0.1MB`；MT5 holder 从 `11:32:09` 到 `15:22:45` 的总 PSS 增量 `+26.0MB`、日志 `+16.6MB`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `752932` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0，`GET /health` 返回 200。
- `2026-06-25 15:17-15:20 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新分布为 `2026-06-25T07:17:00+00:00:5` 与 `2026-06-25T07:18:00+00:00:45`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T07:18:00+00:00`，`dates=447 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T07:18:00.000+00:00`。
- CTP 活动日志在 15:00 后安静窗口内保持预期静默：50 个活动 `bar.log/value.log/position.log` 最新分布为 `2026-06-25T06:58:00+00:00:20`、`2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，`future_gt_120s=0`；监控正确输出 `data_quiet=50 alerts=-`，无 `data_stale`。
- 元数据和组合 API 一致：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 stopped=0 bad_pid=0 missing_runtime=0 running_without_pid=0`；overview `strategy_count=100 running_count=100 total_assets=50499999.31 total_pnl=-0.69`。全局 `/portfolio/trades?limit=1000` 当前仍因时间排序返回 MT5 `1000/1000`，这是第 76/77 项已知场景；前端 `PortfolioPage.vue` 当前已按每个选中工作区分别调用 `portfolioApi.getTrades(1000, [workspace.id])`，本轮不新增修复项。
- 资源趋势和错误日志正常：CTP 新 holder 从 `14:59:39` 到 `15:18:47` 的总 PSS 增量 `+3.0MB`、日志 `+0.1MB`；MT5 holder 从 `11:32:09` 到 `15:18:40` 的总 PSS 增量 `+24.8MB`、日志 `+16.3MB`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `752932` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0，`GET /health` 返回 200。
- `2026-06-25 15:12-15:15 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- 元数据一致性正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 stopped=0 bad_pid=0 missing_runtime=0 running_without_pid=0`，与真实 `/proc` 子进程计数一致。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T07:13:00+00:00`，`log_time_skew=0.6s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T07:13:00+00:00`，`dates=442 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T07:13:00.000+00:00`。
- CTP 活动日志在 15:00 后安静窗口内保持预期静默：50 个活动 `bar.log/value.log/position.log` 最新分布为 `2026-06-25T06:58:00+00:00:20`、`2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，`future_gt_120s=0`；监控正确输出 `data_quiet=50 alerts=-`，无 `data_stale`。
- 成交/订单/信号日志质量正常：MT5 `order.log tail_rows=5622 bad_json=0 bad_1970=0 latest=2026-06-25T07:12:00+00:00`、`trade.log tail_rows=3116 bad_json=0 bad_1970=0 latest=2026-06-25T07:13:00+00:00`、`signal.log tail_rows=1883 bad_json=0 bad_1970=0 latest=2026-06-25T07:13:00+00:00`；CTP 当前 `trade/order/signal` 均为空文件，符合重整后且安静窗口内暂无新成交/信号的现场状态。
- 资源趋势和错误日志正常：CTP 新 holder 从 `14:59:39` 到 `15:14:15` 的总 PSS 增量 `+2.4MB`、日志 `+0.1MB`；MT5 holder 从 `11:32:09` 到 `15:14:34` 的总 PSS 增量 `+25.6MB`、日志 `+16.0MB`。100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `752932` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0，`GET /health` 返回 200。
- `2026-06-25 15:03-15:10 CST`：本轮巡检发现并修复 CTP `data_log_stale` 恢复盲点。14:44 CTP 日志出现 `OnSessionDisconnected[...][8193]` 后，监控曾变为 `data_log=5 data_stale=45 alerts=data_log_stale`；新增 `--skip-fresh-data-logs` 后，先定向滚动恢复 stale-data 单元，再用 `setsid` 启动持久 CTP 全量重整 holder `1324657`。最新 `ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_stale=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_stale=0 data_quiet=0 alerts=-`；严格 `/proc` 复验为 CTP `{'1324657': 50}`、MT5 `{'992775': 50}`。
- CTP 15:00 后处于合约安静窗口：50 个活动 `bar.log/value.log/position.log` 最新分布为 `2026-06-25T06:58:00+00:00:20`、`2026-06-25T06:59:00+00:00:20`、`2026-06-25T07:03:00+00:00:10`，`future_gt_120s=0`；监控正确归为 `data_quiet=50 alerts=-`，不再出现 `data_stale`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T07:04:00+00:00`，`log_time_skew=0.5s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T07:04:00+00:00`，`dates=433 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T07:04:00.000+00:00`。
- 认证后 API 复验：overview `strategy_count=100 running_count=100 total_assets=50499999.53 total_pnl=-0.47`；positions `total=100 dated=100`。成交/订单/信号日志尾部无坏 JSON 或 1970 时间；CTP 重整后当前 trade/order/signal 尚无新行，MT5 最新成交/信号到 `2026-06-25T07:04:00+00:00`。
- 资源与错误日志复验正常：100 个活动单元 `error.log=0 subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0，`GET /health` 返回 200。单进程 RSS 为 CTP `49.7-50.4MB`、MT5 `50.7-51.5MB`，线程最大 5、FD 最大 22。
- `2026-06-25 14:38-14:40 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- 元数据一致性正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 not_running=0 bad_pid=0 missing_runtime=0`，与真实 `/proc` 子进程计数一致。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:39:00+00:00`，`log_time` 范围 `2026-06-25T14:40:01.166+08:00` 到 `2026-06-25T14:40:01.861+08:00`，`log_time_skew=0.7s`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:39:00+00:00`，`log_time` 范围 `2026-06-25T14:40:00.370+08:00` 到 `2026-06-25T14:40:00.931+08:00`，`log_time_skew=0.6s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:39:00+00:00`，`dates=444 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:39:00.000+00:00`。
- 成交/订单/信号日志质量正常：CTP `order.log tail_rows=1476 bad_json=0 bad_1970=0 latest=2026-06-25T06:38:00+00:00`、`trade.log tail_rows=794 bad_json=0 bad_1970=0 latest=2026-06-25T06:39:00+00:00`、`signal.log tail_rows=498 bad_json=0 bad_1970=0 latest=2026-06-25T06:39:00+00:00`；MT5 `order.log tail_rows=5151 bad_json=0 bad_1970=0 latest=2026-06-25T06:38:00+00:00`、`trade.log tail_rows=2858 bad_json=0 bad_1970=0 latest=2026-06-25T06:39:00+00:00`、`signal.log tail_rows=1722 bad_json=0 bad_1970=0 latest=2026-06-25T06:39:00+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:40:50` 的总 PSS 增量约 `+19.0MB`、日志 `+8.3MB`、CPU 从 `3.1%` 降至 `2.4%`；MT5 holder 从 `11:32:09` 到 `14:40:51` 的总 PSS 增量约 `+22.7MB`、日志 `+13.6MB`、CPU 从 `4.0%` 降至 `3.6%`。按全窗口折算，CTP PSS 约 `+5.08MB/h`、MT5 PSS 约 `+7.22MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `14M`、MT5 `29M`，`reports=107M`、根 `logs=109M`。
- 单进程离群检查正常：CTP 单进程 RSS `50.3-50.8MB`，MT5 单进程 RSS `50.6-52.3MB`；100 个活动进程线程数最大 5、FD 最大 22，未见异常 FD 泄漏或单进程内存尖峰。后端 WARNING 仍只有启动时默认管理员密码提示及 09:00 前后的两条 slow request 历史记录，未见持续新增。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 1 条 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 14:34-14:36 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- 元数据一致性正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 not_running=0 bad_pid=0 missing_runtime=0`，与真实 `/proc` 子进程计数一致。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:34:00+00:00`，`log_time` 范围 `2026-06-25T14:35:01.143+08:00` 到 `2026-06-25T14:35:01.835+08:00`，`log_time_skew=0.7s`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:34:00+00:00`，`log_time` 范围 `2026-06-25T14:35:00.304+08:00` 到 `2026-06-25T14:35:00.879+08:00`，`log_time_skew=0.6s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:34:00+00:00`，`dates=439 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:34:00.000+00:00`。
- 成交/订单/信号日志质量正常：CTP `order.log tail_rows=1383 bad_json=0 bad_1970=0 latest=2026-06-25T06:33:00+00:00`、`trade.log tail_rows=744 bad_json=0 bad_1970=0 latest=2026-06-25T06:34:00+00:00`、`signal.log tail_rows=463 bad_json=0 bad_1970=0 latest=2026-06-25T06:34:00+00:00`；MT5 `order.log tail_rows=5127 bad_json=0 bad_1970=0 latest=2026-06-25T06:33:00+00:00`、`trade.log tail_rows=2845 bad_json=0 bad_1970=0 latest=2026-06-25T06:34:00+00:00`、`signal.log tail_rows=1714 bad_json=0 bad_1970=0 latest=2026-06-25T06:34:00+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:36:17` 的总 PSS 增量约 `+18.9MB`、日志 `+7.9MB`、CPU 从 `3.1%` 降至 `2.6%`；MT5 holder 从 `11:32:09` 到 `14:36:15` 的总 PSS 增量约 `+22.5MB`、日志 `+13.3MB`、CPU 从 `4.0%` 到 `4.3%`。按全窗口折算，CTP PSS 约 `+5.16MB/h`、MT5 PSS 约 `+7.33MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `13M`、MT5 `28M`，`reports=107M`、根 `logs=109M`。
- 单进程离群检查正常：CTP 单进程 RSS `50.3-50.8MB`，MT5 单进程 RSS `50.6-52.3MB`；100 个活动进程线程数最大 5、FD 最大 22，未见异常 FD 泄漏或单进程内存尖峰。后端 WARNING 仍只有启动时默认管理员密码提示及 09:00 前后的两条 slow request 历史记录，未见持续新增。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 1 条 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 14:29-14:31 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`，100 个子进程均为 `S (sleeping)`。
- 元数据一致性正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 not_running=0 bad_pid=0 missing_runtime=0`，与真实 `/proc` 子进程计数一致。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:29:00+00:00`，`log_time` 范围 `2026-06-25T14:30:01.124+08:00` 到 `2026-06-25T14:30:01.652+08:00`，`log_time_skew=0.5s`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:29:00+00:00`，`log_time` 范围 `2026-06-25T14:30:00.338+08:00` 到 `2026-06-25T14:30:00.900+08:00`，`log_time_skew=0.6s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:29:00+00:00`，`dates=434 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:29:00.000+00:00`。
- 成交/订单/信号日志质量正常：CTP `order.log tail_rows=1287 bad_json=0 bad_1970=0 latest=2026-06-25T06:28:00+00:00`、`trade.log tail_rows=694 bad_json=0 bad_1970=0 latest=2026-06-25T06:29:00+00:00`、`signal.log tail_rows=434 bad_json=0 bad_1970=0 latest=2026-06-25T06:29:00+00:00`；MT5 `order.log tail_rows=5043 bad_json=0 bad_1970=0 latest=2026-06-25T06:28:00+00:00`、`trade.log tail_rows=2804 bad_json=0 bad_1970=0 latest=2026-06-25T06:29:00+00:00`、`signal.log tail_rows=1686 bad_json=0 bad_1970=0 latest=2026-06-25T06:29:00+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:31:14` 的总 PSS 增量约 `+18.6MB`、日志 `+7.6MB`、CPU 从 `3.1%` 到 `3.2%`；MT5 holder 从 `11:32:09` 到 `14:31:08` 的总 PSS 增量约 `+22.0MB`、日志 `+12.9MB`、CPU 从 `4.0%` 到 `5.0%`。按全窗口折算，CTP PSS 约 `+5.20MB/h`、MT5 PSS 约 `+7.37MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `13M`、MT5 `28M`，`reports=107M`、根 `logs=109M`。
- 单进程离群检查正常：CTP 单进程 RSS `50.3-50.8MB`，MT5 单进程 RSS `50.6-52.3MB`；100 个活动进程线程数最大 5、FD 最大 22，未见异常 FD 泄漏或单进程内存尖峰。后端 WARNING 只有启动时默认管理员密码提示及 09:00 前后的两条 slow request 历史记录，未见持续新增。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 1 条 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 14:24-14:26 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- 元数据一致性正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 not_running=0 bad_pid=0 missing_runtime=0`，与真实 `/proc` 子进程计数一致。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:24:00+00:00`，`log_time` 范围 `2026-06-25T14:25:01.589+08:00` 到 `2026-06-25T14:25:02.081+08:00`，`log_time_skew=0.5s`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:24:00+00:00`，`log_time` 范围 `2026-06-25T14:25:00.370+08:00` 到 `2026-06-25T14:25:00.796+08:00`，`log_time_skew=0.4s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:24:00+00:00`，`dates=429 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:24:00.000+00:00`。
- 成交/订单/信号日志质量正常：CTP `order.log tail_rows=1209 bad_json=0 bad_1970=0 latest=2026-06-25T06:23:00+00:00`、`trade.log tail_rows=649 bad_json=0 bad_1970=0 latest=2026-06-25T06:24:00+00:00`、`signal.log tail_rows=408 bad_json=0 bad_1970=0 latest=2026-06-25T06:24:00+00:00`；MT5 `order.log tail_rows=4974 bad_json=0 bad_1970=0 latest=2026-06-25T06:23:00+00:00`、`trade.log tail_rows=2764 bad_json=0 bad_1970=0 latest=2026-06-25T06:24:00+00:00`、`signal.log tail_rows=1664 bad_json=0 bad_1970=0 latest=2026-06-25T06:24:00+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:26:10` 的总 PSS 增量约 `+18.4MB`、日志 `+7.2MB`、CPU 从 `3.1%` 降至 `3.0%`；MT5 holder 从 `11:32:09` 到 `14:26:02` 的总 PSS 增量约 `+21.6MB`、日志 `+12.6MB`、CPU 从 `4.0%` 降至 `3.9%`。按全窗口折算，CTP PSS 约 `+5.26MB/h`、MT5 PSS 约 `+7.45MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `13M`、MT5 `27M`，`reports=107M`、根 `logs=109M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 1 条 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 14:18-14:20 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:18:00+00:00`，`log_time` 范围 `2026-06-25T14:19:01.502+08:00` 到 `2026-06-25T14:19:01.913+08:00`，`log_time_skew=0.4s`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:18:00+00:00`，`log_time` 范围 `2026-06-25T14:19:00.376+08:00` 到 `2026-06-25T14:19:00.923+08:00`，`log_time_skew=0.5s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:19:00+00:00`，`dates=424 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:19:00.000+00:00`。
- 成交/订单/信号日志质量正常：CTP `order.log tail_rows=1152 bad_json=0 bad_1970=0 latest=2026-06-25T06:17:00+00:00`、`trade.log tail_rows=614 bad_json=0 bad_1970=0 latest=2026-06-25T06:18:00+00:00`、`signal.log tail_rows=387 bad_json=0 bad_1970=0 latest=2026-06-25T06:18:00+00:00`；MT5 `order.log tail_rows=4896 bad_json=0 bad_1970=0 latest=2026-06-25T06:17:00+00:00`、`trade.log tail_rows=2714 bad_json=0 bad_1970=0 latest=2026-06-25T06:18:00+00:00`、`signal.log tail_rows=1636 bad_json=0 bad_1970=0 latest=2026-06-25T06:18:00+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:20:06` 的总 PSS 增量约 `+18.2MB`、日志 `+6.8MB`、CPU 从 `3.1%` 持平为 `3.1%`；MT5 holder 从 `11:32:09` 到 `14:20:25` 的总 PSS 增量约 `+21.1MB`、日志 `+12.1MB`、CPU 从 `4.0%` 升至 `4.5%`。按全窗口折算，CTP PSS 约 `+5.36MB/h`、MT5 PSS 约 `+7.52MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `12M`、MT5 `27M`，`reports=107M`、根 `logs=109M`。
- 单进程离群检查正常：CTP 单进程 RSS `50.3-50.7MB`，MT5 单进程 RSS `50.6-52.3MB`；100 个活动进程线程数最大 5、FD 最大 22，未见异常 FD 泄漏或单进程内存尖峰。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 14:13-14:16 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- 元数据一致性正常：`src/backend/data/live_trading_instances.json` 为 `total=100 running=100 not_running=0 bad_pid=0 missing_runtime=0`，与真实 `/proc` 子进程计数一致。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:13:00+00:00`，新增数据 `log_time` 范围 `2026-06-25T14:14:01.958+08:00` 到 `2026-06-25T14:14:02.445+08:00`，`log_time_skew=0.5s`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:13:00+00:00`，`log_time` 范围 `2026-06-25T14:14:00.331+08:00` 到 `2026-06-25T14:14:00.868+08:00`，`log_time_skew=0.5s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:14:00+00:00`，`dates=419 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:14:00.000+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:15:33` 的总 PSS 增量约 `+18.1MB`、日志 `+6.4MB`、CPU 从 `3.1%` 降至 `2.7%`；MT5 holder 从 `11:32:09` 到 `14:15:50` 的总 PSS 增量约 `+20.8MB`、日志 `+11.8MB`、CPU 从 `4.0%` 持平为 `4.0%`。按全窗口折算，CTP PSS 约 `+5.45MB/h`、MT5 PSS 约 `+7.62MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `12M`、MT5 `27M`，`reports=107M`、根 `logs=109M`。
- 单进程离群检查正常：CTP 单进程 RSS `50.3-50.7MB`，MT5 单进程 RSS `50.6-52.3MB`；100 个活动进程线程数最大 5、FD 最大 22，未见异常 FD 泄漏或单进程内存尖峰。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 14:09-14:11 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:09:00+00:00`，新增数据 `log_time` 范围 `2026-06-25T14:10:01.166+08:00` 到 `2026-06-25T14:10:01.663+08:00`，`log_time_skew=0.5s`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:09:00+00:00`，`log_time` 范围 `2026-06-25T14:10:00.305+08:00` 到 `2026-06-25T14:10:01.080+08:00`，`log_time_skew=0.8s`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:10:00+00:00`，`dates=415 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:10:00.000+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:11:01` 的总 PSS 增量约 `+17.9MB`、日志 `+6.1MB`、CPU 从 `3.1%` 降至 `2.8%`；MT5 holder 从 `11:32:09` 到 `14:11:14` 的总 PSS 增量约 `+20.3MB`、日志 `+11.5MB`、CPU 从 `4.0%` 降至 `3.9%`。按全窗口折算，CTP PSS 约 `+5.52MB/h`、MT5 PSS 约 `+7.66MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `12M`、MT5 `26M`，`reports=107M`、根 `logs=109M`。
- 单进程离群检查正常：CTP 单进程 RSS `50.3-50.7MB`，MT5 单进程 RSS `50.6-52.3MB`；100 个活动进程线程数最大 5、FD 最大 22，未见异常 FD 泄漏或单进程内存尖峰。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 14:05-14:08 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:05:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T14:06:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:05:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:06:00+00:00`，`dates=411 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:06:00.000+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:07:29` 的总 PSS 增量约 `+17.9MB`、日志 `+5.9MB`、CPU 从 `3.1%` 降至 `3.0%`；MT5 holder 从 `11:32:09` 到 `14:07:40` 的总 PSS 增量约 `+20.0MB`、日志 `+11.2MB`、CPU 从 `4.0%` 升至 `4.1%`。按全窗口折算，CTP PSS 约 `+5.62MB/h`、MT5 PSS 约 `+7.72MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `11M`、MT5 `26M`，`reports=107M`、根 `logs=109M`。
- 单进程离群检查正常：CTP 单进程 RSS `50.3-50.7MB`，MT5 单进程 RSS `50.6-52.2MB`；100 个活动进程线程数最大 5、FD 最大 22，未见异常 FD 泄漏或单进程内存尖峰。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 14:02-14:04 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:02:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T14:03:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T06:02:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:03:00+00:00`，`dates=408 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:03:00.000+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:04:27` 的总 PSS 增量约 `+17.8MB`、日志 `+5.6MB`、CPU 从 `3.1%` 降至 `3.0%`；MT5 holder 从 `11:32:09` 到 `14:04:06` 的总 PSS 增量约 `+19.8MB`、日志 `+10.9MB`、CPU 从 `4.0%` 升至 `4.1%`。按全窗口折算，CTP PSS 约 `+5.68MB/h`、MT5 PSS 约 `+7.82MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `11M`、MT5 `26M`，`reports=107M`、根 `logs=109M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:59-14:01 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:59:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T14:00:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:59:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T06:00:00+00:00`，`dates=405 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T06:00:00.000+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `14:00:55` 的总 PSS 增量约 `+16.5MB`、日志 `+5.3MB`、CPU 从 `3.1%` 降至 `2.5%`；MT5 holder 从 `11:32:09` 到 `14:00:32` 的总 PSS 增量约 `+19.1MB`、日志 `+10.6MB`、CPU 从 `4.0%` 升至 `4.4%`。按全窗口折算，CTP PSS 约 `+5.37MB/h`、MT5 PSS 约 `+7.72MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `11M`、MT5 `25M`，`reports=107M`、根 `logs=109M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:55-13:57 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:55:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T13:56:04.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:55:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:56:00+00:00`，`dates=401 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T05:56:00.000+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:57:23` 的总 PSS 增量约 `+16.4MB`、日志 `+5.1MB`、CPU 从 `3.1%` 持平为 `3.1%`；MT5 holder 从 `11:32:09` 到 `13:57:28` 的总 PSS 增量约 `+18.8MB`、日志 `+10.4MB`、CPU 从 `4.0%` 升至 `4.2%`。按全窗口折算，CTP PSS 约 `+5.44MB/h`、MT5 PSS 约 `+7.76MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `10M`、MT5 `25M`，`reports=107M`、根 `logs=109M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:52-13:54 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:52:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T13:53:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:52:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:53:00+00:00`，`dates=398 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T05:53:00.000+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:53:51` 的总 PSS 增量约 `+16.3MB`、日志 `+4.8MB`、CPU 从 `3.1%` 降至 `2.5%`；MT5 holder 从 `11:32:09` 到 `13:53:54` 的总 PSS 增量约 `+18.6MB`、日志 `+10.1MB`、CPU 从 `4.0%` 降至 `3.6%`。按全窗口折算，CTP PSS 约 `+5.51MB/h`、MT5 PSS 约 `+7.87MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `9.7M`、MT5 `25M`，`reports=107M`、根 `logs=109M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:47-13:50 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:48:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T13:49:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:48:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:48:00+00:00`，`dates=393 strategies=100 future_gt_120s=0`，组合 positions 最新 `2026-06-25T05:48:00.000+00:00`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:50:19` 的总 PSS 增量约 `+14.9MB`、日志 `+4.6MB`、CPU 从 `3.1%` 降至 `3.0%`；MT5 holder 从 `11:32:09` 到 `13:50:20` 的总 PSS 增量约 `+18.1MB`、日志 `+9.9MB`、CPU 从 `4.0%` 降至 `3.6%`。按全窗口折算，CTP PSS 约 `+5.14MB/h`、MT5 PSS 约 `+7.86MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `9.3M`、MT5 `25M`，`reports=107M`、根 `logs=109M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:43-13:45 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:44:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T13:45:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:44:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:44:00+00:00`，`dates=389 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:45:16` 的总 PSS 增量约 `+13.2MB`、日志 `+4.3MB`、CPU 从 `3.1%` 持平为 `3.1%`；MT5 holder 从 `11:32:09` 到 `13:45:15` 的总 PSS 增量约 `+17.6MB`、日志 `+9.6MB`、CPU 从 `4.0%` 降至 `3.4%`。按全窗口折算，CTP PSS 约 `+4.69MB/h`、MT5 PSS 约 `+7.93MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `9.0M`、MT5 `24M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:40-13:42 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:40:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T13:41:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:40:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:40:00+00:00`，`dates=385 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:41:44` 的总 PSS 增量约 `+13.1MB`、日志 `+4.0MB`、CPU 从 `3.1%` 降至 `2.8%`；MT5 holder 从 `11:32:09` 到 `13:41:41` 的总 PSS 增量约 `+17.4MB`、日志 `+9.3MB`、CPU 从 `4.0%` 持平为 `4.0%`。按全窗口折算，CTP PSS 约 `+4.75MB/h`、MT5 PSS 约 `+8.06MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `8.7M`、MT5 `24M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:37-13:39 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:37:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T13:38:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:37:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:37:00+00:00`，`dates=382 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:38:42` 的总 PSS 增量约 `+12.8MB`、日志 `+3.8MB`、CPU 从 `3.1%` 到 `3.2%`；MT5 holder 从 `11:32:09` 到 `13:38:37` 的总 PSS 增量约 `+17.2MB`、日志 `+9.1MB`、CPU 从 `4.0%` 降至 `3.6%`。按全窗口折算，CTP PSS 约 `+4.73MB/h`、MT5 PSS 约 `+8.16MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `8.5M`、MT5 `24M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:34-13:35 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 保持 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:34:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T13:35:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:34:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:34:00+00:00`，`dates=379 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:35:10` 的总 PSS 增量约 `+12.8MB`、日志 `+3.6MB`、CPU 从 `3.1%` 降至 `2.9%`；MT5 holder 从 `11:32:09` 到 `13:35:03` 的总 PSS 增量约 `+17.1MB`、日志 `+8.8MB`、CPU 从 `4.0%` 降至 `3.8%`。按全窗口折算，CTP PSS 约 `+4.84MB/h`、MT5 PSS 约 `+8.35MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `8.2M`、MT5 `24M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:30-13:32 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 已从 20/30 过渡恢复为 50 个单元全量写入：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:30:00+00:00`，新增数据 `log_time` 样例为 `2026-06-25T13:31:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=50 data_quiet=0 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:30:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:30:00+00:00`，`dates=375 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:31:39` 的总 PSS 增量约 `+12.4MB`、日志 `+3.3MB`、CPU 从 `3.1%` 降至 `2.4%`；MT5 holder 从 `11:32:09` 到 `13:31:29` 的总 PSS 增量约 `+16.8MB`、日志 `+8.5MB`、CPU 从 `4.0%` 降至 `3.7%`。按全窗口折算，CTP PSS 约 `+4.79MB/h`、MT5 PSS 约 `+8.45MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `7.9M`、MT5 `23M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:27-13:28 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=20 data_quiet=30 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 20/30 分布持续稳定：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 分布为 `2026-06-25T05:27:00+00:00:20`、`2026-06-25T03:29:00+00:00:25` 与 `2026-06-25T03:28:00+00:00:5`，新增数据 `log_time` 样例为 `2026-06-25T13:28:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=20 data_quiet=30 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:27:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:27:00+00:00`，`dates=372 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:28:07` 的总 PSS 增量约 `+11.6MB`、日志 `+3.1MB`、CPU 从 `3.1%` 降至 `2.2%`；MT5 holder 从 `11:32:09` 到 `13:28:26` 的总 PSS 增量约 `+16.7MB`、日志 `+8.3MB`、CPU 从 `4.0%` 降至 `3.7%`。按全窗口折算，CTP PSS 约 `+4.59MB/h`、MT5 PSS 约 `+8.62MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `7.7M`、MT5 `23M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:24-13:25 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=20 data_quiet=30 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 20/30 分布持续稳定：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 分布为 `2026-06-25T05:24:00+00:00:20`、`2026-06-25T03:29:00+00:00:25` 与 `2026-06-25T03:28:00+00:00:5`，新增数据 `log_time` 样例为 `2026-06-25T13:25:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=20 data_quiet=30 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:24:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:24:00+00:00`，`dates=369 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:25:05` 的总 PSS 增量约 `+11.6MB`、日志 `+3.0MB`、CPU 从 `3.1%` 降至 `2.2%`；MT5 holder 从 `11:32:09` 到 `13:24:52` 的总 PSS 增量约 `+16.5MB`、日志 `+8.0MB`、CPU 从 `4.0%` 降至 `3.3%`。按全窗口折算，CTP PSS 约 `+4.68MB/h`、MT5 PSS 约 `+8.78MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `7.6M`、MT5 `23M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:20-13:21 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=20 data_quiet=30 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 20/30 分布持续稳定：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 分布为 `2026-06-25T05:20:00+00:00:20`、`2026-06-25T03:29:00+00:00:25` 与 `2026-06-25T03:28:00+00:00:5`，新增数据 `log_time` 样例为 `2026-06-25T13:21:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=20 data_quiet=30 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:20:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:20:00+00:00`，`dates=365 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:21:03` 的总 PSS 增量约 `+11.5MB`、日志 `+2.9MB`、CPU 从 `3.1%` 降至 `2.4%`；MT5 holder 从 `11:32:09` 到 `13:21:18` 的总 PSS 增量约 `+16.4MB`、日志 `+7.8MB`、CPU 从 `4.0%` 降至 `3.6%`。按全窗口折算，CTP PSS 约 `+4.77MB/h`、MT5 PSS 约 `+9.02MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `7.4M`、MT5 `23M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:16-13:18 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=20 data_quiet=30 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 20/30 分布持续稳定：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 分布为 `2026-06-25T05:16:00+00:00:20`、`2026-06-25T03:29:00+00:00:25` 与 `2026-06-25T03:28:00+00:00:5`，新增数据 `log_time` 样例为 `2026-06-25T13:17:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=20 data_quiet=30 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:16:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:16:00+00:00`，`dates=361 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:17:31` 的总 PSS 增量约 `+11.5MB`、日志 `+2.8MB`、CPU 从 `3.1%` 降至 `2.4%`；MT5 holder 从 `11:32:09` 到 `13:17:45` 的总 PSS 增量约 `+16.3MB`、日志 `+7.6MB`、CPU 从 `4.0%` 降至 `3.5%`。按全窗口折算，CTP PSS 约 `+4.89MB/h`、MT5 PSS 约 `+9.26MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `7.3M`、MT5 `22M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:09-13:10 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=20 data_quiet=30 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 20/30 分布持续稳定：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 分布为 `2026-06-25T05:09:00+00:00:20`、`2026-06-25T03:29:00+00:00:25` 与 `2026-06-25T03:28:00+00:00:5`，新增数据 `log_time` 样例为 `2026-06-25T13:10:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=20 data_quiet=30 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:09:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:09:00+00:00`，`dates=354 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:10:28` 的总 PSS 增量约 `+11.4MB`、日志 `+2.6MB`、CPU 从 `3.1%` 降至 `2.2%`；MT5 holder 从 `11:32:09` 到 `13:10:37` 的总 PSS 增量约 `+15.7MB`、日志 `+7.0MB`、CPU 从 `4.0%` 降至 `3.8%`。按全窗口折算，CTP PSS 约 `+5.10MB/h`、MT5 PSS 约 `+9.57MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `7.1M`、MT5 `22M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:05-13:06 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=20 data_quiet=30 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 20/30 分布持续稳定：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 分布为 `2026-06-25T05:05:00+00:00:20`、`2026-06-25T03:29:00+00:00:25` 与 `2026-06-25T03:28:00+00:00:5`，新增数据 `log_time` 样例为 `2026-06-25T13:06:01.xxx+08:00`，`future_gt_120s=0`。监控继续正确归为 `data_log=20 data_quiet=30 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:05:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:05:00+00:00`，`dates=350 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:06:56` 的总 PSS 增量约 `+11.3MB`、日志 `+2.5MB`、CPU 从 `3.1%` 降至 `2.4%`；MT5 holder 从 `11:32:09` 到 `13:07:04` 的总 PSS 增量约 `+15.2MB`、日志 `+6.8MB`、CPU 从 `4.0%` 降至 `3.6%`。按全窗口折算，CTP PSS 约 `+5.19MB/h`、MT5 PSS 约 `+9.61MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `7.0M`、MT5 `22M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 13:01-13:02 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=20 data_quiet=30 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- CTP 出现部分合约交易小节恢复：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 分布为 `2026-06-25T05:01:00+00:00:20`、`2026-06-25T03:29:00+00:00:25` 与 `2026-06-25T03:28:00+00:00:5`，新增数据 `log_time` 样例为 `2026-06-25T13:02:01.xxx+08:00`，`future_gt_120s=0`。监控将其正确归为 `data_log=20 data_quiet=30 alerts=-`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T05:01:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T05:01:00+00:00`，`dates=346 strategies=100 future_gt_120s=0`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `13:02:54` 的总 PSS 增量约 `+11.2MB`、日志 `+2.4MB`、CPU 从 `3.1%` 降至 `2.6%`；MT5 holder 从 `11:32:09` 到 `13:02:59` 的总 PSS 增量约 `+14.7MB`、日志 `+6.4MB`、CPU 从 `4.0%` 降至 `3.5%`。按全窗口折算，CTP PSS 约 `+5.31MB/h`、MT5 PSS 约 `+9.71MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.9M`、MT5 `21M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:57-12:59 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:57:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:57:00+00:00`，`dates=342 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:59:22` 的总 PSS 增量约 `+11.1MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.7%`；MT5 holder 从 `11:32:09` 到 `12:59:26` 的总 PSS 增量约 `+14.6MB`、日志 `+6.2MB`、CPU 从 `4.0%` 降至 `3.5%`。按全窗口折算，CTP PSS 约 `+5.42MB/h`、MT5 PSS 约 `+10.04MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `21M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:54-12:55 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:54:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:54:00+00:00`，`dates=339 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:55:21` 的总 PSS 增量约 `+11.1MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.6%`；MT5 holder 从 `11:32:09` 到 `12:55:22` 的总 PSS 增量约 `+14.4MB`、日志 `+6.0MB`、CPU 从 `4.0%` 降至 `3.4%`。按全窗口折算，CTP PSS 约 `+5.60MB/h`、MT5 PSS 约 `+10.38MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `21M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:50-12:51 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:50:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:50:00+00:00`，`dates=335 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:51:49` 的总 PSS 增量约 `+11.1MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.6%`；MT5 holder 从 `11:32:09` 到 `12:51:49` 的总 PSS 增量约 `+13.0MB`、日志 `+5.7MB`、CPU 从 `4.0%` 降至 `3.0%`。按全窗口折算，CTP PSS 约 `+5.77MB/h`、MT5 PSS 约 `+9.79MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `20M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:46-12:47 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:46:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:46:00+00:00`，`dates=331 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:47:47` 的总 PSS 增量约 `+11.1MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.6%`；MT5 holder 从 `11:32:09` 到 `12:47:45` 的总 PSS 增量约 `+10.2MB`、日志 `+5.4MB`、CPU 从 `4.0%` 降至 `3.2%`。按全窗口折算，CTP PSS 约 `+5.98MB/h`、MT5 PSS 约 `+8.12MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `20M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:43-12:44 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:43:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:43:00+00:00`，`dates=328 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:44:46` 的总 PSS 增量约 `+11.0MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.6%`；MT5 holder 从 `11:32:09` 到 `12:44:42` 的总 PSS 增量约 `+10.1MB`、日志 `+5.2MB`、CPU 从 `4.0%` 降至 `3.7%`。按全窗口折算，CTP PSS 约 `+6.09MB/h`、MT5 PSS 约 `+8.35MB/h`；当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `20M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:39-12:40 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:39:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:39:00+00:00`，`dates=324 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:40:44` 的总 PSS 增量约 `+10.9MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.7%`；MT5 holder 从 `11:32:09` 到 `12:40:38` 的总 PSS 增量约 `+8.4MB`、日志 `+4.9MB`、CPU 从 `4.0%` 降至 `3.1%`。当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `20M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:33-12:34 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:33:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:33:00+00:00`，`dates=318 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:34:10` 的总 PSS 增量约 `+10.8MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.6%`；MT5 holder 从 `11:32:09` 到 `12:34:32` 的总 PSS 增量约 `+8.1MB`、日志 `+4.5MB`、CPU 从 `4.0%` 降至 `3.5%`。当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `19M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:29-12:30 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:29:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:29:00+00:00`，`dates=314 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:30:39` 的总 PSS 增量约 `+10.8MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.4%`；MT5 holder 从 `11:32:09` 到 `12:30:28` 的总 PSS 增量约 `+7.8MB`、日志 `+4.1MB`、CPU 从 `4.0%` 降至 `3.8%`。当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `19M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:25-12:27 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:25:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:25:00+00:00`，`dates=310 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:27:07` 的总 PSS 增量约 `+10.7MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.4%`；MT5 holder 从 `11:32:09` 到 `12:26:55` 的总 PSS 增量约 `+7.6MB`、日志 `+3.9MB`、CPU 从 `4.0%` 降至 `3.6%`。当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `18M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:22-12:23 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:22:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:22:00+00:00`，`dates=307 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:23:05` 的总 PSS 增量约 `+10.6MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.4%`；MT5 holder 从 `11:32:09` 到 `12:23:22` 的总 PSS 增量约 `+8.4MB`、日志 `+3.7MB`、CPU 从 `4.0%` 降至 `3.5%`。当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `18M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:18-12:20 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:18:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:18:00+00:00`，`dates=303 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:20:04` 的总 PSS 增量约 `+10.6MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.6%`；MT5 holder 从 `11:32:09` 到 `12:19:49` 的总 PSS 增量约 `+8.1MB`、日志 `+3.4MB`、CPU 从 `4.0%` 降至 `3.2%`。当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `18M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:15-12:16 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:15:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:15:00+00:00`，`dates=300 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:16:32` 的总 PSS 增量约 `+10.5MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.8%`；MT5 holder 从 `11:32:09` 到 `12:16:46` 的总 PSS 增量约 `+7.8MB`、日志 `+3.1MB`、CPU 从 `4.0%` 降至 `3.1%`。当前没有 `rss_high/pss_high/log_high` 类告警，压测目录体量 CTP `6.7M`、MT5 `18M`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 已停止写入，里面的 `%s` 401 ERROR 属于修复前历史行；`GET /health` 返回 `200`。
- `2026-06-25 12:11-12:13 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_log=0 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 data_quiet=0 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:11:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:11:00+00:00`，`dates=296 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:13:00` 的总 PSS 增量约 `+10.4MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.7%`；MT5 holder 从 `11:32:09` 到 `12:12:42` 的总 PSS 增量约 `+7.4MB`、日志 `+2.8MB`、CPU 从 `4.0%` 降至 `3.5%`。当前没有 `rss_high/pss_high/log_high` 类告警。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前活跃后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 的 `%s` 401 ERROR 是停止写入的旧文件历史行，后续同类 401 已按现行代码记为 WARNING；`GET /health` 返回 `200`。
- `2026-06-25 12:05-12:09 CST`：本轮巡检发现并修复 `ensure_dual_stress_running.sh start` 只报告首个 split holder 的可观测性盲点；修复后 `start/status` 均列出 CTP split PID `906679`、MT5 split PID `992775` 和 monitor PID `889932`，未启动新的 dual supervisor。严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T04:04:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T04:04:00+00:00`，`dates=289 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `12:05:26` 的总 PSS 增量约 `+10.1MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.7%`；MT5 holder 从 `11:32:09` 到 `12:05:36` 的总 PSS 增量约 `+6.8MB`、日志 `+2.3MB`、CPU 从 `4.0%` 降至 `3.8%`。当前没有 `rss_high/pss_high/log_high` 类告警。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`src/backend/logs/app_2026-06-25.log` 中唯一 ERROR 是未认证 401 的旧日志级别噪声；`GET /health` 返回 `200`。
- `2026-06-25 11:59-12:00 CST`：本轮只读巡检未发现新的代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T03:59:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T03:59:00+00:00`，`dates=284 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `11:59:54` 的总 PSS 增量约 `+10.1MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.6%`；MT5 holder 从 `11:32:09` 到 `12:00:01` 的总 PSS 增量约 `+6.1MB`、日志 `+1.9MB`、CPU 从 `4.0%` 降至 `3.6%`。当前没有 `rss_high/pss_high/log_high` 类告警。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`GET /health` 返回 `200`。
- `2026-06-25 11:56 CST`：本轮只读巡检未发现新的代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T03:55:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T03:55:00+00:00`，`dates=280 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `11:56:52` 的总 PSS 增量约 `+10.0MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.5%`；MT5 holder 从 `11:32:09` 到 `11:56:59` 的总 PSS 增量约 `+5.5MB`、日志 `+1.7MB`、CPU 从 `4.0%` 降至 `3.5%`。当前没有 `rss_high/pss_high/log_high` 类告警。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`GET /health` 返回 `200`。
- `2026-06-25 11:52-11:53 CST`：本轮只读巡检未发现新的代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T03:52:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T03:52:00+00:00`，`dates=277 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 资源趋势正常：CTP holder 从 `10:56:25` 到 `11:53:21` 的总 PSS 增量约 `+9.8MB`、日志 `+2.3MB`、CPU 从 `3.1%` 降至 `1.6%`；MT5 holder 从 `11:32:09` 到 `11:53:26` 的总 PSS 增量约 `+5.0MB`、日志 `+1.5MB`、CPU 基本持平。当前没有 `rss_high/pss_high/log_high` 类告警。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前后端 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0；`GET /health` 返回 `200`。
- `2026-06-25 11:48 CST`：本轮只读巡检未发现新的代码修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T03:48:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T03:48:00+00:00`，`dates=273 strategies=100 future_gt_120s=0`。
- CTP 活动日志继续处于午休静默窗口：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；当前后端日志 `logs/backend.log` 从 PID `752932` 起 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0。`src/backend/logs/app_2026-06-25.log` 中唯一 ERROR 是 `04:06 CST` 修复前的历史 401 占位符日志，文件 `06:53 CST` 后已停止写入，不属于当前新异常。
- `2026-06-25 11:45 CST`：本轮只读巡检未发现新的修复项。`ensure_dual_stress_running.sh status` 显示 CTP `running=50 process=50 heartbeat=50 data_quiet=50 alerts=-`、MT5 `running=50 process=50 heartbeat=50 data_log=50 alerts=-`；严格 `/proc` 复验仍为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- MT5 活动日志继续推进且时间正确：50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T03:45:00+00:00`，`future_gt_120s=0`；认证 API `/portfolio/equity` 与 `/portfolio/simulation/equity` 最新点同为 `2026-06-25T03:45:00+00:00`，`dates=270 strategies=100 future_gt_120s=0`。
- CTP 活动日志在午休窗口内保持预期静默：50 个活动 `bar.log/value.log/position.log` 最新仍为 `2026-06-25T03:28:00+00:00` 或 `2026-06-25T03:29:00+00:00`，监控口径正确输出 `data_quiet=50 alerts=-`。
- 运行日志复扫：100 个活动单元 `error.log=0`、`subprocess.stderr.log=0`，`gateway.stderr.log` 合计 334 字节且无错误关键字；后端 PID `752932` 启动后 `ERROR/Traceback/RuntimeWarning/ModuleNotFoundError/Address already in use/overflow encountered` 均为 0。
- `2026-06-25 11:41 CST`：本轮只读巡检未发现新的 `backtrader_web`、`backtrader` 或 `bt_api_py` 缺陷。`ensure_dual_stress_running.sh status` 能识别 CTP split holder `906679`、MT5 split holder `992775` 和 monitor `889932`；严格 `/proc` 复验为 CTP `{'906679': 50}`、MT5 `{'992775': 50}`。
- 活动日志时间轴持续正确：MT5 50 个活动 `bar.log/value.log/position.log` 最新 `datetime` 全部为 `2026-06-25T03:40:00+00:00`，API 组合权益最新点同为 `2026-06-25T03:40:00+00:00`，`future_gt_120s=0`。CTP 50 个活动单元最新数据停在 `03:28/03:29 UTC`，对应国内期货 11:30 午间休市前最后分钟，监控正确归为 `data_quiet=50 alerts=-`。
- 活动错误日志复扫：100 个活动单元 `error.log` 与 `subprocess.stderr.log` 均为 0 字节，`gateway.stderr.log` 合计 334 字节且无 `Traceback/ERROR/CRITICAL/Exception/ModuleNotFoundError/Address already in use` 命中。
- 认证后 API 复验：overview `strategy_count=100 running_count=100 total_assets=50499808.38 total_pnl=-191.62`；`/portfolio/equity` 与 `/portfolio/simulation/equity` 均为 `dates=265 strategies=100 latest=2026-06-25T03:40:00+00:00 future_gt_120s=0`；`/portfolio/positions` 为 `total=100 dated=100 latest=2026-06-25T03:40:00.000+00:00`。

## 后续继续监控项

- 持续观察 100 个 CTP/MT5 子进程是否有策略异常退出或日志停止增长；当前双目标均为 `heartbeat=50 stale=0 alerts=-`。
- 持续观察 CTP split holder PID `1324657`、MT5 split holder PID `992775` 和只读 monitor PID `889932`，确认 `heartbeat.json` 每 30 秒更新且双目标 monitor 保持 `alerts=-`。
- 后续批量滚动重启不要使用 start 模式 `--no-hold`；优先使用 `--rolling-restart --no-stop-owned-on-signal` 的持有型 supervisor 分批推进。
- 后续如需再次安全滚动重启压测单元，继续使用 `--rolling-restart --no-stop-owned-on-signal`，并在每批完成后抽样检查 `logs/heartbeat.json`、`bar/value/position` 时间分布和子进程 env。
- 持续抽样检查 `bar.log/value.log/position.log` 的 `datetime` 与 epoch/交易所时区一致，防止重新出现 `UTC+8` 或 MT5 broker wall time 被错标为 `+00:00`。
- 继续观察 qcheck 修复后的 CPU 使用率，确认单进程 CPU 长期保持低占用且不因行情空窗回到忙等水平。
- 持续抽样检查 `logs/system.log`，确认 `session_started.event_time` 使用真实 wall-clock 时间，`store_connecting/store_connected.event_time` 带显式 UTC offset。
- 后续继续抽样检查子进程 `PYTHONPATH` 与 env，当前 100 个子进程已确认 `/home/yun/Documents/backtrader` 位于 `/home/yun/Documents/bt_api_py/bt_api_py` 之前，且 `BT_STORE_LOCAL_TIMEZONE=Asia/Shanghai`、`BT_FEED_ENABLE_LIGHT_COLUMNS=1` 缺失数为 0。
- 后续 CTP gateway 新启动或滚动重启后，抽样检查 `reports/ctp*_supervisor.log` 与对应单元 `logs/gateway.stderr.log`，确认原生 super-user/DMI warning 只落在单元 gateway stderr，不污染 supervisor 总控日志。
- 继续比对 `trade.log`、`position.log`、组合接口聚合结果和前端显示是否一致。
- 当前 100 个策略子进程已由新的持有型 supervisor 接管；后续需要安全滚动重启时，应继续使用 patched supervisor，避免再次因 DB 假 idle 退出并让策略失去父级 supervisor。
- 测试输出目前仍可能出现一条 `asyncio.selector_events` DEBUG 行，非错误；如后续需要更干净的 CI 输出，可再把测试环境的 `asyncio` logger 降到 WARNING。
- MT5 已配置 demo 账号并纳入 50 单元长时监控；后续重点观察 MT5 gateway 单账号共享 50 策略时的 WebSocket 稳定性、内存占用和组合风控聚合一致性。
