# Subtask Spec

## Parent Task
20260716-173324-v2-decision-card

## Subtask Title
decision-card — 每日决策卡 + daily 编排

## Owner Role
- agent-change(btc_agent/,Python src 布局)

## Goal
新增每日 BTC 决策卡渲染与 daily 编排入口:快照→环境识别→(环境允许时)研判图评级→
渲染卡片→复用现有 push sink 推送。本子任务交付"无候选版"决策卡;候选段与账本由
ST5/ST6 以注入方式加挂。

## Scope
- 允许触碰:
  - 新增 `btc_agent/src/btc_agent/decision_card.py`
  - 新增 `btc_agent/src/btc_agent/daily.py`(+ 使 `python -m btc_agent.daily` 可运行,
    可新增 `btc_agent/src/btc_agent/daily_main` 之类不必要——直接在 daily.py 写
    `if __name__ == "__main__"` 且在包内注册即可;如需 `__main__` 惯例参照 intel/)
  - `btc_agent/tests/` 新增单测
- 禁止触碰:
  - `intel/` 下所有现有文件(push.py 只 import 不改;run_intel.py 不动——
    v1 告警入口保持独立,决策卡是新入口)
  - `run.py`、`agents/schemas.py`、`dataflows/` 全部、`graph/` 全部、
    `evidence.py`、`regime.py`(只 import 不改)

## Dependencies
- depends-on: [evidence-snapshot, regime-detector]  # task 分支已含
- provides-to: [swing-candidate, sqlite-ledger]

## Inputs
- parent plan(**必读 全局裁定 G1/G7 与 ST4 条目**):workflow/tasks/20260716-173324-v2-decision-card/plan.md
- brief 的决策卡字段规范:同目录 brief.md(Scope 第 4 条)
- ST2 reviewer 备忘:daily 必须把现成 snapshot 传给 build_dashboard/各消费方,
  同一次运行不得二次触发 vendor 取数(evidence.py 的快照就是唯一取数点)。

## 实现要点(plan ST4 + 设计门 G1 裁定)

1. `decision_card.py`:`render_decision_card(snapshot, regime_result, rating, reasoning,
   levels, candidates=None) -> str`,纯函数。字段(brief 规定):
   - BTC市场环境(五分类中文名)、证据完整度(snapshot.health 汇总:完整/数据不完整)
   - 机械观察(regime_result.observations 择要 + F&G/资金费率等快照信号)
   - TradingAgents评级 + 理由(环境白卷时明示"白卷:<原因>",跳过评级)
   - 本次操作候选:无 / 候选段(ST5 加挂,本子任务 candidates=None 渲染"无")
   - 空仓建议/持仓建议(基于环境的纪律表,机械文案,非 LLM)
   - 关注位置:下沿观察位/突破确认位(trade_levels 同源机械计算,如 compute_trade_levels
     的 ATR 或区间高低点;绝不来自 LLM)
   - **消息约束**:首行为短句(可作邮件主题);总长超 Telegram 4096 时按 section 截断
     (保环境/评级/候选/关注位,截理由长文),截断逻辑进单测。
2. `daily.py`(G1:依赖方向 daily → {intel.push, graph, evidence, regime};
   intel 包不 import graph):
   - 流程:build_evidence_snapshot → detect_regime → blank_sheet 时跳过研判图
     (卡片明示白卷),否则构造图跑评级(复用 run.py 的模式:延迟 import
     TradingAgentsGraph,graph 参数可注入 fake)→ compute_trade_levels 机械价位 →
     render_decision_card → push(复用 intel.push 的 build_sinks_from_config/dispatch)。
   - 扩展点:`run_daily(..., graph=None, snapshot=None, candidate_provider=None,
     ledger_recorder=None)`——后两者本子任务为 None 即跳过,ST5/ST6 加挂。
   - 推送失败/部分 sink 未送达 → 非零退出码(沿用 run_intel 的语义,但代码独立实现,
     不改 run_intel)。
   - `main()` 校验 DEEPSEEK_API_KEY(blank_sheet 路径也统一校验,保持简单)。
   - **机械价位一律经由 trade_levels 既有函数**;daily.py 源码须含
     `compute_trade_levels` 调用与白卷语义关键字(ST7 会把 structural_check 指到这里)。
3. 决策卡是新入口,与 v1 告警(python -m btc_agent.intel)并存;不合并推送
   (plan Open Questions 决议的"同一入口"指 daily 内部一次推送,不指改造 intel)。

## Acceptance Criteria
- [ ] 单测:五种环境各渲染一张卡,字段齐全(环境/证据完整度/机械观察/评级或白卷/
      候选=无/空仓持仓建议/关注位)。
- [ ] 单测:blank_sheet(chaos/insufficient_data)时不调用图(fake graph 断言零调用),
      卡片明示白卷及原因。
- [ ] 单测:daily 编排注入 fake graph + fake snapshot 全离线,vendor 零调用
      (monkeypatch 计数),graph.propagate 恰被调用一次(非白卷路径)。
- [ ] 单测:推送失败 → 非零退出码;全部送达 → 0。
- [ ] 单测:超长卡片按 section 截断后 <= 4096 字符,且首行仍是主题短句。
- [ ] daily.py 含 compute_trade_levels 调用;卡片中所有数字仅来自机械计算
      (单测:fake graph 返回的文本里埋一个价格数字,断言它不出现在关注位/价位字段)。
- [ ] btc_agent/ 内 `python -m ruff check .` + `python -m pytest` 全绿(既有 118 + 新增)。

## Verification
- maker checks: ruff + pytest(btc_agent/ 全量,离线)
- checker gates: 契约漂移检查;AC 逐条复核
- independent re-verify: `workflow/scripts/verify_subtask.ps1`(orchestrator 执行)

## Stop Conditions
- 发现必须改 intel/ 现有文件或 run.py 才能完成 → 停,报告。
- 发现必须让 LLM 输出数字才能填卡片字段 → 停,回设计层。
- 任何路径需要真实网络/API key/推送凭据 → 停(全部离线,凭据缺失走 sink 降级模式)。

## Recommended Workflow
agent-change
