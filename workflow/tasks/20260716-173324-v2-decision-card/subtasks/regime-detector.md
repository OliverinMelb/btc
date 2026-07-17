# Subtask Spec

## Parent Task
20260716-173324-v2-decision-card

## Subtask Title
regime-detector — 机械市场环境识别

## Owner Role
- agent-change(btc_agent/,Python src 布局)

## Goal
新增纯规则的市场环境识别器:输入 EvidenceSnapshot,输出五分类
trend_up / trend_down / range / chaos / insufficient_data。chaos 与 insufficient_data
必须携带"下游白卷"标志。零 LLM、零网络——只消费快照里已有的数据。

## Scope
- 允许触碰:
  - 新增 `btc_agent/src/btc_agent/regime.py`
  - `btc_agent/tests/` 新增单测(如 test_regime.py)
- 禁止触碰:其余一切文件(evidence.py 只 import 不改;契约 marker 文件全禁)

## Dependencies
- depends-on: [evidence-snapshot]  # 已合入 task 分支,worktree 从 task 分支切出即含
- provides-to: [decision-card, swing-candidate]

## Inputs
- parent plan(**必读 全局裁定 G5 与 ST3 条目**):workflow/tasks/20260716-173324-v2-decision-card/plan.md
- EvidenceSnapshot 定义:btc_agent/src/btc_agent/evidence.py(ST2 已交付)

## 实现要点(plan ST3 的裁定)

1. `regime.py`:
   - `REGIME_PARAMS`:模块级 dict,集中全部规则参数(SMA 窗口、斜率阈值、ATR 百分位
     阈值、最少 K 线数等)。这是 G5 版本 hash 的输入之一——参数改动即新策略版本,
     所以必须集中、可序列化(canonical json),不许散在函数里。
   - `detect_regime(snapshot) -> RegimeResult`(dataclass:`regime: str`、
     `blank_sheet: bool`、`observations: dict`(机械观察值,供决策卡引用)、
     `params_used: dict`)。
   - 分类规则(纯确定性,建议实现,可微调但参数须进 REGIME_PARAMS):
     - insufficient_data:snapshot.ohlcv 为 None 或 K 线数 < 最少要求,或 ohlcv health
       非 ok → blank_sheet=True
     - chaos:ATR(或日收益率标准差)处于近端历史高百分位 → blank_sheet=True
     - trend_up / trend_down:收盘价相对 SMA 与 SMA 斜率同向确认
     - range:以上皆非
   - blank_sheet 仅在 chaos/insufficient_data 为 True。
2. 不 import graph/intel/llm 任何东西;只依赖 evidence(类型)+ pandas/stockstats。

## Acceptance Criteria
- [ ] 单测用构造 OHLCV 覆盖五个分支各至少一例(上升趋势/下降趋势/震荡/高波动/数据不足)。
- [ ] chaos 与 insufficient_data 的结果 blank_sheet=True;其余三类为 False,单测断言。
- [ ] REGIME_PARAMS 可 json 序列化(单测断言 json.dumps 成功),detect_regime 的
      params_used 与之一致。
- [ ] regime.py 不 import graph/intel/llm(单测或 grep 断言)。
- [ ] btc_agent/ 内 `python -m ruff check .` 通过;`python -m pytest` 全绿
      (既有 105 个 + 新增,零跳过零失败)。

## Verification
- maker checks: ruff + pytest(btc_agent/ 全量,离线)
- checker gates: 契约漂移检查(不应触碰任何 marker);AC 逐条复核
- independent re-verify: `workflow/scripts/verify_subtask.ps1`(orchestrator 执行)

## Stop Conditions
- 发现必须改 evidence.py 才能拿到所需数据 → 停,报告(快照字段不够是设计问题)。
- 任何路径需要真实网络 → 停(全部测试用构造 DataFrame)。

## Recommended Workflow
agent-change
