# Subtask Summary — ccxt-vendor (ST2)

## 执行者说明
子代理(ai-workflow:implementer)连续两次因 Anthropic API "Connection closed mid-response"
早退且未落改动。为不空转,**本子任务由编排者在主会话直接实现**;独立门禁仍由
`verify_subtask.ps1` 机械重跑(见 .verify.md),不以本自述为准。

## What changed
把 crypto 行情接入 vendored dataflows,并封死 fundamentals:
1. 新增 `dataflows/ccxt_vendor.py`：自包含 ccxt vendor。
   - `get_ccxt_data(symbol,start,end)` → OHLCV CSV(对应 `get_stock_data`)。
   - `get_ccxt_indicators_window(symbol,indicator,curr_date,look_back)` → stockstats 指标
     窗口(对应 `get_indicators`),支持与 yfinance 路径相同的 13 个指标键。
   - `BTC`→`BTC/USDT`(默认 binance);网络出口集中在 `_fetch_ohlcv_raw`(测试可 patch)。
   - `curr_date` 过滤防前视;crypto 7×24 无休市,窗口内每天有数据。
2. `dataflows/interface.py`：
   - 注册 ccxt 进 `VENDOR_METHODS` 的 get_stock_data / get_indicators;`VENDOR_LIST` 加 ccxt。
   - **禁用 fundamentals**：移除 get_fundamentals/get_balance_sheet/get_cashflow/
     get_income_statement 的 VENDOR_METHODS 条目与 TOOLS_CATEGORIES 类目及其未用 import;
     新增 `DISABLED_METHODS` 集合 + `route_to_vendor` 开头显式守卫,调用抛
     "not applicable to crypto" 而非回退股票数据源。
3. `default_config.py`：`core_stock_apis`/`technical_indicators` 默认改 `ccxt`
   (只改这两键;fundamental_data 值保留仅占位)。

## Files touched
- 新增: `btc_agent/src/btc_agent/dataflows/ccxt_vendor.py`
- 新增: `btc_agent/tests/test_ccxt_vendor.py`(7 个离线单测)
- 改: `btc_agent/src/btc_agent/dataflows/interface.py`
- 改: `btc_agent/src/btc_agent/default_config.py`

## fundamentals 禁用方式
**移除路由 + 显式守卫**(非抛错占位):VENDOR_METHODS 与 TOOLS_CATEGORIES 里都不再有它们,
`DISABLED_METHODS` 守卫保证任何调用得到清晰的 not-applicable 错误。全包 grep 确认无残留外部引用,
顶层 `TradingAgentsGraph` 仍能 import。

## 检查(共享 venv python 实跑)
- `ruff check .` → All checks passed!
- `pytest -q` → 10 passed(ST1 的 3 个 + ST2 的 7 个)

## Mock 了什么
`test_ccxt_vendor.py` monkeypatch `ccxt_vendor._fetch_ohlcv_raw` 返回固定录制蜡烛
(起点 2020-09,不依赖当前时间),**不打真实交易所网络**,离线可跑。断言:OHLCV/指标结构、
`route_to_vendor("get_stock_data","BTC",...)` 走到 ccxt、fundamentals 四方法禁用抛错、
ccxt 已注册。

## Open risks / follow-ups
- ccxt vendor 未对真实 binance 接口做过一次真跑(VPN 不稳,刻意留到 ST4 端到端);
  真实符号/时间框架/限流行为待 ST4 验证。
- `get_ccxt_data` 的输出表头与 yfinance 版格式相近但不完全一致(列名一致,注释头文案不同),
  下游 market 分析师 prompt 若对表头敏感,ST4 端到端时留意。
- langgraph 1.x 运行时兼容仍未验(承自 ST1),ST4 首次真跑图时确认。

## Reviewer recommendation
pass（实现完成、检查全绿、验收项达标;真实交易所连通性按设计留 ST4）
