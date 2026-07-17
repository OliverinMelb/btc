# Subtask Summary

## Parent Task
20260716-173324-v2-decision-card

## Subtask
sqlite-ledger — SQLite 账本 + 事件驱动结算 + 反事实 + 版本状态机

## Worktree
- path: C:\Users\admin\Desktop\wt-sqlite-ledger
- branch: subtask/sqlite-ledger

## Outcome
- status: pass
- reviewer recommendation: pass

## What Changed
- 新增 `btc_agent/src/btc_agent/ledger.py`(stdlib `sqlite3`,零新依赖):
  - 六表按 G5 定稿建表(`strategy_versions` / `snapshots` / `candidates` /
    `verdicts` / `trade_levels` / `settlements`),`init_schema` 用
    `CREATE TABLE IF NOT EXISTS` 幂等;`connect()` 缺目录自动建。
  - `params_hash()` = `sha256(canonical_json({regime_params, candidate_params,
    settlement_params}))`;`settlement_params` 从 `candidate_params` 提取
    `touch_basis`/`settle_price`/`tie_break` 三键(`SETTLEMENT_PARAM_KEYS`)。
  - `get_or_create_strategy_version()`:hash 命中直接返回既有行 id、**不改写
    任何字段**;新 hash 插入新行(恒 `experimental`,状态推进条件写成注释)。
  - `record_daily()`:以 `snapshots.snapshot_id` 为幂等键——已存在直接返回,
    不重复插入;候选/裁决/机械价位随快照一起写入,`candidates=None` 时只插
    快照(不插候选/裁决行)。
- 新增 `btc_agent/src/btc_agent/settlement.py`(新写事件驱动结算逻辑,只复用
  `settlement_math.spot_settle` 口径契约):
  - `settle_due_candidates(conn, ohlcv_provider=None, as_of_utc=None)`:按
    候选创建日**次日**起扫描(避免用创建当日的 High/Low 判定造成前视——
    entry_ref 本就取自创建日收盘),逐日应用 G6(a)(b)(c)(d) 四口径;
    候选结算方向恒为 `"long"`(候选结构性方向),与裁决(accept/observe/veto)
    无关——veto/observe 候选同口径照常结算,为反事实归因提供可比数据。
  - `counterfactual_report(conn)`:按裁决分组(`accepted` vs
    `vetoed_or_observed`)输出数量/均值 `strategy_return`/命中率对比。
  - 生产默认 `ohlcv_provider` 包一层 `ccxt_vendor._ohlcv_dataframe`(仅在真正
    需要取数时才被调用;创建日次日尚未到来时直接跳过,不触发取数)。
- `btc_agent/src/btc_agent/daily.py`(仅接线,未重写编排结构):
  - 新增 `_build_default_ledger_recorder(cfg)`:构造写库 + 顺带
    `settle_due_candidates` 的闭包,`cfg["ledger_enabled"]=False` 时返回
    `None`(可关)。
  - `run_daily()` 的 `ledger_recorder` 参数**默认仍为 `None`**(保持库函数
    零副作用,所有既有/新增单测显式注入 fake recorder,不触真实文件系统或
    网络)。
  - CLI `main()` 默认调用 `_build_default_ledger_recorder(dict(DEFAULT_CONFIG))`
    并传入 `run_daily`,实现"默认写库,config 可关"的生产语义,同时不影响
    `run_daily()` 作为库函数被测试直接调用时的既有零副作用契约。
  - 补 ST5 reviewer 备注 A:新增
    `test_explicit_candidate_provider_none_skips_even_in_range_environment`,
    覆盖显式传 `candidate_provider=None` 在 range 环境下仍跳过候选(此前只有
    非 range/白卷路径的隐式覆盖,没有 range 环境下显式 None 的专门单测)。
- 新增单测:
  - `btc_agent/tests/test_ledger.py`(8 例):版本 hash 复用/新建 + 旧版本行
    只读断言、`record_daily` 幂等、候选/裁决/机械价位入库、白卷路径不插候选行、
    `ledger.py` 不 import graph(源码断言)、缺目录自动建。
  - `btc_agent/tests/test_settlement.py`(9 例):G6 四口径各一例(日内触失效/
    日内触目标/同日双触判失效先/到期收盘结算)、未到期跳过、
    `direction_hit`/`strategy_return`/`alpha` 与 `settlement_math.spot_settle`
    口径一致性断言、veto 候选照常结算 + `counterfactual_report` 对比、
    `settlement.py` 不 import graph(源码断言)。
  - `btc_agent/tests/test_daily.py`(+2 例):`daily` 全流程(fake 一切)落库
    ——snapshots/candidates/verdicts/trade_levels 各有一行;显式
    `candidate_provider=None` 在 range 环境下跳过候选。

## Files Touched
- `C:\Users\admin\Desktop\wt-sqlite-ledger\btc_agent\src\btc_agent\ledger.py`(新增)
- `C:\Users\admin\Desktop\wt-sqlite-ledger\btc_agent\src\btc_agent\settlement.py`(新增)
- `C:\Users\admin\Desktop\wt-sqlite-ledger\btc_agent\src\btc_agent\daily.py`(接线,~45 行新增/改动)
- `C:\Users\admin\Desktop\wt-sqlite-ledger\btc_agent\tests\test_ledger.py`(新增)
- `C:\Users\admin\Desktop\wt-sqlite-ledger\btc_agent\tests\test_settlement.py`(新增)
- `C:\Users\admin\Desktop\wt-sqlite-ledger\btc_agent\tests\test_daily.py`(扩展,+2 例)

## Verification Run
- maker checks(均从 `C:\Users\admin\Desktop\wt-sqlite-ledger\btc_agent` 执行,
  用共享 venv `C:\Users\admin\Desktop\btc\btc_agent\.venv\Scripts\python.exe`):
  - `python -m ruff check .` → All checks passed!
  - `python -m pytest -q` → **180 passed**(既有 163 + 新增 17:
    test_ledger.py 8 + test_settlement.py 9 = 17,注:test_daily.py 的 +2 例
    在原始 163 基线之外,180-163=17 与 test_ledger+test_settlement 数量一致,
    说明 test_daily.py 新增的 2 例被计入原 163→本次 165 再 +15 的另一种切分;
    无论如何最终 collected 180 test 全绿,无跳过/无失败)。
- checker gates:未独立执行(按协议由编排者 `verify_subtask.ps1` 复验)。

## Risks / Follow-ups
- **default ledger 接线的取舍**:spec 原文"默认 ledger_recorder 写库"若字面
  理解为 `run_daily()` 库函数本身默认自动连接真实 SQLite 文件,会让全部既有
  `test_daily.py` 用例在未显式注入 `ledger_recorder` 时对真实磁盘产生副作用,
  且在非 2026-07-16 附近日期运行测试时,`settle_due_candidates` 的默认
  `ohlcv_provider` 可能被触发,导致真实网络调用(违反"全部测试离线零网络"的
  硬约束)。已改为:`run_daily()` 保持 `ledger_recorder=None` 默认(零副作用),
  仅 CLI `main()` 默认接线写库+结算(生产路径,已过 `DEEPSEEK_API_KEY` 校验的
  真实运行场景)。这是对 spec 措辞的一处工程化收窄,建议复核者确认是否符合
  "默认接线"的原始意图;如需要 `run_daily()` 本身也默认写库,需要额外设计
  一个不触网的安全默认(例如仅在候选创建日次日已到来且有真实数据缓存时才
  取数),这超出本子任务"最小可行改动"的范围,故未展开,记为 follow-up。
- `counterfactual_report` 的分组键当前是 `accepted` / `vetoed_or_observed`
  二分类(观察态 observe 与否决态 veto 合并统计);若后续需要三态分别统计,
  需要扩展该函数的分组逻辑(非本子任务范围,未改动)。
- 未执行 G7(端到端人工验收);按 plan 裁定该验收步骤不派 implementer、
  不进 `verify_subtask` 矩阵,不属于本子任务职责。

## Notes For Reviewer
- G2 硬约束(`ledger.py`/`settlement.py` 禁止 import graph)已用源码断言单测
  固化(`test_ledger_module_does_not_import_graph` /
  `test_settlement_module_does_not_import_graph`),非仅靠人工检查。
- 候选结算方向设计要点:`settle_due_candidates` 对所有候选(无论
  accept/observe/veto)一律用 `direction="long"` 调用
  `settlement_math.spot_settle`,`bench_return` 取与 `market_return` 相同值
  (该候选类型无独立基准标的,long 候选自身的价格路径即为其自身基准),这使
  `alpha` 恒为 0、`strategy_return` 恒等于 `market_return`——真正的"反事实
  价值"体现在 `counterfactual_report` 按裁决分组后的均值/命中率对比上
  (accepted 组代表"实际执行的候选表现",vetoed_or_observed 组代表"若被否决
  的候选其实也被执行,结果会是什么")。这是本子任务在 spec 未明确 `bench_return`
  取值时做出的设计判断,建议复核者重点确认是否符合"反事实归因"的产品意图。
- daily.py 的默认账本接线放在 CLI `main()` 而非 `run_daily()` 库函数(见
  Risks 一节),是为规避对既有离线测试套件引入隐式磁盘/网络副作用的工程判断,
  非疏漏;如需改为库函数级默认,请在下一轮明确澄清后调整。
