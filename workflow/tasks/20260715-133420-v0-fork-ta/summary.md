# Task Summary — v0: fork TradingAgents → BTC 单资产日度研判

## What Changed
把 TradingAgents(main, 已原生支持 crypto)选择性 vendored 进 `btc_agent/`，改装成能对
单一资产 BTC 产出一条结构化日度研判记录(方向评级+理由+机械价位)并落记忆日志的最小可运行系统。
4 个子任务(串行,后者依赖前者):

- **ST1 vendor-core**：拷 graph/agents/dataflows/schemas/memory/default_config 进 src,包名
  tradingagents→btc_agent 全量改名,加最小依赖(langgraph 1.x/langchain/ccxt/pandas/stockstats 等)。
- **ST2 ccxt-vendor**：新增 `dataflows/ccxt_vendor.py`(BTC OHLCV + stockstats 指标),注册进
  interface 的 get_stock_data/get_indicators;禁用 fundamentals 四路由(DISABLED_METHODS 守卫)。
- **ST3 calendar-benchmark**：结算取价从 yfinance 改走 ccxt;去掉股票周末缓冲,窗口按连续 UTC 天;
  benchmark 改 BTC-HODL(benchmark_ticker=BTC/USDT + benchmark_label)。
- **ST4 config-run**：DeepSeek 配置;`python -m btc_agent.run` 入口;`trade_levels.py` 纯确定性
  机械价位(ATR);结构化 JSON 记录;research_manager prompt 反调白卷文化。
- **端到端联调修复**(真跑暴露):ccxt 交易所/代理 config 驱动(binance 主站 451→binance.us+Clash
  代理);中转站 link3.top + deepseek-chat 双档;run.py 修 propagate 元组解包。

## Files Touched
新增: `btc_agent/`(整个 src 树 vendored)、`ccxt_vendor.py`、`trade_levels.py`、`run.py`、
`__main__.py`、`VENDORED.md`、5 个测试文件。改: `default_config.py`、`interface.py`、
`graph/trading_graph.py`、`graph/reflection.py`、`agents/managers/research_manager.py`、`pyproject.toml`。

## Verification Run
- 每个子任务独立复验(verify_subtask.ps1 机械重跑,非自查)全 PASS,证据:
  `subtask-summaries/{vendor-core,ccxt-vendor,calendar-benchmark,config-run}.verify.md`。
- 主 checkout 合并后重跑:**ruff 全绿 + pytest 25 passed**。
- **端到端真跑**:`python -m btc_agent.run --asset BTC --date 2026-07-15` exit 0,产出
  `~/.btc_agent/logs/records/BTC_2026-07-15.json`——rating=Hold(白卷生效)、direction=flat、
  entry=64859.84(ccxt 真实价,机械填)、含完整多空辩论+三方风控+经理裁决理由。
  真验通三个承接风险:langgraph 1.x 运行时、ccxt 真实行情、DeepSeek 辩论链。

## Drift / Checker Result
无契约面检查(v0 契约尚未成形,config.json contract_touchpoints 仍空)。

## Follow-ups
- **prompt 的 crypto 语境适配(v1 重点)**：vendored prompt 面向股票,真跑时 LLM 把 BTC 说成
  "ETF"、把技术指标数值当价格量级。不影响机械价位,但研判文本质量待 v1 打磨。
- **alpha 退化(已知 v0 局限)**：BTC 资产 vs BTC-HODL 基准,v0 不建仓 → alpha≈0,待决策变仓位。
- **`-m` 需 `PYTHONPATH=src`**：src 布局未 pip 安装;正式部署 `pip install -e` 可免。
- **回填 config.json contract_touchpoints**：vendor 接口/输出 schema 已成形,可在 v1 登记。
- **机械价位公式**：ATR 1.5/3.0 是 v0 最简版,留 v2 精修。
- 记忆日志的 pending 记录路径 `~/.btc_agent/memory/`,下次同标的运行会结算+反思(未真验多轮)。

## Human Review Notes
子代理 API 连续中断(connection closed mid-response),ST2 起改由编排者主会话实现,但独立复验
门禁照走。DeepSeek 走用户提供的中转站(key 在 .env,已 gitignore 不入库)。

## Task
v0-fork-ta
