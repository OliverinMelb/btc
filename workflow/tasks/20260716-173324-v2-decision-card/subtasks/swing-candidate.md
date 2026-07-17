# Subtask Spec

## Parent Task
20260716-173324-v2-decision-card

## Subtask Title
swing-candidate — 波段候选引擎 + LLM 裁决

## Owner Role
- agent-change(btc_agent/,Python src 布局;**触碰契约面 schemas.py → full lane**)

## Goal
一种机械波段候选规则「震荡下沿做多」+ LLM 裁决点(accept/observe/veto,零数字),
以注入方式加挂进 daily 编排的 candidate_provider 扩展点。

## Scope
- 允许触碰:
  - 新增 `btc_agent/src/btc_agent/candidates.py`
  - `btc_agent/src/btc_agent/agents/schemas.py`(**仅新增** CandidateVerdict;
    ResearchPlan/TraderProposal/PortfolioDecision 三类一字不动——structural_check 不变式)
  - `btc_agent/src/btc_agent/daily.py`(仅接线:默认 candidate_provider 的装配与
    CLI 集成;编排流程结构不重写)
  - `btc_agent/src/btc_agent/decision_card.py`(仅候选段渲染:candidates 非 None 时
    输出 候选类型/裁决/机械入场参考/机械失效位置/机械目标区域/候选有效期)
  - `btc_agent/tests/` 新增/扩展单测
- 禁止触碰:intel/、run.py、dataflows/、graph/、evidence.py、regime.py、
  settlement_math.py(只 import 不改)

## Dependencies
- depends-on: [decision-card]  # task 分支已含 ST1-ST4
- provides-to: [sqlite-ledger]

## Inputs
- parent plan(**必读 G1/G5/G6 与 ST5 条目**):workflow/tasks/20260716-173324-v2-decision-card/plan.md
- ST4 遗留回归项:候选段超长文本的截断级联(decision_card 的 4096 截断此前只测过
  candidates="无"路径)——本子任务补一个长候选文本截断回归单测。

## 实现要点(plan ST5 + G5/G6 裁定)

1. `candidates.py`:
   - `CANDIDATE_PARAMS`:模块级可 json 序列化 dict(区间回看窗口、下沿带宽度、
     有效期天数 N、以及 G6 结算口径参数 touch_basis="intraday"、
     settle_price="level"、tie_break="stop_first" 等)。G5 版本 hash 输入之一。
   - `find_swing_candidate(snapshot, regime_result) -> Candidate | None`(dataclass):
     仅 regime_result.regime == "range" 且 blank_sheet=False 且价格触及区间下沿带
     时产出;否则 None。数据缺失(ohlcv None/不足)→ None(白卷,不硬凑)。
   - Candidate 字段:candidate_type="range_lower_long"、entry_ref、invalidation、
     target_zone、expires_utc(N 个 UTC 日)、params_used、机械依据 observations。
     **全部价位机械计算**(区间高低点/ATR,与 trade_levels 同源思路),禁止 LLM 参与。
2. `agents/schemas.py` 新增:
   ```python
   class CandidateVerdict(BaseModel):
       verdict: Literal["accept", "observe", "veto"]
       reason: str
   ```
   **无任何数值类型字段**(单测断言字段类型集合无 int/float)。
3. LLM 裁决(candidates.py 或独立小模块):
   - prompt:给出候选机械依据 + 快照要点,要求 LLM 只判 accept/observe/veto + 定性理由;
     **白卷文化写进 prompt**(证据不足就 observe/veto,不硬给);不得让 LLM 产任何数字。
   - 解析沿用 `agents/utils/rating.py` 的安全模式:明确标签才算,歧义/解析失败 → observe。
   - LLM 客户端注入式(测试 fake);真实路径复用图的 LLM 配置(延迟 import)。
4. daily 接线:默认 candidate_provider = 机械候选 + (有候选且非白卷时)LLM 裁决;
   卡片候选段按 brief 格式渲染。白卷时 provider 不产候选(现有测试语义保持)。

## Acceptance Criteria
- [ ] 单测:regime=range 且价格进下沿带 → 产出候选,携带机械 entry_ref/invalidation/
      target_zone/expires_utc;非 range(四种)→ None;数据缺失 → None。
- [ ] 单测:CandidateVerdict schema 字段类型集合无 int/float;
      三个既有 schema 类一字未动(可对比断言或 grep)。
- [ ] 单测:裁决解析——明确 accept/observe/veto 标签各一例;歧义文本 → observe;
      fake LLM 全程零网络。
- [ ] 单测:候选段渲染进决策卡(裁决+四个机械字段+有效期);**长候选文本 4096 截断回归**。
- [ ] 单测:CANDIDATE_PARAMS json 可序列化,Candidate.params_used 与之一致。
- [ ] daily 全流程单测(fake graph+fake snapshot+fake llm):range 环境出候选卡,
      blank_sheet 不出候选。
- [ ] btc_agent/ 内 ruff + pytest 全绿(既有 138 + 新增)。

## Verification
- maker checks: ruff + pytest(离线)
- checker gates: 契约漂移检查(schemas.py 三类不变式必须仍过);AC 逐条复核;
  **full lane reviewer**(契约面)
- independent re-verify: `workflow/scripts/verify_subtask.ps1`

## Stop Conditions
- 发现必须给 CandidateVerdict 加数值字段才能实现 → 停,回设计层(红线)。
- 发现必须改 graph/ 或重写 daily 编排结构 → 停,报告。
- 任何路径需要真实网络/API key → 停(fake LLM)。

## Recommended Workflow
agent-change
