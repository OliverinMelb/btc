# BTC Agent 设计完整性评估 & v0→成熟版路线（2026-07-15）

> 三方交叉：`BTC-AGENT-FEASIBILITY.md`（你的路线）× TradingAgents main 分支**真实源码** ×
> `BEACON-FEATURE-REFERENCE.md`（A股产品化参照）。
> 结论先行：**路线方向对，但有一个过时假设要纠正、四个关键机制缺失要补、一批 BTC 专有工程要加。**

---

## 〇、最重要的纠正:TradingAgents 已原生支持 crypto

FEASIBILITY 文档写"移植到 BTC 需要把数据适配层整个换掉"——**这个判断基于论文版,已过时。**
main 分支实测：

- agent（bull_researcher 等）已接收 `asset_type`（"stock or crypto"）参数；
- `trading_graph.py` 有 `resolve_instrument_context`，`dataflows/` 有 `symbol_utils`；
- 数据层是 **vendor 路由抽象**（`route_to_vendor` + `tool_vendors` 覆盖），换数据源是配置+新增 vendor 模块，**不是重写编排**；
- 已接 Polymarket 预测市场（对加密事件驱动尤其有用）。

**影响**：你不是"抄架构自己重写"，而是 **fork + 换 vendor + 改日历**。工作量从"重建"降到"改装"，v0 能更快落地。整个 `graph/`（LangGraph 编排、双模型路由、辩论轮次逻辑）、5 类 agent 的 prompt 模板、结构化输出 schema、记忆/反思闭环——**全部与标的无关，直接复用**。

---

## 一、TradingAgents 真实架构（你要接手的骨架）

| 层 | 实现 | 复用性 |
|---|---|---|
| 编排 | **LangGraph StateGraph**，编译成图 `graph.invoke()`；线性主干+局部辩论循环 | ✅ 通用 |
| 分析师 | market / social / news / sentiment / **fundamentals** 五类，各配专属 ToolNode 取数 | fundamentals 对 BTC 无意义,删 |
| 辩论 | bull↔bear 交替（`2×max_debate_rounds`，默认 2 次）；风控三方 aggressive/conservative/neutral（`3×rounds`，默认 3 次） | ✅ 通用 |
| 仲裁链 | 研究经理 → 交易员 → 基金经理终裁；被要求"有证据就明确表态,别动辄 Hold" | ✅ 通用 |
| 双模型 | `deep_think_llm`（辩论/经理/风控）+ `quick_think_llm`（取数/交易员/反思），省成本 | ✅ 通用 |
| 输出 | Pydantic schema（TraderProposal: action+入场价+止损+仓位；PortfolioDecision: 5档评级+目标价+持有期）+ **确定性文本解析**（不二次调 LLM） | ✅ 通用,关键 |
| 记忆 | **markdown 日志**（非向量）；两阶段写：先 `pending` 决策，事后 `update_with_outcome` 补真实收益+反思 | ✅ 通用,换基准即可 |
| 反思 | 对已结算决策算 raw return + **alpha return（相对基准）**，quick LLM 出 2-4 句教训注入下次 prompt | ✅ 通用 |
| 数据 | vendor 路由：yfinance/AlphaVantage(可互换)/FRED(宏观)/Polymarket；look-back 从 `curr_date` 反向截断 | 换 vendor |
| 回测 | **无独立回测引擎**（虽依赖 backtrader）；"回测"=记忆日志逐日重跑，官方声明结果不可复现 | ⚠️ 不能当回测用 |

**结构性局限（评估时必须对照）**：① 记忆是规则截取非语义检索,规模化召回弱；② PM 只出离散评级,`position_sizing` 是自由文本,没连撮合;③ 回测无滑点/手续费/流动性,不可复现;④ 前视防护止于"end 日期截断",未处理新闻/基本面发布时滞;⑤ LLM 主观辩论 + temperature 漂移 → 高方差,**对波动更大的 BTC 风险被放大**。

---

## 二、你的 BTC 设计:缺什么(按重要性)

### 🔴 P0 缺失机制(不补,产品没有护城河也无法自证价值)

1. **机械规则出候选 / LLM 只做裁决 —— 分工没写死。**
   FEASIBILITY 只说"LLM 做分析层"。但 Beacon 和 TradingAgents 的共同铁律是:**候选和交易价位由确定性规则算,LLM 出现在辩论/点将/点评三个裁决点,绝不让 LLM 报买卖数字。** TradingAgents 靠 Pydantic schema + 确定性解析落地这条。你的设计要明确写:入场价/止损/仓位一律机械规则算,LLM 只输出方向评级+理由。

2. **反事实归因 —— 完全没有。**
   Beacon 追踪"被剔除票的后续表现 vs 终榜"。这是**检验 LLM 裁决有没有增量价值的唯一硬办法**,直接回答你 v2 的晋级条件"2-3 个月统计优势显著"。没有反事实,你无法区分"LLM 选得好"还是"这段行情谁选都涨"。必须加。

3. **策略版本状态机(实验→前向验证→已验证)—— 有晋级思想,没做成机制。**
   你的 v1→v4 是"路线阶段",Beacon 把它做成**每个策略版本的状态机**:不可跳级、晋级"已验证"必须引用前向真账(样本量/收益/胜率)、战绩按版本归因、改参数留血统不原地覆盖。这才是"晋级制产品化"。建议直接抄这个状态机。

4. **前向考场 —— 缺一个"只认真实前向数据"的验证层。**
   TradingAgents 的记忆闭环 + Beacon 的因子前向考场,合起来正好是你 v2 到 v3 之间缺的一环:信号先在真实前向数据上机械结算(扣成本、超额减基准),证实了再进模拟盘。TradingAgents 的 pending→outcome 两阶段记忆**已经实现了一半**,补一个结算器即可。

### 🟡 P1 应补(降方差/降成本/守纪律)

5. **双模型共识** —— 同一情报两家模型独立研判、标注共识,低成本对冲单模型措辞敏感(FEASIBILITY 自己提到"换措辞就翻转多空")。Beacon 有,你的设计没有。
6. **白卷文化** —— "环境不行按纪律不出票"要写进 prompt 和终榜逻辑,对抗 LLM"必须给答案"倾向。TradingAgents 反而被调成"别动辄 Hold",方向相反——**BTC 波动大,你要的是敢交白卷,需反向调 prompt。**
7. **双模型成本分层** —— 直接用 TradingAgents 的 deep/quick 分层,别所有环节都用最强模型(FEASIBILITY 提到有人烧 $1500 API 费无产出)。
8. **持仓决策台 + 下单前检查卡** —— v4 之前的人工执行辅助,Beacon 的"买入前七问"是很好的纪律模板。

### 🟢 P2 BTC 专有工程(两份文档都没充分展开)

9. **7×24 无交易日历** —— TradingAgents 全部按"交易日 `curr_date`"(含休市)组织 look-back、bar 粒度、`end` 独占修正。**BTC 连续时间,这套要整体重写**:终榜/结算改成固定 UTC 时点的滚动窗口。这是移植中最脏的工程活。
10. **crypto 原生指标** —— fundamentals 四件套(资产负债/现金流/利润表)对 BTC 无意义,整类删。换成:资金费率、未平仓合约(OI)、爆仓热图、多空比、交易所净流、MVRV、活跃地址。FEASIBILITY 已列链上源但注明"免费层残缺"——这是真实约束,v0 先用交易所衍生品数据(免费)顶上,链上留到有预算。
11. **现货优先,永续要隔离** —— Alpha Arena 是永续合约实盘(杠杆放大亏损)。设计要写死:**v4 之前只做现货信号**,杠杆/永续是独立的、更晚的、更严的分支。
12. **标的宇宙小** —— TradingAgents/Beacon 是"扫全市场筛候选";BTC 宇宙就 BTC/ETH+少数主流币。你的"推荐中心/终榜"退化成小篮子多资产研判,**不是筛选问题,是配置问题**——这反而简化了,别照搬 A股的全市场扫描。

---

## 三、你的设计里已经对的(别改)

- ✅ 晋级制 v1→v4 的**方向和心态**(把 Alpha Arena 多数亏损当基线预期);
- ✅ "不让 LLM 直接下单"、执行层交给 freqtrade;
- ✅ v1 情报层零风险先做、与 news agent 70% 复用的判断;
- ✅ 对回测不可信/前视泄漏的警惕(TradingAgents 自己的"回测"也只是记忆重跑,印证了你的判断——**别用 TradingAgents 的回测当数,真回测必须 freqtrade**);
- ✅ 数据源清单(CryptoPanic/F&G/ccxt)选得对且大多免费。

---

## 四、修订后的 v0→成熟版路线

| 版本 | 目标 | 核心交付 | 复用/新建 | 晋级条件 |
|---|---|---|---|---|
| **v0 脚手架** | 让 TradingAgents 跑通单资产 BTC 日度研判 | fork TradingAgents → 删 fundamentals 分析师 → dataflows 加 crypto vendor(ccxt/CryptoPanic/F&G) → 交易日历改 7×24 UTC → benchmark 改 BTC-HODL → 产出结构化决策记录(不执行) | fork 改装 | 能每日产出一条带评级+理由+机械价位的结构化记录并落记忆日志 |
| **v1 情报层** | 零风险资讯产品 | 新闻聚合 + F&G + 盘面仪表盘(资金费率/OI/爆仓/多空比) + 盯盘规则告警 → 推送 | news agent 架构 70% + Beacon 盘面观察 | 直接做,稳定推送 |
| **v2 决策记录** | 自证 LLM 有无增量价值 | 全 agent 辩论 → 结构化决策 + **记忆/反思闭环** + 命中率跟踪 + **反事实归因** + **策略版本状态机** + 白卷文化 + 双模型共识 | TradingAgents 记忆闭环 + Beacon 推荐中心/反事实 | 2-3 个月:反事实证明 LLM 终榜显著跑赢池等权基准 |
| **v2.5 前向考场** | 信号验真 | 机械结算器(扣成本、超额减 BTC-HODL);版本状态机推进到"前向验证" | Beacon 前向考场 + TA pending→outcome | 3-6 个月前向 alpha 为正 |
| **v3 模拟盘** | 带摩擦的仿真 | freqtrade dry-run 接 LLM 信号,含滑点/手续费;每策略版本一个纸面账户;熔断 | freqtrade + Beacon 模拟盘 | 夏普为正且跑赢 BTC-HODL |
| **v4 小资金实盘** | 现货限额 | 限额+硬止损+最大回撤熔断+大单人工确认;持仓决策台+下单前检查卡;**只现货** | Beacon 持仓决策台 | v3 达标;永续是更晚的独立分支 |

**关键路径变化 vs 原文档**：原文档 v2"TradingAgents 多 agent 架构可抄";修订为 **v0 就 fork 跑通骨架**(因为已支持 crypto),把省下的时间投到 v2 的**反事实+状态机**(护城河所在)。

---

## 五、v0 立刻能做的改装清单(具体到文件)

基于源码结构,fork 后按此改:

1. `tradingagents/default_config.py`：新增 crypto vendor 配置项;`benchmark_map` 改 BTC-HODL;`output_language="Chinese"`。
2. `dataflows/`：新增 `ccxt_vendor.py`(行情/OI/资金费率)、`cryptopanic_vendor.py`(新闻)、`feargreed_vendor.py`(F&G);在 `interface.py` 的 `route_to_vendor` 注册;**删/禁用** fundamentals/balance_sheet/cashflow/income_statement 路由。
3. `agents/analysts/`：禁用 `fundamentals_analyst`;`market_analyst` 的 ToolNode 加资金费率/OI 指标;新增或改造 `onchain_analyst`(可选,v0 先跳过)。
4. `graph/propagation.py` + look-back 逻辑：交易日历改连续 UTC 时间,去掉休市日修正。
5. `agents/utils/memory.py`：`update_with_outcome` 的 alpha 计算基准换 BTC-HODL;结算改按 UTC 滚动窗口。
6. prompt 微调：研究经理"别动辄 Hold"→ BTC 版加"环境不明确时交白卷优于硬凑"(白卷文化)。
7. 新增反事实追踪(记忆日志里同时记被否决的候选,事后一起结算对比)。

---

## 六、一句话结论

你的设计**大方向正确、心态清醒**,主要问题是三个:
1. **过时假设**——以为要重写,其实 TradingAgents 已支持 crypto,fork 改装即可,v0 可提前;
2. **四个 P0 机制缺失**——机械/LLM 分工写死、反事实归因、版本状态机、前向考场,这些是"能不能自证价值 + 有没有护城河"的关键,Beacon 全做了、TradingAgents 提供了一半基建,你的文档还没有;
3. **BTC 专有工程被低估**——7×24 日历重写、crypto 原生指标、现货优先,是移植中真正的脏活。

补齐后,这份设计就从"可行性调研"升级成"可执行蓝图"。
