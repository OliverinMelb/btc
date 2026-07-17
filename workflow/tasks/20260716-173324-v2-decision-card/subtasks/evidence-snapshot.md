# Subtask Spec

## Parent Task
20260716-173324-v2-decision-card

## Subtask Title
evidence-snapshot — 统一证据快照

## Owner Role
- agent-change(btc_agent/,Python src 布局)

## Goal
新增 EvidenceSnapshot:一份冻结的 UTC as-of 证据快照(行情+指标/新闻/F&G/资金费率/OI/
per-source 健康状态),把**三条机械取数路径**(intel 仪表盘、trade_levels 的 OHLCV、
后续决策卡/环境识别)收敛到同一快照对象。

**范围裁定(设计门 G3,不得扩大)**:研判图 ToolNode 图内取数**本子任务不改线**——
它已有各 vendor 的 as-of 防护且与快照同参数调同一 vendor;并入快照记 backlog v2.5。

## Scope
- 允许触碰:
  - 新增 `btc_agent/src/btc_agent/evidence.py`
  - `btc_agent/src/btc_agent/intel/dashboard.py`(改为从快照装配,保留 errors/降级语义)
  - `btc_agent/src/btc_agent/run.py`(仅第 97 行附近的 `_ohlcv_dataframe` 直调改为从
    快照读;`compute_trade_levels` 调用与 "mechanical (ATR-based), not LLM" 字样、
    DEEPSEEK_API_KEY 校验**必须原样保留**——契约不变式)
  - `btc_agent/tests/` 新增/修改对应单测
- 禁止触碰:
  - `dataflows/` 下所有 vendor 文件(**只调用,不重写取数**;as-of 语义原样保留)
  - `dataflows/interface.py`、`agents/schemas.py`、`intel/rules.py`、`intel/push.py`、
    `intel/run_intel.py`、`graph/` 全部
  - graph ToolNode 取数路径(G3 裁定)

## Dependencies
- depends-on: []  # 与 spot-settlement 并行,双方触碰文件无交集
- provides-to: [regime-detector, decision-card]

## Inputs
- parent spec: workflow/tasks/20260716-173324-v2-decision-card/spec.md
- parent plan(**必读 全局裁定 G3 与 ST2 条目**):同目录 plan.md
- 设计门记录:同目录 design-review.md

## 实现要点(plan ST2 的裁定)

1. `evidence.py`:`build_evidence_snapshot(asset: str, curr_date: str | None) ->
   EvidenceSnapshot`(dataclass),字段:
   - `ohlcv`(DataFrame,来自现有 `ccxt_vendor._ohlcv_dataframe`)
   - `news`(来自现有 crypto RSS vendor 的注册入口)
   - `fear_greed`(来自 `feargreed_vendor`)
   - `derivatives`(资金费率/OI,来自 `derivatives_vendor`)
   - `health`:dict,per-source `ok | error:<原因>`(单源失败→记 health,不崩,
     沿用 dashboard.py 现有降级哲学)
   - `snapshot_id`(如 `BTC-2026-07-16-<短hash>`)、`frozen_at_utc`、`asset`、`curr_date`
2. `intel/dashboard.py`:`build_dashboard` 改为接受/构建快照并从中装配,
   对外 dict 结构(fear_greed/derivatives/rsi/price_move_pct/close/errors)**保持不变**
   (rules.py 消费它,不许破)。errors 从 health 映射。
3. `run.py`:ohlcv 取数走快照(可 `snapshot=None` 参数注入,默认自建),
   trade_levels 消费 `snapshot.ohlcv`。
4. 快照就是"取一次、处处用"——同一次运行内不得二次触发 vendor 取数。

## Acceptance Criteria
- [ ] 单测:同一快照对象上,dashboard 路径读到的 close 与 trade_levels 路径消费的
      OHLCV 最后收盘价一致(mock vendor 计数断言 vendor 只被调用一次)。
- [ ] 单测:单源失败(如 F&G 抛异常)→ snapshot.health 记录该源 error,其余源正常,
      dashboard errors 字段同步呈现,流程不崩。
- [ ] 既有全部单测保留并通过(尤其 vendor as-of 前视防护相关、dashboard/rules 相关)。
- [ ] `run.py` 契约不变式原样:`compute_trade_levels`、
      "mechanical (ATR-based), not LLM"、`DEEPSEEK_API_KEY` 均在。
- [ ] btc_agent/ 内 `python -m ruff check .` 通过;`python -m pytest` 全绿(零跳过零失败)。

## Verification
- maker checks: ruff + pytest(btc_agent/ 全量,离线)
- checker gates: 契约漂移检查(structural_checks);AC 逐条复核
- independent re-verify: `workflow/scripts/verify_subtask.ps1`(orchestrator 执行)

## Stop Conditions
- 发现必须修改 vendor 内部取数逻辑才能完成 → 停,报告(只允许调用)。
- 发现必须改 graph/ 或 interface.py 才能达成 AC → 停,报告(G3 裁定禁区)。
- 任何路径需要真实网络/API key → 停(全部测试离线,monkeypatch vendor,
  参照 btc_agent/tests/test_intel_vendors.py 与 test_ccxt_vendor.py)。

## Recommended Workflow
agent-change
