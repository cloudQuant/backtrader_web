# 模拟交易策略

CTP 模拟盘策略，凭证从 `.env` 读取，策略配置从 `config.yaml` 读取。

## 配置说明

### 1. 凭证（.env）

每个策略目录下需有 `.env` 文件：

```bash
cd strategies/simulate/<策略名>
cp .env.example .env
# 编辑 .env，填写 CTP_BROKER_ID、CTP_INVESTOR_ID、CTP_USER_ID、CTP_PASSWORD
```

或使用项目根目录的 `.env`（run.py 会优先读取策略目录，未设置时回退到项目根）。

### 2. 策略配置（config.yaml）

```bash
cp config.example.yaml config.yaml
# 按需修改 live、backtest/simulate、ctp.fronts 等
```

### 3. 运行

```bash
cd strategies/simulate/<策略名>
python run.py
```

## 策略列表

| 目录 | 策略 |
|------|------|
| a_td_sequential | 豆一 TD 序列 |
| al_turtle | 铝海龟 |
| au_boll_reverser | 金布林反转 |
| c_chandelier_exit | 蜡烛台退出 |
| CF_donchian_channel | 棉花唐奇安通道 |
| cs_hma_multitrend | 玉米 HMA 多趋势 |
| cu_macd_atr | 铜 MACD+ATR |
| hc_supertrend | 热卷超级趋势 |
| i_r_breaker | 铁矿石 R-Breaker |
| j_dual_thrust | 焦炭双重推力 |
| jm_stochastic | 焦煤随机指标 |
| m_ichimoku_cloud | 豆粕一目均衡 |
| MA_trix | MA Trix |
| OI_rsi_dip_buy | 豆油 RSI 逢低买入 |
| p_bb_rsi | 棕榈油 BB+RSI |
| rb_dual_ma | 螺纹 dual MA |
| SR_keltner_channel | 白糖肯特纳通道 |
| TA_cci | PTA CCI |
| y_alligator | 豆油鳄鱼 |
| zn_kelter | 锌肯特纳 |
