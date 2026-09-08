# 迭代 196 部署侧文件数据集接线与验证

日期：2026-09-05。候选工作树：`codex/iteration-196-ai-research-trust`；默认配置仍关闭。不使用现有业务数据、用户 `.env`、Provider 凭据或生产存储。

## 1. 已实现范围

FR-DATA-002 现有一个可显式配置的 POSIX filesystem resolver，不再只有进程内 fixture 接口：

- 部署操作员先将受控正规文件登记为随机、不透明的 receipt ID；对象版本、SHA-256、字节数、inode/权限/修改身份由服务端实际读取获得。
- receipt 以严格 JSON、schema/self-hash、独占创建及原子发布持久化；重建 resolver 实例后仍可读取。self-hash 是完整性检查，不是针对有权写 receipt 目录者的数字签名。
- 每次 `resolve_receipt` / `resolve_current` 重新校验 manifest、打开文件、流式计算摘要并检查读取前后身份及路径重开结果；返回本次检查时间，原始 receipt 的摄取时间不改写。
- API 的 `get_dataset_object_resolver` 已接入静态配置 factory。浏览器仍只能提交 receipt ID，不能指定 resolver 类型、路径、URI、摘要、版本或字节数。
- 文件读取和哈希通过 `asyncio.to_thread` 执行，不阻塞 API/worker 的事件循环。取消等待不等于线程已经强制终止；被取消的调用不能发布迟到的 API 结果，后台只读工作仍受文件大小上界约束。

## 2. 配置与接口

| 配置 | 默认值/约束 |
| --- | --- |
| `AI_RESEARCH_PROTOCOL_V2_DATASET_OBJECT_RESOLVER_TYPE` | 空；仅允许 exact `filesystem`，不是动态 Python import 路径 |
| `AI_RESEARCH_PROTOCOL_V2_DATASET_FILESYSTEM_ROOT` | 空；部署预建、绝对、非 symlink 的数据根目录 |
| `AI_RESEARCH_PROTOCOL_V2_DATASET_RECEIPT_STORE` | 空；独立 receipt 根目录，与数据根不相等也不嵌套 |
| `AI_RESEARCH_PROTOCOL_V2_DATASET_MAX_BYTES` | 0；启用时必须显式设置正整数，上限 10 GiB，不代表建议使用该最大值 |

两个根目录和逐级对象目录须由服务 UID 拥有且不能 group/world writable；文件不得多硬链接，不接受 FIFO、设备等非正规文件。依赖 POSIX `openat/dir_fd/O_NOFOLLOW` 等能力；不具备这些能力的平台不能宣称支持该 resolver。Windows 和真实跨主机部署仍需独立选择后端并验收。

服务器接口：

```python
resolve_configured_dataset_object_resolver(settings)  # resolver 或 None
import_filesystem_dataset(settings, user_id=..., source_path=..., partition_kind=...)
```

显式 CLI 为 `python -m app.research_deployments.dataset_import --user-id ... --source-path ... --partition-kind DISCOVERY`。本机实际运行 Python 时仍必须使用用户的 Anaconda base。CLI 用 `Settings(_env_file=None)`，仅从部署进程环境读配置；成功只输出 `{"receipt_id":"..."}`，失败只输出稳定 `DATASET_IMPORT_FAILED` 并退出 2。这里只记录操作契约，本轮没有对用户真实文件执行摄取。

允许分区为 `DISCOVERY`、`ITERATION_VALIDATION`、`FORWARD_OBSERVATION`；该后端不提供 `SEALED_HOLDOUT` 能力。空 resolver 配置保留既有失败关闭语义；错误类型或路径在 API 映射为安全 409，不回显路径。

## 3. 独立复核与回归

实现者已完成 14 项、6 worker 聚焦回归与 Ruff check/format；主代理的完整目录回归另在 [六 worker 记录](REGRESSION_6_WORKERS_20260905.md) 记录，不把代理聚焦跑次拼成全量证据。测试文件为：

- `src/backend/tests/test_ai_research_filesystem_dataset_resolver.py`：真实小字节文件、重建实例、同内容 inode 替换、跨 owner、路径穿越、symlink、越界、权限、非正规文件、sealed 拒绝、receipt 篡改、崩溃恢复与事件循环活性。
- `src/backend/tests/test_ai_research_dataset_resolver_factory.py`：静态 allowlist、默认关闭、配置拒绝、显式摄取及 CLI 不读取 dotenv/只输出 opaque ID。
- `src/backend/tests/test_ai_research_v2_api.py` 的 resolver 配置负例：真实 API 依赖接线与路径脱敏。

独立只读安全复核发现并已修复：

1. 先阻塞 open 再判断 regular 会被 FIFO 卡住：source/receipt 的末级打开均加 `O_NONBLOCK`，再做正规文件检查。
2. 发布 hard link 后、删除临时 link 前崩溃会留下 `nlink=2`：仅当可信 receipt 目录中的指定 final/tmp 是同 dev/inode、服务 UID、权限合规的正规文件时，才移除本次临时 link、fsync 并复验 final 为单链接；不会清理任意用户路径。
3. 复验时间一直等于初始摄取时间：每次成功 resolve 返回新检查时间，持久 receipt 原始时间与 hash 不变。
4. `async def` 内直接读大文件会阻塞 heartbeat：完整同步解析移出事件循环，用受控 gate 验证另一个任务可运行及取消后不暴露路径。

独立复核已确认这些修复没有放松路径/owner/字节身份边界；它是代码审查，不是第二份独立运行证据。

## 4. 不能外推的结论

- 这证明本地受控文件字节和持久 receipt 的实现，不是市场数据真实性、point-in-time/source manifest 正确性或数据授权证明。
- POSIX UID/mode/FD 校验不能替代 ACL、容器挂载权限、独立服务账户、对象存储 IAM 或管理员隔离；部署必须自行证明这些边界。
- 仍需将同一 resolver 绑定到真实 GENERATE executor / materializer，完成当前版本 authenticated UI/API 与 worker 链路验证；新 factory/API 接线存在不等于整个任务链已运行。
- 真实独立 Evaluator、Sandbox、Provider、完整配额对账和 T2/T3 门禁仍未通过；默认 flag 不应因此打开。
