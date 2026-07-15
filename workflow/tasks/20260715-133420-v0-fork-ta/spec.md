# Task Spec — v0: fork TradingAgents → BTC 单资产日度研判

## Requirement
在 `btc_agent/` 里得到一个最小可运行系统:对 BTC 产出一条结构化日度研判记录(方向评级+理由
+机械价位)并落 markdown 记忆日志。基座复用 TradingAgents(main, 已原生支持 crypto)。

## Problem Statement
TradingAgents 面向美股/A股:有 fundamentals 分析师、按交易日历(含休市)组织 look-back、
benchmark 是 SPY/区域指数、数据源是 yfinance/AlphaVantage/FRED。BTC 是 7×24 连续时间、
无财报基本面、需交易所行情与衍生品指标。需在保留其编排/辩论/记忆闭环的前提下完成改装。

## Desired Outcome
`python -m btc_agent.run --asset BTC --date <UTC日>` 跑通 LangGraph 编排(v0 仅 market 分析师
→ 多空辩论 → 研究经理 → 交易员 → 风控三辩 → 基金经理终裁),终裁经确定性解析得到 5 档评级,
交易价位由机械规则算,整条写入记忆日志。

## Affected Surfaces
- agent 代码: btc_agent/src/btc_agent/{graph,agents,dataflows,schemas,memory,config,run}
- contract: dataflows vendor 接口 + agents 输出 schema(首次成形)
- docs/workflow: 完成后回填 config.json 的 contract_touchpoints / env_consistency

## Acceptance Criteria
- [ ] pytest 全绿(新增 vendor + 日历 + run 的单测,LLM 可 mock)
- [ ] ruff check 通过
- [ ] run 入口执行后记忆日志新增一条结构化记录,字段: 资产/UTC时点/5档评级/理由/入场区间/止损/目标
- [ ] 交易价位数值来自机械规则(单测断言:改 LLM 输出不改价位)
- [ ] fundamentals 分析师与 4 个财报路由已禁用(grep 确认)
- [ ] look-back 对股票休市日(如周六)不跳过(单测)
- [ ] benchmark alpha 基准为 BTC-HODL

## Decisions(用户已定/默认)
- LLM provider: **DeepSeek**(OpenAI 兼容端点; default_config backend_url 指向 DeepSeek, key 走 .env)
- Vendor 策略: **选择性拷贝**需要的模块进 src,删股票专用件(默认,可改)
- 分析师范围: **v0 仅 market 分析师**(ccxt 行情);news/sentiment 留 v1(默认,可改)

## Non-Goals
freqtrade / 实盘 / 下单 / 杠杆 / 反事实归因 / 策略版本状态机 / CryptoPanic·F&G vendor(v1)。

## Risks
- vendored 后 crypto 路径(asset_type 贯通)可能与文档不符 → 停下报告实情(见 Stop Rules)。
- langgraph/langchain 重依赖装机风险(VPN 代理)→ 显式 PyPI 默认源,先装最小子集。
- DeepSeek 结构化输出/reasoning 参数与 TradingAgents 的 provider 注入是否兼容需实测。
- 单资产宇宙下"多空辩论"是否退化(无横向比较)→ v0 接受,记录观察。

## Open Questions
- DeepSeek 是否稳定支持 TradingAgents 依赖的结构化输出(Pydantic 强约束)?实现时验证,
  不行则退到 prompt+确定性解析。
- 交易价位机械规则的具体公式(入场区间/止损/目标)v0 用什么(ATR? 近期高低点?)→
  实现时选最简单可解释的一种并单测,留 v2 精修。

## Task
v0-fork-ta
