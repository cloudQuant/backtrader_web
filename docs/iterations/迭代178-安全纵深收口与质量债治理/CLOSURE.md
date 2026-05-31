# 迭代 178 关闭报告 — 安全纵深收口与质量债治理

**关闭日期**: 2026-05-31
**起点**: 迭代 177 收口（commit `e15d7bfc`）
**终点**: §A/§B/§D/§E 代码侧收口；§C 顺延（环境网络受限）；§F 决策记录
**性质**: 安全收口 / 异步正确性 / 质量债棘轮下行（非新产品特性）

---

## 0. 一句话结论

收口了 177 留下的两条最硬尾巴：① 把实盘网关层阻塞 I/O 从事件循环上移走（§B，P1 正确性），
② 为 git 历史凭据清除备好了可执行的 runbook + 脚本 + 门控 CI flip（§A，P0 安全的代码侧
闭环，破坏性运维动作交 owner）。同时把 16 处静默吞异常全部加上可观测日志（§D），并实测把
mypy 仓库级 baseline 从 1065 下拧到 1017（§E，证明棘轮能双向工作）。§C（pip-audit flip）
因本地环境无法访问 PyPI 顺延到 CI 执行。

---

## 1. 验收结果总表

| 项 | PLAN 目标 | 终态 | 状态 |
| --- | --- | --- | :---: |
| §B 阻塞 I/O 治理 | 3 个 async 网关端点改 to_thread | 实际覆盖 **7 个**阻塞端点 + 并发不阻塞回归测试 | ✅ |
| §D 吞异常留痕 | 16 处加日志 | 16 处全部 `logger.debug(exc_info=True)`，实盘/隧道路径 100% | ✅ |
| §E mypy 棘轮下行 | baseline 实测下降 | `app/api/live_trading` strict 清零，1065→**1017**（-48） | ✅ |
| §A git 历史清除收口 | runbook + 脚本 + 门控 flip | 全部就绪并验证；轮换/重写交 owner | ✅（代码侧） |
| §C pip-audit flip | 基线入库 + flip blocking | **顺延**：本地无法访问 PyPI，需 CI 干净网络 | ⏭️ |
| §F advisory flip 决策 | 决策清单 | §A/§C 已门控/顺延，其余记录理由 | ✅ |
| 质量基线 | ruff 0 / format 全过 / 测试绿 | 全部通过；mypy 棘轮稳定 1017 | ✅ |

---

## 2. §B — 实盘网关阻塞 I/O 治理（commit `22933b2e`）

`api/live_trading/api.py` 的多个 `async def` 端点直接调用同步阻塞的 manager 方法，
单个慢调用会阻塞整个事件循环。PLAN 预估 3 个端点，实测发现并修复 **7 个**：

| 端点 | 阻塞来源 | 处置 |
| --- | --- | --- |
| `get_gateway_health` | 文件读 + PID 存活检查 | `await asyncio.to_thread(mgr.get_gateway_health)` |
| `query_gateway_account` | runtime snapshot（持锁） | `to_thread` |
| `query_gateway_positions` | runtime positions（持锁） | `to_thread` |
| `disconnect_gateway` | `runtime.stop()` + `thread.join(timeout=5.0)` | `to_thread` |
| `get_live_detail` | `parse_all_logs` 日志文件解析 | `to_thread` |
| `get_live_kline` | `parse_data_log` + `parse_trade_log` + 目录扫描 | `to_thread` |
| `get_live_monthly_returns` | `parse_value_log` + 目录扫描 | `to_thread` |

`connect_gateway` 不动——它已正确用同步 `def`（FastAPI 自动丢线程池），是正面参照。
service 层内部保持同步，零行为变化（backlog P1#4 slice 2）。

**回归测试**：新增 `test_gateway_query_offloads_blocking_call`，mock 一个 `time.sleep(0.5)`
的慢查询，断言并发的轻量请求能在慢请求返回**之前**完成（`order == ["fast", "slow"]`）。
实测：去掉 `to_thread` 包裹后该测试 **fail**（exit 1），证明它有牙齿。

---

## 3. §D — 静默吞异常留痕（commit `3b140bc`）

16 处 `except Exception: pass`（实盘/隧道热路径为主）全部改为
`logger.debug(..., exc_info=True)`，保留 best-effort 吞行为（不改控制流），让异常可观测：

- `main.py`（2）：关停时 quote service / feature-flags 缓存清理
- `gateway/manual.py`（5）：端口释放兜底、retry 前 runtime stop、env 加载兜底、TUN 路由探测
- `ctp_tunnel.py`（4）：代理配置解析 + socket/selector 关闭清理
- `workspace/units.py`、`workspace/run_ops.py`：优化进度加载
- `sync_service.py`：远程临时 dump 清理（**新增模块 logger**——原文件无任何 logging）
- `quote_service.py`：网关就绪 ping 探测
- `reqdocs_migration_service.py`：MongoDB client 关闭（**新增模块 logger**）

验收：复扫 `except Exception` + `pass` = **0**；相关服务测试全绿；mypy 棘轮不变。

---

## 4. §E — mypy 仓库级棘轮下行（commit `3fa20cf`）

证明棘轮不仅拦新债、也能往下拧。对 `app/api/live_trading` 整包做 strict 清零：

- 给每个路由 handler 补 `current_user: TokenPayload` 与精确返回类型（`InstanceData` /
  `StartResult` / `StopResult` / `ConnectResult` / `OperationResult` / 响应 schema），
  清掉 48 个 `no-untyped-def`。
- 把 `sys.modules`-swap shim 导入（`live_trading_manager`/`strategy_service`/`deps`/
  `manual_gateway_service`）换成 mypy 可解析的真实模块直接导入——**零运行时变化**
  （shim 本就是 re-export）。
- 给 `credentials.py` 两个 helper 补类型。

终态：`mypy app/api/live_trading` = 0 issues；仓库级 baseline `1065 → 1017` 并 `--update`
锁定。棘轮牙齿验证：注入 +1 错误 → `errors=1018 baseline=1017` → exit 1。

---

## 5. §A — git 历史凭据清除收口（commit `4d512051`，P0 代码侧）

177 §D 已 untrack 泄露文件并加 gitleaks 门禁，但**历史快照仍含明文凭据**：

```bash
git log --all --oneline -- src/backend/data/manual_gateways.json
# 命中 f575cce6 / b6d3097a（早于 177 的 untrack 提交 2e620ab5）
```

实测确认 7 类文件仍在历史中（manual_gateways.json + manual_gateways/ + sync_config.json +
sync_history.json + auto_trading_config.json + live_trading_instances.json +
quote_custom_symbols.json）。清除需 force-push 重写历史，属破坏性运维、不可由 agent 执行。

**本迭代代码侧交付（可闭环部分）**：

1. `scripts/ops/purge_secret_history.sh`：`git filter-repo --invert-paths` 包装。
   - `--dry-run`：列出 7 类待清路径（已验证输出正确，无误伤）。
   - `--execute`：三道交互确认（`rotated` → `coordinated` → `PURGE`），任一不符即中止；
     缺 `git-filter-repo` 时给出安装指引；完成后打印 force-push + re-clone + flip 后续步骤。
2. `ROTATION_RUNBOOK.md`：逐 provider 轮换检查单（Binance/OKX/HTX/CTP/MT5/IB + 本地与远程
   MySQL root）+ 历史清除 + force-push + 协作者 re-clone + CI flip 全流程，每步可勾选。
3. CI 门控 flip：`ci.yml` 的全史 `secret-scan` 步骤现由仓库变量
   **`SECRET_SCAN_HISTORY_BLOCKING`** 控制——历史清干净后设为 `true` 即从 advisory 翻成
   blocking，**无需改代码**。PR-diff 扫描保持 blocking。YAML 已校验通过。
4. `REFACTORING_BACKLOG.md` P0#3 更新：仍 OPEN（待 owner 轮换/重写），补上 178 工具就绪证据链。

**⛔ 仍需 owner 执行（非代码、本迭代不做）**：按 RUNBOOK 轮换全部凭据 → 跑
`purge_secret_history.sh --execute` → force-push → 通知全员 re-clone → 设
`SECRET_SCAN_HISTORY_BLOCKING=true`。

---

## 6. §C — pip-audit flip（顺延）

PLAN 计划在 CI 拿 `pip-audit` 漏洞基线后 flip blocking。**本地环境无法访问 PyPI**
（`pip-audit` 对 `pypi.org` 的 HTTPS 握手 `SSL: UNEXPECTED_EOF`，并最终超时），无法产出
可信的漏洞基线。按"不臆造验证结果"的纪律，本项**顺延到 CI 干净网络执行**：

- 当前 CI `ci.yml:493` 仍 `pip-audit ... || true`（advisory），不阻塞。
- 后续步骤（在 CI 或可访问 PyPI 的环境）：跑 `pip-audit --format json` 拿基线 → 逐条
  升级或 `--ignore-vuln <ID>` + 记录理由 → 去掉 `|| true` flip blocking。

> 这是诚实的"未完成"标注，而非假装通过。基线一旦在 CI 产出即可在下一个小迭代收口。

---

## 7. §F — CI advisory 门禁 flip 决策记录

| 门禁 | 当前 | 178 处置 |
| --- | --- | --- |
| `secret-scan` 全史 | advisory | §A：已门控，历史清除后设 `SECRET_SCAN_HISTORY_BLOCKING=true` 即 blocking |
| `pip-audit` | advisory | §C：顺延，待 CI 拿基线 |
| i18n 全量 strict / e2e i18n | advisory | 未在本迭代收敛，沿用 177 顺延理由（需 baseline 清中文泄露） |
| `monorepo-check` | advisory | 团队策略项，不在本迭代 flip |

---

## 8. 未完成 / 顺延项

- **§C pip-audit flip**：环境网络受限，顺延到 CI 执行（见 §6）。
- **§A 轮换 + 历史重写**：P0 owner 运维动作，代码侧已备好全部工具（见 §5）。
- **P1#4 网关家族拆分（slice 3）**：本迭代只做了 slice 2（to_thread），按文件拆分仍需独立
  分支 + 纸面验证。
- **F5 超大文件拆分**：standing 规则，滚动推进。
- **前端**：本迭代未触前端，沿用 177 终态（vue-tsc 0 / vitest 全绿）。

---

## 9. 提交清单

| commit | 内容 |
| --- | --- |
| `22933b2e` | fix(live-trading): offload blocking gateway I/O via asyncio.to_thread (§B) |
| `3b140bc` | refactor(observability): log swallowed exceptions on live/tunnel/sync paths (§D) |
| `3fa20cf` | ci(types): strict-clean app/api/live_trading, ratchet 1065→1017 (§E) |
| `4d512051` | ops(security): history-purge runbook + gated secret-scan blocking flip (§A) |

---

## 10. 复现命令

```bash
# §B 阻塞 I/O 已 offload + 回归测试
grep -n "asyncio.to_thread" src/backend/app/api/live_trading/api.py
python -m pytest tests/test_live_trading_api.py -q          # 39 passed（含并发测试）

# §D 吞异常已清零
grep -rn -A1 "except Exception" src/backend/app --include="*.py" | grep -B1 "pass$" | grep except  # 空

# §E mypy 棘轮
python -m mypy app/api/live_trading                         # 0 issues
python scripts/ci/mypy_ratchet.py                           # errors=1017 baseline=1017

# §A 历史清除工具
scripts/ops/purge_secret_history.sh --dry-run               # 列出 7 类待清路径
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"  # CI YAML OK

# 质量基线
ruff check src/backend                                      # 0
ruff format --check src/backend                             # all formatted
```
