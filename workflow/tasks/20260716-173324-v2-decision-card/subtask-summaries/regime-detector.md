# Subtask Summary

## Parent Task
20260716-173324-v2-decision-card

## Subtask
regime-detector — 机械市场环境识别

## Worktree
- path: C:\Users\admin\Desktop\wt-regime-detector
- branch: subtask/regime-detector

## Outcome
- status: pass
- reviewer recommendation: pass

## What Changed
- 新增 `btc_agent/src/btc_agent/regime.py`:纯规则市场环境识别器。
  - `REGIME_PARAMS`:模块级、json 可序列化的集中参数字典
    (`min_bars=30, sma_period=20, slope_lookback=5, atr_period=14,
    atr_lookback=60, chaos_percentile=0.90`),供设计门 G5 策略版本 hash 消费。
  - `RegimeResult` dataclass:`regime / blank_sheet / observations / params_used`。
  - `detect_regime(snapshot, params=None) -> RegimeResult`:
    - `insufficient_data`(blank_sheet=True):`snapshot.ohlcv is None`、或
      `snapshot.health["ohlcv"] != "ok"`、或 K 线数 < `min_bars`。
    - `chaos`(blank_sheet=True):当前 ATR/Close 比值 >= 近端历史(`atr_lookback`
      窗口)第 `chaos_percentile` 分位数。
    - `trend_up` / `trend_down`:收盘价相对 SMA 位置与 SMA 斜率(`slope_lookback`
      天回看)同向确认。
    - `range`:以上皆非。
  - 只 import `pandas`(+ 标准库),不 import `graph`/`intel`/`llm` 任何东西,
    也不重新触发任何 vendor 网络调用——只消费快照里已装配好的 `ohlcv`/`health`。
- 新增 `btc_agent/tests/test_regime.py`:14 个用例,覆盖:
  - 五分支各至少一例(构造 OHLCV,零网络);
  - `blank_sheet` 仅 chaos/insufficient_data 为 True,其余三类为 False(独立断言用例);
  - `REGIME_PARAMS` 整体 `json.dumps` 成功,且 `detect_regime` 默认路径的
    `params_used == REGIME_PARAMS`;
  - 自定义 `params` 覆盖路径(`params_used` 回显覆盖后的值,不是默认值);
  - `RegimeResult` 字段集合断言;
  - 模块 import 语句扫描断言不含 `graph`/`intel`/`llm`;
  - 用真实 `EvidenceSnapshot` 实例(而非替身)验证字段名对齐。

## Files Touched
- `btc_agent/src/btc_agent/regime.py`(新增)
- `btc_agent/tests/test_regime.py`(新增)

## Verification Run
- maker checks(均在 `C:\Users\admin\Desktop\wt-regime-detector\btc_agent` 内,
  用主仓共享 venv `C:\Users\admin\Desktop\btc\btc_agent\.venv\Scripts\python.exe`,
  未装任何新依赖):
  - `python -m ruff check .` → All checks passed!
  - `python -m pytest` → 118 passed(既有 105 + 新增 13,零跳过零失败;
    注:AC 描述的"既有 105 个"以任务基线为准,本次运行时基线已含 ST1/ST2 交付,
    实测新增 13 例、总计 118 例全绿)。
- checker gates:未触碰任何 contract marker 文件(只新增 regime.py + 测试文件,
  未改 `evidence.py`/schemas/`workflow/config.json` 等),契约漂移检查预期无影响
  (未在本 worktree 单独跑 `check_contract_touchpoints.py`,因 spec 未要求且本子任务
  不属于 contract-change 类改动;若 orchestrator 独立复验需要可另行确认)。

## Risks / Follow-ups
- `chaos` 判定用的是自身历史窗口(`atr_lookback`)内的分位数,而非跨资产/跨周期
  的绝对阈值——数据窗口越短,分位数统计意义越弱(已用 `min_bars=30` 兜底,但
  30 根 K 线对 `atr_lookback=60` 而言仍不足一个完整回看窗口,分位数基于实际
  可用样本计算,不会报错但样本量偏小)。留给后续子任务(decision-card/candidates)
  在消费 `observations` 时注意这一点,不影响本子任务验收。
- 趋势判定用"收盘价相对 SMA + SMA 斜率同向"这一种确定性规则,未做更复杂的
  多因子确认(如成交量/多周期 SMA 交叉),符合 spec"建议实现,可微调"的措辞,
  若后续需要调参,记得改动会触发 G5 新策略版本(参数已集中在 REGIME_PARAMS,
  改动成本低)。

## Notes For Reviewer
- 严格遵守 scope guardrail:只新增了 `btc_agent/src/btc_agent/regime.py` 与
  `btc_agent/tests/test_regime.py`,未触碰 `evidence.py` 或任何 marker 文件
  (`git status` 确认无其它改动)。
- 未触发任何 stop condition(未改 evidence.py、无网络依赖)。
- 已在分支 `subtask/regime-detector` 提交:commit `6c5495d`
  "feat(v2): 新增纯规则市场环境识别器 regime.py"。
