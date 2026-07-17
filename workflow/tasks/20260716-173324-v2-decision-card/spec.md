# Task Spec

## Requirement
v2「决策卡+账本」:把现有 v0 研判图 + v1 情报层升级成单一 BTC 的**人工决策支持系统**——
每日一张决策卡推送、机械波段候选 + LLM 裁决、SQLite 账本事后结算与反事实归因。
不接 freqtrade、不读交易所账户、不自动下单。依据 `BTC-DESIGN-REVIEW.md` 路线表 v2 行
(2026-07-16 修订)与任务包 brief。

## Problem Statement
1. **结算口径错误(既有缺陷)**:`graph/trading_graph.py` 把 Sell 结算成
   `strategy_return = -market_return`(做空口径)。只做现货的系统里空仓收益应为 0,
   现口径会系统性高估 Sell 信号价值,污染后续所有前向统计。
2. **两条平行取数链路**:intel(`intel/dashboard.py`)与研判图(graph ToolNode 取数)
   各自调 vendor,同一天两边看到的数据可能不一致,无法保证"所有 agent 看同一份冻结证据"。
3. **没有环境分类**:只有单项告警规则,无"趋势涨/趋势跌/震荡/高波动/数据不足"的机械环境
   识别,"何时该看什么"没有纪律载体。
4. **没有候选机制**:系统每天只出一条评级记录,不存在"规则触发→LLM 裁决→跟踪结算"的
   波段候选闭环;LLM 增量价值(vs 机械全接受)无从统计。
5. **记录不可统计**:JSON 文件 + markdown 记忆日志撑不起按版本归因、反事实对比、
   100+ 候选的长期统计。

## Desired Outcome
每日运行一次(定时任务沿用 v1 部署方式)产出并推送一张 BTC 决策卡:
市场环境、证据完整度、机械观察、LLM 评级+理由、操作候选(如有,附机械入场/失效/目标/有效期)、
机械关注位。所有快照/候选/裁决/结算入 SQLite;被否决候选同口径结算;
候选规则版本化,改参数即新版本重新计数。跑数月后能用账本数据回答:
"LLM 过滤是否优于机械全接受"。

## Affected Surfaces
- backend(唯一组件 btc_agent/):
  - `graph/trading_graph.py`:结算口径修正(现货口径 + 方向命中分离)
  - `graph/reflection.py` / `agents/utils/memory.py`:反思/记忆使用新口径字段
  - 新增 `evidence.py`(或 `dataflows/snapshot.py`):EvidenceSnapshot 统一装配
  - `intel/dashboard.py`:改为消费 EvidenceSnapshot(保留降级语义)
  - 新增 `regime.py`:机械环境识别器
  - 新增 `candidates.py`:波段候选引擎(v2 第一版仅一种)+ 规则版本
  - 新增 `ledger.py`(SQLite)+ `settlement.py`(机械结算器,含反事实)
  - 新增 `decision_card.py` + intel push 集成:决策卡渲染与推送
  - `run.py` / `intel/run_intel.py` 或新入口:每日流程编排
- frontend: 无(推送文本卡片)
- contract(`workflow/config.json` structural_checks 覆盖面,不变式必须保持):
  - `dataflows/interface.py`:ccxt/cryptorss 注册与 DISABLED_METHODS 不动
  - `agents/schemas.py`:ResearchPlan/TraderProposal/PortfolioDecision 保留;
    新增裁决 schema(verdict: accept/observe/veto + 理由,无任何数字字段)
  - `run.py`:`compute_trade_levels` 与 "mechanical (ATR-based), not LLM" 字样保留
  - `intel/rules.py`:`def evaluate` 保留
- docs/workflow:任务包留痕;完成后回写 V1-NEXT/项目记忆(task-close 时)

## Acceptance Criteria
- [ ] 结算口径:单测断言 (a) Sell 空仓语境 `strategy_return == 0` 且
      `alpha == -bench_ret`;(b) 方向命中率(direction_hit)独立于收益记录;
      (c) 代码中不再存在 `-market_return` 做空口径路径。
- [ ] EvidenceSnapshot:单一函数产出冻结快照(行情+指标/新闻/F&G/资金费率/OI/
      per-source 健康状态);**三条机械取数路径**(intel 仪表盘、trade_levels 的 OHLCV、
      决策卡/环境识别)均出自同一快照对象;单测断言同一快照两处读到的 close/资金费率一致;
      既有 as-of 前视防护单测全部保留并通过。
      (设计门决议 G3:研判图 ToolNode 图内取数本任务不改线——已有 as-of 防护且与快照
      同参数调同一 vendor;daily 把 snapshot_id 记入账本;ToolNode 并入快照记 backlog v2.5。)
- [ ] 环境识别:纯规则五分类(trend_up/trend_down/range/chaos/insufficient_data),
      离线单测用构造 OHLCV 覆盖五个分支;chaos/insufficient_data 时下游强制白卷。
- [ ] 决策卡:给定快照+环境+评级+候选(或无),渲染出 brief 规定字段的卡片文本;
      通过现有 push sink 推送;证据不完整时卡片明示"数据不完整/白卷"。
- [ ] 波段候选:恰好一种规则(震荡下沿做多),仅在环境=range 且规则条件满足时产出;
      候选携带机械入场参考/失效位/目标区域/有效期(全部来自 trade_levels 或同类机械计算);
      LLM 裁决输出限 accept/observe/veto+定性理由(可断言形式:CandidateVerdict schema
      **无任何数值类型字段**,单测检查字段类型集合);
      数据缺失时不产出候选(白卷),单测覆盖。
- [ ] SQLite 账本:表覆盖 快照/候选/裁决/策略版本/机械价位/结算;被 veto 的候选照常入库
      并到期同口径机械结算;查询能输出"accepted vs vetoed 候选的结算对比"(反事实);
      候选规则参数变更产生新 strategy_version 行,旧版本数据不被覆盖或重算;单测覆盖以上各条。
- [ ] 全量检查:`ruff check .` 通过;pytest 全绿(含既有 83 个);
      `workflow/config.json` structural_checks 契约漂移检查通过。
- [ ] 端到端(最终验收,允许真实网络/LLM):跑一次日度流程,产出决策卡推送成功,
      SQLite 可查到当日快照与决策记录。

## Non-Goals
- freqtrade 接入、dry-run、任何下单/账户读写。
- 多币种支持(只做 BTC)。
- 第二种及以上候选规则(趋势突破/回踩留给后续版本)。
- 手动登记持仓(可选项,明确移出本任务;账本 schema 预留 position_context 字段即可)。
- 情报层告警规则重写(现有 rules.py 告警继续工作,决策卡是新增产物)。
- Web UI / 可视化(推送文本卡片即可)。

## Risks
- **快照重构回归风险**:as-of 防护散在三个 vendor 里,收敛到快照层时可能丢语义。
  缓解:快照层只做"调用现有 vendor + 冻结结果",不重写取数;既有单测全保留。
- **结算口径迁移**:已有 pending 记录按旧口径写入,新结算器要能识别或一次性标注旧记录。
  缓解:账本从零开始,markdown 记忆日志旧记录标注口径版本即可,不做数据迁移。
- **LLM 裁决 prompt 漂移**:裁决点是新 prompt,可能重现"动辄 Hold/硬凑"问题。
  缓解:白卷文化写进裁决 prompt;解析沿用 rating.py 的安全解析模式(歧义→observe)。
- **范围膨胀**:六个交付项,子任务边界若切不干净会互相阻塞。
  缓解:严格按依赖序拆分,每个子任务独立可验;账本 schema 在 plan 阶段先定稿。

## Open Questions
- 决策卡与 v1 告警是否合并成一次推送?(倾向:同一 intel 入口两个 section,一次推送;
  设计门确认)
- SQLite 文件位置与命名(倾向:`results_dir/ledger.sqlite3`,与 records/ 同级)。
- 候选有效期的机械定义(倾向:N 个 UTC 日或触及失效位,取先到者;N 由规则版本参数定)。

## Task
v2-decision-card
