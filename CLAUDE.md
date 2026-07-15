# BTC Agent — 项目说明（每会话加载）

BTC 信息检索→决策→(模拟)交易 agent，架构基座是 **TradingAgents**（LangGraph 多 agent 辩论
+ 记忆/反思闭环）改装：数据源换 crypto vendor（ccxt / CryptoPanic / F&G），交易日历改 7×24 UTC。

## 设计文档（动手前先读）
- `BTC-AGENT-FEASIBILITY.md` — 可行性调研与晋级制路线（v1→v4）
- `BEACON-FEATURE-REFERENCE.md` — A股 TradingAgents 产品(烛塔 Beacon)功能拆解，产品化参照
- `BTC-DESIGN-REVIEW.md` — **设计完整性评估 + 修订后 v0→成熟版路线**（含 v0 改装清单，以此为准）

## 核心原则（写进代码和 prompt）
- **机械规则出候选和交易价位，LLM 只做裁决**（辩论/点将/点评三个点），绝不让 LLM 报买卖数字。
- **白卷文化**：环境不明确时交白卷优于硬凑（与 TradingAgents 默认"别动辄 Hold"相反，需反向调 prompt）。
- **不让 LLM 直接下单**；v4 之前只做现货信号，执行/回测交给 freqtrade。
- 反事实归因 + 策略版本状态机（实验→前向验证→已验证）自证价值，不靠自觉靠机制。

## 开发协议
本项目用 ai-workflow 多代理协议。新需求走 `/task-new` 分级路由；配置见 `workflow/config.json`，
协议见 `workflow/README.md`。代码在 `btc_agent/`（Python，src 布局；检查：ruff + pytest）。
