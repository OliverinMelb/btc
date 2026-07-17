# Task Plan(v2,按设计门第一轮三镜头发现修订)

## Selected Workflow
- agent-change(唯一组件 btc_agent/,检查矩阵:ruff + pytest + 契约漂移)

## 全局裁定(设计门第一轮决议,子任务不得偏离)

- **G1 编排入口定死**:顶层 `btc_agent/daily.py`(`python -m btc_agent.daily`)。
  依赖方向单向:daily → {intel, graph, evidence, regime, candidates, ledger}。
  **intel 包不得 import graph**(v1 情报层"不做决策"的层次不破)。daily 带显式扩展点:
  candidates 提供者与 ledger 记录器为可选注入(None 时跳过),ST5/ST6 对编排是加挂不是重写。
- **G2 结算数学独立成纯函数模块**:新增 `btc_agent/settlement_math.py`(模块级纯函数,
  不依赖 graph/llm)。`trading_graph._fetch_returns` 与 ST6 `settlement.py` 都调用它。
  **ledger/settlement 禁止 import graph 包**。
- **G3 快照收敛范围(spec AC 对应修订)**:ST2 统一三条机械取数路径
  (intel 仪表盘、trade_levels 的 OHLCV、决策卡/环境识别)到同一 EvidenceSnapshot;
  研判图 ToolNode 的图内取数**本任务不改线**(它已有各 vendor 的 as-of 防护,
  且与快照同参数 curr_date 调用同一 vendor),但 daily 编排把 snapshot_id 与
  frozen_at_utc 记入当日账本记录,图内取数一致性升级留待 v2.5(写入 backlog)。
  spec 的 AC 措辞随本决议同步修订。
- **G4 statistics source of truth**:前向统计只认 SQLite ledger;
  JSON records 与 markdown 记忆日志是运行痕迹,不进统计。
- **G5 strategy_versions schema 定稿**(ST3/ST5/ST6 共同引用):
  表 `strategy_versions(id INTEGER PK, rule_name TEXT, params_json TEXT,
  params_hash TEXT UNIQUE, status TEXT CHECK IN ('experimental','forward_validated',
  'validated') DEFAULT 'experimental', created_at_utc TEXT)`。
  `params_hash = sha256(canonical_json({regime_params, candidate_params, settlement_params}))`
  ——regime 参数、候选参数、结算口径参数**任一变更即新版本**;旧版本行及其结算数据只读。
  状态推进条件只写注释,本任务只实现 experimental 与按版本归因。
- **G6 候选结算三口径定死**(全部纳入 settlement_params 进版本 hash):
  (a) 触及判定:日内触及即算——long 候选 `day.Low <= 失效位` 即失效、
  `day.High >= 目标下沿` 即到达目标;
  (b) 触发日结算价:按被触及的价位本身结算(失效按失效位价、目标按目标下沿价),
  非当日收盘;
  (c) 同一日线双触(Low<=失效位 且 High>=目标):保守 tie-break,视为**失效先触发**;
  (d) 有效期到期(N 个 UTC 日)未触任何位:按到期日收盘结算。
- **G7 最终端到端验收由人工/主会话执行**(需 DEEPSEEK_API_KEY + 推送凭据,本机已配 env),
  **不派 implementer、不进 verify_subtask 矩阵**——避免撞 stop-rules 的凭据升级规则。
  子任务验证矩阵一律纯离线。

## Subtask Split(一次一个子任务一个 worktree)

依赖关系:ST1 ∥ ST2 可并行;ST3←ST2;ST4←{ST2,ST3};ST5←ST4;ST6←{ST1,ST4,ST5}。
ST7 收尾契约回填←全部。

### ST1 `spot-settlement`:现货收益口径修正
- 新增 `btc_agent/settlement_math.py`:纯函数
  `spot_settle(direction, market_return, bench_return) -> {strategy_return, alpha,
  direction_hit, settlement_basis: "spot"}`——
  long: strategy_return=market_return;short(现货空仓): strategy_return=0、
  alpha=-bench_return;flat: strategy_return=0、alpha=-bench_return。
  **direction_hit 定义**:long → market_return>0;short → market_return<0;
  market_return==0 → False;flat/hold → None(不入命中率分母)。
- `graph/trading_graph.py`:`_fetch_returns` 改调 `settlement_math`,
  删除 `-market_return` 做空路径;返回值透传 direction_hit/settlement_basis。
- `graph/reflection.py`:签名扩展,direction_hit 穿进反思入参
  (否则 spot 口径下 Sell 的 raw=0,反思无从判断方向对错)。
- `agents/utils/memory.py` **legacy 口径处理(不迁移数据,不破解析器)**:
  - pending 行格式**完全不动**(`endswith("| pending]")` 与 fields[3] 语义保持);
  - 仅已结算条目在 tag **尾部追加**可选字段 `| basis=spot | hit=<0/1>`,
    `_parse_entry` 按字段数容错(旧长度=legacy,新长度=spot);
  - `get_past_context`/反思注入渲染时,legacy 已结算条目标注 `(legacy short-basis)`,
    避免 LLM 混用两套不可比 alpha。
- 单测:spot_settle 三方向+0 边界;Sell 空仓 strategy_return==0 且 alpha==-bench_ret;
  direction_hit 独立;代码无 `-market_return` 路径;旧格式条目解析回归
  (pending 匹配、fields 下标、legacy 标注);`_resolve_pending_entries` 测试连 reflector
  一起 fake(现有 _FakeGraph 模式)。

### ST2 `evidence-snapshot`:统一证据快照(可与 ST1 并行)
- 新增 `btc_agent/evidence.py`:`build_evidence_snapshot(asset, curr_date) ->
  EvidenceSnapshot`(dataclass:ohlcv+指标、news、fear_greed、funding/OI、
  per-source health、snapshot_id、frozen_at_utc)。
  **只调用现有 vendor 函数,不重写取数**,as-of 语义原样保留;单源失败→health 记录降级。
- `intel/dashboard.py` 改为从快照装配(保留 errors/降级语义);
  `run.py`/后续 daily 的 trade_levels OHLCV 从快照读。
- 范围明确排除:graph ToolNode 图内取数不改线(G3)。
- 单测:同一快照 intel 与 trade_levels 路径读到同一 close/funding;单源失败不崩;
  既有 vendor as-of 单测全部保留通过。

### ST3 `regime-detector`:机械市场环境识别(依赖 ST2)
- 新增 `btc_agent/regime.py`:`detect_regime(snapshot) -> Regime`
  五分类 trend_up/trend_down/range/chaos/insufficient_data,纯规则
  (SMA 斜率/价格相对均线定趋势,ATR 百分位定 chaos,K 线不足/健康缺失定 insufficient)。
  规则参数集中为 `REGIME_PARAMS` dict——即 G5 hash 输入之一,改动即新策略版本。
- 单测:构造 OHLCV 覆盖五分支;chaos/insufficient → 白卷标志。

### ST4 `decision-card`:每日决策卡 + daily 编排(依赖 ST2/ST3)
- 新增 `btc_agent/decision_card.py`:`render(snapshot, regime, rating, candidates)`
  → brief 规定字段文本卡;数据不完整明示白卷;关注位 trade_levels 同源机械计算。
  **消息约束**:首行短句(作邮件主题);总长超 Telegram 4096 时按 section 截断
  (保环境/评级/候选,截理由长文),进单测。
- 新增 `btc_agent/daily.py` 编排(G1):快照→环境→(环境允许时)研判图评级→渲染→
  复用现有 push sink 推送;candidates/ledger 为可选注入扩展点;推送失败非零退出
  (沿用 v1 语义);**机械价位一律经由 trade_levels 既有路径**(不变式延伸到新入口)。
- 单测:daily 编排注入 fake graph + fake snapshot,**全离线不触网不调 LLM**
  (test_run_record.py 的 _FakeGraph 模式);各环境卡片字段齐全;白卷卡;
  推送失败退出码;长度截断;邮件主题行。

### ST5 `swing-candidate`:波段候选 + LLM 裁决(依赖 ST4)
- 新增 `btc_agent/candidates.py`:一种规则「震荡下沿做多」——仅 regime=range 且
  价格触及区间下沿带时产出候选;机械入场参考/失效位/目标区域 = trade_levels 同源计算;
  有效期 N 个 UTC 日(N 为 `CANDIDATE_PARAMS` 之一,进 G5 hash)。
- `agents/schemas.py` 新增 `CandidateVerdict`:字段仅
  `verdict: Literal["accept","observe","veto"]` + `reason: str`,
  **无任何数值类型字段**(可断言:schema 字段类型集合里无 int/float)。
  裁决 prompt 写白卷文化;解析沿用 rating.py 安全模式,歧义→observe。
- 接入 daily 的 candidates 注入点(加挂,不重写编排)。
- 单测:非 range 不产候选;数据缺失不产候选;CandidateVerdict 无数值字段断言;
  歧义降级 observe;既有三 schema 类不动(契约)。

### ST6 `sqlite-ledger`:账本 + 事件驱动结算 + 反事实 + 版本状态机(依赖 ST1/ST4/ST5)
- 新增 `btc_agent/ledger.py`:SQLite(`results_dir/ledger.sqlite3`)表:
  snapshots / candidates(含 position_context 预留) / verdicts / strategy_versions(G5) /
  trade_levels / settlements。
- 新增 `btc_agent/settlement.py`:**事件驱动结算器,新写**——按 G6 四口径逐日扫描
  到期/触位候选;**只复用 ST1 的口径契约(settlement_math 纯函数/字段),不 import graph**;
  被 veto/observe 的候选同口径照常结算;查询函数输出 accepted vs vetoed 结算对比(反事实)。
- 版本状态机:G5 schema;参数 hash 变更→新版本行(experimental),旧版本行及结算数据只读。
- 接入 daily 的 ledger 注入点:每日 快照/候选/裁决/价位 入库 + 到期结算。
- 单测:veto 候选入库且被结算;改参数→新版本、旧数据不动;反事实查询出对比;
  G6 四口径各一测(触失效/触目标/双触 tie-break/到期收盘);Sell 口径来自 settlement_math。

### ST7 `contract-backfill`:契约与文档回填(依赖全部,可与 task-close 合并执行)
- `workflow/config.json`:
  (a) surface_markers 增补 `evidence.py`、`candidates.py`、`ledger.py`、
  `settlement.py`、`decision_card.py`、`daily.py`;
  (b) structural_checks 增补:schemas.py must_contain `class CandidateVerdict`;
  daily.py must_contain `compute_trade_levels`(机械价位不变式延伸到活路径)与白卷关键字;
  ledger.py 版本只读不变式关键字;
  (c) env_consistency 增补 daily.py 的 `DEEPSEEK_API_KEY` 规则。
- 顺手修 `workflow/checks/verification.md` 里 `ai_helper_backend` 陈旧文案(指向本项目矩阵)。
- 验证:契约漂移检查全绿(新旧断言一起跑)。

## Execution Steps
1. ~~设计门~~(第一轮 fail 已修订本 plan;第二轮复审通过后拆包)。
2. 按依赖图逐个 task-assign(ST1 与 ST2 可并行开 worktree,其余串行)。
3. 每子任务完成 → task-verify 独立复验(ruff+pytest+契约漂移,**纯离线**)→ 合入 task 分支。
4. ST7 合入后:**人工/主会话**真数据端到端一次(G7):`python -m btc_agent.daily`,
   决策卡推送成功 + SQLite 可查当日快照与决策记录。
5. task-close:合回 master、summary、两层记忆分拣、V1-NEXT/设计文档回写、
   backlog 记入"图内 ToolNode 取数并入快照(v2.5)"。

## Verification Steps
1. 每子任务:btc_agent/ 内 `python -m ruff check .` + `python -m pytest` 全绿;
   structural_checks 契约漂移检查通过。
2. 任务级:全部合入后 pytest 全绿(≥既有 83 + 新增);G7 人工端到端。

## Stop Rules
- 需要接交易所私有 API / 账户读写 → 停(超出 v2)。
- 某交付必须让 LLM 输出数字才能实现 → 停,回设计层。
- ST2 快照重构导致既有单测大面积失败且原因不明 → 停,报告。
- 触碰 DEEPSEEK_API_KEY 读取方式或推送凭据存储方式 → 停(env_consistency 契约)。
- 子任务验证需要真实凭据 → 停(G7 保留给人工,implementer 不得索取凭据)。

## Open Questions 决议
- 决策卡与 v1 告警:同一次运行一次推送、卡内分 section(告警规则 rules.py 不动)。
- SQLite 位置:`results_dir/ledger.sqlite3`。
- 候选有效期与触位结算:见 G6。
- 图内 ToolNode 取数:本任务不改线,记 backlog(G3)。

## Worktree
- branch: task/v2-decision-card(task 分支;子任务各开 worktree 由 task-assign 管理)
- path: C:\Users\admin\Desktop\btc(主仓;子任务 worktree 形如 C:\Users\admin\Desktop\wt-<subtask>)

## Workflow Reference
(no per-class runbook in this project)
