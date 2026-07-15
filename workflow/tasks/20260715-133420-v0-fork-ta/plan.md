# Task Plan — v0: fork TradingAgents → BTC 单资产日度研判

## Selected Workflow
agent-change

## 子任务拆分(一次一个 worktree,ST1 阻塞其余)

### ST1 — vendor 核心模块 + 依赖就位(基础,阻塞后续)
选择性拷贝 TradingAgents(main)的 graph/agents/dataflows/schemas/memory/default_config
进 `btc_agent/src/btc_agent/`;删明显股票专用件;加最小依赖(langgraph, langchain-core,
langchain-openai, ccxt, stockstats, pandas, pytz)进 pyproject;bootstrap 绿;冒烟 import 单测。
验收: pytest 绿、能 import 顶层 graph 构造函数、fundamentals 相关模块已移除或隔离。

### ST2 — ccxt 行情 vendor + 禁 fundamentals 路由
写 `dataflows/ccxt_vendor.py`(BTC OHLCV/现价,交易所只读公开接口),在 interface 的
route_to_vendor 注册为 core_stock_apis/technical_indicators 的 crypto vendor;禁用
fundamental/balance_sheet/cashflow/income_statement 路由。单测用录制/mock 数据,不打真实网。
验收: market_analyst 的 ToolNode 能取到 BTC 行情;grep 确认财报路由不 active。

### ST3 — 7×24 UTC 日历 + BTC-HODL 基准
把 look-back/propagation 的交易日历改连续 UTC(去休市跳过、去 end 独占的交易日修正);
memory/reflection 的 alpha 基准换 BTC-HODL。单测: 含周六的窗口不跳过、alpha 相对 BTC-HODL。
验收: 日历单测绿、基准断言绿。

### ST4 — DeepSeek 配置 + run 入口 + 端到端
default_config 配 DeepSeek(llm_provider=openai 兼容, backend_url, deep/quick 模型名, key 读 .env);
禁用 fundamentals 分析师(v0 仅 market);研究经理 prompt 反向调成白卷文化;交易价位机械规则
(选最简可解释一种, 如近期高低点/ATR);`python -m btc_agent.run` 产出一条结构化记录入记忆日志。
LLM 在单测里 mock。验收: 全部 Acceptance Criteria 通过;回填 config.json contract_touchpoints。

## Verification Steps
1. 每个 ST 在其 worktree 跑 `ruff check .` + `pytest`(经 task-verify 独立复验,不认子代理自查)。
2. ST4 后跑一次真实(带 DeepSeek key)端到端,人工确认记忆日志记录合理。
3. 合并前确认 6 条 Acceptance Criteria 逐条可验证。

## Stop Rules
- vendored crypto 路径与文档不符(asset_type 未贯通)→ 停下报告,不硬改编排。
- 最小依赖装不动(代理/SSL)→ 停下报告,不反复换镜像试。
- 触及实盘/下单/杠杆 → 停(超 v0 范围)。
- DeepSeek 结构化输出不兼容 → 停下报告,提退到 prompt+确定性解析的方案再继续。

## Workflow Reference
(no per-class runbook in this project)

## Worktree
- branch: task/v0-fork-ta
- path: C:\Users\admin\Desktop\wt-v0-fork-ta
（standard: 每个子任务由 task-assign 另开独立 worktree)
