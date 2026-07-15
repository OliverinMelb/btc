# 项目工程教训（BTC Agent）

> 任务闭环时(task-close)按分拣规则追加：只放"换一个子任务仍成立、且非代码本身能记录"的教训。
> 全局层教训进 `~/.claude/workflow-memory/lessons.md`，本文件只放本项目特有的。

<!-- 闭环时在此追加，最新在上 -->

## v0（fork TradingAgents）2026-07-15

- **vendored TradingAgents 的 prompt 面向股票，是 v1 的主要打磨点。** v0 端到端真跑时 LLM 把
  BTC 说成 "ETF"、把技术指标数值($30.59 等)当成价格量级——因为 market 分析师喂的是指标数值、
  且 prompt 语境是股票。不影响机械价位(用真实 close),但研判文本质量要靠 v1 的 crypto prompt 适配。
- **TradingAgents main 已原生支持 crypto**(asset_type / resolve_instrument_context / symbol_utils /
  Polymarket)，所以是 fork+换 vendor+改日历，不是重写。propagate("BTC", date, asset_type="crypto")。
- **`propagate()` 返回 `(final_state, processed_signal)` 元组**，不是 dict;记忆日志的 pending 记录
  在 propagate 内部由 store_decision 自动写(rating 由 parse_rating 从决策文本抽)。
- **机械/LLM 分工的落地**：LLM 只出 5 档评级+理由(store_decision 写记忆日志)；交易价位由
  `trade_levels.compute_trade_levels` 纯确定性算(ATR)，rating→long/short/flat。改 LLM 措辞不改价位。
- 中转站(OpenAI 兼容)接法:`llm_provider="deepseek"` + `backend_url` 指中转站 /v1 + 模型名对齐
  中转站实际列表(不同站命名不同,先打 /v1/models 查) + key 走 `DEEPSEEK_API_KEY`(.env)。
