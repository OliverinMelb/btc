# Task Brief — v0: fork TradingAgents → BTC 单资产日度研判

## Goal
把 TradingAgents(TauricResearch/TradingAgents, main 分支)vendored 进 `btc_agent/`，
改装成能对**单一资产 BTC** 产出一条**结构化日度研判记录**(方向评级 + 理由 + 机械算出的
交易参考价位)并写入 markdown 记忆日志的最小可运行系统。**不接实盘、不执行、不下单。**

这是 `BTC-DESIGN-REVIEW.md` 路线表里的 v0；晋级 v1 的条件即本任务的验收标准。

## Scope
- agent(btc_agent/):
  - vendored TradingAgents 的 `graph/`(LangGraph 编排)、`agents/`(角色+prompt)、
    `dataflows/`(vendor 路由骨架)、`default_config.py`、schemas、memory/reflection。
  - 新增 crypto vendor: `ccxt_vendor.py`(行情/OHLCV,v0 必需)；CryptoPanic/F&G vendor
    列为可选(v0 可先跳过,留 v1 情报层)。
  - 禁用 fundamentals 系分析师与 balance_sheet/cashflow/income_statement 路由。
  - 交易日历改 7×24 UTC 连续时间(去休市日修正);benchmark 改 BTC-HODL。
  - prompt 微调:研究经理"别动辄 Hold" → "环境不明确时交白卷优于硬凑"(白卷文化)。
- shared contract: dataflows vendor 接口 + agents 输出 schema(本任务里首次成形,
  完成后回填 config.json 的 contract_touchpoints)。
- 不在本任务: freqtrade 接入、实盘、反事实归因、策略版本状态机(留 v2/v3)。

## Constraints
- 机械规则出候选和交易价位,**LLM 只输出方向评级+理由,绝不报买卖数字**(schema 强约束)。
- 双模型分层(deep/quick)复用 TradingAgents 现成机制,别所有环节用最强模型(控 API 成本)。
- **环境事实**(引用 ~/.claude/workflow-memory/environment.md):
  - 裸 `python` 是 Store 别名,用 venv 的 `.venv\Scripts\python.exe` 或 `$WORKFLOW_PYTHON`。
  - 装依赖显式 `--index-url https://pypi.org/simple`(清华镜像在 VPN 下 SSL EOF)。
  - 含中文的 config/JSON 存 UTF-8 with BOM(PS 5.1 Get-Content 按 GBK 误读)。
  - TradingAgents 重依赖(langgraph/langchain/ccxt)逐步加进 pyproject `[project].dependencies`,
    bootstrap 会自动同步安装;先加最小可跑子集。
- LLM key 走 .env(不进 git);v0 用哪个 provider 由实现时按可用 key 决定(OpenAI 兼容端点优先)。

## Verification Plan(每条可验证)
1. `btc_agent/.venv\Scripts\python.exe -m pytest` 全绿(含新增 vendor/日历的单测)。
2. `ruff check .` 通过。
3. 存在一条可运行的入口(如 `python -m btc_agent.run --asset BTC --date <UTC日>`),
   执行后在记忆日志文件里**新增一条结构化记录**,字段含:资产、UTC 时点、方向评级
   (5 档枚举)、理由文本、机械算出的入场区间/止损/目标(数值来自规则不来自 LLM)。
4. fundamentals 分析师与其 4 个财报路由已禁用(grep 确认不在 active 路由表)。
5. 日历为连续 UTC:look-back 窗口对"周六"这类股票休市日不跳过(单测覆盖)。
6. benchmark alpha 计算基准为 BTC-HODL(非 SPY/区域指数)。

## Stop Conditions
- 若 vendored TradingAgents 的 crypto 路径与文档描述不符(如 asset_type 实际未贯通),
  停下报告实情,别硬改编排。
- 若 v0 最小依赖子集仍装不动(网络/代理),停下报告,不擅自换镜像反复试。
- 触及实盘/下单/杠杆逻辑一律停(超出 v0 范围)。

## Notes
- 设计依据: 仓库根 `BTC-DESIGN-REVIEW.md`(第五节"v0 立刻能做的改装清单"具体到文件)。
- TradingAgents main 已原生支持 crypto(asset_type / resolve_instrument_context /
  symbol_utils / Polymarket),优先复用而非重写。
- 其"回测"只是记忆日志重跑、不可复现,**不能当回测数**,真回测留 v3 freqtrade。

## Task
v0-fork-ta

## Workflow
agent-change
