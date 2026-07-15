# Subtask Spec

## Parent Task
20260715-133420-v0-fork-ta（v0: fork TradingAgents → BTC 单资产日度研判）

## Subtask Title
ST1 — vendor 核心模块 + 最小依赖就位（基础，阻塞 ST2-ST4）

## Owner Role
agent-change

## Goal
把 TradingAgents(TauricResearch/TradingAgents, **main 分支**)的核心模块**选择性拷贝**进
`btc_agent/src/btc_agent/`，加最小可运行依赖进 pyproject，使 bootstrap 通过、能 import 顶层
LangGraph 编排构造、冒烟单测绿。**本子任务只搬骨架、不改业务逻辑、不接数据源、不改日历。**

## Scope
- 允许触碰:
  - `btc_agent/pyproject.toml`（`[project].dependencies` 加最小子集）
  - `btc_agent/src/btc_agent/`（新增 vendored 模块目录）
  - `btc_agent/tests/`（新增冒烟单测）
- 选择性拷贝的目标模块（从 TradingAgents main 的 `tradingagents/`）:
  `graph/`(setup/conditional_logic/propagation/trading_graph/signal_processing/reflection)、
  `agents/`(analysts/researchers/managers/risk_mgmt/trader/utils 含 memory.py/agent_states.py/schemas.py)、
  `dataflows/`(interface.py 路由骨架 + 现有 vendor 文件,可先全带后续删)、`default_config.py`。
- **禁止触碰**: 日历/look-back 逻辑改写(ST3)、写 ccxt vendor(ST2)、default_config 的 LLM/基准值
  改写(ST3/ST4)、run 入口(ST4)、仓库根的设计 md、workflow/config.json。
- 保留原始 licence/版权头;在 `btc_agent/src/btc_agent/` 顶层加一个 `VENDORED.md` 记录来源
  commit、拷了哪些、删了哪些。

## Dependencies
- depends-on: []
- provides-to: [ccxt-vendor(ST2), calendar(ST3), config-run(ST4)]

## Inputs
- parent spec: workflow/tasks/20260715-133420-v0-fork-ta/spec.md
- 设计依据: 仓库根 BTC-DESIGN-REVIEW.md（第一节 TradingAgents 架构、第五节 v0 改装清单）
- 环境事实: ~/.claude/workflow-memory/environment.md（python 别名/PyPI 源/BOM/依赖同步）
- **TradingAgents 源码已在本地就绪**（编排者已下载 main 分支解压，避免子代理联网）:
  `C:\Users\admin\AppData\Local\Temp\claude\C--Users-admin-Desktop-btc\149325a3-6d36-44c3-b415-4d10bc82d3a8\scratchpad\TradingAgents`
  —— 从这里的 `tradingagents/` 与 `pyproject.toml` 拷贝，**不要自己 git clone / 联网抓取**。
  拷贝时把包名从 `tradingagents` 归一到 `btc_agent`（import 路径随之改），或作为
  `btc_agent` 的子包引入——选其一并在 VENDORED.md 说明。

## Acceptance Criteria
- [ ] `btc_agent/pyproject.toml` 的 dependencies 增加最小子集(至少: langgraph, langchain-core,
      langchain-openai, pydantic, pandas, pytz, stockstats, ccxt),bootstrap.ps1 跑通(venv 就绪)
- [ ] vendored 模块落在 `btc_agent/src/btc_agent/` 下,`import btc_agent` 及顶层 graph 构造类
      可被 import(冒烟单测断言 import 成功,不实际调 LLM/网络)
- [ ] `ruff check .` 通过
- [ ] `pytest` 通过(含新增冒烟 import 单测 + 原有 test_smoke)
- [ ] `btc_agent/src/btc_agent/VENDORED.md` 记录: 源 repo+commit、拷入清单、删除清单
- [ ] 若拷入的模块 import 时强依赖尚未装的重依赖(如 langchain-anthropic/google),要么补进
      dependencies、要么在冒烟测里隔离,不得让 import 直接失败

## Verification
- maker checks: ruff、pytest（config.json 的 agent 类）
- checker gates: 无（v0 契约面尚未成形）
- independent re-verify: 由编排者跑 task-verify，不由本子代理自证

## Stop Conditions
- vendored 后发现 main 分支 crypto 路径(asset_type 贯通)与 BTC-DESIGN-REVIEW 描述明显不符
  → 停下，在 summary 里报告实情，不硬改编排。
- 最小依赖在本机(VPN 代理)反复装不动(SSL EOF/ECONNRESET)→ 停下报告，按 environment.md
  已知手段试一次(显式 pypi.org 源),仍不行则停，不反复换镜像。
- 需要改日历/写 vendor/改 LLM 配置才能让 import 通过 → 说明拷贝边界划错，停下报告，别越界到 ST2-4。

## Parent Task
20260715-133420-v0-fork-ta

## Subtask Title
vendor-core

## Recommended Workflow
agent-change
