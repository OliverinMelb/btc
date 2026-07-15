# Subtask Summary

## Parent Task
20260715-133420-v0-fork-ta（v0: fork TradingAgents → BTC 单资产日度研判）

## Subtask
vendor-core（ST1）

## Worktree
- path: C:\Users\admin\Desktop\wt-vendor-core
- branch: subtask/vendor-core

## Outcome
- status: pass
- reviewer recommendation: pass

## What Changed
本轮是收尾轮（前一轮子代理已完成绝大部分拷贝+改名+依赖安装），本轮只做剩余 3 项：

1. 新增 `btc_agent/src/btc_agent/VENDORED.md`：记录来源（TauricResearch/TradingAgents，
   `main` 分支 tarball，编排者预下载到本机临时目录，非 git clone 故无逐 commit 元数据）、
   逐文件拷入清单（graph/agents/dataflows/llm_clients/default_config.py/reporting.py/
   LICENSE）、未拷清单（cli/main.py/scripts/tests/assets 等仓库级工具与脚手架，非
   `tradingagents/` 包本体）、包名处理方式（`tradingagents`→`btc_agent` 全量改名，已用
   Grep 核实仓库内 0 处 `tradingagents` 残留）、已知未验证风险（langgraph 1.x vs 上游原
   pin 0.4.x 的运行时兼容未验证；dataflows 整包拷入含 v0 用不到的路由，留给 ST2）。
2. 新增冒烟单测 `btc_agent/tests/test_vendored_import.py`：断言 `import btc_agent` 与
   `from btc_agent.graph.trading_graph import TradingAgentsGraph, GraphSetup` 均 import
   成功，不实例化 graph、不调 LLM、不联网。实测导入过程中未触发任何强依赖缺失（未用到
   `pytest.importorskip`，也未需要额外补依赖到 pyproject——前一轮装的依赖子集已经够用）。
3. 跑了 ruff 与 pytest 两个检查，均一次通过，**未需要**在 `pyproject.toml` 里加
   `extend-exclude` 排除 vendored 目录（vendored 代码本身已经是 ruff-clean 的，没有触发
   既有告警）。因此本轮未改动 pyproject 的 `[tool.ruff]` 配置。

未触碰：日历/look-back 逻辑、ccxt vendor 编写、`default_config.py` 的 LLM/基准值。

## Files Touched
- `btc_agent/src/btc_agent/VENDORED.md`（新增，本轮唯一实质新增文件）
- `btc_agent/tests/test_vendored_import.py`（新增，本轮唯一实质新增文件）
- 以下为前一轮已完成、本轮未改动但需在此列出以便编排者核对完整改动面（均为 vendored
  骨架文件，未在本轮触碰）：`btc_agent/pyproject.toml`（依赖声明）、
  `btc_agent/src/btc_agent/__init__.py`（.env 加载样板）、
  `btc_agent/src/btc_agent/{graph,agents,dataflows,llm_clients}/`、
  `btc_agent/src/btc_agent/default_config.py`、`btc_agent/src/btc_agent/reporting.py`、
  `btc_agent/src/btc_agent/THIRD_PARTY_LICENSES/TradingAgents-LICENSE`

## Verification Run
- maker checks（均在 `C:\Users\admin\Desktop\wt-vendor-core\btc_agent` 目录下，用
  `C:\Users\admin\Desktop\btc\btc_agent\.venv\Scripts\python.exe`）：
  - `python -m ruff check .` → `All checks passed!`（PASS）
  - `python -m pytest -q` → `3 passed in 1.15s`（PASS；含新增 2 个 vendored-import 测试 +
    原有 `test_smoke.py` 的 1 个）
- checker gates: 无（config 里 v0 契约面尚未成形，符合 spec）
- independent re-verify: 未做（按规则由编排者独立跑 task-verify 复验，本子代理自查不计数）

## Risks / Follow-ups
- **langgraph 版本差异未做运行时验证**：上游 TradingAgents 原 pin `langgraph` 0.4.x 系列，
  本项目 pyproject 未锁版本，共享 venv 实际装的是 1.2.9。本子任务只验证了
  `import btc_agent.graph.trading_graph` 能成功（类定义/导入期语法兼容），**没有实例化
  `TradingAgentsGraph` 或跑一次真实的 graph 编排**，所以 `StateGraph`/`add_conditional_edges`
  等 API 在 1.x 下的行为是否与 0.4.x 一致仍是未知数。建议 ST4（跑通编排/config-run）落地
  第一个真实调用时重点盯这里，若报 API 不兼容，回来 VENDORED.md 记录的风险节里补丁。
- `dataflows/` 是整包拷入（含 alpha_vantage/fred/reddit/polymarket/stocktwits 等 v0 不需要
  的路由），只保证能被 import，不保证其内部逻辑在无对应 API key 时可运行；ST2（ccxt-vendor）
  会视需要精简/替换。
- VENDORED.md 里的"来源 commit"因为是 tarball 而非 git clone，没有精确 commit hash 可查；
  如果后续需要精确追溯上游代码版本（例如上游修了某个已知 bug 需要对比是否已包含），需要
  重新走一遍 git clone 流程补记 commit hash。这不阻塞 v0，但留痕以免以后有人以为记录不全是
  疏漏。

## Notes For Reviewer
- 验证 VENDORED.md 里"包名全量改名、0 残留"的结论时可直接跑
  `rg tradingagents C:\Users\admin\Desktop\wt-vendor-core\btc_agent\src` 复核（本子代理已用
  等价的 Grep 工具核实为空）。
- 复验 ruff/pytest 时请务必 `cd` 到 `wt-vendor-core\btc_agent`（不是仓库根），否则
  `pyproject.toml` 的 `testpaths`/`pythonpath` 相对路径解析会出错，会得到与本报告不一致的
  假阴性结果。
- Acceptance Criteria 逐条核对：pyproject 最小依赖子集已在（PASS，前一轮完成）；
  vendored 模块可 import（PASS，本轮新增测试验证）；ruff 通过（PASS）；pytest 通过（PASS）；
  VENDORED.md 记录来源/拷入/删除清单（PASS，本轮新增）；强依赖隔离/补齐（PASS，未触发该
  情形，无需额外动作）。
