# Subtask Spec

## Parent Task
20260715-133420-v0-fork-ta（v0: fork TradingAgents → BTC 单资产日度研判）

## Subtask Title
ST3 — 7×24 UTC 日历 + BTC-HODL 基准

## Owner Role
agent-change

## Goal
把结算/复盘链路里残留的**股票交易日历假设**改成 crypto 的 7×24 连续 UTC，并把 alpha 计算的
**基准从 SPY/区域指数改为 BTC-HODL**，且结算取价走 ccxt 而非 yfinance。只碰日历/基准/结算取价，
不写 run 入口、不改 LLM 配置、不改编排与 prompt(ST4)。

## 已知代码结构（编排者已核实）
- `graph/trading_graph.py`:
  - `_resolve_benchmark(ticker)`：从 `benchmark_map`/`benchmark_ticker` 取基准 ticker。
  - `_fetch_returns(ticker, trade_date, holding_days=5, benchmark="SPY")`：**用 yfinance 直接取
    asset 与 benchmark 收盘价**算 raw/alpha；`end = start + timedelta(days=holding_days + 7)`
    的 **+7 是周末/假日缓冲**(股票专用)。
  - `_resolve_pending_entries`：调 `_fetch_returns` 结算 pending 记忆条目。
- `graph/reflection.py`：`reflect_on_final_decision(..., benchmark_name="SPY")` alpha 标签默认 SPY。
- `default_config.py`：`benchmark_ticker=None`、`benchmark_map`(股票交易所后缀→区域指数)。
- ST2 已提供 `dataflows/ccxt_vendor.py`(`_ohlcv_dataframe(symbol, curr_date)` 返回带 Date/Close
  的连续日线 DataFrame，网络出口 `_fetch_ohlcv_raw` 可 mock)。

## Scope（允许触碰）
- `default_config.py`：基准改 BTC-HODL —— 设 `benchmark_ticker` 指向 BTC 的现货(如 "BTC/USDT")，
  并让标签读作 "BTC-HODL"(可加一个 `benchmark_label` 键或在 reflection 侧映射)。benchmark_map
  的股票条目可保留(占位)但默认走 BTC-HODL。
- `graph/trading_graph.py`：
  - `_fetch_returns`：asset 与 benchmark 取价**改走 ccxt vendor**(用 ST2 的 `_ohlcv_dataframe`
    或 route_to_vendor)，去掉 `+7` 周末缓冲(crypto 连续，`holding_days` 即连续 UTC 天)；
    raw/alpha 计算逻辑保留。
  - `_resolve_benchmark`：BTC 场景返回 BTC-HODL 基准符号。
- `graph/reflection.py`：`benchmark_name` 默认/透传改为 "BTC-HODL"。
- 新增/改单测：`tests/test_calendar_benchmark.py`。

## 禁止触碰
- run 入口(ST4)、default_config 的 LLM/DeepSeek 键、agents 编排与 prompt、ccxt_vendor.py 本身
  的取数逻辑(可调用不可改)。

## 已知 v0 局限（记录，不在本子任务解决）
BTC 资产 vs BTC-HODL 基准：v0 只出方向评级、不建仓，realized raw≈持有 BTC 收益≈benchmark，
故 alpha≈0。这是"只记录不执行"的 v0 结构性局限，待决策变成实际仓位后 alpha 才有意义。
本子任务只需把管道改对(基准是 BTC-HODL、取价走 ccxt、日历连续)，不需让 alpha 非零。

## Dependencies
- depends-on: [vendor-core(ST1), ccxt-vendor(ST2)]
- provides-to: [config-run(ST4)]

## Acceptance Criteria
- [ ] `default_config` 的 benchmark 解析结果为 BTC-HODL(基准符号是 BTC 现货，非 SPY/区域指数)
- [ ] `_fetch_returns` 不再调用 yfinance；asset 与 benchmark 取价走 ccxt(单测 mock 交易所层验证)
- [ ] 去掉股票周末/假日缓冲：结算窗口按连续 UTC 天(单测断言:含周六的窗口不因"非交易日"跳过)
- [ ] reflection 的 alpha 标签读作 "BTC-HODL"
- [ ] 顶层 `TradingAgentsGraph` 仍可 import；ruff + pytest 全绿(含新单测)
- [ ] 未触碰 run 入口/LLM 配置/prompt(grep 或 diff 确认)

## Verification
- maker checks: ruff、pytest
- checker gates: 无
- independent re-verify: 由编排者跑 task-verify

## Stop Conditions
- 改结算取价为 ccxt 时发现要动 ccxt_vendor 内部才能拿到 asset+benchmark 两条价格序列 → 停下报告
  (应能通过调用现有接口 + 传不同 symbol 完成)。
- 发现要改 run 入口/编排才能完成 → 边界划错，停下上报。
- alpha 计算因单资产退化无法产出有意义值 → 这是已知 v0 局限，**不是失败**，记录即可，别为此扩范围。

## Parent Task
20260715-133420-v0-fork-ta

## Subtask Title
calendar-benchmark

## Recommended Workflow
agent-change
