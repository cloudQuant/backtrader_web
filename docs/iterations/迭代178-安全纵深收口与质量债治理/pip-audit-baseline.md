# pip-audit 依赖漏洞基线（迭代 178 §C）

> **日期**: 2026-05-31
> **范围**: `config/requirements-prod.lock`（67 包）+ `config/requirements-dev.lock`（121 包）
> **结论**: 处置后 **0 个已知漏洞**，CI `pip-audit` 已 flip 为 **blocking**。

---

## 1. 基线获取方式

177 §C 把后端依赖审计从弃用的 `safety check` 换成 `pip-audit`（PyPA 出品、OSV 数据源、
无需账号），但留作 advisory 未拿到可信基线。178 §C 收口。

本地直接跑 `pip-audit`（默认 PyPI advisory 服务）对 188 个包逐一查询时，因本机到 `pypi.org`
的 HTTPS 链路异常缓慢（单请求 ~13s），整体超时。改用两条等价且更快的路径交叉验证：

1. **OSV 批量查询**（`api.osv.dev/v1/querybatch`）：把锁文件里已 pin 的 `name==version`
   一次性批量查 OSV，避免 pip-audit 的逐包解析开销。
2. **`pip-audit --requirement <lock> --no-deps`**：`--no-deps` 跳过依赖解析（锁文件已全 pin），
   只做漏洞查询。对 prod lock 实测可在超时内完成。

两条路径结论一致。

## 2. 处置前发现（1 个）

| 包 | 锁定版本 | 漏洞 | 别名 | 说明 |
| --- | --- | --- | --- | --- |
| starlette | 1.0.0 | PYSEC-2026-161 | CVE-2026-48710 / GHSA-86qp-5c8j-p5mr / X41-2026-002 | "BadHost"：缺少 Host 头校验，`request.url.path` 可被污染，绕过基于路径的安全检查（如鉴权）。2026-05-22 披露。 |

- **影响面**：starlette 为 FastAPI 传递依赖（FastAPI 0.136.1 要求 `starlette>=0.46.0`）。
- **修复版本**：`starlette==1.0.1`（fixed 范围 `[0, 1.0.1)`）。
- **依赖元数据对比**：1.0.0 与 1.0.1 的 `requires_python` 与 `requires_dist` **完全一致**，
  单行 bump 不引入任何传递依赖变化。

## 3. 处置

- 把 4 个锁文件的 `starlette==1.0.0` → `1.0.1`：
  - `config/requirements-prod.lock`、`config/requirements-dev.lock`
  - `src/backend/requirements-prod.lock`、`src/backend/requirements-dev.lock`
- 本地验证：`pip install starlette==1.0.1` 干净安装；`app.main` 正常 import；
  auth/middleware/main 路由测试 66 passed（starlette 1.0.1 改了 Host 头处理，确认不破坏请求/路由）。

## 4. 处置后基线

```text
pip-audit --requirement config/requirements-prod.lock --no-deps --desc
  → No known vulnerabilities found  (exit 0)

OSV 批量查询（prod 67 + dev 121 包）
  → No known vulnerabilities in pinned locks (OSV)
```

## 5. CI flip

`.github/workflows/ci.yml` 的 `backend-security` job：

- 旧：`pip-audit --desc ... || true`（advisory，吞错误）。
- 新：`pip-audit --requirement ../../config/requirements-prod.lock --no-deps --desc`
  （**blocking**，去掉 `|| true`）。审计 pin 的生产锁——结果确定、与部署镜像一致。
- 任何**新增**漏洞（或 starlette 回退）会让 `backend-security` 直接 fail。

## 6. 维护

- 依赖变更后按 `CONTRIBUTING.md` 重新生成锁文件，CI `pip-audit` 会对新依赖集重新审计。
- 若出现暂时无法升级的漏洞，用 `pip-audit --ignore-vuln <ID>` 显式 ignore 并在本文件追加
  一行（含理由 + 复查日期），保持基线"0 未解释漏洞"。

## 7. 2026-07-18 基线刷新（迭代 183）

发布后 CI run `29637645538` 运行到 blocking `pip-audit` 时，实时漏洞库对 5 个锁定包返回
18 条记录（同一漏洞可能同时以 GHSA / PYSEC ID 出现）。全部都有兼容的修复版本，因此不做
ignore，直接升级：

| 包 | 旧版本 | 修复版本 |
| --- | --- | --- |
| cryptography | 48.0.0 | 48.0.1 |
| pydantic-settings | 2.14.1 | 2.14.2 |
| PyJWT | 2.12.1 | 2.13.0 |
| python-multipart | 0.0.29 | 0.0.31 |
| starlette | 1.0.1 | 1.3.1 |

处置同步覆盖 `config/` 和 `src/backend/` 下的生产/开发锁，并在 `pyproject.toml` 提高安全
版本下限，避免非锁安装回退到受影响版本。修复后验证：

```text
pip-audit --requirement config/requirements-prod.lock --no-deps
  → No known vulnerabilities found  (exit 0)

pip check
  → No broken requirements found.

认证、安全、同步传输相关测试
  → 101 passed
```
