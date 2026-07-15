# Subtask Spec

## Parent Task
20260715-133420-v0-fork-ta（v0: fork TradingAgents → BTC 单资产日度研判）

## Subtask Title
ST4 — DeepSeek 配置 + run 入口 + 机械价位 + 结构化记录（v0 收尾）

## Owner Role
agent-change

## Goal
接上 DeepSeek，写 `python -m btc_agent.run --asset BTC --date <UTC日>` 入口:跑 market-only
crypto 图 → 记忆日志落一条(rating+reasoning，vendored 已实现) → 机械规则算交易价位(entry/stop/
target) → 汇成一条结构化记录(JSON)。研究经理 prompt 反调白卷文化。**LLM 部分单测全 mock；
真 key + 真交易所的端到端跑留给用户(需 DEEPSEEK_API_KEY)。**

## 已知集成点（编排者已核实）
- DeepSeek 内置:`llm_provider="deepseek"`，模型 `deepseek-v4-pro`(deep)/`deepseek-v4-flash`(quick)，
  `ProviderSpec(base_url="https://api.deepseek.com")` 自动，key env `DEEPSEEK_API_KEY`。
- `TradingAgentsGraph(selected_analysts=["market"], config=...).propagate("BTC", date, asset_type="crypto")`
  内部会 `_resolve_pending_entries` → 跑图 → `store_decision`(写 `[date|BTC|rating|pending]`+DECISION)。
  返回 `final_state`(含 `final_trade_decision`)。
- `store_decision` 用 `parse_rating` 得 5 档评级；记忆日志机制已就绪，不需重写。
- ST2 `ccxt_vendor._ohlcv_dataframe(symbol, curr_date)` 提供 OHLCV DataFrame。

## Scope（允许触碰）
- `default_config.py`：`llm_provider`→"deepseek"、`deep_think_llm`→"deepseek-v4-pro"、
  `quick_think_llm`→"deepseek-v4-flash"。（backend_url 保持 None，自动。）
- `agents/managers/research_manager.py`：把"reserve Hold for genuinely balanced"一段反调为
  **白卷文化**——环境不明确/证据不足时，交白卷(Hold/不出票)优于硬凑方向。
- 新增 `btc_agent/trade_levels.py`：`compute_trade_levels(ohlcv_df, direction) -> {entry,stop,target}`，
  **纯确定性**(如基于 ATR 或近期高低点)，不依赖任何 LLM 文本。
- 新增 `btc_agent/run.py` + `btc_agent/__main__.py`：argparse `--asset`(默认 BTC) `--date`;
  构造 market-only crypto 图、propagate、算机械价位、写结构化 JSON 记录到 `results_dir`。
- 新增单测 `tests/test_trade_levels.py`、`tests/test_run_record.py`。

## 禁止触碰
- ccxt_vendor / interface / 日历逻辑(ST2/ST3 已定，可调用不可改)、其他 agent 的编排。
- 不把真实 key 写进代码或 git;key 只从 `DEEPSEEK_API_KEY` 环境变量读。

## Dependencies
- depends-on: [vendor-core, ccxt-vendor, calendar-benchmark]
- provides-to: []（v0 最后一个子任务）

## Acceptance Criteria
- [ ] `default_config` LLM 为 deepseek + v4-pro/v4-flash
- [ ] `python -m btc_agent.run --help` 可运行(argparse 就绪)
- [ ] `compute_trade_levels` 纯确定性:单测断言同一 OHLCV → 同一 {entry,stop,target}，
      **且价位与任何 LLM 文本无关**(改 mock 的 decision 文本不改价位)
- [ ] run 入口(mock 掉 propagate/LLM 与 ccxt)执行后**写出一条结构化记录**,字段含:
      asset、UTC 时点、5 档评级、reasoning、entry/stop/target(机械)
- [ ] research_manager prompt 含白卷文化措辞(grep 确认)
- [ ] 顶层 import + ruff + pytest 全绿(LLM/网络全 mock，离线可跑)

## Verification
- maker checks: ruff、pytest
- independent re-verify: 编排者跑 task-verify
- **真 key 端到端**:非本子任务自动化范围;用户放 `DEEPSEEK_API_KEY` 后由编排者手动跑一次
  `python -m btc_agent.run --asset BTC --date <今日UTC>` 确认真实记录合理(langgraph 1.x 运行时
  兼容在此首次真验)。

## Stop Conditions
- langgraph 1.x 真跑图时运行时报错(承自 ST1 风险)→ 记录实情;若仅端到端受影响、离线单测仍绿，
  归入"待 key 端到端"，不算本子任务失败。
- 机械价位要读 LLM 输出才能算 → 设计错了，价位必须纯机械，停下重想。
- 发现要改 ccxt_vendor/日历才能完成 → 越界，停下上报。

## Parent Task
20260715-133420-v0-fork-ta

## Subtask Title
config-run

## Recommended Workflow
agent-change
