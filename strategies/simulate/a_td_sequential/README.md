# 豆一 TD Sequential 策略

基于 Tom DeMark TD 序列的期货模拟交易策略。

## 配置说明

### 1. 凭证配置（.env）

**凭证已从 config.yaml 移出，请使用 .env 文件：**

```bash
cp .env.example .env
# 编辑 .env，填写 SimNow 账号信息
```

必需变量：`CTP_BROKER_ID`, `CTP_INVESTOR_ID`, `CTP_USER_ID`, `CTP_PASSWORD`

### 2. 策略配置（config.yaml）

```bash
cp config.example.yaml config.yaml
# 按需修改 fronts、live、backtest 等
```

`config.yaml` 仅包含策略参数与连接地址，不含敏感凭证。

### 3. 调试输出

设置环境变量 `TD_DEBUG=1` 可开启 tick/bar 打印，生产环境请关闭：

```bash
TD_DEBUG=1 python run.py
```

## 运行

```bash
cd strategies/simulate/a_td_sequential
python run.py
```
