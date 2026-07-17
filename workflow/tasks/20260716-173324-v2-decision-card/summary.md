# Task Summary — v2-decision-card(2026-07-16 → 2026-07-17)

## 交付了什么

v2「决策卡+账本」:BTC 人工决策支持系统,7 个子任务全部完成并合回 master。

1. **ST1 spot-settlement**:`settlement_math.py` 纯函数(现货口径:Sell 空仓收益 0、
   alpha=-bench;direction_hit 与收益分离;flat 不入命中率分母);修掉
   trading_graph 的 `-market_return` 做空口径;reflection 穿透 direction_hit;
   memory 旧记录 legacy 兼容(pending 格式不动、tag 尾部追加、渲染标注)。
2. **ST2 evidence-snapshot**:`evidence.py` 统一证据快照(OHLCV/新闻/F&G/衍生品 +
   per-source health),intel 仪表盘与 trade_levels"取一次处处用"(vendor 调用计数=1
   有断言);graph ToolNode 取数按 G3 裁定不改线,记 backlog v2.5。
3. **ST3 regime-detector**:`regime.py` 纯规则五分类(trend_up/trend_down/range/
   chaos/insufficient_data),chaos+数据不足→白卷;REGIME_PARAMS 集中可序列化。
4. **ST4 decision-card**:`decision_card.py` + `daily.py`(`python -m btc_agent.daily`):
   白卷不建图、4096 截断、首行邮件主题、LLM 数字防泄漏进价位字段(有单测)、
   candidates/ledger 注入式扩展点、推送不完整非零退出。
5. **ST5 swing-candidate**:`candidates.py` 震荡下沿做多候选(纯机械价位)+
   `CandidateVerdict`(accept/observe/veto+定性理由,零数值字段)+ 白卷文化裁决
   prompt + 歧义降级 observe。
6. **ST6 sqlite-ledger**:`ledger.py`(6 表,G5 schema,版本行只读)+
   `settlement.py`(事件驱动结算,G6 四口径;veto/observe 照常结算=反事实;
   counterfactual_report 输出 accepted vs vetoed 对比)。
7. **ST7 contract-backfill**:config.json +8 surface_markers/+10 structural_checks
   断言(做过破坏→FAIL→恢复→PASS 验牙)/+1 env 规则;ST6 reviewer F1/F2/F3 清理;
   verification.md 陈旧文案修正。

## 验证证据

- 每子任务独立复验(orchestrator 重跑,非自查):
  `subtask-summaries/*.verify.md` 共 7 份,全 PASS。
- full lane reviewer:ST2/ST5/ST6(契约面或统计根基),verdict 均 PASS,
  记录在各子任务往来(ST6 的 3 条非阻断 follow-up 已由 ST7 清理)。
- 设计门:`design-review.md`——第一轮三镜头 FAIL(14 条必改),plan v2 修订后
  第二轮 PASS。
- 合并 master 后:pytest 183 passed、ruff 全过、契约漂移检查 OK。
- **G7 真数据端到端(2026-07-17,人工/主会话)**:link3.top 双模型
  (deep=deepseek-v4-pro-202606,quick=deepseek-v4-flash-202605)真跑
  `python -m btc_agent.daily --asset BTC`:399 真 K 线、F&G=27、资金费率/OI 取到;
  环境=trend_up;辩论后评级 Hold;趋势环境不产候选(符合规则);卡片 stdout 推送;
  账本落库(snapshot BTC-2026-07-17-eca1694d、strategy_version v1 experimental、
  trade_levels Hold/flat)。email sink 因缺 SMTP 凭据跳过并如实报"未完整送达"
  ——部署侧待办,非代码缺陷。

## 遗留 follow-ups

- **部署侧**:配 SMTP(或飞书)凭据进 btc_agent/.env,挂 Windows 计划任务每日跑
  `python -m btc_agent.daily`,监控非零退出码。(v1 的"稳定推送"晋级条件同此)
- **backlog v2.5**:graph ToolNode 图内取数并入 EvidenceSnapshot(G3 裁定遗留)。
- **观察项**:LLM 辩论输出为英文(output_language 配置未强制到所有 prompt),
  不影响机制,后续 prompt 打磨时统一。
- **统计口径备忘**:候选结算的 alpha 字段恒 0(bench=market 设计),候选组统计
  只用 strategy_return/hit_rate(settlement.py docstring 已注明)。
- 版本状态机推进条件(experimental→forward_validated→validated)本任务只写注释,
  推进逻辑等前向数据积累后实现。

## 关键决策存档

- 设计门 G1-G7 全局裁定见 plan.md;v2 定位修订见 BTC-DESIGN-REVIEW.md
  路线表(2026-07-16 修订段)。
- freqtrade 门槛:≥100 结算候选、≥6 个月前向、反事实证明 LLM 过滤优于机械全接受、
  扣成本正增量。
