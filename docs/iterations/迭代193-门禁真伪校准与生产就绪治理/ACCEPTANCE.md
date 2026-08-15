# 迭代 193：门禁真伪校准与生产就绪治理 - 验收清单

> 状态:执行中(2026-08-13 建立;同日按计划优化补充 Task M 与量化收口报告;2026-08-14 P0 核心完成)。实现与证据按 PLAN.md 的 Task A-M 逐项填写。

## 验收口径

本迭代唯一红线:**不新增功能**。所有变更限于重构、配置、测试、门禁、文档。每条验收必须附可复现命令与实测输出,证据存入 `evidence/`。

## 总表

| Task | 内容 | 状态 | 证据 |
| --- | --- | --- | --- |
| A | 解除 CI 红灯并恢复棘轮信用(P0-2) | ✅ 完成 | 棘轮 exit 0;--update 防刷 exit 2;回归项 manual.py 就地修复至 2708;5 项 god file 登记;2 项前端回归 deferred_to_194;CODEOWNERS 创建 |
| B | 依赖锁单一事实源(P0-1) | ✅ 完成 | 全仓仅 config/ 一份 310 行锁;src/backend 副本已删;Dockerfile 显式 COPY 无回退;pip-audit "No known vulnerabilities"(cryptography 50.0.0/soupsieve 2.8.4 修复 5 漏洞);check_prod_lock_singleton 守卫接入 CI |
| C | 可观测性"接线"收口(P0-3) | ⚠️ 核心完成 | record_api_request/error 已接入 LoggingMiddleware(dispatch+`__call__`);record_error 接入异常处理;record_db_query 接入 SQLAlchemy 事件;实测 api_request_total 随请求递增;alerting.yaml 9 个指标名 100% grep 命中;request_id 32hex;skip_paths 前缀匹配。OTel 生产开启/cleanup_old_records 调度/log_ai_call 装饰器/monitoring 重启恢复为 M 级余项 |
| D | CI 门禁真伪校准 | ⚠️ 部分完成 | Lighthouse 死门禁修复(config 路径+LHCI_EXIT 显式失败+无报告失败);dependabot.yml 四生态创建;锁单一性守卫接入 ci.yml。monorepo-check/job timeout/action 钉 SHA/concurrency 余项待续 |
| E | 供应链与发布链路加固 | 待执行 | - |
| F | 仓库卫生(246.7MB 被跟踪数据) | 待执行 | - |
| G | 安全纵深收口 | 待执行 | - |
| H | 事件循环与数据库性能 | 待执行 | - |
| I | 后端代码质量 | 待执行 | - |
| J | 测试体系加固 | ⚠️ 时间炸弹部分完成 | 4 个时间炸弹全部拆除:test_schedule_runner.py 动态 _FIRE_AT/_CLAIM_AT/_AS_OF_AT;test_report_artifacts.py + test_schedule_manifests.py persist_identity 显式 valid_from;test_datetime_utils.py freezegun 冻结;freezegun 加入 pyproject+dev lock。omit 收缩/实盘失败路径/e2e 隔离余项待续 |
| K | 前端质量收口 | 待执行(排入 194) | - |
| L | 文档与 DX 一致性 | ⚠️ 核心完成 | check_doc_links 扩展全仓根级(exit 0,修复 20 个死链);README.en.md 仓库名/路径修复;CONTRIBUTING.md 克隆命令+CI_CD 链接修复 |
| M | DR 与备份恢复演练(计划优化补充) | 待执行 | - |

## 硬验收项(可复现命令)

| # | 验收项 | 命令/方法 | 目标 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 大文件棘轮转绿 | `python3 scripts/ci/large_file_ratchet.py` | exit 0 | ✅ 实跑 exit 0(2026-08-14) |
| 2 | 锁文件单一事实源 | grep 全仓 `requirements-prod.lock` | 仅 `config/` 一份;Dockerfile 显式 COPY | ✅ find 全仓=1 份;Dockerfile:17 COPY config/...;回退分支数=0 |
| 3 | RED 指标真实化 | 刮取 `/api/v1/metrics` 后发请求再刮取 | `api_request_total` 递增 | ✅ 实测:GET /api/v1/test x2 + POST x1 -> api_request_total 显示 2.0/1.0 |
| 4 | 告警指标名对齐 | 逐条 grep `config/alerting.yaml` 指标名于 `middleware/metrics.py` | 100% 命中 | ✅ 9/9 命中;3 类未实现指标标 DEFERRED TO 194 注释 |
| 5 | 测试任意日期可复现 | 临时改系统日期至 2027-01-01 复跑 `tests/asset_research` | 全绿 | ⚠️ 4 个时间炸弹已拆除(动态日期+freezegun);全绿复跑需 DB 环境 |
| 6 | e2e 隔离 | `scripts/dev/run-e2e.sh` 内断言 `DATABASE_URL` 被覆盖 | 不触碰真实库 | 待执行 |
| 7 | BOLA 回归测试 | 新增测试:用户 B 操作用户 A 的网关 | 403/404 | 待执行 |
| 8 | admin 保留名 | 新增测试:注册 `admin` | 拒绝 | 待执行 |
| 9 | 缓存越权复现 | 新增测试:用户 B 用用户 A 的 task_id 请求回测结果 | 不命中缓存/无结果 | 待执行 |
| 10 | 文档链接根级全绿 | `python3 scripts/ci/check_doc_links.py`(扩展根级后) | 根级 *.md 全绿 | ✅ 实跑 "OK: All local doc links resolve correctly" exit 0(修复 20 死链) |
| 11 | check-all 本地可执行 | `make check-all` | 不因 bt_api_py 声明失败 | 待执行 |
| 12 | i18n CJK 清零 | `make i18n-cjk`(恢复门禁后) | 0 命中 | 待执行 |
| 13 | async 阻塞调用清零 | `python3 scripts/ci/async_blocking_check.py` | 无新增违规(豁免清单除外) | 待执行(脚本+CI 接线为 193 新增规格) |
| 14 | 安全扫描双轨一致 | `bash scripts/ci/security_scan.sh` 与 ci.yml | 结论一致 | 待执行 |
| 15 | CI 全绿 | push 触发 | ci.yml 全部 job 通过(advisory job 除外) | 待执行(需 push 验证) |
| 16 | 镜像冒烟 | docker-publish 流程内 `docker run` + health 探针 | healthy | 待执行 |
| 17 | 棘轮 --update 防刷 | 无 `ALLOW_BASELINE_UPDATE` 时 `--update` | exit ≠ 0 | ✅ 实跑 exit 2(3 个 ratchet 脚本统一接入 shared guard) |
| 18 | 回归项就地修复 | 3 项回归文件行数 | ≤ 原基线值(非吸收) | ⚠️ manual.py 2708=基线✅;2 项前端回归登记 deferred_to_194(理由:M 级抽取不可盲抽,见 PLAN §0.4-1 细化) |
| 19 | L 级递延交付物 | `docs/iterations/迭代194-工程债切片续作/PLAN.md` 存在 | 含 5 项 god file 切片计划 | ✅ 已创建(Task A-H 全部 L 级条目) |
| 20 | DR 恢复演练 | `bash scripts/dev/run-restore-drill.sh` | exit 0 + "restore verified" | 待执行 |
| 21 | 回滚 runbook | `docs/runbooks/rollback-193.md` 存在 | 含 7 个变更域回滚命令 | ⚠️ 回滚策略表已写入 PLAN §6;runbook 文件待建 |

## 量化收口报告(计划优化补充)

验收完成时填写 `evidence/closing-report-2026-08-13.md`,汇总前后对比:

| 指标 | 迭代前(基线) | 迭代后(实测) | 变化 |
| --- | --- | --- | --- |
| P0 闭合数 | 0/3 | 3/3 核心闭合 | A✅ B✅ C 核心✅ |
| P1 闭合数(S+M 级) | 0/~40 | ~10(审计+修复) | D 部分/J 时间炸弹/L 核心 |
| 大文件棘轮状态 | 红(8 项违规) | 绿 | ✅ |
| 死门禁修复数(Lighthouse/monorepo/就绪探测等) | 0 | 1(Lighthouse) | 部分 |
| 死指标接线数(record_* 系列) | 0 | 4(api_request/api_error/db_query/error) | ✅ |
| 死配置清理数(alerting.yaml/cleanup_old_records/log_ai_call) | 0 | 1(alerting.yaml 对齐) | 部分 |
| 后端覆盖率(omit 收缩后) | ~70%(含 5 模块 omit) | 未变 | 待执行 |
| skip 数(含 ticket 引用率) | 20 skip/0 ticket | 未变 | 待执行 |
| CI job timeout 覆盖率 | ~30% | 未变 | 待执行 |
| actions 钉 SHA 率 | 0% | 未变 | 待执行 |
| bundle entry gzip | 基线值 | 未变 | 待执行 |
| 仓库跟踪数据体积 | 246.7MB | 未变 | 待执行 |
| 文档死链接(根级) | 20(16 README.en+2 CONTRIBUTING+2 vendored) | 0 | ✅ |

## 复核修正记录(验收前必读)

- 初稿 "容器健康检查 404 阻断生产栈" 不成立:根路径 `/health` 存在(`main_routes.py:99`),已从 P0 移除。
- 初稿 "Dockerfile 锁分支永不命中" 不成立:实际问题是双锁漂移(见 P0-1/Task B)。
- 计划优化(2026-08-13):新增 Task M(DR)、§6 回滚策略、Task A 回归项就地修复、Task H async 检查脚本规格化、量化收口报告模板、L 级递延显式交付物。详见 PLAN.md §0.4。
- 执行修正(2026-08-14):Task A 回归项中,2 项前端回归(+180/+57)经评估需 M 级组件抽取(排入 194),本迭代不盲抽,登记 `_deferred_regressions` 字段挂 194 ticket——与"就地修复"原则的显式例外(理由见基线 JSON 注释)。
- 其余 P0/P1 结论均已独立实跑复核,证据见 `evidence/audit-2026-08-13-full-findings.md`。
