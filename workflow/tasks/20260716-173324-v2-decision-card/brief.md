# Task Brief

## Goal
把 v2 建成「单一 BTC 的人工决策支持系统」:每日 BTC 决策卡 + 机械波段候选 + LLM 裁决 +
SQLite 账本事后结算,自证 LLM 过滤有无增量价值。**不接 freqtrade、不读交易所账户、不自动下单。**
定位与晋级条件以 `BTC-DESIGN-REVIEW.md` 路线表 v2 行(2026-07-16 修订)为准。

## Context(已知事实,避免重新踩坑)
- v0/v1 已完成:TradingAgents 骨架端到端跑通;情报层(RSS 新闻/F&G/衍生品 vendor +
  规则告警 + stdout/Telegram/飞书/邮件 sink)已交付。见项目记忆 `v0-status.md`/`v1-status.md`。
- 2026-07-16 加固提交(7ac0d97)后:LLM schema 已删除全部价位/仓位数字字段;取数失败白卷贯穿;
  as-of 前视防护在 ccxt/F&G/衍生品 vendor 各自实现;83 pytest 全绿。
- **已知缺陷(本任务第一批必修)**:`graph/trading_graph.py` 结算把 Sell 记为
  `strategy_return = -market_return`(做空口径),与"只做现货"冲突——现货空仓收益应为 0。
- intel 链路与 TradingAgents 图入口目前各自取数(两条平行链路),统一快照时要收敛而非重写
  现有 as-of 防护。
- 契约面见 `workflow/config.json` contract_touchpoints:interface.py 路由 / schemas.py /
  run.py 机械价位 / intel/。本任务会触碰全部四处,structural_checks 的不变式不得破坏。
- 核心原则(CLAUDE.md):机械规则出候选和交易价位,LLM 只裁决(接受/观察/否决);白卷文化;
  不让 LLM 报买卖数字。
- 项目 lessons:`workflow/context/lessons.md`;vendor 相关教训见项目记忆 `crypto-vendor-audit.md`;
  中转站模型 ID 用 `deepseek-v3.2`(`relay-model-ids.md`)。

## Scope
- agent(唯一组件,btc_agent/):
  1. **现货收益口径修正**:方向命中率与现货口径收益分开记录;Sell 在空仓语境收益 0、
     alpha = -bench_ret;持仓语境为减仓/退出。历史结算逻辑与反思/记忆闭环同步更新口径。
  2. **统一 EvidenceSnapshot**:行情+技术指标/新闻/F&G/资金费率/OI/数据健康状态,一份冻结的
     UTC as-of 快照,intel 与 trading graph 都从它取数(把现有 vendor as-of 取数收敛到快照层)。
     (设计门 G3 修订:本任务收敛三条机械取数路径——intel/trade_levels/决策卡;
     研判图 ToolNode 图内取数不改线,记 backlog v2.5,daily 把 snapshot_id 入账本。)
  3. **机械市场环境识别器**:趋势上涨/趋势下跌/震荡/高波动/数据不足 五分类,纯规则;
     高波动与数据不足 → 白卷。
  4. **每日 BTC 决策卡**:环境+证据完整度+机械观察+LLM 评级理由+候选(如有)+机械关注位,
     复用现有 push sink 推送;有候选时附机械入场参考/失效位/目标区域/有效期。
  5. **一种机械波段候选**(第一版只做一种,如震荡下沿)+ LLM 裁决接受/观察/否决,
     LLM 不得凭空创造交易、不得给数字、不得在数据缺失时硬给建议。
  6. **SQLite 结构化账本**:证据快照/候选事件/裁决/策略版本/机械价位/事后结算;
     **反事实归因**:被否决候选同口径机械结算,出 LLM 增量对比;
     **策略版本状态机**:候选规则参数版本化,改参数即新版本重新计数,前向数据按版本归因。
- shared contract:schemas.py(裁决输出)、interface.py(如加快照取数入口)、intel/(决策卡推送)、
  run.py(机械价位入口不变式保持)。

## Constraints
- LLM 只做裁决,一切数字机械算——这是不可协商的红线,schema 层不得回加价位/仓位字段。
- 现有 as-of 前视防护不得在快照重构中丢失(有单测保护的行为不得回归)。
- 白卷语义:环境=高波动/数据不足、或证据不完整时,决策卡明示白卷,不硬凑候选。
- 手动登记持仓为**可选**扩展(本地存储、不连交易所),不阻塞主线,可作为末位子任务或砍掉。
- 离线可测:所有新逻辑单测不依赖真实网络/LLM;真实端到端只做最终验收。

## Verification Plan
- 每子任务:`ruff check .` + `pytest` 全绿(btc_agent/,含新增单测),独立复验走 task-verify。
- 契约漂移检查(structural_checks)通过。
- 口径修正:单测断言 Sell 空仓结算收益=0 且方向命中独立记录;做空口径不再出现。
- 账本:单测覆盖 被否决候选也入库并被结算、改候选参数生成新版本、旧版本数据不被覆盖。
- 最终验收:真数据端到端跑一次,产出一张完整决策卡(白卷或有候选皆可)并推送成功,
  SQLite 中能查到当日快照与决策记录。

## Stop Conditions
- 需要接交易所私有 API/账户读写 → 停,超出 v2 范围。
- 发现必须让 LLM 输出数字才能实现某交付 → 停,回到设计层重新讨论。
- 统一快照重构导致现有 83 个单测大面积失效且原因不明 → 停,报告后再动。

## Notes
- 依据:任务评估报告(2026-07-16 对齐)+ `BTC-DESIGN-REVIEW.md` v2 修订段。
- 建议子任务顺序 = 开发顺序:口径修正 → EvidenceSnapshot → 环境识别 → 决策卡 →
  波段候选+LLM 裁决 → SQLite 账本+反事实+版本状态机。拆分在 plan/设计门后定稿。
- freqtrade 门槛(≥100 结算候选/≥6 个月/正增量)写在路线表,不属于本任务交付。

## Task
v2-decision-card


## Workflow
agent-change
