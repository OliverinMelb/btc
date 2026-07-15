# Subtask Spec

## Parent Task
20260715-133420-v0-fork-ta（v0: fork TradingAgents → BTC 单资产日度研判）

## Subtask Title
ST2 — ccxt 行情 vendor + 禁用 fundamentals 路由

## Owner Role
agent-change

## Goal
在 vendored 的 `dataflows/` 里新增一个 **ccxt 行情 vendor**，让 `get_stock_data`(OHLCV) 与
`get_indicators`(技术指标) 能对 BTC 取到真实交易所行情；并**禁用 fundamentals 系四个路由**
(对 BTC 无意义)。让 market 分析师的取数路径走 crypto。**只碰数据源层与其配置项,不改日历
(ST3)、不改 LLM 配置/写 run 入口(ST4)、不改编排。**

## 已知代码结构（编排者已核实，基于 task 分支含 ST1 的 vendored 代码）
- `dataflows/interface.py`:
  - `VENDOR_METHODS[method][vendor] -> impl 函数`；`VENDOR_LIST`；`TOOLS_CATEGORIES`;
    `get_vendor(category)` 读 config 选 vendor；`route_to_vendor(method,...)` 带 fallback。
  - core_stock_apis→`get_stock_data`；technical_indicators→`get_indicators`；
    fundamental_data→`get_fundamentals/get_balance_sheet/get_cashflow/get_income_statement`。
- `default_config.py` 里 `core_stock_apis`/`technical_indicators`/`fundamental_data` 等键选 vendor。

## Scope（允许触碰）
- 新增 `dataflows/ccxt_vendor.py`：用 ccxt(已装)取 BTC 的 OHLCV 与由 OHLCV 计算的技术指标
  (指标可复用已装的 stockstats，与 yfinance 路径同构)。**只读公开行情接口,不带 key、不下单。**
- `dataflows/interface.py`：把 ccxt impl 注册进 `VENDOR_METHODS["get_stock_data"]` 与
  `["get_indicators"]`；`VENDOR_LIST` 加 "ccxt"；**禁用 fundamentals**——把
  get_fundamentals/get_balance_sheet/get_cashflow/get_income_statement 从 active 路由移除，
  或改为对 crypto 抛显式"not applicable"(选其一，在 summary 说明；market 分析师不该再触发它们)。
- `default_config.py`：`core_stock_apis` 与 `technical_indicators` 默认 vendor 改 "ccxt"
  (**只改这两个 vendor 选择键**,不碰 benchmark/LLM/日历相关键——那些是 ST3/ST4)。
- 新增单测 `tests/test_ccxt_vendor.py`。

## 禁止触碰
- 日历/look-back/propagation（ST3）、benchmark 值、default_config 的 LLM/DeepSeek 键、
  run 入口、memory/reflection、agents 编排与 prompt。

## Dependencies
- depends-on: [vendor-core(ST1)]
- provides-to: [calendar(ST3), config-run(ST4)]

## Inputs
- parent spec / plan / brief（同目录上级）
- 设计依据: 仓库根 BTC-DESIGN-REVIEW.md（第五节改装清单第 2、3 条）
- 环境事实: ~/.claude/workflow-memory/environment.md

## Acceptance Criteria
- [ ] `dataflows/ccxt_vendor.py` 存在;对 BTC 能返回 OHLCV 与技术指标(单测用**录制/mock 数据**,
      不打真实交易所网络——CI/离线可跑)
- [ ] ccxt 已注册进 `VENDOR_METHODS` 的 get_stock_data / get_indicators;`VENDOR_LIST` 含 ccxt
- [ ] `default_config` 的 core_stock_apis 与 technical_indicators 默认为 ccxt
- [ ] fundamentals 四路由已禁用:`grep` 确认它们不在 active VENDOR_METHODS(或对 crypto 抛
      not-applicable),且单测断言调用它们不会返回股票财报
- [ ] `route_to_vendor("get_stock_data", ...)` 对 BTC 走到 ccxt impl(单测 mock 交易所层验证)
- [ ] ruff + pytest 全绿(用共享 venv 的 python)

## Verification
- maker checks: ruff、pytest
- checker gates: 无
- independent re-verify: 由编排者跑 task-verify

## Stop Conditions
- ccxt 对 BTC 的接口与预期不符、或必须联网才能让单测过 → 停下报告(单测应可离线跑,用 mock)。
- 发现要改日历/编排才能完成 → 边界划错，停下上报，别越界到 ST3/ST4。
- 禁用 fundamentals 导致 graph import 或既有单测崩 → 停下报告(可能有隐藏依赖)。

## Parent Task
20260715-133420-v0-fork-ta

## Subtask Title
ccxt-vendor

## Recommended Workflow
agent-change
