# Subtask Summary — calendar-benchmark (ST3)

## 执行者说明
承 ST2:子代理 API 仍不稳,本子任务由编排者主会话实现;独立门禁由 `verify_subtask.ps1`
机械重跑(见 .verify.md)。

## What changed
把结算/复盘链路从股票日历+SPY 基准改成 crypto 7×24 + BTC-HODL:
1. `graph/trading_graph.py`:
   - `_fetch_returns`：**取价从 yfinance 改走 ccxt vendor**(`_ohlcv_dataframe`);去掉
     `+7 周末/假日缓冲`,窗口按**连续 UTC 天**(`holding_days` 即连续天);raw/alpha 逻辑保留;
     默认 benchmark 参数 SPY→"BTC/USDT"。删除 `import yfinance as yf`(该文件已不再用)。
   - `_resolve_pending_entries`：reflection 的 `benchmark_name` 传**人读标签**
     `config["benchmark_label"]`("BTC-HODL"),与取价符号("BTC/USDT")解耦。
2. `default_config.py`：`benchmark_ticker` None→"BTC/USDT";新增 `benchmark_label`="BTC-HODL"。
3. `graph/reflection.py`：`benchmark_name` 默认 SPY→"BTC-HODL"。

## Files touched
- 改: `graph/trading_graph.py`、`default_config.py`、`graph/reflection.py`
- 新增: `tests/test_calendar_benchmark.py`(6 个离线单测)

## 检查(共享 venv python 实跑)
- `ruff check .` → All checks passed!
- `pytest -q` → 15 passed(ST1 3 + ST2 7 + ST3 5* ；*含 1 个回归守卫)
- 顶层 `TradingAgentsGraph` 仍可 import。

## Mock / 覆盖
`test_calendar_benchmark.py` monkeypatch `ccxt_vendor._fetch_ohlcv_raw` 返回**UTC 午夜**连续日线
(含周末),不打网络。断言:①默认基准是 BTC/USDT + BTC-HODL 标签(非 SPY);②`_resolve_benchmark("BTC")`
返回 crypto;③`_fetch_returns` 走 ccxt、连续 5 UTC 天(含周六不跳)、`days==5`;④trading_graph
不再有 `yf`。

## 已知 v0 局限（记录，非缺陷）
BTC 资产 vs BTC-HODL 基准在 v0"只出评级不建仓"下退化:realized raw≈持有 BTC≈benchmark → alpha≈0
(单测 `abs(alpha)<1e-9` 明确固化这一事实)。管道已改对(基准 BTC-HODL、取价 ccxt、日历连续),
待决策变成实际仓位后 alpha 才有意义——留 v2/后续。

## Open risks / follow-ups
- 真实 ccxt 结算取价未做真跑(VPN 不稳,留 ST4 端到端)。
- `_fetch_returns` 依赖 ccxt_vendor 的私有 `_ohlcv_dataframe`;若后续 ccxt vendor 重构其签名需同步。
- langgraph 1.x 运行时兼容仍未验(承自 ST1),ST4 首次真跑确认。

## Reviewer recommendation
pass（实现完成、检查全绿、验收达标;alpha 退化是文档化的 v0 已知局限）
