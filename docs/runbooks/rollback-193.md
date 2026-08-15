# Rollback Runbook — 迭代 193 变更域

> 来源:PLAN.md §6 回滚与应急策略。所有安全/CI 变更必须 dev 验证 → staging 灰度 → prod 上线后 1h 监控窗口;P0 回滚须 ≤15 分钟可执行。

## 1. 棘轮基线刷新(Task A)

- **触发条件**:棘轮误报阻塞合入
- **回滚**:`git checkout HEAD~1 -- scripts/ci/large_file_baseline.json`(回退基线 commit)
- **验证**:`python3 scripts/ci/large_file_ratchet.py` 重新转绿
- **注意**:`--update` 已加 `ALLOW_BASELINE_UPDATE` 守卫,不会意外刷新

## 2. 锁文件合并(Task B)

- **触发条件**:镜像构建失败或缺 extras(akshare/aiomysql 等)
- **回滚**:恢复 `src/backend/requirements-prod.lock` 副本 + Dockerfile 原 `if [ -f ]` 分支
- **验证**:`docker build -f src/backend/Dockerfile .` + health 冒烟
- **注意**:`check_prod_lock_singleton.py` 会拦截第二份锁,回滚需同步移除该门禁步骤

## 3. 可观测性接线(Task C)

- **触发条件**:middleware 异常影响吞吐;metrics 刮取拖慢请求
- **回滚**:注释 `logging.py`/`exception_handling.py` 中 `record_*` 调用(均为 try-safe 单行);`db/database.py` 中 `_register_db_metrics` 调用移除
- **验证**:`/api/v1/metrics` 刮取恢复正常;请求日志无异常

## 4. alerting.yaml 指标名对齐(Task C)

- **触发条件**:监控服务按新指标名解析失败
- **回滚**:`git checkout HEAD~1 -- config/alerting.yaml`
- **验证**:grep 检查监控服务日志无 metric-not-found

## 5. Lighthouse 死门禁修复(Task D)

- **触发条件**:LHCI 新显式失败逻辑阻塞合入(如 a11y 阈值首次真实生效)
- **回滚**:恢复 `--config=lighthouserc.js`(原死门禁形态)或降 a11y 阈值为 0.8
- **验证**:检查 `./lighthouse-reports` 产出与 a11y 分数

## 6. check_doc_links 范围扩展(Task L)

- **触发条件**:新扫描误报第三方/生成文档链接
- **回滚**:在 `EXCLUDED_PARTS` 增加对应目录名,重新跑 `python3 scripts/ci/check_doc_links.py`

## 7. 安全变更域(Task G,待执行批次)

| 变更 | 回滚触发 | 回滚手段 | 灰度验证 |
| --- | --- | --- | --- |
| 安全 fail-closed(D-5) | 合法请求 401/403 激增 | `DEBUG=true` 临时恢复;config 回退 commit | staging 24h;上线后 1h 4xx 监控 |
| BOLA 网关归属校验 | admin 跨用户被误拦 | is_admin 豁免路径保留;降级原逻辑 | 回归测试先行;admin 操作日志抽查 |
| 限流键/代理头 | nginx 后误杀流量 | `TRUST_PROXY` 回退不信任;Redis 回退 in-memory | staging 压测 |

## 8. 时间炸弹拆除(Task J)

- **触发条件**:动态日期引入断言失败(极少)
- **回滚**:`git checkout HEAD~1 -- src/backend/tests/asset_research/test_schedule_runner.py src/backend/tests/asset_research/test_report_artifacts.py src/backend/tests/asset_research/test_schedule_manifests.py src/backend/tests/test_datetime_utils.py`
- **验证**:`pytest tests/asset_research/test_schedule_runner.py -x -q`
