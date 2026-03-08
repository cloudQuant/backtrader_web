# 故障排查指南

本文档收集 Backtrader Web 常见问题及解决方案。

## 1. 安装问题

### 1.1 Python 依赖安装失败

**症状**: `pip install -r requirements.txt` 报错

**解决方案**:
```bash
# 升级 pip
pip install --upgrade pip

# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 如果 backtrader 安装失败，单独安装
pip install backtrader==1.9.78.123

# 如果 fincore 安装失败
pip install fincore>=1.0.0
```

### 1.2 Node.js 依赖安装失败

**症状**: `npm install` 报错

**解决方案**:
```bash
# 清除缓存
npm cache clean --force
rm -rf node_modules package-lock.json

# 使用淘宝镜像
npm install --registry=https://registry.npmmirror.com

# 或使用 pnpm
pnpm install
```

### 1.3 Playwright 浏览器安装失败

**症状**: `npx playwright install` 超时或报错

**解决方案**:
```bash
# 设置代理
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright

# 只安装 Chromium
npx playwright install chromium

# Python 版本
python -m playwright install chromium
```

## 2. 启动问题

### 2.1 后端启动失败

**症状**: `uvicorn app.main:app` 报错

**常见原因与解决**:

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `ModuleNotFoundError: No module named 'app'` | 工作目录不对 | `cd src/backend` 后再启动 |
| `Address already in use` | 端口被占用 | `lsof -i :8000` 找到并关闭占用进程 |
| `Database error` | 数据库未初始化 | 首次启动会自动创建 SQLite 数据库 |
| `SECRET_KEY warning` | 使用默认密钥 | 设置环境变量 `SECRET_KEY=<random-string>` |

### 2.2 前端启动失败

**症状**: `npm run dev` 报错

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `ENOENT: no such file` | 依赖未安装 | 运行 `npm install` |
| `Port 3000 is in use` | 端口被占用 | `npm run dev -- --port 3001` |
| `Cannot find module` | TypeScript 类型错误 | `npm run build` 检查错误 |

### 2.3 前后端连接失败

**症状**: 前端页面显示但 API 请求失败

**检查清单**:
1. 后端是否运行在 `http://localhost:8000`
2. CORS 配置是否包含前端地址
3. 环境变量 `CORS_ORIGINS` 是否设置
4. 浏览器控制台是否有 CORS 错误

```bash
# 检查后端是否运行
curl http://localhost:8000/docs

# 检查 CORS 配置
export CORS_ORIGINS="http://localhost:3000"
```

## 3. 登录问题

### 3.1 无法登录

**检查项**:
1. 默认管理员账号: `admin` / `admin123` （仅开发环境默认值，不可作为生产环境配置建议）
2. 确认后端正在运行
3. 检查浏览器控制台错误

```bash
# 直接测试 API
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### 3.2 Token 过期

**症状**: 操作中突然被跳转到登录页

**原因**: JWT Token 过期（默认 30 分钟）

**解决**: 重新登录即可。如需延长，在后端配置中修改 `ACCESS_TOKEN_EXPIRE_MINUTES`。

## 4. 回测问题

### 4.1 回测提交后无响应

**检查项**:
1. 是否选择了策略
2. 后端日志中是否有错误: `tail -f logs/backend.log`
3. 策略文件是否存在于 `strategies/` 目录

### 4.2 策略加载失败

**症状**: 策略下拉列表为空或回测报错

**解决**:
```bash
# 检查策略目录
ls strategies/*/config.yaml | wc -l  # 应该显示 100+

# 验证特定策略
cat strategies/002_dual_ma/config.yaml
python -c "
from app.services.strategy_service import StrategyService
import asyncio
s = StrategyService()
templates = asyncio.run(s.get_templates())
print(f'Loaded {len(templates)} templates')
"
```

### 4.3 回测结果数据异常

**可能原因**:
- 数据源无可用数据（检查股票代码和日期范围）
- 策略参数配置不合理
- fincore 指标计算异常（查看 `metrics_source` 字段）

## 5. 数据问题

### 5.1 数据查询无结果

**检查项**:
1. 股票代码格式：`000001.SZ`（深圳）/ `600519.SH`（上海）
2. 日期范围是否合理
3. 数据源（AkShare）是否可访问

### 5.2 数据下载缓慢

**解决**: AkShare 数据源依赖网络状况，可考虑：
- 缩小日期范围
- 使用本地数据缓存
- 检查网络连接

## 6. 性能问题

### 6.1 后端响应慢

**排查步骤**:
1. 检查慢请求日志：`grep "SLOW" logs/backend.log`
2. 检查数据库查询性能
3. 检查回测任务队列是否堆积

### 6.2 前端加载慢

**优化建议**:
- 检查网络请求：F12 → Network 面板
- 确认是否有大量策略模板加载
- 检查 WebSocket 连接状态

## 7. E2E 测试问题

### 7.1 测试超时

```bash
# 增加超时时间
npx playwright test --timeout 60000

# 或在 playwright.config.ts 中设置
# timeout: 60000
```

### 7.2 元素找不到

**排查**:
1. 使用 `--debug` 模式查看页面状态
2. 检查选择器是否与最新 UI 匹配
3. 确认是否需要等待异步加载

```bash
# 调试模式
npx playwright test --debug

# 生成报告
npx playwright test --reporter=html
npx playwright show-report
```

### 7.3 测试不稳定 (Flaky)

**解决方案**:
- 替换 `waitForTimeout` 为 `waitForSelector`
- 增加重试次数：`--retries 2`
- 使用 `storageState` 避免重复登录

## 8. 日志位置

| 日志 | 位置 | 用途 |
|------|------|------|
| 后端日志 | `logs/backend.log` | API 请求、错误 |
| 审计日志 | `logs/audit.log` | 登录、敏感操作 |
| 回测日志 | `logs/backtest/` | 回测执行详情 |
| 前端日志 | 浏览器控制台 (F12) | 前端错误 |

## 9. 获取帮助

如果以上方案无法解决问题：
1. 查看 [完整技术文档](TECHNICAL_DOCS.md)
2. 查看 [运维手册](OPERATIONS.md) 的监控和诊断部分
3. 提交 Issue 并附上：
   - 错误截图或日志
   - 操作步骤
   - 系统环境信息（OS、Python 版本、Node 版本）
