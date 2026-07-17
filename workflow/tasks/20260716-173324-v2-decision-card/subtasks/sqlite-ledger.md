# Subtask Spec

## Parent Task
20260716-173324-v2-decision-card

## Subtask Title
sqlite-ledger — SQLite 账本 + 事件驱动结算 + 反事实 + 版本状态机

## Owner Role
- agent-change(btc_agent/,Python src 布局)

## Goal
v2 的统计根基:SQLite 账本记录 快照/候选/裁决/策略版本/机械价位/结算;
事件驱动结算器按 G6 四口径机械结算到期/触位候选(**被 veto/observe 的候选照常入库
照常结算**——反事实归因);策略版本状态机(参数 hash 变更→新版本,旧数据只读)。
前向统计只认本账本(G4)。

## Scope
- 允许触碰:
  - 新增 `btc_agent/src/btc_agent/ledger.py`
  - 新增 `btc_agent/src/btc_agent/settlement.py`
  - `btc_agent/src/btc_agent/daily.py`(仅接线:默认 ledger_recorder 装配 + 每日运行时
    顺带触发到期结算;编排结构不重写)
  - `btc_agent/tests/` 新增/扩展单测
- 禁止触碰:intel/、run.py、agents/schemas.py、dataflows/、graph/(**尤其禁止
  import graph 包**——G2 硬约束)、evidence.py、regime.py、candidates.py、
  decision_card.py、settlement_math.py(只 import 不改)

## Dependencies
- depends-on: [spot-settlement, decision-card, swing-candidate]  # task 分支已含 ST1-ST5
- provides-to: [contract-backfill]

## Inputs
- parent plan(**必读 G2/G4/G5/G6 与 ST6 条目**):workflow/tasks/20260716-173324-v2-decision-card/plan.md
- 口径契约:`btc_agent/src/btc_agent/settlement_math.py`(ST1,纯函数
  spot_settle + direction_hit 定义)——**只复用口径契约,结算器新写事件驱动逻辑**
- 版本参数源:`regime.REGIME_PARAMS` + `candidates.CANDIDATE_PARAMS`(其中已含
  G6 结算口径参数 touch_basis/settle_price/tie_break)
- ST5 reviewer 备注 A(顺手补):daily 显式传 candidate_provider=None 跳过路径
  缺专门单测,补一行。

## 实现要点(plan ST6 + G5/G6 裁定)

1. `ledger.py`(stdlib sqlite3,零新依赖;文件 `results_dir/ledger.sqlite3`):
   - 表(G5 定稿):
     - `strategy_versions(id INTEGER PRIMARY KEY, rule_name TEXT, params_json TEXT,
       params_hash TEXT UNIQUE, status TEXT CHECK(status IN ('experimental',
       'forward_validated','validated')) DEFAULT 'experimental', created_at_utc TEXT)`
       -- params_hash = sha256(canonical_json({regime_params, candidate_params,
       settlement_params}));状态推进条件写注释,本任务只用 experimental
     - `snapshots(snapshot_id TEXT PRIMARY KEY, asset TEXT, trade_date TEXT,
       frozen_at_utc TEXT, health_json TEXT, regime TEXT, blank_sheet INTEGER,
       observations_json TEXT)`
     - `candidates(id INTEGER PK, snapshot_id, strategy_version_id, candidate_type,
       entry_ref REAL, invalidation REAL, target_zone_json, expires_utc,
       position_context TEXT DEFAULT NULL, created_at_utc)` -- position_context 预留
     - `verdicts(id INTEGER PK, candidate_id, verdict TEXT, reason TEXT, created_at_utc)`
     - `trade_levels(id INTEGER PK, snapshot_id, rating TEXT, direction TEXT,
       entry REAL, stop REAL, target REAL, atr REAL)` -- 每日评级的机械价位
     - `settlements(id INTEGER PK, candidate_id UNIQUE, settled_at_utc, outcome TEXT,
       settle_price REAL, market_return REAL, strategy_return REAL, alpha REAL,
       direction_hit INTEGER, settlement_basis TEXT, detail_json TEXT)`
   - `get_or_create_strategy_version(...)`:hash 已存在→返回现有 id;新 hash→插新行。
     **旧版本行与其结算数据只读**:不提供 update/delete API,单测断言改参数后旧行原样。
   - `record_daily(...)`:daily 一次运行的 快照/候选/裁决/价位 一并入库(幂等:同
     snapshot_id 重跑不重复插候选)。
2. `settlement.py`(**新写事件驱动结算器,不 import graph**):
   - `settle_due_candidates(conn, ohlcv_provider, as_of_utc)`:扫描未结算候选,
     对每个候选取其创建日→as_of 的日线(ohlcv_provider 注入,默认包一层
     ccxt_vendor._ohlcv_dataframe;测试注入构造 DataFrame):
     - G6(a) 日内触及即算:long 候选 day.Low <= invalidation → 失效;
       day.High >= target 下沿 → 到达目标
     - G6(b) 触发日按被触及价位结算(失效按 invalidation 价,目标按 target 下沿价)
     - G6(c) 同日双触 → 保守 tie-break:失效先触发
     - G6(d) 有效期到期未触 → 按到期日收盘结算
     - 收益字段用 settlement_math 的口径契约(strategy_return/alpha/direction_hit/
       settlement_basis="spot";候选是 long,direction_hit 沿用 market_return>0 定义,
       此处 market_return = (settle_price-entry_ref)/entry_ref)
     - **veto/observe 候选同口径照常结算**(outcome 照记,统计侧区分)
   - `counterfactual_report(conn)`:查询输出 accepted vs vetoed/observed 的结算对比
     (数量、均值 strategy_return、命中率),这是"LLM 增量价值"的证据查询。
3. daily 接线:默认 ledger_recorder 写库(config 可关);每日运行顺带
   settle_due_candidates。库文件缺目录自动建。

## Acceptance Criteria
- [ ] 单测:veto 候选入库且到期被结算(反事实);counterfactual_report 输出
      accepted vs vetoed 对比行。
- [ ] 单测:改 CANDIDATE_PARAMS(拷贝改值)→ 新 strategy_version 行生成,
      旧版本行与其 settlements 原样(只读断言)。
- [ ] 单测:G6 四口径各至少一例——日内触失效/日内触目标/同日双触判失效先/
      到期收盘结算;结算价与口径一致。
- [ ] 单测:direction_hit/strategy_return/alpha 字段与 settlement_math.spot_settle
      口径一致(long 候选)。
- [ ] 单测:record_daily 幂等(同 snapshot_id 重跑不重复插入)。
- [ ] 单测:daily 全流程(fake 一切)落库——snapshots/candidates/verdicts/
      trade_levels 各有行;显式 candidate_provider=None 跳过候选(ST5 备注 A)。
- [ ] ledger.py/settlement.py 不 import graph(grep/单测断言)。
- [ ] btc_agent/ 内 ruff + pytest 全绿(既有 163 + 新增)。

## Verification
- maker checks: ruff + pytest(离线,sqlite 用 tmp_path)
- checker gates: 契约漂移检查;AC 逐条复核
- independent re-verify: `workflow/scripts/verify_subtask.ps1`

## Stop Conditions
- 发现必须 import graph 才能结算 → 停(G2 硬约束,设计已保证不需要)。
- 发现口径无法与 settlement_math 契约对齐 → 停,报告。
- 任何路径需要真实网络 → 停(ohlcv_provider 注入构造数据)。

## Recommended Workflow
agent-change
