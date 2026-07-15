# Subtask Summary — config-run (ST4)

## 执行者说明
承 ST2/ST3:子代理 API 不稳,本子任务由编排者主会话实现;独立门禁由 `verify_subtask.ps1`
机械重跑(见 .verify.md)。**真 key + 真交易所端到端未跑**(需用户的 DEEPSEEK_API_KEY),
是本子任务刻意留给用户的一步。

## What changed
1. `default_config.py`：`llm_provider`→"deepseek"、deep→"deepseek-v4-pro"、quick→"deepseek-v4-flash"
   (base_url 自动、key 走 DEEPSEEK_API_KEY,均内置 provider)。
2. `agents/managers/research_manager.py`：把 anti-Hold 一段反调为**白卷文化**——BTC 7×24 高波动,
   环境不明确/证据薄时 Hold(白卷)优于硬凑方向,只在辩论强论据支持时才给方向。
3. 新增 `trade_levels.py`：`compute_trade_levels(ohlcv, direction)` 纯确定性(ATR(14) + 1.5/3.0
   风险距离),`rating_to_direction` 把 5 档评级映射 long/short/flat。**不接触任何 LLM 文本。**
4. 新增 `run.py` + `__main__.py`：`python -m btc_agent.run --asset BTC --date <UTC日>`。
   构造 market-only crypto 图 → propagate(记忆日志落 rating+reasoning) → ccxt OHLCV 算机械价位 →
   `build_structured_record` 汇成 JSON 写 results_dir/records/。`run(graph=...)` 可注入便于离线测。

## Files touched
- 改: `default_config.py`、`agents/managers/research_manager.py`
- 新增: `trade_levels.py`、`run.py`、`__main__.py`、`tests/test_trade_levels.py`、`tests/test_run_record.py`

## 检查(共享 venv python 实跑)
- `ruff check .` → All checks passed!
- `pytest -q` → 25 passed(ST1 3 + ST2 7 + ST3 5 + ST4 10)
- `python -m btc_agent.run --help` → 正常(需 `PYTHONPATH=src`,见下)。

## 机械价位铁律的固化
`test_run_record.py::test_price_levels_independent_of_llm_wording`：同 date 同 rating、**不同 LLM
措辞** → entry/stop/target 完全一致,证明价位来自机械规则而非 LLM。`test_trade_levels.py` 另测
确定性、多空对称、flat 无方向价位。所有测试 mock `ccxt_vendor._fetch_ohlcv_raw` 与注入 FakeGraph,
**不联网、不调 LLM**。

## Open risks / follow-ups
- **待用户端到端**:设 `DEEPSEEK_API_KEY` 后跑
  `PYTHONPATH=src python -m btc_agent.run --asset BTC --date <今日UTC>`;langgraph 1.x 运行时兼容
  (承自 ST1)在此首次真验;ccxt 真实 binance 连通(承自 ST2)在此首次真验。
- **`-m` 需 `PYTHONPATH=src`**:src 布局未 pip 安装;真实部署可 `pip install -e btc_agent` 免此。
  已在 run 说明与本 summary 注明,未擅自改 bootstrap。
- 机械价位公式(ATR 1.5/3.0)是 v0 最简版,留 v2 精修;alpha 退化(ST3)仍是已知 v0 局限。

## Reviewer recommendation
pass（离线实现完成、检查全绿、6 条验收中 5 条离线达标;第 6 条"真 key 端到端"按设计留用户手动一步）
