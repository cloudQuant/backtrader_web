# 迭代 195：跨平台产品发布与可观测性 Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 backtrader_web 交付为可在 macOS、Ubuntu 和 Windows 11 上安全安装、启动、停止、重启、升级和排障的产品，并把关键操作纳入可检索、可关联、可验收的日志与发布治理体系。

**Architecture:** 产品发行版采用 Docker Compose 优先的本地产品档（Linux 容器同时运行于 macOS、Ubuntu、Windows 11 的 Docker Desktop/Engine），以避免用户分别安装 Python、Node、MySQL、Redis 后产生不可复现的组合。根目录的 start_app、stop_app、restart_app 脚本只做稳定入口；平台特定控制器只管理本 Compose 项目，绝不按端口或模糊进程名杀进程。现有原生启动链保留为开发者模式，不能再被描述为生产产品启动方式。

**Tech Stack:** Docker Compose v2、Linux amd64/arm64 OCI 镜像、Python 3.11、FastAPI、Alembic、MySQL 8、Redis 7、Vue 3/Vite 静态构建、Nginx、Loguru、OpenTelemetry、pytest、Vitest、GitHub Actions。

---

## 0. 本计划的边界、决策与完成定义

本文件是实施计划，不代表以下能力已经实现。除本计划外，不应通过新增产品入口顺带开放实盘交易、绕过审批、改变行情/模型结论，或把开发环境默认值带入产品环境。

### 0.1 推荐的发行策略和决策门

| 方案 | 说明 | 结论 |
| --- | --- | --- |
| Docker-first 产品档 | 用户先安装 Docker Desktop/Engine，脚本拉取经签名的多架构镜像，自动配置隔离数据库和运行目录 | **推荐且为 v1.0 发布门槛**；三平台行为最一致 |
| 原生开发档 | 脚本在项目目录创建虚拟环境、安装锁定依赖，使用 SQLite 或显式外部数据库 | 保留给开发/排障；不能作为 v1.0 的“普通用户一键安装”承诺 |
| 原生桌面安装包 | DMG/MSI/AppImage 内嵌运行时与升级器 | 作为 v1.1+ 选项；只有在产品负责人明确要求“不依赖 Docker”后立项 |

**Gate-0 决策：** 产品负责人必须在实施开始前书面确认 Docker-first 为 v1.0 的对外支持边界，或改为投入原生桌面安装包。若选择后者，后续任务的测试矩阵、签名、升级器和工期必须重新估算；不得把两种发行方式混合后宣称均已验收。

### 0.2 v1.0 交付定义

1. 新用户在受支持系统中执行根目录入口后，获得可登录的本地产品 URL，且不需单独启动前端、后端、数据库或缓存。
2. start、stop、restart、status、logs、doctor 都有一致的退出码和可读输出；stop 只能停止本产品拥有的容器，restart 不删除任何诊断日志。
3. 首次配置生成高熵密钥，禁止默认管理员口令、隐式建表和隐式实盘开关。
4. 数据库迁移、健康检查、版本信息、日志、备份恢复和升级都有独立、可自动验证的契约。
5. GitHub Release 中存在可复现的镜像摘要、SBOM、签名/证明、校验和、支持矩阵和已知限制；发布候选在三种目标系统上均有证据。
6. 研究、回测和模拟盘可作为 v1.0 主路径；实盘交易默认关闭，只有完成迭代 193 的授权、隔离和人工审批门槛后才能作为单独发布的功能档开放。

### 0.3 不在本迭代中做的事

- 不静默安装 Docker、系统 Python、Node、浏览器驱动、数据库服务或交易终端；doctor 必须给出平台对应的前置条件和链接。
- 不在 start 命令中执行不可逆的数据清空、数据库降级或强制升级；升级/恢复必须显式确认并先产出备份。
- 不以“端口可监听”代替应用、数据库、迁移和前端均就绪。
- 不把请求体、口令、Cookie、API Key、券商凭据、原始模型提示词或完整交易数据写入普通日志。

## 1. 当前审计结论与本计划的对应关系

| 优先级 | 已核实的现状 | 风险 | 本计划处置 |
| --- | --- | --- | --- |
| P0 | 期望保留的根目录 start_app、stop_app、restart_app 兼容入口当前不存在；迭代 174 的记录却称其已保留 | 用户和文档中的命令立即失效 | Task 1 |
| P0 | scripts/windows/start_app.bat 将 scripts/windows 当作项目根目录，导致 src/backend 和 src/frontend 路径错误；scripts/ops/app.bat 的转发路径也不正确 | Windows 11 无法可靠启动 | Task 1、Task 4 |
| P0 | Unix 启动器只检查少量 import，默认启动 Vite 开发服务器；不会基于锁文件建环境、运行迁移或完成前端健康验证 | 开发脚本被误作产品启动器，安装不可复现 | Task 2、Task 4、Task 5 |
| P0 | Unix/Windows stop 会按端口或宽泛进程名强杀进程；Windows restart 会删除后端、前端和异步日志 | 误杀其他服务且破坏故障证据 | Task 4 |
| P0 | Docker 基础 Compose 文件本身没有服务；local 档依赖宿主 MySQL；prod 档暴露 3306 并启用自动建表/默认管理员 | 不能作为安全的一键产品档 | Task 2、Task 3 |
| P0 | 当前 CI 工作流均运行于 ubuntu-latest；没有 macOS/Windows 生命周期验收 | 无法声明三平台支持 | Task 8 |
| P0 | release.sh 固定为 v0.1.0，发布说明中仍有 docker compose up 一类无效命令，未产生 SBOM/摘要/签名证据 | 发布物不可追溯 | Task 9 |
| P0 | 现有日志基础设施已经有 JSON、脱敏、request_id、task_id、trace_id、审计文件和回归测试；但 AuditLogger 的内建事件只覆盖登录、权限、策略和回测，启动器日志会截断/删除 | 关键产品操作无法统一审计与关联 | Task 6、Task 7 |
| P0 | src/backend/alembic 已有唯一 head，但 docs/operations/DATABASE_INIT.md 仍把 Alembic 描述为未来能力 | 首装、升级和故障恢复会使用冲突流程 | Task 3、Task 11 |
| P0 | 迭代 193 仍列出供应链、授权隔离、e2e 隔离、DR 恢复等未关闭验收项 | 平台即使能启动也不应宣称生产就绪 | Task 9、Task 10、Task 12 |
| P1 | 迭代 194 的后端/前端大文件、N+1、阻塞 I/O、分页与测试债仍在切片治理 | 可维护性和容量风险持续累积 | Task 13，作为持续门禁而非阻塞根安装器 |
| P1 | 多资产真实数据、模型质量、数据许可、PIT 证据仍有未闭合门禁 | 不可将研究输出宣传为已验证投资建议 | Task 12、Task 13 |

当前已做的定向验证（仅用于建立本计划基线）：

- Unix 生命周期脚本的 Bash 语法检查通过。
- Alembic 报告唯一 head：20260811_asset_research_task_leases。
- src/backend/tests/test_app_lifecycle_scripts.py：1 passed。
- 日志定向套件：83 passed、3 skipped；基础日志能力不能被重复建设或回退。

## 2. 目标运行模型

### 2.1 目录和所有权契约

    repository/
      start_app.sh | stop_app.sh | restart_app.sh
      start_app.bat | stop_app.bat | restart_app.bat
      scripts/product/
        app.sh
        app.bat
        init_product_env.sh
        init_product_env.ps1
      docker/compose/product.yml
      runtime/                         # Git 忽略、用户数据，不由 restart 清理
        product.env                    # 0600 / 仅当前 Windows 用户可读
        compose/                       # Compose project state
        mysql/
        redis/
        backend/logs/
        backups/
        launcher-events.jsonl

产品 Compose project name 固定为 backtrader-web-product，但每个命令必须从运行目录读取配置，不得操作同机任意其他 Compose project。数据库、Redis 和后端只在内部网络暴露；默认仅将前端绑定到 127.0.0.1:8080。对外网暴露、反向代理、TLS、独立 MySQL 或实盘网关必须使用另一个服务器部署档并明确配置。

### 2.2 生命周期状态机

| 命令 | 允许的前态 | 成功后状态 | 失败行为 |
| --- | --- | --- | --- |
| start | NOT_INSTALLED、STOPPED、DEGRADED | READY | 保留日志和容器状态，输出失败服务及修复建议 |
| stop | READY、DEGRADED、STOPPED | STOPPED | 幂等；绝不按端口杀非本项目进程 |
| restart | READY、DEGRADED、STOPPED | READY | 先 stop，再 start；不清理日志、数据库、卷或备份 |
| status | 任意 | 不改变状态 | 输出 backend、frontend、db、redis、迁移版本、镜像摘要 |
| doctor | 任意 | 不改变状态 | 验证 Docker/Compose、磁盘、端口、目录权限、版本兼容和密钥文件权限 |
| upgrade | READY、STOPPED | READY 或明确失败 | 拉取已签名摘要，备份，迁移，健康验证；失败进入可回滚状态 |

## 3. 工作流、责任划分与并行规则

| Lane | 主责 | 可并行任务 | 互斥文件/前置条件 |
| --- | --- | --- | --- |
| A：产品运行时 | Runtime Engineer | Task 1、2、4 | Task 1 先于 Task 4；统一拥有 root 脚本和 scripts/product |
| B：后端与数据库 | Backend/DB Engineer | Task 3、5、6、7、10 | Task 3 的迁移契约先于 Task 2 最终 compose；不要改 A 的脚本 |
| C：前端与镜像 | Frontend/Release Engineer | Task 5、9、11 | Task 5 的镜像标签接口需与 Task 9 一致 |
| D：质量与安全 | QA/SRE/Security Engineer | Task 8、9、10、12 | 维护证据目录和发布闸门；不得以局部绿替代 RC 证据 |
| E：持续质量 | 各领域 owner | Task 13 | 不与 v1.0 launcher 改动混合提交 |

建议以 4 名工程师并行：A/B/C/D 分别负责一条 Lane。预计研发量为 30–42 人日，另加 5–8 人日的三平台 RC、恢复演练和发布审批；这是工作量区间，不是发布日期承诺。

## 4. 任务清单

### Task 0：锁定产品档架构和对外支持边界

**Owner:** 技术负责人 + 产品负责人
**Files:**

- Create: docs/adr/014-product-runtime-and-distribution.md
- Modify: docs/adr/README.md
- Modify: docs/iterations/README.md
- Modify: docs/plans/2026-08-17-iteration-195-cross-platform-product-release.md

**Step 1: 写出待决策的验收表**

在 ADR 中列出 Docker-first、原生开发档、原生桌面安装包三种方案的依赖、支持系统、升级、数据目录、签名和回滚差异。把 Docker-first 标记为推荐方案，并要求负责人确认。

**Step 2: 验证文档在当前导航中可达**

Run:

    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_doc_links.py

Expected: exit 0，ADR、迭代索引和本计划链接均可解析。

**Step 3: 固化不可违反的契约**

ADR 必须明确以下规则：产品默认 paper/research-only；容器只用 Linux amd64/arm64；Windows 是 Linux containers on Docker Desktop，不是 Windows container；普通用户不必安装 Node/Python；不支持 Docker 时 doctor 失败而不是悄悄转入不受控环境。

**Step 4: Commit**

    git add docs/adr/014-product-runtime-and-distribution.md docs/adr/README.md docs/iterations/README.md docs/plans/2026-08-17-iteration-195-cross-platform-product-release.md
    git commit -m "docs(release): decide product runtime distribution"

### Task 1：恢复稳定根入口并修正跨平台路径契约

**Owner:** Runtime Engineer
**Files:**

- Create: start_app.sh
- Create: stop_app.sh
- Create: restart_app.sh
- Create: start_app.bat
- Create: stop_app.bat
- Create: restart_app.bat
- Create: src/backend/tests/test_product_launcher_contract.py
- Modify: scripts/ops/app.sh
- Modify: scripts/ops/app.bat
- Modify: scripts/ops/start_app.sh
- Modify: scripts/ops/stop_app.sh
- Modify: scripts/ops/restart_app.sh
- Modify: scripts/windows/start_app.bat
- Modify: scripts/windows/stop_app.bat
- Modify: scripts/windows/restart_app.bat
- Create: .gitattributes
- Modify: .gitignore

**Step 1: 写失败的入口契约测试**

测试必须从任意当前工作目录调用根入口，并断言：

- 六个根入口真实存在且可执行/可调用；
- Unix 入口以仓库根为锚点，不依赖调用目录；
- Windows 入口把 %~dp0 解释为仓库根，而非 scripts/windows；
- scripts/ops 旧入口只做兼容转发，不能留下第二套生命周期实现；
- .sh 为 LF，.bat 为 CRLF；
- 传递的 start、stop、restart、status、logs、doctor 参数不丢失。

示例断言：

    def test_windows_launcher_resolves_repository_root() -> None:
        launcher = ROOT / "start_app.bat"
        text = launcher.read_text(encoding="utf-8")
        assert "scripts/product/app.bat" in text.replace("\\", "/")
        assert "scripts/windows/src/backend" not in text.replace("\\", "/")

**Step 2: 运行测试，确认旧实现失败**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_launcher_contract.py -q

Expected: 当前仓库因根入口缺失和 Windows 相对根路径错误而失败。

**Step 3: 以极薄兼容层实现根入口**

Unix root shim 的目标形态如下；stop/restart 只替换第一个参数：

    #!/usr/bin/env bash
    set -euo pipefail
    ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
    exec "$ROOT_DIR/scripts/product/app.sh" start "$@"

Windows root shim 的目标形态如下：

    @echo off
    call "%~dp0scripts/product/app.bat" start %*
    exit /b %ERRORLEVEL%

旧 scripts/ops 与 scripts/windows 文件必须改为同一控制器的兼容 shim 或明确的 developer-only shim。不要复制 start/stop 逻辑。

**Step 4: 验证脚本格式和静态契约**

Run:

    bash -n start_app.sh stop_app.sh restart_app.sh scripts/product/app.sh
    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_launcher_contract.py -q

Expected: 全绿；Windows 的实际调用在 Task 8 的 windows-latest job 中验证。

**Step 5: Commit**

    git add start_app.sh stop_app.sh restart_app.sh start_app.bat stop_app.bat restart_app.bat scripts/ops scripts/windows scripts/product .gitattributes .gitignore src/backend/tests/test_product_launcher_contract.py
    git commit -m "fix(release): restore cross-platform product entrypoints"

### Task 2：创建可发行的 product Compose 档和多架构镜像契约

**Owner:** Runtime Engineer + Release Engineer
**Files:**

- Create: docker/compose/product.yml
- Create: docker/product.env.example
- Create: docker/release-images.env.example
- Create: scripts/ci/verify_product_compose.py
- Create: tests/product/test_product_compose.py
- Modify: docker/docker-compose.yml
- Modify: src/backend/Dockerfile
- Modify: src/frontend/Dockerfile
- Modify: docker/nginx.prod.conf
- Modify: .gitignore

**Step 1: 写失败的 Compose 契约测试**

测试读取 docker/compose/product.yml 并断言：

- backend、frontend、mysql、redis、migrate 五个服务存在；
- MySQL、Redis、backend 没有宿主 ports；
- frontend 默认只绑定 127.0.0.1；
- backend 依赖 migrate 成功完成；
- DB_AUTO_CREATE_SCHEMA 和 DB_AUTO_CREATE_DEFAULT_ADMIN 均为 false；
- 所有持久目录位于 runtime/ 或命名 volume；
- 镜像使用发布摘要变量，产品档不得包含 build:；
- product profile 不引用 host.docker.internal 或宿主 MySQL。

**Step 2: 运行测试，确认当前 Compose 不能满足产品档**

Run:

    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/product/test_product_compose.py -q
    docker compose -f docker/docker-compose.yml -f docker/compose/product.yml config

Expected: 测试在新文件实现前失败；当前 local/prod 档不被误判为 product 档。

**Step 3: 实现 product.yml**

实现独立产品覆盖文件而不是修改 dev/local/prod 的既有语义。关键形态如下：

    services:
      migrate:
        image: <BACKEND_IMAGE_DIGEST>
        command: ["alembic", "upgrade", "head"]
        restart: "no"
      backend:
        image: <BACKEND_IMAGE_DIGEST>
        depends_on:
          migrate:
            condition: service_completed_successfully
      frontend:
        image: <FRONTEND_IMAGE_DIGEST>
        ports:
          - "127.0.0.1:<PRODUCT_HTTP_PORT>:80"

在 release-images.env 中只允许不可变 digest，不允许 latest。Dockerfile 必须能构建 linux/amd64 与 linux/arm64，且镜像内使用非 root 用户。确认前端镜像只服务已构建静态文件，不运行 Vite。

**Step 4: 验证配置与启动冒烟**

Run:

    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/verify_product_compose.py
    docker compose --project-name backtrader-web-product-ci --env-file docker/product.env.example -f docker/docker-compose.yml -f docker/compose/product.yml config

Expected: 配置验证通过；示例文件不会含真实凭据，也不会展开为对外暴露数据库。

**Step 5: Commit**

    git add docker docker/nginx.prod.conf src/backend/Dockerfile src/frontend/Dockerfile scripts/ci/verify_product_compose.py tests/product/test_product_compose.py .gitignore
    git commit -m "feat(release): add isolated product compose profile"

### Task 3：实现安全首次配置、显式迁移与数据库生命周期

**Owner:** Backend/DB Engineer
**Files:**

- Create: scripts/product/init_product_env.sh
- Create: scripts/product/init_product_env.ps1
- Create: src/backend/tests/test_product_bootstrap.py
- Create: src/backend/tests/test_product_migration_contract.py
- Create: src/backend/alembic/versions/20260817_product_bootstrap_state.py
- Modify: src/backend/app/config.py
- Modify: src/backend/app/startup/database.py
- Modify: src/backend/app/db/database.py
- Modify: src/backend/app/main_routes.py
- Modify: docker/compose/product.yml
- Modify: docker/product.env.example

**Step 1: 写失败的安全配置和迁移测试**

覆盖以下场景：

- product.env 缺失时初始化生成两个不同的 32 字节以上随机密钥；
- 生成的文件不包含 admin/admin123、replace-with、dev-secret 等默认值；
- Unix 权限为 0600；Windows 初始化脚本只授权当前用户；
- 运行中的 product 档拒绝 DB_AUTO_CREATE_SCHEMA=true 和 DB_AUTO_CREATE_DEFAULT_ADMIN=true；
- 迁移服务在 database 未就绪时失败，ready 后只能执行一次；
- 两个并发 migrate 命令只允许一个获取数据库迁移锁；
- 首次管理员只能由一次性本地 onboarding token 创建，token 不写普通日志。

**Step 2: 运行失败测试**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_bootstrap.py tests/test_product_migration_contract.py -q

Expected: 新行为未实现前失败；现有开发环境自举不能被视为产品档通过。

**Step 3: 最小实现**

- 初始化脚本只创建 runtime/product.env、runtime/ 目录和一个一次性 onboarding token；不得打印 secret。
- product Compose 的 migrate 服务在 backend 启动前执行 Alembic upgrade head，并记录当前/目标 revision、镜像 digest 和耗时。
- 使用数据库 advisory lock 或等价的 MySQL lock 保护迁移；任何失败均非零退出且 backend 不启动。
- 保留 SQLite、MySQL、PostgreSQL 的应用配置能力，但 v1.0 product profile 固定为容器内 MySQL；原生开发档可继续使用 SQLite。
- 增加 liveness、readiness、version 三类端点。readiness 必须同时验证迁移 revision、数据库连接与关键依赖；liveness 不访问数据库。

**Step 4: 运行回归与迁移检查**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m alembic heads
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_bootstrap.py tests/test_product_migration_contract.py tests/test_app_lifecycle_scripts.py -q

Expected: 一个 Alembic head；所有 product bootstrap 测试通过；不存在隐式 create_all 成功即继续的产品路径。

**Step 5: Commit**

    git add scripts/product/init_product_env.sh scripts/product/init_product_env.ps1 src/backend/app src/backend/alembic/versions docker/compose/product.yml docker/product.env.example src/backend/tests/test_product_bootstrap.py src/backend/tests/test_product_migration_contract.py
    git commit -m "feat(release): add secure product bootstrap and migration gate"

### Task 4：实现无破坏性的跨平台生命周期控制器

**Owner:** Runtime Engineer
**Files:**

- Create: scripts/product/app.sh
- Create: scripts/product/app.bat
- Create: scripts/product/tests/fake_docker.py
- Create: src/backend/tests/test_product_lifecycle_controller.py
- Modify: start_app.sh
- Modify: stop_app.sh
- Modify: restart_app.sh
- Modify: start_app.bat
- Modify: stop_app.bat
- Modify: restart_app.bat
- Modify: scripts/ops/app.sh
- Modify: scripts/ops/app.bat
- Modify: scripts/windows/start_app.bat
- Modify: scripts/windows/stop_app.bat
- Modify: scripts/windows/restart_app.bat

**Step 1: 写失败的控制器测试**

使用 fake Docker 二进制记录 argv，覆盖：

- start 调用 compose pull、migrate、up --wait 与 readiness 检查；
- stop 只使用项目名与产品 compose 文件，不调用 kill、taskkill、lsof、netstat 强杀或 docker system prune；
- restart 顺序为 stop 后 start，且 runtime/backend/logs 文件的内容不变；
- status 输出服务健康、镜像摘要、Alembic revision 与本地 URL；
- logs 只跟随本 project 的服务；
- doctor 返回结构化失败码：缺 Docker、Compose 过旧、端口冲突、权限不足、磁盘不足、配置无效；
- 同时启动两个命令时第二个因 runtime/launch.lock 退出，不能产生竞争。

**Step 2: 运行测试，确认旧脚本失败**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_lifecycle_controller.py tests/test_product_launcher_contract.py -q

Expected: 旧脚本因端口杀进程、日志删除、未等待 readiness 或路径偏差而失败。

**Step 3: 实现命令契约**

Unix 和 Windows 的 app 控制器必须接受相同的子命令：

    start [--port N] [--offline]
    stop
    restart [--port N] [--offline]
    status [--json]
    logs [backend|frontend|db|all]
    doctor [--json]
    upgrade <release-digest>

start 的成功输出必须包括浏览器 URL、release version、镜像 digest、日志目录、备份目录和 paper-only 状态。失败时输出 service 名称、最近日志路径、request/launch ID 与不含敏感信息的恢复建议。

**Step 4: 验证控制器不破坏外部进程**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_lifecycle_controller.py -q
    bash -n scripts/product/app.sh start_app.sh stop_app.sh restart_app.sh

Expected: 测试会使用一个占用同端口但不属于本 Compose project 的假进程，并断言 stop/restart 后该进程仍存活。

**Step 5: Commit**

    git add scripts/product start_app.sh stop_app.sh restart_app.sh start_app.bat stop_app.bat restart_app.bat scripts/ops scripts/windows src/backend/tests/test_product_lifecycle_controller.py src/backend/tests/test_product_launcher_contract.py
    git commit -m "feat(release): add safe cross-platform lifecycle controller"

### Task 5：收敛为真正的产品 Web 运行时和可判定健康检查

**Owner:** Frontend/Backend Engineer
**Files:**

- Create: src/backend/tests/test_product_readiness.py
- Create: src/frontend/src/__tests__/buildInfo.test.ts
- Modify: src/backend/app/main.py
- Modify: src/backend/app/main_routes.py
- Modify: src/backend/app/config.py
- Modify: src/backend/Dockerfile
- Modify: src/frontend/Dockerfile
- Modify: docker/nginx.prod.conf
- Modify: src/frontend/vite.config.ts
- Modify: src/frontend/src/main.ts
- Create: src/frontend/src/services/buildInfo.ts
- Modify: docker/compose/product.yml

**Step 1: 写失败测试**

后端测试应区分：

- GET /health 或 /livez 只证明进程存活；
- GET /readyz 在迁移版本不一致、数据库不可用、关键 worker 未准备好时非 200；
- GET /version 返回应用版本、Git SHA、构建时间、镜像 digest 与 schema revision，但不泄露环境变量。

前端测试应断言 build info 可显示、API 默认使用同源相对地址、生产构建不依赖 Vite dev server。

**Step 2: 运行失败测试**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_readiness.py -q
    cd ../frontend
    npm run test -- --run src/__tests__/buildInfo.test.ts

Expected: 现状中仅健康端点与版本常量不足以满足完整就绪契约。

**Step 3: 实现**

- 前端镜像使用多阶段 build，最终只含 Nginx 和 dist；移除任何产品档中的 npm run dev。
- Nginx 代理 /api、/ws，并提供 SPA fallback、合理缓存、CSP 基线和静态资源缓存策略。
- 后端启动前后的状态明确记录；Gunicorn/Uvicorn 优雅停止必须等待任务取消或到期并写入最终事件。
- 产品档通过 frontend 与 backend 两个独立 readiness 条件后才输出 READY。

**Step 4: 运行验证**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_readiness.py -q
    cd ../frontend
    npm run typecheck
    npm run build

Expected: 后端端点、前端生产构建和 build-info 测试通过。

**Step 5: Commit**

    git add src/backend/app src/backend/tests/test_product_readiness.py src/backend/Dockerfile src/frontend docker/nginx.prod.conf docker/compose/product.yml
    git commit -m "feat(release): serve verified production web runtime"

### Task 6：以统一事件契约补齐关键操作日志和审计

**Owner:** Backend/Observability Engineer
**Files:**

- Create: src/backend/app/observability/operation_events.py
- Create: src/backend/app/schemas/operation_event.py
- Create: src/backend/tests/test_operation_events.py
- Create: src/backend/tests/test_operation_event_redaction.py
- Modify: src/backend/app/utils/logger.py
- Modify: src/backend/app/middleware/logging.py
- Modify: src/backend/app/services/audit_service.py
- Modify: src/backend/app/api/auth.py
- Modify: src/backend/app/services/backtest/service.py
- Modify: src/backend/app/services/asset_research/task_runner.py
- Modify: src/backend/app/services/gateway/runtime.py
- Modify: src/backend/app/services/direct_order_service.py
- Modify: src/backend/app/services/ai_strategy_research_service.py
- Modify: src/backend/app/api/audit.py
- Modify: docs/operations/LOGGING.md

**Step 1: 写失败的事件模式测试**

定义 schema_version=1。每个关键事件至少具有：

    event_name
    outcome
    occurred_at
    release_version
    request_id
    task_id
    trace_id
    actor_type
    actor_id
    resource_type
    resource_id
    duration_ms
    error_code

其中 request_id、task_id、trace_id、actor/resource 字段可为空，但必须明确为 null，而不是混用缺失、N/A、空字符串。测试必须验证事件模式、JSON 可解析、敏感字段脱敏、异常中没有密钥、关联 ID 从 HTTP 到后台任务保留。

**Step 2: 运行失败测试**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_operation_events.py tests/test_operation_event_redaction.py -q

Expected: 新事件 schema 与覆盖范围实现前失败。

**Step 3: 最小实现和覆盖清单**

用一个类型化 emit_operation_event 帮助器接入既有 Loguru、AuditRecord 和 OpenTelemetry，而不是并行创建第三个日志系统。必须至少记录以下事件：

| 域 | 必须记录的事件 |
| --- | --- |
| 生命周期 | install/config_created, start_requested/ready/failed, stop_requested/completed, restart_requested, upgrade_started/rolled_back, migration_started/completed/failed |
| 身份与授权 | login、logout、refresh、password_changed、role_changed、permission_denied、onboarding_completed |
| 研究与策略 | strategy CRUD、strategy version promote、backtest queued/started/completed/cancelled/failed、report exported |
| 数据与 AI | provider fetch started/completed/timeout/fallback、data refresh、research task lifecycle、model call 的 provider/model/token/cost 摘要和 budget decision |
| 交易高风险边界 | gateway credential configured 的元数据、connect/disconnect、paper order、live order attempt/approval/rejection；永不记录 credentials、完整订单备注或原始账户号 |
| 运维 | backup、restore drill、health degradation、retention cleanup、audit export |

高风险事件需同时进入现有持久 AuditRecord 路径和带 tags=[audit] 的结构化日志；普通诊断事件只需日志/trace。客户端上传审计事件必须保留服务端 actor 校验，不能让浏览器伪造高风险服务器事件。

**Step 4: 运行日志回归**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_enhanced_logger.py tests/test_structured_logging.py tests/test_logging_middleware.py tests/test_audit_and_logging.py tests/test_operation_events.py tests/test_operation_event_redaction.py -q

Expected: 既有日志能力不回退；新增事件全部通过模式、脱敏和关联测试。

**Step 5: Commit**

    git add src/backend/app/observability src/backend/app/schemas src/backend/app/utils/logger.py src/backend/app/middleware/logging.py src/backend/app/services src/backend/app/api src/backend/tests docs/operations/LOGGING.md
    git commit -m "feat(observability): audit product operations with typed events"

### Task 7：将日志、指标、trace、告警和保留策略接成可操作闭环

**Owner:** Observability/SRE Engineer
**Files:**

- Create: config/dashboards/product-runtime-dashboard.json
- Create: config/alerting/product-runtime-alerts.yaml
- Create: src/backend/tests/test_product_observability_contract.py
- Create: scripts/ci/check_alert_metric_alignment.py
- Modify: src/backend/app/telemetry.py
- Modify: src/backend/app/middleware/metrics.py
- Modify: src/backend/app/main.py
- Modify: src/backend/app/config.py
- Modify: docker/compose/product.yml
- Modify: docs/operations/LOGGING.md
- Modify: docs/operations/OPERATIONS.md

**Step 1: 写失败的可观测性契约测试**

测试检查启动失败、迁移失败、数据库不可用、慢请求、后台任务超时、备份失败分别产生可查询事件、指标和关联 trace。测试还要断言 LOG_RETENTION_APP_DAYS、LOG_RETENTION_ERROR_DAYS、LOG_RETENTION_AUDIT_DAYS 的配置一致，日志清理不会删除当天活跃文件或审计保留期内文件。

**Step 2: 运行失败测试**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_observability_contract.py tests/test_telemetry_e2e.py -q

Expected: 当前缺少产品启动器指标、产品专用告警及完整恢复证据时失败。

**Step 3: 实现可观测性闭环**

- 保留现有 JSON stdout、文件轮转、压缩和 trace correlation；产品容器以 JSON 输出，不输出 ANSI 色码。
- 新增 product_start_total、product_ready、product_migration_duration_seconds、backup_age_seconds、audit_event_write_failures_total、task_timeout_total 等明确指标；每个告警规则都必须有真实 producer。
- OTEL 由配置显式启用；未配置 exporter 时 trace 必须无副作用地降级。
- launcher-events.jsonl 采用追加写入和大小/日期轮转，restart 禁止清空它。
- 定义 RED/USE dashboard、告警阈值、责任人、抑制规则与 runbook 链接；不可只提交未被调用的 metrics 函数或 YAML 名称。

**Step 4: 验证**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_observability_contract.py tests/test_ai_observability.py tests/test_telemetry_e2e.py -q
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_alert_metric_alignment.py

Expected: 事件、指标、告警名和 runbook 100% 对齐。

**Step 5: Commit**

    git add config/dashboards config/alerting src/backend/app src/backend/tests docker/compose/product.yml docs/operations
    git commit -m "feat(observability): add product runtime monitoring contract"

### Task 8：建立三平台验证矩阵与生命周期端到端测试

**Owner:** QA/SRE Engineer
**Files:**

- Create: .github/workflows/product-lifecycle.yml
- Create: tests/product/test_product_e2e.py
- Create: tests/product/test_product_windows.bat
- Create: scripts/ci/run_product_smoke.sh
- Create: scripts/ci/run_product_smoke.ps1
- Modify: .github/CODEOWNERS
- Modify: README.md

**Step 1: 写失败的 E2E 规格**

规格要逐条覆盖 macOS、Ubuntu、Windows 11：

1. fresh workspace 与空 runtime；
2. doctor 显示缺失前置条件或通过；
3. start 完成配置、迁移、数据库与前端就绪；
4. GET /livez、/readyz、/version 以及浏览器 login 页面通过；
5. 创建/登录测试用户并运行一个离线回测或受控 fixture；
6. logs 可找到相同 request_id/task_id；
7. restart 后用户数据和历史日志仍存在；
8. stop 后仅本项目容器停止；
9. upgrade 的备份/迁移/回滚分支在隔离项目中通过。

**Step 2: 先实现无 Docker 的脚本静态测试**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_launcher_contract.py tests/test_product_lifecycle_controller.py -q

Expected: 每个 PR 都能先在 hosted runner 验证入口和参数，不依赖 Docker Desktop。

**Step 3: 实现分层 CI**

- PR 主矩阵：ubuntu-latest、macos-latest、windows-latest，运行 shell/batch 路径、格式、fake-Docker 和 contract tests。
- Linux 容器 E2E：每个 PR 运行 product compose 的真实 start/restart/stop。
- macOS（Intel 与 Apple Silicon）和 Windows 11 的 Docker Desktop E2E：使用受控 self-hosted release runners，或在 RC 期间由指定人工运行同一脚本并上传不可变证据；不得把 Linux 绿冒充三平台绿。
- workflow 设 timeout、concurrency、最小权限、缓存键绑定 lockfile；收集 compose ps、inspect、健康输出和去敏日志作为失败 artifact。

**Step 4: 运行验证**

Run:

    bash scripts/ci/run_product_smoke.sh --mode linux
    pwsh -File scripts/ci/run_product_smoke.ps1 -Mode windows-contract

Expected: Linux 本地/CI 冒烟全绿；Windows 真实 Docker 证据在 release runner 中产生。

**Step 5: Commit**

    git add .github/workflows/product-lifecycle.yml .github/CODEOWNERS tests/product scripts/ci/run_product_smoke.sh scripts/ci/run_product_smoke.ps1 README.md
    git commit -m "ci(release): verify product lifecycle across supported platforms"

### Task 9：完成发布供应链、版本单一事实源与安全发布门

**Owner:** Release/Security Engineer
**Files:**

- Create: scripts/release/build_release_manifest.py
- Create: scripts/release/verify_release_manifest.py
- Create: scripts/ci/check_version_sync.py
- Create: docs/release/RELEASE_CHECKLIST.md
- Create: docs/release/SUPPORTED_PLATFORMS.md
- Create: tests/product/fixtures/invalid-manifest.json
- Modify: scripts/ops/release.sh
- Modify: .github/workflows/docker-publish.yml
- Modify: .github/workflows/ci.yml
- Modify: src/backend/pyproject.toml
- Modify: src/frontend/package.json
- Modify: src/backend/app/main.py
- Modify: src/backend/app/main_routes.py
- Modify: CHANGELOG.md
- Modify: LICENSE
- Create: NOTICE

**Step 1: 写失败的版本与发布清单测试**

断言 backend package、frontend package、API version、release manifest、image tag 和 CHANGELOG 指向同一版本。验证 manifest 中有：

- Git commit、签名 tag、backend/frontend image digest；
- linux/amd64、linux/arm64 架构清单；
- SBOM 路径、许可证清单、校验和、构建时间；
- 目标平台、最低 Docker/Compose 版本、已知限制；
- 完整 RC 证据链接。

**Step 2: 运行失败测试**

Run:

    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_version_sync.py
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/release/verify_release_manifest.py --fixture tests/product/fixtures/invalid-manifest.json

Expected: 当前硬编码 v0.1.0 的 release.sh 和版本分散状态应被检测为失败。

**Step 3: 实现安全发布链**

- 版本从一个经过评审的文件或生成脚本导出，其他位置由 CI 校验，禁止手工漂移。
- docker-publish 构建多架构 manifest，生成 CycloneDX 或 SPDX SBOM，执行许可证审阅、pip/npm 漏洞门禁、镜像扫描、digest 校验和 keyless Cosign 签名/证明。
- release.sh 改为编排验证脚本，不得硬编码仓库名、版本、latest、过期 Quick Start 或无服务的 docker compose up。
- 发布资产包含 product compose bundle、release-images.env、SHA256SUMS、SBOM、release manifest、升级/回滚说明；用户从 release digest 安装而不是本地 build。
- 将迭代 193 的未关闭安全项作为严格门：网关资源所有权隔离、admin 保留名、默认密钥/管理员防护、Docker sandbox、覆盖率与安全扫描双轨一致。

**Step 4: 验证**

Run:

    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_version_sync.py
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/release/build_release_manifest.py --dry-run
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/release/verify_release_manifest.py --dry-run

Expected: 所有版本字段一致；manifest 能验证；不能以 latest 或可变 tag 作为 v1.0 安装源。

**Step 5: Commit**

    git add scripts/release scripts/ci/check_version_sync.py scripts/ops/release.sh .github/workflows src/backend/pyproject.toml src/frontend/package.json src/backend/app/main.py src/backend/app/main_routes.py CHANGELOG.md LICENSE NOTICE docs/release
    git commit -m "feat(release): produce signed reproducible product releases"

### Task 10：补齐备份、恢复演练、升级回滚和数据保护

**Owner:** Backend/DB Engineer + SRE
**Files:**

- Create: scripts/product/backup_product.sh
- Create: scripts/product/backup_product.ps1
- Create: scripts/product/restore_product.sh
- Create: scripts/product/restore_product.ps1
- Create: scripts/dev/run-product-restore-drill.sh
- Create: src/backend/tests/test_product_backup_restore.py
- Modify: scripts/ops/backup_mysql.py
- Modify: docker/compose/product.yml
- Modify: docs/runbooks/backup-restore.md
- Modify: docs/runbooks/rollback-193.md
- Modify: docs/operations/OPERATIONS.md

**Step 1: 写失败的恢复测试**

使用隔离 Compose project 创建最小数据、备份、销毁测试数据库、恢复并验证：

- schema revision 相同；
- 关键表行数和用户/策略/回测 fixture 完整；
- 备份不含 runtime/product.env；
- 恢复前会检查目标 project、磁盘空间、checksum 和兼容版本；
- upgrade 前备份失败则升级中止；
- 停止/恢复过程产生 operation event，但不泄露路径外的敏感信息。

**Step 2: 运行失败测试**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest tests/test_product_backup_restore.py -q

Expected: 新的产品恢复契约实现前失败。

**Step 3: 实现**

- MySQL 备份以 application least-privilege 凭据和明确的 snapshot/checksum 完成；现有 backup_mysql.py 增加 --verify，恢复到临时 project 后校验。
- 产品卷、策略、工作区、配置模板分级备份；密钥文件必须由用户单独安全保管，默认不导出。
- upgrade 生成带 release digest、schema revision、备份 ID 的 transaction record；失败时可恢复上一个已验证 image digest 和备份点。
- 把迭代 193 Task M 的 staging/本地恢复演练证据纳入 release artifact。

**Step 4: 验证**

Run:

    bash scripts/dev/run-product-restore-drill.sh

Expected: exit 0，输出 restore verified: row counts match，并生成去敏证据 JSON。

**Step 5: Commit**

    git add scripts/product scripts/ops/backup_mysql.py scripts/dev/run-product-restore-drill.sh src/backend/tests/test_product_backup_restore.py docker/compose/product.yml docs/runbooks docs/operations/OPERATIONS.md
    git commit -m "feat(ops): verify product backup restore and rollback"

### Task 11：统一安装、运维、数据库和日志文档

**Owner:** Technical Writer + 各 Lane owner review
**Files:**

- Create: docs/docs/zh/getting-started/product-install.md
- Create: docs/docs/en/getting-started/product-install.md
- Create: docs/docs/zh/deployment/product-local.md
- Create: docs/docs/en/deployment/product-local.md
- Create: docs/operations/PRODUCT_LIFECYCLE.md
- Create: scripts/ci/check_product_docs_commands.py
- Modify: README.md
- Modify: README.en.md
- Modify: scripts/README.md
- Modify: docs/operations/DATABASE_INIT.md
- Modify: docs/operations/DEPLOYMENT.md
- Modify: docs/operations/OPERATIONS.md
- Modify: docs/operations/LOGGING.md
- Modify: docs/docs/zh/deployment/index.md
- Modify: docs/docs/en/deployment/index.md

**Step 1: 写失败的文档命令测试**

新增一个文档命令提取器或在 check_doc_links.py 中增加规则，验证所有用户可见的 start/stop/restart 命令指向真实根入口或 scripts/product 控制器；不允许继续出现不存在的 scripts/start_app.sh、无服务的 docker compose up，或“Alembic 是未来能力”的陈述。

**Step 2: 运行失败验证**

Run:

    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_doc_links.py
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_product_docs_commands.py

Expected: 修改前检出入口与数据库文档漂移。

**Step 3: 写面向用户的最短路径**

中文和英文文档均应给出：

    macOS / Ubuntu:
      ./start_app.sh
      ./stop_app.sh
      ./restart_app.sh

    Windows 11:
      start_app.bat
      stop_app.bat
      restart_app.bat

同时包含 doctor、logs、离线镜像导入、端口/代理、升级、备份、恢复、卸载、开发档与产品档差异、默认 paper-only 限制、隐私/日志保留和故障收集说明。每段生产命令必须提供预期输出和失败处理，不得要求用户编辑源代码。

**Step 4: 验证**

Run:

    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_doc_links.py
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_product_docs_commands.py
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m mkdocs build -f docs/mkdocs.yml --strict

Expected: 双语文档、命令和站点构建全部通过。

**Step 5: Commit**

    git add README.md README.en.md scripts/README.md docs/docs docs/operations scripts/ci/check_product_docs_commands.py
    git commit -m "docs(release): document supported product lifecycle"

### Task 12：执行发布候选验收并形成不可替代的证据包

**Owner:** QA Lead，需 Product/Security/SRE 三方签字
**Files:**

- Create: docs/releases/v<version>/RC_ACCEPTANCE.md
- Create: docs/releases/v<version>/evidence/<platform>-lifecycle.json
- Create: docs/releases/v<version>/evidence/<platform>-screenshots/
- Create: docs/releases/v<version>/evidence/restore-drill.json
- Create: docs/releases/v<version>/evidence/security-and-sbom.json
- Modify: docs/release/RELEASE_CHECKLIST.md

v<version> 是 Task 9 生成并经 check_version_sync.py 校验的唯一发布版本目录名，不是字面路径；每次 RC 必须只创建一个与 release manifest 相同版本的目录。

**Step 1: 写出 RC 的失败条件**

下列任一项失败则 RC 不可发布：

- 任一目标平台无法从空 runtime 完成 start 到 ready；
- stop/restart 影响非本项目进程或删除旧日志；
- 迁移失败后 backend 仍声称 ready；
- 任一高风险事件缺 request/task/trace 关联或泄露敏感信息；
- 镜像未签名、SBOM 不完整、版本不同步、CVE/许可证门禁失败；
- 未关闭的实盘授权隔离、备份恢复、产品安装文档、三平台证据；
- 将 fixture 成功当作真实数据/模型/实盘成功。

**Step 2: 执行自动门禁**

Run:

    cd src/backend
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -m "not e2e" -q --tb=short
    cd ../frontend
    npm run typecheck
    npm run lint
    npm run test -- --run
    npm run build
    cd ../..
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_doc_links.py
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_version_sync.py

Expected: 全部退出码为 0；任何历史基线失败必须单列、获批准并不计为发布绿色。

**Step 3: 执行每平台人工/物理机验收**

在 macOS Intel、macOS Apple Silicon、Ubuntu LTS、Windows 11 各执行同一 release digest 的 product smoke。记录 OS 版本、Docker/Compose 版本、镜像 digest、命令、退出码、浏览器截图、日志摘要和执行人。若 v1.0 不支持其中一个架构，必须从 README 的支持矩阵移除，不能以“理论可用”代替证据。

**Step 4: 审核已知风险**

将迭代 191/192 的真实数据、模型治理、许可、PIT、生产备份等证据与本次产品运行时证据分开签署。产品可交付不等于投资信号/模型有效性/实盘适格。

**Step 5: 发布或明确阻断**

只有三方签字后，Task 9 的发布工作流才可创建 tag/release。任何缺失项必须写入 RC_ACCEPTANCE.md 的阻断表并创建带 owner/日期/验收条件的 issue。

### Task 13：把现有工程债与金融产品风险纳入后续棘轮，而非在 v1.0 后遗忘

**Owner:** Tech Lead + 各领域 owner
**Files:**

- Create: docs/iterations/迭代195-跨平台产品发布与可观测性/POST_RELEASE_BACKLOG.md
- Modify: docs/iterations/迭代193-门禁真伪校准与生产就绪治理/ACCEPTANCE.md
- Modify: docs/iterations/迭代194-工程债切片续作/PLAN.md
- Modify: docs/iterations/迭代192-可信多资产研究收口与模型治理/ACCEPTANCE.md

**Step 1: 建立不可关闭的遗留项清单**

按 P0/P1/P2、owner、依赖、目标版本、验收命令登记下表项目；禁止只写“后续优化”：

| 域 | 必须追踪的后续项 |
| --- | --- |
| 安全 | 网关对象所有权、admin 保留名、缓存越权、Docker 策略沙箱、依赖与 actions SHA 固定、秘密轮换 |
| 质量 | e2e 独立数据库、覆盖率 omit 收缩、skip ticket 化、全局单例清理、真实时钟清除 |
| 性能 | async 阻塞 I/O、数据库 N+1、连接池、缓存键隔离、容量/恢复指标 |
| 可维护性 | ai_strategy_research、asset_research、StrategyPage 等大文件切片，relationship lazy raise，分页统一，兼容 shim 清理 |
| 前端 | i18n CJK 清零、错误边界、404、bundle budget、无障碍和真实浏览器性能 |
| 数据与模型 | 数据许可/主数据、真实资产 T1/T2、PIT、provider timeout/fallback、预测结果校准和禁止误导性营销 |
| 运营 | staging DR、成本/LLM 降级、告警演练、支持工单与隐私删除流程 |

**Step 2: 确认 release gate 与 post-release 的分界**

至少将安全授权、备份恢复、供应链、三平台生命周期和真实产品路径列为 release gate。大文件拆分可以在后续版本完成，但不得降低现有 ratchet 或增加新超限文件。

**Step 3: 验证追踪完整性**

Run:

    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/check_doc_links.py
    /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python scripts/ci/large_file_ratchet.py

Expected: 所有遗留项有唯一 owner 与可验证退出条件；代码棘轮不倒退。

**Step 4: Commit**

    git add docs/iterations/迭代195-跨平台产品发布与可观测性 docs/iterations/迭代193-门禁真伪校准与生产就绪治理 docs/iterations/迭代194-工程债切片续作 docs/iterations/迭代192-可信多资产研究收口与模型治理
    git commit -m "docs(roadmap): track product release follow-up risks"

## 5. 依赖顺序和合并策略

| 顺序 | 必须完成的任务 | 原因 |
| --- | --- | --- |
| 1 | Task 0、Task 1 | 先确定产品边界和稳定入口，避免所有后续文档/CI 指向漂移路径 |
| 2 | Task 2、Task 3 | Compose 产品档必须建立在安全配置和显式迁移之上 |
| 3 | Task 4、Task 5 | 生命周期控制器依赖稳定 compose，且只在真实 readiness 后宣称成功 |
| 4 | Task 6、Task 7 | 先定义事件再接指标与告警，避免死配置/死指标 |
| 5 | Task 8、Task 9、Task 10、Task 11 | 可并行，但 Task 12 的 RC 前必须全部合并 |
| 6 | Task 12 | 唯一可发布证明；不得被局部测试替代 |
| 持续 | Task 13 | 每次发布候选复核，不影响已定义的 v1.0 门槛 |

每个任务使用独立分支和单一 owner。跨 Lane 共享文件（docker/compose/product.yml、README、release manifest）须在合并前由对应 owner pair-review；禁止为了合并方便使用 git add . 或覆盖其他 Lane 的未提交改动。

## 6. 发布门禁总表

| Gate | 证据 | 通过条件 |
| --- | --- | --- |
| G0 发行决策 | ADR 014 批准记录 | Docker-first/非 Docker 路线及支持边界明确 |
| G1 安装与生命周期 | 三平台 lifecycle evidence | 从空 runtime start/stop/restart/status/logs/doctor 均通过 |
| G2 数据库安全 | migration、backup、restore evidence | 显式迁移、可验证备份恢复、无默认管理员/隐式建表 |
| G3 可观测性 | JSON schema、trace、dashboard、alert test | 所有关键操作可关联、脱敏、可告警 |
| G4 供应链与安全 | SBOM、签名、CVE/许可证/授权测试 | 不可变 digest、版本同步、无未批准高危项 |
| G5 产品主路径 | 浏览器 E2E、受控回测、日志关联 | 登录、研究/回测、报告、重启持久化可用，paper-only 清晰 |
| G6 运营恢复 | 真实 restore drill、runbook | 备份、升级回滚、故障升级可执行 |
| G7 业务可信度 | 迭代 191/192 单独证据 | 不把 fixture 或运行时绿色误当真实数据/模型/实盘验收 |

## 7. 风险与回滚规则

| 风险 | 防护 | 回滚 |
| --- | --- | --- |
| 新 Compose 迁移失败 | 迁移锁、迁移前备份、backend 等待 migrate 成功 | 恢复上一 image digest 与已验证备份；保留失败日志 |
| 生命周期误伤外部服务 | Compose project labels、无 kill-by-port、测试保留外部占用进程 | stop 仅停止本 project；不执行 docker system prune |
| 密钥泄露 | 初始化不打印、权限检查、结构化日志脱敏、release 扫描 | 立即轮换密钥、使旧 token 失效、记录审计事件 |
| Apple Silicon 镜像不可用 | multi-arch manifest 验证及实体机 RC | 不发布该架构，或回滚至上一多架构 digest |
| 数据/模型结论被误用 | paper-only 默认、UI/文档声明、发布分级 | 隐藏或禁用未批准高风险入口，保留研究数据 |
| 日志容量耗尽 | 分级保留、压缩、磁盘告警、外部采集可选 | 优先保留审计/错误日志，按 runbook 扩容或归档 |

## 8. 计划完成后的交接包

交接给发布负责人时必须包含：

1. 已批准 ADR、支持矩阵、用户安装文档、运维/恢复 runbook。
2. 含 digest 的 Release Manifest、SBOM、签名/证明、校验和、许可证审阅记录。
3. macOS Intel、macOS Apple Silicon、Ubuntu LTS、Windows 11 的生命周期证据，或明确的不支持声明。
4. 自动测试原始输出、CI run URL、已知基线失败说明、三方 RC 签字。
5. 后续 backlog 中每项的 owner、日期、优先级、代码/文档定位和可复现验收命令。

任何缺少上述交付物的状态只能标为“候选/内测”，不能标为“正式产品发布”。
