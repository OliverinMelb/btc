# Subtask Summary

## Parent Task
20260716-173324-v2-decision-card

## Subtask
decision-card — 每日决策卡 + daily 编排

## Worktree
- path: C:\Users\admin\Desktop\wt-decision-card
- branch: subtask/decision-card

## Outcome
- status: pass
- reviewer recommendation: pass

## What Changed
- 新增 `btc_agent/src/btc_agent/decision_card.py`:`render_decision_card(snapshot,
  regime_result, rating, reasoning, levels, candidates=None) -> str` 纯函数。字段齐全
  (BTC市场环境五分类中文名/证据完整度/机械观察择要/评级或白卷及原因/本次操作候选(本子任务
  恒"无")/空仓建议+持仓建议机械纪律表/关注位)。首行为可作邮件主题的短句;总长超 4096
  时按 section 分级截断(先裁机械观察段,再裁评级理由长文,极端情况硬截断到上限),截断始终
  保留首行主题。所有价位数字只来自入参 `levels`(即 `compute_trade_levels` 的输出),
  `reasoning` 仅作纯文本展示,不解析/不写入关注位字段。
- 新增 `btc_agent/src/btc_agent/daily.py`:`run_daily(asset, trade_date, config, graph=None,
  snapshot=None, candidate_provider=None, ledger_recorder=None)` 编排:
  `build_evidence_snapshot`(可注入)→ `detect_regime` → 白卷(chaos/insufficient_data)时
  **不构造/不调用**研判图,直接渲染白卷卡;否则延迟 import `TradingAgentsGraph`(可注入
  fake graph)跑 `graph.propagate` 一次 → `compute_trade_levels` 机械关注位 →
  `render_decision_card` → 复用 `intel.push.build_sinks_from_config`/`dispatch` 推送。
  `candidate_provider`/`ledger_recorder` 为 None 时跳过(ST5/ST6 加挂点)。推送未完整
  送达 → `main()` 返回非零退出码;`main()` 统一校验 `DEEPSEEK_API_KEY`(含白卷路径)。
  `python -m btc_agent.daily` 可运行(`if __name__ == "__main__"` 直接注册,无需额外
  `__main__.py`,与 spec 允许的写法一致)。
- 新增 `btc_agent/tests/test_decision_card.py`(11 例)与
  `btc_agent/tests/test_daily.py`(9 例),全部纯离线(构造 OHLCV / EvidenceSnapshot /
  RegimeResult 替身,fake graph/fake sink,monkeypatch `build_evidence_snapshot` 断言
  vendor 零调用)。

## Files Touched
- btc_agent/src/btc_agent/decision_card.py (新增)
- btc_agent/src/btc_agent/daily.py (新增)
- btc_agent/tests/test_decision_card.py (新增)
- btc_agent/tests/test_daily.py (新增)

## Verification Run
- maker checks: `python -m ruff check .`(btc_agent/ 内)→ All checks passed；
  `python -m pytest`(btc_agent/ 内)→ 138 passed(既有 118 + 新增 20)
- checker gates: 未独立跑 structural_checks/契约漂移(留给 orchestrator 的
  verify_subtask.ps1 独立复验，属于其职责范围);本子任务未触碰
  `workflow/config.json`/`intel/`/`run.py`/`agents/schemas.py`/`dataflows/`/`graph/`/
  `evidence.py`/`regime.py`,仅新增两个源文件与两个测试文件，边界未越界。

## Acceptance Criteria 逐条自检
- [x] 五种环境各渲染一张卡,字段齐全(参数化测试 `test_all_five_regimes_render_full_fields`)。
- [x] blank_sheet(chaos/insufficient_data)不调图(`_RejectingGraph` 在 propagate 内
  `raise AssertionError`,`test_blank_sheet_path_skips_graph`);卡片明示白卷及原因
  (`test_blank_sheet_card_states_reason_and_no_levels`)。
- [x] daily 编排注入 fake graph + fake snapshot 全离线,vendor 零调用
  (`_no_vendor_calls` autouse fixture 把 `build_evidence_snapshot` 打成"调用即断言失败"),
  `graph.propagate` 恰调用一次(`test_non_blank_path_calls_graph_exactly_once`)。
- [x] 推送失败 → 非零退出码(`test_delivery_failure_triggers_nonzero_exit` +
  `test_cli_exit_code_nonzero_when_delivery_incomplete`);全部送达 → 0
  (`test_all_sinks_delivered_yields_success` + `test_cli_exit_code_zero_when_delivery_complete`)。
- [x] 超长卡片截断后 <= 4096 字符且首行仍是主题短句
  (`test_long_card_is_truncated_to_telegram_limit_and_keeps_subject`)。
- [x] daily.py 含 `compute_trade_levels` 调用(源码断言 `test_daily_module_source_contains_
  mechanical_levels_and_blank_sheet_keywords`);fake graph 文本里埋的价格数字不出现在
  关注位/价位字段(`test_reasoning_price_number_does_not_leak_into_levels_section` +
  `test_fake_graph_price_number_does_not_leak_into_levels_field`)。
- [x] `python -m ruff check .` + `python -m pytest` 全绿(138 passed)。

## Risks / Follow-ups
- 决策卡的截断策略是分级(先裁机械观察段,再裁评级理由,最后硬截断),已用超长文本单测
  覆盖到最终 <=4096 分支;若后续候选段(ST5)本身文本很长,可能需要重新评估截断优先级
  (目前候选段与关注位段不参与裁剪,理论上存在候选文本本身超长导致仍需硬截断的边缘情况,
  已有兜底但未针对候选段专门构造超长用例——ST5 接入候选段时建议补一条超长候选文本的截断
  回归测试)。
- `render_decision_card`/`run_daily` 均未触碰 intel/run.py/schemas.py/graph 包内部,
  未发现需要越界的情况,无需停下上报。
- G7 端到端真实验收(需 DEEPSEEK_API_KEY + 推送凭据)按 plan 裁定不在本子任务范围内,
  交由人工/主会话执行。

## Notes For Reviewer
- 决策卡字段与消息约束逐条对照 brief Scope 第 4 条与 plan ST4 条目实现;daily 依赖方向
  单向 daily → {intel.push, graph, evidence, regime},未反向被 intel 依赖(intel/ 未改动)。
- 白卷路径统一校验 `DEEPSEEK_API_KEY`(与 run.py 的 v0 语义一致,按 spec 第 63 行"保持简单"
  的裁定实现,未额外为白卷路径开绿色通道)。
- 建议复核点:`decision_card._truncate_by_section` 的三级降级逻辑(替换 observations →
  裁 rating 理由 → 硬截断)是否符合预期的"保环境/评级/候选/关注位,截理由长文"语义——
  当前实现里 observations 段被整体替换为占位提示(不算严格意义上的"理由"段,但它是
  除 reasoning 外唯一的可变长自由文本,故一并纳入裁剪候选)。
