# Subtask Summary

## Parent Task
20260716-173324-v2-decision-card

## Subtask
swing-candidate — 波段候选引擎 + LLM 裁决

## Worktree
- path: C:\Users\admin\Desktop\wt-swing-candidate
- branch: subtask/swing-candidate

## Outcome
- status: pass
- reviewer recommendation: pass

## What Changed
- 新增 `btc_agent/src/btc_agent/candidates.py`:
  - `CANDIDATE_PARAMS`(集中式、可 `json.dumps` 序列化,策略版本 hash 输入之一):
    `lookback_bars`/`atr_period`/`lower_band_atr_mult`/`invalidation_atr_mult`/
    `expiry_days`,以及 G6 结算口径静态参数 `touch_basis="intraday"`、
    `settle_price="level"`、`tie_break="stop_first"`(本子任务不消费,预留给 ST6)。
  - `Candidate` dataclass:`candidate_type`/`entry_ref`/`invalidation`/
    `target_zone`/`expires_utc`/`params_used`/`observations`。
  - `find_swing_candidate(snapshot, regime_result, params=None) -> Candidate | None`:
    仅 `regime_result.regime == "range"` 且 `blank_sheet=False` 且 OHLCV 足量
    且最新价格触及区间下沿带(`range_low + lower_band_atr_mult*ATR` 之内)时产出;
    非 range、数据缺失/不足、未触及 → `None`(白卷,不硬凑)。全部价位机械计算
    (区间高低点 + ATR,复用 `trade_levels.compute_atr`,与 ST4 同源)。
  - `judge_candidate(candidate, snapshot, llm=None) -> CandidateVerdict`:LLM 裁决点,
    prompt 明示"绝不输出任何数字"+白卷文化;解析沿用 `agents/utils/rating.py`
    的安全标签模式(`Verdict: <label>`,或独立成行的标签词),歧义/无法解析/LLM
    调用异常一律降级 `observe`。`llm=None` 时延迟构造真实客户端(生产路径,
    `btc_agent.llm_clients.create_llm_client` + `DEFAULT_CONFIG`);测试路径始终注入
    fake llm(`.invoke(prompt) -> 带 .content 的对象`),零网络零凭据。
  - `default_candidate_provider(snapshot, regime_result, llm=None) -> dict | None`:
    机械候选 + 有候选时的 LLM 裁决组装,返回 `decision_card` 消费的字典形态
    (`candidate_type`/`verdict`/`reason`/`entry_ref`/`invalidation`/`target_zone`/
    `expires_utc`)。
- `btc_agent/src/btc_agent/agents/schemas.py`:仅**新增** `CandidateVerdict`
  (`verdict: Literal["accept","observe","veto"]` + `reason: str`,无任何数值
  字段);`ResearchPlan`/`TraderProposal`/`PortfolioDecision` 三类字段与代码一字未动
  (`git diff` 确认为纯追加)。
- `btc_agent/src/btc_agent/daily.py`:仅接线。`candidate_provider` 参数默认值改为
  哨兵 `_UNSET`——调用方未显式传参时接线为 `candidates.default_candidate_provider`
  (ST5 新语义);调用方显式传 `None` 仍可跳过候选(ST4 遗留语义原样保留,现有
  测试全部未传该参数且 regime 均非 range,不会触发 LLM/网络调用)。编排流程结构
  未重写。
- `btc_agent/src/btc_agent/decision_card.py`:仅候选段渲染。`candidates` 为 falsy
  时仍渲染 `"本次操作候选: 无"`(与既有单测字符串断言保持一致);非 None 时渲染
  候选类型/裁决/机械入场参考/机械失效位置/机械目标区域/候选有效期/理由,兼容
  dict 或带属性对象两种载体(`_candidate_field` 辅助函数)。截断级联(4096 上限)
  逻辑本身未改动——极端硬截断分支是文本长度无关的通用兜底,天然覆盖超长候选段。
- 新增/扩展单测:
  - `btc_agent/tests/test_candidates.py`(新增,20 例):非 range 四分支/数据缺失/
    区间未触及 → `None`;range+触及 → 候选携带四个机械字段;`CANDIDATE_PARAMS`
    json 可序列化且与 `params_used` 一致;`CandidateVerdict` 无数值字段 + 三个既有
    schema 类字段集合契约;裁决三标签解析、歧义降级 observe、LLM 异常降级 observe
    (不抛出打断编排)、prompt 文案含"白卷"与"数字"关键字;
    `default_candidate_provider` 组装(非 range → None;range → 候选+裁决合一)。
  - `btc_agent/tests/test_decision_card.py`(扩展 3 例):候选段四字段+裁决+有效期
    +理由渲染;`candidates=None` 仍显示"无";**长候选文本 4096 截断回归**
    (ST4 遗留项——此前截断单测只覆盖过 `candidates="无"` 的短路径)。
  - `btc_agent/tests/test_daily.py`(扩展 2 例):range 环境(monkeypatch
    `detect_regime`)+ fake graph + fake llm → 默认 provider 出候选卡,卡片含四个
    机械字段;白卷路径(`insufficient_data`)候选恒为 `None`,卡片仍显示"无"。

## Files Touched
- btc_agent/src/btc_agent/candidates.py(新增)
- btc_agent/src/btc_agent/agents/schemas.py(仅新增 CandidateVerdict)
- btc_agent/src/btc_agent/daily.py(接线 candidate_provider 默认值)
- btc_agent/src/btc_agent/decision_card.py(候选段渲染)
- btc_agent/tests/test_candidates.py(新增)
- btc_agent/tests/test_decision_card.py(扩展)
- btc_agent/tests/test_daily.py(扩展)

## Verification Run
- maker checks(均从 `C:\Users\admin\Desktop\wt-swing-candidate\btc_agent` 执行,
  复用主仓 venv,零新依赖):
  - `python -m ruff check .` → All checks passed
  - `python -m pytest` → 163 passed(既有 138 + 新增/扩展 25)
- checker gates:
  - 契约漂移(schemas.py 三类不变式):`test_existing_three_schemas_untouched`
    单测断言字段集合;`git diff` 确认纯追加,未改动既有代码行。
  - full lane reviewer(契约面):建议 orchestrator 按 full lane 独立复验
    `workflow/scripts/verify_subtask.ps1`。

## Risks / Follow-ups
- `default_candidate_provider` 的生产路径(`llm=None`)会延迟构造真实 LLM 客户端
  (`create_llm_client` + `DEFAULT_CONFIG`),仅在 `regime=="range"` 且触及下沿带
  时才会被调用;这条真实路径未在本子任务离线覆盖(需要 API key),留给 G7
  人工端到端验证时自然覆盖(`python -m btc_agent.daily` 若命中 range 环境)。
- ST6(sqlite-ledger)将消费 `CANDIDATE_PARAMS` 里的 `touch_basis`/`settle_price`/
  `tie_break` 三个静态参数进行结算口径判定,本子任务只是把它们放进了参数字典,
  未做任何消费逻辑——与 spec 范围一致(候选参数集中化,结算逻辑归 ST6)。
- decision_card 的候选段渲染依赖 `candidates` 是 dict 或带属性对象;若后续
  子任务(ledger/settlement)决定用别的载体形状,需要同步检查 `_candidate_field`
  的两分支是否仍覆盖。

## Notes For Reviewer
- 红线核查:`CandidateVerdict` 字段仅 `verdict`(Literal 三值)+ `reason`(str),
  无 int/float 字段,单测 `test_candidate_verdict_has_no_numeric_fields` 固化。
- 全部候选价位(entry_ref/invalidation/target_zone)均来自 `find_swing_candidate`
  的机械计算(区间高低点 + ATR),LLM(`judge_candidate`)只消费已算好的
  `candidate.observations` 文本描述,不重新计算或复述任何数字;prompt 显式要求
  "绝不要输出任何价格、数量、百分比或其它数字"。
- daily.py 默认接线改动是本任务范围内允许的唯一行为变化点;若 reviewer 担心
  默认值变更影响下游(ST6)接线方式,可核对 `_UNSET` 哨兵设计——显式传
  `candidate_provider=None` 仍可完全跳过,向后兼容。
