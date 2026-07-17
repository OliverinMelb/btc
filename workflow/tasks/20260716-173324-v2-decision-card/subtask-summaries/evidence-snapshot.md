# Subtask Summary

## Parent Task
20260716-173324-v2-decision-card

## Subtask
evidence-snapshot — 统一证据快照

## Worktree
- path: C:\Users\admin\Desktop\wt-evidence-snapshot
- branch: subtask/evidence-snapshot

## Outcome
- status: pass
- reviewer recommendation: pass

## What Changed
- 新增 `btc_agent/src/btc_agent/evidence.py`:`EvidenceSnapshot` dataclass
  (`asset`/`curr_date`/`ohlcv`/`news`/`fear_greed`/`derivatives`/`health`/
  `snapshot_id`/`frozen_at_utc`) 与 `build_evidence_snapshot(asset, curr_date)`。
  四个源(ccxt OHLCV、crypto RSS 新闻、feargreed、derivatives)各自 try/except,
  失败只记 `health["<source>"] = "error:<原因>"`,不整体崩(与 dashboard.py 既有
  降级哲学一致)。`snapshot_id` 形如 `BTC-<date>-<8位hash>`。
- `btc_agent/src/btc_agent/intel/dashboard.py`:`build_dashboard` 新增可选
  `snapshot` 参数(缺省自建),改为从快照装配四个信号;对外 dict 结构
  (`fear_greed`/`derivatives`/`rsi`/`price_move_pct`/`close`/`errors`)与
  `errors` 里纯 reason 文本格式**保持不变**(剥掉快照 health 里的 `error:` 前缀)。
  价格信号(`close`/`rsi`/`price_move_pct`)现由快照里的同一份 OHLCV 算出,不再
  独立触发 vendor 调用。
- `btc_agent/src/btc_agent/run.py`:第 97 行附近的 `_ohlcv_dataframe` 直调改为
  从快照读(新增可选 `snapshot` 参数注入,缺省自建);快照 OHLCV 缺失时原样
  `raise`(机械价位离不开真实行情,不像 dashboard 那样降级)。
  `compute_trade_levels` 调用、`"mechanical (ATR-based), not LLM"` 字样、
  `DEEPSEEK_API_KEY` 校验均原样保留(未改动那部分代码,已有回归测试断言存在)。
- 新增 `btc_agent/tests/test_evidence.py`:覆盖快照全绿装配、同一快照对象上
  dashboard 与 trade_levels 消费同一 OHLCV(vendor 调用计数=1)、单源失败(F&G)
  降级不崩、OHLCV 失败时 dashboard 降级 vs run() 原样重新抛出、run.py 契约
  不变式(源码文本断言)。

范围裁定(设计门 G3):研判图 ToolNode 图内取数路径本次未改动,`dataflows/` 下
vendor 文件、`interface.py`、`agents/schemas.py`、`intel/rules.py`、
`intel/push.py`、`intel/run_intel.py`、`graph/` 均未触碰。

## Files Touched
- `btc_agent/src/btc_agent/evidence.py`(新增)
- `btc_agent/src/btc_agent/intel/dashboard.py`(改)
- `btc_agent/src/btc_agent/run.py`(改)
- `btc_agent/tests/test_evidence.py`(新增)

## Verification Run
- maker checks(均在 `btc_agent/` 目录下,离线,`.venv\Scripts\python.exe`):
  - `python -m ruff check .` → All checks passed
  - `python -m pytest` → 89 passed(既有全部单测保留并通过,新增 test_evidence.py
    7 条用例全部通过,零跳过零失败)
- checker gates: 未运行(orchestrator 独立复验范围;本子代理未跑
  `workflow/scripts/verify_subtask.ps1`)

## Risks / Follow-ups
- 研判图 ToolNode 取数路径未并入快照,记 backlog v2.5(design-review 已裁定,
  非本子任务遗漏)。
- `evidence.py` 的新闻窗口(`start_date`/`end_date`)复用了
  `global_news_lookback_days` 配置项(默认 7 天),未新增专属配置键;如后续
  decision-card 需要不同的新闻回看窗口,可在快照层加参数覆盖。
- `derivatives_vendor.get_derivatives_snapshot_data` 本身拒绝非当日的历史
  `curr_date` 请求(既有 as-of 防护,未改动);快照对该行为原样透传到
  `health["derivatives"]`,回看历史日期时衍生品盘面会记为 error,属预期行为
  而非本次改动引入的回归。

## Notes For Reviewer
- 未触碰 spot-settlement 子任务负责的 `graph/trading_graph.py`、
  `reflection.py`、`memory.py`,无合并冲突面。
- `dashboard.py` 对外 dict 结构与 `errors` 文本格式做了逐字段比对以保证
  `rules.py`/`test_intel_run.py` 消费不受影响(后者 mock 了 `build_dashboard`
  本身,未依赖内部实现)。
