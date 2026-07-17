# Subtask Spec

## Parent Task
20260716-173324-v2-decision-card

## Subtask Title
spot-settlement — 现货收益口径修正

## Owner Role
- agent-change(btc_agent/,Python src 布局)

## Goal
把结算口径从"做空口径"改为现货口径,并把结算数学抽成可被后续账本(ST6)离线复用的
模块级纯函数;方向命中(direction_hit)与收益分离记录;旧 markdown 记忆记录以
不破解析器的方式区分 legacy 口径。

背景缺陷:`graph/trading_graph.py` 目前把 Sell 结算成 `strategy_return = -market_return`。
只做现货的系统里,空仓时收益应为 0(alpha = -bench_return,即踏空成本),不能按做空记账。

## Scope
- 允许触碰:
  - 新增 `btc_agent/src/btc_agent/settlement_math.py`
  - `btc_agent/src/btc_agent/graph/trading_graph.py`(仅结算相关:`_fetch_returns`、
    `_resolve_pending_entries` 及其调用点)
  - `btc_agent/src/btc_agent/graph/reflection.py`(签名扩展:direction_hit 入参)
  - `btc_agent/src/btc_agent/agents/utils/memory.py`(tag 尾部可选字段 + 解析容错 +
    legacy 渲染标注)
  - `btc_agent/tests/` 新增/修改对应单测
- 禁止触碰:
  - `agents/schemas.py`、`dataflows/interface.py`、`run.py` 的
    `compute_trade_levels`/"mechanical (ATR-based), not LLM" 不变式、`intel/` 全部
  - prompt 文本(除 reflection 需要引用 direction_hit 的最小改动外)
  - `default_config.py` 的 DEEPSEEK_API_KEY 读取方式

## Dependencies
- depends-on: []
- provides-to: [sqlite-ledger]  # ST6 复用 settlement_math 的口径契约(纯函数+字段名)

## Inputs
- parent spec: workflow/tasks/20260716-173324-v2-decision-card/spec.md
- parent plan(**必读 全局裁定 G2/G4 与 ST1 条目**):同目录 plan.md
- 设计门记录:同目录 design-review.md(round 1 的 C1 条目解释了 memory.py 解析约束)

## 实现要点(plan ST1 的裁定,不得偏离)

1. `settlement_math.py`:模块级纯函数,**不 import graph/llm 任何东西**:
   `spot_settle(direction, market_return, bench_return) -> dict`
   返回 `{strategy_return, alpha, direction_hit, settlement_basis: "spot"}`:
   - long: strategy_return = market_return, alpha = strategy_return - bench_return
   - short(现货空仓): strategy_return = 0.0, alpha = -bench_return
   - flat: strategy_return = 0.0, alpha = -bench_return
   - direction_hit: long → market_return > 0;short → market_return < 0;
     market_return == 0 → False;flat → None(不入命中率分母)
2. `trading_graph._fetch_returns`:改调 spot_settle,删除 `-market_return` 路径;
   返回值透传 direction_hit/settlement_basis(元组扩展或改 dict,调用点同步)。
3. `reflection.py`:direction_hit 穿进反思入参(spot 口径下 Sell 的 raw=0,
   反思必须能直接看到方向对错,而非从 alpha 反推)。
4. `memory.py` legacy 处理(**解析器约束,违反即返工**):
   - pending 行格式**完全不动**(`endswith("| pending]")` 与 fields[3] 语义保持);
   - 仅已结算条目 tag **尾部追加** `| basis=spot | hit=<0/1>`(hit=None 时省略 hit 段);
   - `_parse_entry` 按 len(fields) 容错:旧长度=legacy,新长度=spot;
   - `get_past_context`/反思注入渲染时,legacy 已结算条目标注 `(legacy short-basis)`。
   - 不迁移旧数据。

## Acceptance Criteria
- [ ] `settlement_math.spot_settle` 单测:三方向 + market_return==0 边界 + flat→None。
- [ ] 单测断言:Sell(short)结算 strategy_return == 0 且 alpha == -bench_return。
- [ ] 单测断言 direction_hit 与收益字段相互独立(Sell 且市场下跌:hit=True、return=0)。
- [ ] `git grep -n -- "-market_return" btc_agent/src` 无结果(做空路径已删)。
- [ ] memory 解析回归单测:旧格式已结算/pending 条目照常解析;新格式条目读出 basis/hit;
      pending 匹配(`endswith("| pending]")`)行为不变。
- [ ] legacy 渲染单测:past context 里旧已结算条目带 `(legacy short-basis)` 标注。
- [ ] `_resolve_pending_entries` 相关单测中 reflector 一并 fake(不触网不调 LLM)。
- [ ] btc_agent/ 内 `python -m ruff check .` 通过;`python -m pytest` 全绿
      (既有 83 个 + 新增,零跳过零失败)。

## Verification
- maker checks: ruff + pytest(btc_agent/ 全量,离线)
- checker gates: 契约漂移检查(structural_checks——本子任务不应触碰任何 marker 文件的
  不变式);AC 逐条复核
- independent re-verify: `workflow/scripts/verify_subtask.ps1`(orchestrator 执行,
  非本子代理)

## Stop Conditions
- 发现必须改 `agents/schemas.py` 或 `run.py` 不变式才能完成 → 停,报告。
- 发现 memory.py 解析约束(pending 格式不动 + 尾部追加)无法同时满足 → 停,报告,
  不得自行改造 tag 结构。
- 任何路径需要真实 DEEPSEEK_API_KEY / 网络 → 停(全部测试离线,用 _FakeGraph/mock 模式,
  参照 btc_agent/tests/test_run_record.py 与 test_ccxt_vendor.py)。

## Recommended Workflow
agent-change
