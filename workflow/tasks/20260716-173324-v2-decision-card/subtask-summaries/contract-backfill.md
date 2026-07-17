# Subtask Summary

## Parent Task
20260716-173324-v2-decision-card

## Subtask
contract-backfill — 契约回填 + ST6 reviewer follow-up 清理

## Worktree
- path: C:\Users\admin\Desktop\wt-contract-backfill
- branch: subtask/contract-backfill
- commit: 7a254de "feat(v2-ST7): 契约回填 + ST6 reviewer follow-up 清理(F1/F2/F3)"

## Outcome
- status: pass
- reviewer recommendation: pass

## What Changed

1. **`workflow/config.json`**(有效 JSON,UTF-8 无 BOM,已用 python json.load 验证；
   现有断言一条未改删):
   - `surface_markers` 增补 v2 新增契约面 8 个文件:`evidence.py` `regime.py`
     `candidates.py` `ledger.py` `settlement.py` `decision_card.py` `daily.py`
     `settlement_math.py`。
   - `structural_checks` 增补 5 条(先读各文件实际字面量再写 must_contain):
     - `schemas.py`:并入现有条目,追加 `must_contain: "class CandidateVerdict"`。
     - `daily.py`(新条目):must_contain `compute_trade_levels` 与 `blank_sheet`——
       机械价位不变式延伸到活路径 + 白卷开关。
     - `settlement_math.py`(新条目):must_contain `def spot_settle` 与
       `"spot"`(结算口径字面量)。
     - `ledger.py`(新条目):must_contain `旧版本行及其结算数据只读`(实际字面量,
       模块 docstring 里的只读不变式说明)、`get_or_create_strategy_version`、
       `params_hash`。
     - `candidates.py`(新条目):must_contain `CANDIDATE_PARAMS` 与
       `from btc_agent.agents.schemas import CandidateVerdict`(实际 import 行,
       该行在文件中出现两次,任一处保留即通过)。
   - `env_consistency.rules` 增补:`daily.py` must_contain `DEEPSEEK_API_KEY`
     (daily.py 的 `main()` 有独立的 DEEPSEEK_API_KEY 校验,不与 run.py 那条重复,
     两条规则分别锚定各自入口)。
2. **`workflow/checks/verification.md`**:删除陈旧的 `ai_helper_backend` /
   `ai_helper_frontend` 双组件示例文案(该项目从未有前端组件),替换为本项目
   实际单组件矩阵(`btc_agent` + ruff/pytest),Contract Change / Workflow-Only
   Change 两节改用 `{engine}/...` 占位符指向 plugin 脚本(与 config.json 里的
   `$comment` 约定一致)。
3. **F1**(`btc_agent/tests/test_settlement.py`):新增
   `test_creation_day_double_touch_is_not_settled` ——注入"创建当日即双触"
   (Low<=失效位 且 High>=目标)的唯一一根 K 线,`as_of_utc` 设在数日之后但
   `ohlcv_provider` 只能提供创建当日这一根;断言 `settle_due_candidates`
   返回空列表、`settlements` 表零行,证明创建当日不落入结算扫描窗口
   (次日起算的前视防护未被回退)。
4. **F2**(`btc_agent/src/btc_agent/settlement.py`,零逻辑改动,仅
   docstring):模块级 docstring 新增段落说明候选结算 alpha 恒为 0 的设计原因
   (`spot_settle("long", market_return=r, bench_return=r)` 里
   bench=market,与 ST1 的 reflection/memory 整仓 alpha 是两套不同统计对象,
   不要混用);`counterfactual_report` 函数 docstring 追加一句,明确只统计
   `avg_strategy_return`/`hit_rate`,不含 alpha。
5. **F3**(`btc_agent/src/btc_agent/default_config.py`,仅新增键):
   `DEFAULT_CONFIG` 显式声明 `"ledger_enabled": True`(带注释说明只被 CLI
   入口 `_build_default_ledger_recorder` 读取,`run_daily()` 库函数本身不受
   影响)。`btc_agent/tests/test_daily.py` 新增两条单测:
   `test_build_default_ledger_recorder_returns_none_when_ledger_disabled`
   (关闭路径 → None)与
   `test_build_default_ledger_recorder_wires_up_when_enabled`(对照组,启用时
   返回可调用 recorder)。

## Files Touched
- `C:\Users\admin\Desktop\wt-contract-backfill\workflow\config.json`
- `C:\Users\admin\Desktop\wt-contract-backfill\workflow\checks\verification.md`
- `C:\Users\admin\Desktop\wt-contract-backfill\btc_agent\src\btc_agent\default_config.py`
- `C:\Users\admin\Desktop\wt-contract-backfill\btc_agent\src\btc_agent\settlement.py`
- `C:\Users\admin\Desktop\wt-contract-backfill\btc_agent\tests\test_settlement.py`
- `C:\Users\admin\Desktop\wt-contract-backfill\btc_agent\tests\test_daily.py`

## Verification Run
- maker checks(均从 `C:\Users\admin\Desktop\wt-contract-backfill\btc_agent`,
  用主仓共享 venv `C:/Users/admin/Desktop/btc/btc_agent/.venv`,全离线):
  - `python -m ruff check .` → All checks passed!
  - `python -m pytest` → 183 passed(既有 180 + F1 1 条 + F3 2 条)
- checker gates(契约漂移):
  - `check_contract_touchpoints.py`(worktree-aware,`project_root()` 走
    `git rev-parse --show-toplevel`,能正确识别我这个 worktree 的 diff):
    在提交前的工作区差异上跑,`OK: contract-relevant diff detected and
    structural touchpoints still look intact`,退出码 0。
  - **验牙测试**(AC 要求项):临时把 `daily.py` 里唯一一处
    `regime_result.blank_sheet` 改成 `regime_result.blankSheetTEMP`(该
    字符串在文件中仅出现 1 次,可控破坏),重跑
    `check_contract_touchpoints.py` → `ERROR: ...(missing: blank_sheet)`,
    退出码 1(FAIL,断言真的有牙齿)。随即改回原字面量,`git diff` 确认
    `daily.py` 无残留差异,重跑同一命令 → 恢复 `OK`,退出码 0(PASS)。
  - `check_env_consistency.py` → `OK: environment-facing defaults are
    internally consistent`,退出码 0。
  - `run_contract_drift.py`(按 launch prompt 指示,在 worktree 根目录用主仓
    venv python 运行)→ `decision=NO_ACTION`,退出码 0。**需要向复验方标注一个
    工具行为细节**:该脚本内部对 `check_contract_touchpoints.py` 的子进程调用
    显式传了 `cwd=main_root()`(`_lib.main_root()` 取 `git worktree list` 的
    第一条,恒为主检出 `C:\Users\admin\Desktop\btc`),所以
    `run_contract_drift.py` 实际检查的是**主检出的工作区 diff**,不是我这个
    子任务 worktree 的 diff——主检出当前 clean,故报 `NO_ACTION` 是预期结果,
    不代表我的 worktree 改动被漏检;真正对我 worktree diff 生效的是上面直接
    调用的 `check_contract_touchpoints.py` / `check_env_consistency.py`
    (两者用 `project_root()`,worktree-aware)。ST7 合入主检出/task 分支后,
    `run_contract_drift.py` 会在那个上下文里正确覆盖这批新断言。

## Risks / Follow-ups
- 无新增源码逻辑改动,风险面很小。唯一需要复验方留意的是上面记录的
  `run_contract_drift.py` vs `check_contract_touchpoints.py` 的 cwd 差异
  (工具本身行为,非本子任务引入),独立复验时如果直接跑
  `run_contract_drift.py` 而不 cd 进任何 worktree,得到的是主检出快照的结果——
  这是脚本设计如此,不是本次改动的缺陷。
- `ledger.py` 的 must_contain 用了中文字面量 `"旧版本行及其结算数据只读"`
  (模块 docstring 原文),比英文关键字更贴合"描述现状"的要求,但若未来该
  docstring 措辞被人工改写(即使语义不变),这条断言会误报——这是描述性断言
  的固有代价,已选用当前最稳定、最不像会被顺手改掉的一段原文。

## Notes For Reviewer
- 未触碰任何源码逻辑,`settlement.py` 的改动限定在 docstring(F2 要求零逻辑
  改动,已核对 diff 只增加注释段落)。
- `workflow/config.json` 的三处增补(surface_markers/structural_checks/
  env_consistency)均为纯增补,原有 4 条 structural_checks 条目与 1 条
  env_consistency 规则字面量未改一个字符(除 schemas.py 那条按 spec 要求
  "加进现有该文件条目"追加了一个 must_contain 元素,原有三个 must_contain
  元素保留)。
- 验牙测试记录见上方 Verification Run,已确认恢复现场(`git diff` 确认
  `daily.py` 无残留改动,最终提交里 `daily.py` 不在改动文件列表中)。
