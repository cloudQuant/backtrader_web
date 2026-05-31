# 迭代 179 关闭报告 — 质量债棘轮续拧与安全收尾

**关闭日期**: 2026-05-31
**起点**: 迭代 178 收口（commit `6c386388`）
**终点**: §A/§B/§C/§D 全部代码侧收口；§E 清单刷新；G1（P0 历史凭据）复核仍待 owner
**性质**: 质量债棘轮下行 / 异步正确性深化 / 安全收尾（非新产品特性）

---

## 0. 一句话结论

清掉了 178 收口后浮出的两个真实小尾巴——① 把 git 仍跟踪的 slowapi 运行时产物 `.slowapi.env`
untrack + gitignore（§A），② 把 `gateway/manual.py` 的纯解析 helper 抽到新 `net_probe.py`
并让 macOS TUN 探测优先走 psutil 而非 shell `ifconfig`（§B，P1#4 slice 1/4）——并继续把
mypy 仓库级棘轮实测从 1017 下拧到 **958**（§C，-59），把 PR-template i18n 门禁改成 diff-aware
后从 advisory flip 成 blocking（§D）。本迭代 §A–§D 全部代码侧闭环，零行为变化、全测试绿。

---

## 1. 验收结果总表

| 项 | PLAN 目标 | 终态 | 状态 |
| --- | --- | --- | :---: |
| §A `.slowapi.env` 收口 | untrack + gitignore | `git rm --cached` + gitignore 规则 + Limiter 仅在文件存在时加载（去掉启动 UserWarning） | ✅ |
| §B net_probe 抽取 + psutil 化 | slice 1 抽 helper + slice 4 psutil | `net_probe.py`（6 helper + 15 单测）；`_count_utun_interfaces` psutil-first；`manual.py` 2061→2044 | ✅ |
| §C mypy 棘轮续拧 | 1017 实测下降 | `app/api/workspace_api` strict 清零，1017→**958**（-59）并 `--update` | ✅ |
| §D PR-template i18n flip | flip 或留理由 | 脚本改 diff-aware（CHANGED_FILES），flip 成 blocking | ✅ |
| §E 大文件清单刷新 | standing | 清单更新；`manual.py` 下行入档 | ✅ |
| G1 P0 历史凭据 | backlog 证据链 | 复核仍 OPEN，178 工具仍就绪，待 owner 轮换/重写 | ✅（记录） |
| 质量基线 | ruff 0 / format 全过 / 测试绿 | 全部通过；mypy 棘轮稳定 958 | ✅ |

---

## 2. §A — `.slowapi.env` 运行时产物收口（commit `d26ee14b`）

slowapi 的 `Limiter` 用 `config_filename=.slowapi.env` 作为可选运行时覆盖文件，该空文件被
git 跟踪（`git ls-files | grep .env` 命中）。它今天是空文件、无泄露，但属"运行时状态混进
版本库"，应在写入敏感内容前收口。

- `git rm --cached src/backend/.slowapi.env`（保留磁盘文件）。
- `.gitignore` 加 `src/backend/.slowapi.env` + `**/.slowapi.env`。
- `rate_limit.py`：`config_filename` 改为仅在 `_SLOWAPI_CONFIG_FILE.is_file()` 时传入，否则
  传 `None`——避免新 clone 启动时 starlette 反复 `Config file '... .slowapi.env' not found`
  UserWarning（实测确认该警告存在）。

**验证**：`git check-ignore` 命中；`tests/test_rate_limiting.py` + `test_rate_limit_headers.py`
共 23 passed，限流功能不回归。

---

## 3. §B — net_probe 抽取 + psutil-first utun 探测（commit `9fa8d647`）

`gateway/manual.py`（2061 行，全仓第 2 大）同时是阻塞 I/O 与超大文件重灾区。178 §B 已在
async caller 包了 `to_thread`（slice 2）；本迭代做 P1#4 的另外两个可闭环切片：

**slice 1（抽纯 helper，零行为变化）**：把 6 个 side-effect-free 解析函数移到新模块
`app/services/gateway/net_probe.py`：

| 函数 | 用途 |
| --- | --- |
| `extract_port_from_zmq_error` | 从 ZMQ "Address in use" 错误串解析端口 |
| `extract_err_msg_from_error_entry` | 从 health 快照错误条目取消息字符串 |
| `is_address_in_use_error` | 判定是否 "address in use" 错误 |
| `find_recent_bind_error` | 从快照取最近的 bind 错误 |
| `parse_tcp_front_endpoint` | 解析 `tcp://host:port` CTP 前置地址 |
| `extract_ips_from_fronts` | 从前置地址提取去重 IP（跳过 loopback/hostname） |

`manual.py` 以原私有名（`_extract_port_from_zmq_error` 等）**re-export**，所有调用点与
patch target 不变（实测 facade identity 为 True）。

**slice 4（psutil-first，去外部命令硬依赖）**：新增 `_count_utun_interfaces()`，优先用
`psutil.net_if_addrs()` 数 `utun*` 接口，psutil 不可用才回落 `ifconfig`；`_is_macos_tun_proxy_active`
改用它。`scutil --proxy` 与 `route` 探测（macOS 专有）无干净 psutil 等价物，保留为有注释的
shell 兜底。`_kill_process_on_port` 早已是 psutil-first（前序 pass）。

**新增测试** `tests/test_gateway_net_probe.py`（15 个）：覆盖 6 个 helper + psutil-first/
ifconfig-fallback 两条 utun 计数路径。

**验证**：`manual.py` 2061→2044；`ruff` 0；mypy gateway 包 0；`test_extracted_modules`（105）+
gateway/live-trading 五个套件（206）+ net_probe（15）全绿；mypy 棘轮 delta +0。

---

## 4. §C — mypy 仓库级棘轮续拧 1017→958（commit `18cf2b81`）

延续 178 §E 纪律，证明棘轮持续双向工作。选 `app/api/workspace_api.py`（59 错误，其中 58 个
纯 `no-untyped-def` + 1 个 `attr-defined`）做 strict 清零，纯类型工作、零逻辑改动：

- 给 29 个路由 handler 补 `current_user: TokenPayload` 与精确返回类型（响应 schema /
  `dict[str, Any]` / `dict[str, str]` / `list[...]`，按各 handler 实际返回值）。
- 修 `attr-defined`：`from app.api.deps import get_current_user` 改为
  `from app.api._dependencies import get_current_user`（`deps.py` 是 `sys.modules`-swap
  shim，mypy 不可解析；与 178 §E 对 live_trading 的处置同法），零运行时变化。

终态：`mypy app/api/workspace_api` = 0；仓库级 baseline `1017 → 958`（-59）并 `--update`
锁定。**棘轮牙齿验证**：临时注入一个 untyped def → `errors=959 baseline=958` → exit 1（报
`::error::type errors increased by 1`），随即还原。`test_workspace_service` 等 19 测试全绿，
router 仍注册 29 条路由。

---

## 5. §D — PR-template i18n 门禁 diff-aware + flip blocking（commit `2bf82c5a`）

`ci.yml` 的 PR-template i18n 步骤原 `continue-on-error: true`（advisory），因为它对**每个**
PR 都强制要求填 i18n 变更清单——即使该 PR 没碰任何翻译，flip 成 blocking 会无谓地拦截所有
PR。

**改法**：`check_pr_template.py` 增加 `CHANGED_FILES` 入参（diff-aware）：

- PR 没改 `src/frontend/src/i18n/locales/*` → 直接 pass（exit 0），不要求清单。
- PR 改了 locale 文件但清单缺失/有占位符 → fail（exit 1）。
- `CHANGED_FILES` 未设 → 退回旧的无条件检查（向后兼容）。
- `PR_BODY` 为空（非 PR 上下文）→ exit 2，不 fail。

CI 步骤改为：用 `git diff --name-only base..head` 算出 `CHANGED_FILES` 传给脚本，去掉
`continue-on-error`，flip 成 **blocking**。CI YAML 已校验通过；四个场景实测行为正确。

### 其余 3 个 advisory 门禁决策（不在本迭代 flip，记录理由 + 解锁条件）

| 门禁 | 行号 | 为何暂不 flip | 解锁条件 |
| --- | --- | --- | --- |
| i18n 全量 strict（CJK+English） | `ci.yml:950` | ~14k 为 scanner over-reach（合法英文占位符/缩写/配置串），非用户可见裸串 | 需给 scanner 加启发式区分；177/178 已记 |
| e2e i18n（`\|\| true`） | `ci.yml:978` | 需先清前端中文泄露 baseline，本迭代未触前端 | 清完中文泄露后建 baseline 再 flip |
| `monorepo-check` | `ci.yml:1098/1116` | 团队策略项（接受更长 PR 时间 + flake 预算） | 团队决议 |

---

## 6. §E — 超大文件清单刷新（standing）

`manual.py` 经 §B 由 2061→2044。`sync_service.py`（2490，178 时 2483，反增 7 行）仍最大，
本迭代不拆。完整清单见 PLAN §7。

---

## 7. 未完成 / 顺延项

- **G1（P0 历史凭据轮换 + 历史重写）**：复核仍 OPEN（`git log --all` 仍可取出
  `f575cce6`/`b6d3097a` 的明文凭据）。178 工具完好，是 owner 运维动作，代码侧无可做。
- **P1#4 slice 3（网关家族按 ib/ctp/ccxt/mt5 拆文件）**：触及实盘下单全路径，需独立分支 +
  纸面验证。
- **`sync_service.py` 2490 拆分、前端 `: any`×18 / 后端 `type: ignore`×11**：滚动推进。
- **前端**：本迭代未触前端，沿用 178 终态（vue-tsc 0 / vitest 全绿）。

---

## 8. 提交清单

| commit | 内容 |
| --- | --- |
| `d26ee14b` | chore(security): untrack .slowapi.env runtime artifact + gitignore (§A) |
| `9fa8d647` | refactor(gateway): extract net_probe helpers + psutil-first utun detect (§B) |
| `18cf2b81` | ci(types): strict-clean app/api/workspace_api, ratchet 1017→958 (§C) |
| `2bf82c5a` | ci(i18n): make PR-template i18n gate diff-aware + flip to blocking (§D) |

---

## 9. 复现命令

```bash
# §A .slowapi.env 已 untrack + gitignore
git ls-files | grep slowapi            # 空
git check-ignore src/backend/.slowapi.env  # 命中
python -m pytest src/backend/tests/test_rate_limiting.py -q  # 23 passed

# §B net_probe 抽取 + psutil utun
grep -n "asyncio.to_thread\|net_probe" src/backend/app/services/gateway/manual.py | head
wc -l src/backend/app/services/gateway/manual.py            # 2044
python -m pytest src/backend/tests/test_gateway_net_probe.py -q  # 15 passed

# §C mypy 棘轮
python -m mypy app/api/workspace_api.py                     # Success (cwd=src/backend)
python scripts/ci/mypy_ratchet.py                           # errors=958 baseline=958

# §D PR-template i18n diff-aware
CHANGED_FILES="src/backend/app/main.py" PR_BODY="x" python3 scripts/ci/check_pr_template.py  # OK, exit 0
CHANGED_FILES="src/frontend/src/i18n/locales/zh-CN.ts" PR_BODY="x" python3 scripts/ci/check_pr_template.py  # FAIL, exit 1
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"  # CI YAML OK

# 质量基线
ruff check src/backend                                      # 0
ruff format --check src/backend                             # all formatted
```
