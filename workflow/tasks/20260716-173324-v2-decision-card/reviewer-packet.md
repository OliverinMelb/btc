# Reviewer Packet

## Parent Task
20260716-173324-v2-decision-card

## Requirement Summary
# Task Brief

## Goal
�?v2 建成「单一 BTC 的人工决策支持系统�?每日 BTC 决策�?+ 机械波段候�?+ LLM 裁决 +
SQLite 账本事后结算,自证 LLM 过滤有无增量价值�?*不接 freqtrade、不读交易所账户、不自动下单�?*
定位与晋级条件以 `BTC-DESIGN-REVIEW.md` 路线�?v2 �?2026-07-16 修订)为准�?
## Context(已知事实,避免重新踩坑)
- v0/v1 已完�?TradingAgents 骨架端到端跑�?情报�?RSS 新闻/F&G/衍生�?vendor +
  规则告警 + stdout/Telegram/飞书/邮件 sink)已交付。见项目记忆 `v0-status.md`/`v1-status.md`�?- 2026-07-16 加固提交(7ac0d97)�?LLM schema 已删除全部价�?仓位数字字段;取数失败白卷贯穿;
  as-of 前视防护�?ccxt/F&G/衍生�?vendor 各自实现;83 pytest 全绿�?- **已知缺陷(本任务第一批必�?**:`graph/trading_graph.py` 结算�?Sell 记为
  `strategy_return = -market_return`(做空口径),�?只做现货"冲突——现货空仓收益应�?0�?- intel 链路�?TradingAgents 图入口目前各自取�?两条平行链路),统一快照时要收敛而非重写
  现有 as-of 防护�?- 契约面见 `workflow/config.json` contract_touchpoints:interface.py 路由 / schemas.py /
  run.py 机械价位 / intel/。本任务会触碰全部四�?structural_checks 的不变式不得破坏�?- 核心原则(CLAUDE.md):机械规则出候选和交易价位,LLM 只裁�?接受/观察/否决);白卷文化;
  不让 LLM 报买卖数字�?- 项目 lessons:`workflow/context/lessons.md`;vendor 相关教训见项目记�?`crypto-vendor-audit.md`;
  中转站模�?ID �?`deepseek-v3.2`(`relay-model-ids.md`)�?
## Scope
- agent(唯一组件,btc_agent/):
  1. **现货收益口径修正**:方向命中率与现货口径收益分开记录;Sell 在空仓语境收�?0�?     alpha = -bench_ret;持仓语境为减�?退出。历史结算逻辑与反�?记忆闭环同步更新口径�?  2. **统一 EvidenceSnapshot**:行情+技术指�?新闻/F&G/资金费率/OI/数据健康状�?一份冻结的
     UTC as-of 快照,intel �?trading graph 都从它取�?把现�?vendor as-of 取数收敛到快照层)�?     (设计�?G3 修订:本任务收敛三条机械取数路径——intel/trade_levels/决策�?
     研判�?ToolNode 图内取数不改�?�?backlog v2.5,daily �?snapshot_id 入账本�?
  3. **机械市场环境识别�?*:趋势上涨/趋势下跌/震荡/高波�?数据不足 五分�?纯规�?
     高波动与数据不足 �?白卷�?  4. **每日 BTC 决策�?*:环境+证据完整�?机械观察+LLM 评级理由+候�?如有)+机械关注�?
     复用现有 push sink 推�?有候选时附机械入场参�?失效�?目标区域/有效期�?  5. **一种机械波段候�?*(第一版只做一�?如震荡下�?+ LLM 裁决接受/观察/否决,
     LLM 不得凭空创造交易、不得给数字、不得在数据缺失时硬给建议�?  6. **SQLite 结构化账�?*:证据快照/候选事�?裁决/策略版本/机械价位/事后结算;
     **反事实归�?*:被否决候选同口径机械结算,�?LLM 增量对比;
     **策略版本状态机**:候选规则参数版本化,改参数即新版本重新计�?前向数据按版本归因�?- shared contract:schemas.py(裁决输出)、interface.py(如加快照取数入口)、intel/(决策卡推�?�?  run.py(机械价位入口不变式保�?�?
## Constraints
- LLM 只做裁决,一切数字机械算——这是不可协商的红线,schema 层不得回加价�?仓位字段�?- 现有 as-of 前视防护不得在快照重构中丢失(有单测保护的行为不得回归)�?- 白卷语义:环境=高波�?数据不足、或证据不完整时,决策卡明示白�?不硬凑候选�?- 手动登记持仓�?*可�?*扩展(本地存储、不连交易所),不阻塞主�?可作为末位子任务或砍掉�?- 离线可测:所有新逻辑单测不依赖真实网�?LLM;真实端到端只做最终验收�?
## Verification Plan
- 每子任务:`ruff check .` + `pytest` 全绿(btc_agent/,含新增单�?,独立复验�?task-verify�?- 契约漂移检�?structural_checks)通过�?- 口径修正:单测断言 Sell 空仓结算收益=0 且方向命中独立记�?做空口径不再出现�?- 账本:单测覆盖 被否决候选也入库并被结算、改候选参数生成新版本、旧版本数据不被覆盖�?- 最终验�?真数据端到端跑一�?产出一张完整决策卡(白卷或有候选皆�?并推送成�?
  SQLite 中能查到当日快照与决策记录�?
## Stop Conditions
- 需要接交易所私有 API/账户读写 �?�?超出 v2 范围�?- 发现必须�?LLM 输出数字才能实现某交�?�?�?回到设计层重新讨论�?- 统一快照重构导致现有 83 个单测大面积失效且原因不�?�?�?报告后再动�?
## Notes
- 依据:任务评估报告(2026-07-16 对齐)+ `BTC-DESIGN-REVIEW.md` v2 修订段�?- 建议子任务顺�?= 开发顺�?口径修正 �?EvidenceSnapshot �?环境识别 �?决策�?�?  波段候�?LLM 裁决 �?SQLite 账本+反事�?版本状态机。拆分在 plan/设计门后定稿�?- freqtrade 门槛(�?00 结算候�?�? 个月/正增�?写在路线�?不属于本任务交付�?
## Task
v2-decision-card


## Workflow
agent-change

## Acceptance Criteria
- [ ]
- [ ]
- [ ]

## Subtasks
- name: spot-settlement
- worktree: C:\Users\admin\Desktop\wt-spot-settlement
- branch: subtask/spot-settlement
- summary: C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\subtask-summaries\spot-settlement.md
- name: evidence-snapshot
- worktree: C:\Users\admin\Desktop\wt-evidence-snapshot
- branch: subtask/evidence-snapshot
- summary: C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\subtask-summaries\evidence-snapshot.md

## Changed Files By Subtask
- spot-settlement: no unstaged diff detected from worktree HEAD
- evidence-snapshot: no unstaged diff detected from worktree HEAD

## Checker Results
- spot-settlement: - status: pass
- evidence-snapshot: - status: pass
- report: C:\Users\admin\Desktop\btc\workflow\reports\contract-drift-20260716-180438.md

## Reviewer Decision
- pass | fail | needs follow-up
- review lane used: fast | full (see workflow/checks/stop-rules.md)

## Risks

## Follow-up Requests

