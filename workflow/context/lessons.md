# 项目工程教训（BTC Agent）

> 任务闭环时(task-close)按分拣规则追加：只放"换一个子任务仍成立、且非代码本身能记录"的教训。
> 全局层教训进 `~/.claude/workflow-memory/lessons.md`，本文件只放本项目特有的。

<!-- 闭环时在此追加，最新在上 -->

## v2（决策卡+账本）2026-07-17

- **"加固"提交也会引入语义 bug——收益口径这类统计根基改动必须过设计评审。** 7ac0d97 把
  Sell 结算写成 `-market_return`(做空口径),与"只做现货"冲突,若不修会污染此后全部前向
  统计。教训:凡改结算/口径,连同**读取侧**(反思 prompt、记忆渲染、历史条目兼容)一起改,
  并给旧数据留 legacy 标注而非静默混用。
- **memory.md 的 tag 是固定位置字段解析**(`fields[3]=="pending"`、`endswith("| pending]")`),
  扩展只能"尾部追加+按字段数容错",动前缀/中间字段必砸旧解析。
- **link3.top 双模型部署可用**:deep=deepseek-v4-pro-202606、quick=deepseek-v4-flash-202605
  (均 thinking 型,vendored client 的 `^deepseek-v\d` capabilities 模式已覆盖:抑制
  tool_choice + reasoning_content 回传)。配置走 btc_agent/.env 的 TRADINGAGENTS_DEEP/
  QUICK_THINK_LLM,.env 需 cwd 在 btc_agent/ 下才会被 find_dotenv 找到。
- **候选结算的 alpha 恒 0**(bench=market 设计):候选组统计只用 strategy_return 与
  hit_rate,不用 alpha(settlement.py docstring 有注)。
- **G3 遗留**:研判图 ToolNode 图内取数仍独立于 EvidenceSnapshot(各自 as-of 防护,
  同参数同 vendor),并入快照记 backlog v2.5。


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
