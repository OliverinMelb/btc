# Subtask Spec

## Parent Task
20260716-173324-v2-decision-card

## Subtask Title
contract-backfill — 契约回填 + ST6 reviewer follow-up 清理

## Owner Role
- agent-change(触碰 workflow/config.json 契约配置本身 → full lane 由 orchestrator 直接终审)

## Goal
把 v2 新增的契约面纳入漂移检查护栏(plan ST7/设计门 B1),并清掉 ST6 reviewer 的
三条非阻断 follow-up(F1/F2/F3)。这是收尾子任务,全部是小改动。

## Scope
- 允许触碰:
  - `workflow/config.json`(surface_markers/structural_checks/env_consistency 增补;
    **现有断言一条不许改删**)
  - `workflow/checks/verification.md`(修 ai_helper_backend 陈旧文案,指向本项目矩阵)
  - `btc_agent/src/btc_agent/default_config.py`(仅新增 ledger_enabled 键,F3)
  - `btc_agent/tests/`(新增 F1/F3 单测)
  - `btc_agent/src/btc_agent/ledger.py` 或 `settlement.py` 的 **docstring/注释**(F2,
    不改逻辑)
- 禁止触碰:其余一切源码逻辑

## Dependencies
- depends-on: [全部 ST1-ST6,task 分支已含]
- provides-to: []（最后一个子任务）

## 实现要点

1. `workflow/config.json`(注意保持 UTF-8 无 BOM,JSON 有效性用 python 验证):
   - surface_markers 增补:
     `btc_agent/src/btc_agent/evidence.py`、`regime.py`、`candidates.py`、
     `ledger.py`、`settlement.py`、`decision_card.py`、`daily.py`、`settlement_math.py`
   - structural_checks 增补(先读各文件实际字面量再写 must_contain,别凭空猜):
     - schemas.py 追加 must_contain `class CandidateVerdict`(加进现有该文件条目)
     - daily.py:must_contain `compute_trade_levels`(机械价位不变式延伸到活路径)
       与 `blank_sheet`(白卷开关)
     - settlement_math.py:must_contain `def spot_settle` 与 `"spot"`(口径契约)
     - ledger.py:must_contain 只读契约关键字(如注释行"只读"或
       `get_or_create_strategy_version`)与 `params_hash`
     - candidates.py:must_contain `CANDIDATE_PARAMS` 与 `class CandidateVerdict` 的
       消费点(实际 import 行);error 文案说明破坏了什么
   - env_consistency 增补:daily.py must_contain `DEEPSEEK_API_KEY`
2. F1:`btc_agent/tests/test_settlement.py` 补一条——注入"创建当日即双触"的 K 线,
   断言创建当日不计入结算窗口(次日起算的前视防护不被回退)。
3. F2:在 settlement.py 的 counterfactual/结算 docstring 注明:候选结算 alpha 恒 0
   (bench=market 设计),候选组统计只用 strategy_return/hit_rate。
4. F3:DEFAULT_CONFIG 显式声明 `"ledger_enabled": True`;补 `_build_default_ledger_recorder`
   关闭路径(ledger_enabled=False → None)单测。
5. `workflow/checks/verification.md`:把 ai_helper_backend/ai_helper_frontend 的陈旧
   示例文案替换为本项目实际矩阵(btc_agent + ruff/pytest)。

## Acceptance Criteria
- [ ] config.json 是有效 JSON(python json.load 验证),现有断言全保留。
- [ ] 契约漂移检查在 task 分支跑通且 PASS(新旧断言一起)。
- [ ] 故意破坏一处新断言(临时改 daily.py 字样)漂移检查报 FAIL,恢复后 PASS
      (验证新断言真的有牙齿;结果写进 summary,恢复现场)。
- [ ] F1/F3 单测存在且过;F2 docstring 可 grep 到。
- [ ] btc_agent/ 内 ruff + pytest 全绿(既有 180 + 新增)。

## Verification
- maker checks: ruff + pytest + run_contract_drift.py
- independent re-verify: `workflow/scripts/verify_subtask.ps1`

## Stop Conditions
- 发现必须改源码逻辑才能让断言成立 → 停,报告(断言应描述现状,不是改现状迁就断言)。

## Recommended Workflow
agent-change
