# BTC 信息检索→决策→交易 Agent — 可行性分析与开源调研（2026-07-14）

> 结论先行：**"信息检索 + 决策支持"可行且有真实价值，架构与 news agent 共享 70%；
> "LLM 直接扣扳机交易"是社区公认的幻觉区，唯一的真金实盘公开实验以多数亏损收场。**
> 建议按 v1 情报层 → v2 决策记录 → v3 模拟盘 → v4 小资金实盘 的晋级制推进，每级有硬性晋级条件。

---

## 一、可行性分析：三层拆解，可行性断崖式下降

### ① 信息检索层 — 完全可行，比 dev 资讯更容易
BTC 信息源高度结构化，全部有现成接口：

| 数据 | 来源 | 成本 |
|---|---|---|
| 新闻聚合 | [CryptoPanic API](https://cryptopanic.com/developers/api/)（含社区多空投票，有现成 [MCP server](https://github.com/kukapay/cryptopanic-mcp-server)） | 免费 key |
| 恐惧贪婪指数 | [Alternative.me F&G](https://alternative.me/crypto/fear-and-greed-index/)（JSON，含历史） | 完全免费无 key |
| 行情 | 交易所 API / [ccxt](https://github.com/ccxt/ccxt)（100+ 所统一接口，43k★） | 免费 |
| 媒体 RSS | CoinDesk / CoinTelegraph / Decrypt | 免费 |
| 社交情绪 | [crypto-sentiment-mcp](https://github.com/kukapay/crypto-sentiment-mcp)；LunarCrush 免费层已收紧 | 免费/付费 |
| 链上指标 | Glassnode / Santiment 免费层均残缺（最近 30 天数据被切除等） | 基本要付费 |

架构与 news agent 同构：源适配器 → 去重 → LLM 打分/摘要 → 推送，约 70% 复用。

### ② 分析决策层 — 生死线在这里
- **决策支持**（聚合情报、事件警报、结构化观点供人参考）：可行，本质仍是资讯 agent。
- **自动择时赚 alpha**：结构性不可行。核心不是技术，是对手盘与信号本身：
  - 机构新闻→交易延迟毫秒级（Bloomberg/RavenPack 专线），你拿到 RSS 时价格已反应完；
  - 新闻情绪对价格影响微弱且 2-3 天内完全衰减（r/algotrading 实测）；
  - LLM 输出不稳定：同一输入换措辞就翻转多空（HN 实测）；某原型实测 **15% 信号正确率、70% 假阳性**；
  - LLM 决策无法可信回测（训练数据"见过"历史行情 → 前视泄漏）。

### ③ 执行层 — 技术最简单，风险最集中
下单 = 一个 ccxt 调用；真正的工程量在仓位管理、止损、密钥安全、断线恢复、
交易所风控。这一层的 bug 直接烧钱（真实案例：一个 bug 抹掉账户 40%；
新币抢购 bot 一小时内 $25k 账户被手续费磨光）。

## 二、决定性证据：Alpha Arena 真金实盘实验

[nof1.ai 的 Alpha Arena](https://www.iweaver.ai/blog/alpha-arena-ai-trading-season-1-results/)：
6 个前沿 LLM 各持 $10,000 在 Hyperliquid 实盘自主交易永续合约——目前最干净的"LLM 直接炒币"实证：

- **4/6 亏损，GPT-5 亏至约 -59%/-40%（两阶段数据）垫底**；仅 Qwen3 Max（+22%）与 DeepSeek 微赚；
- 赛中仅 2 个模型跑赢"简单持有 BTC"；
- 关键发现：**金融推理 benchmark 成绩与实盘盈亏完全脱钩**（跑分最强的模型亏最多）。

配套学术证据 [InvestorBench](https://arxiv.org/pdf/2412.18174)：更强的 LLM 并不稳定优于传统策略，熊市风控尤其差。

## 三、GitHub 开源现状

### 可参考的架构（分析层）
| 项目 | Stars | 要点 |
|---|---|---|
| [TradingAgents](https://github.com/TauricResearch/TradingAgents)（[论文](https://arxiv.org/abs/2412.20138)） | 92.9k | 多 agent 模拟交易公司：基本面/情绪/新闻/技术面分析师 → 多空辩论 → 交易员 → 风控 → 基金经理。**架构参考价值最高**，但只有短窗口回测、无实盘审计，作者自评"研究框架非投资建议" |
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 61.6k | 投资人格 agent（巴菲特/Burry 等）+ 回测；作者明确声明**不执行真实交易、仅教育** |
| [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 20.9k | 金融情绪分析 LLM（LoRA 微调），适合当管道里的**情绪打分器组件** |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 15.7k | 金融强化学习管道，学术导向，RL 过拟合是公认痛点 |
| [LLM_trader](https://github.com/qrak/LLM_trader) | ~110 | 与设想最接近的单人项目：RSS 新闻 + K线图喂多模态 LLM + 记忆推理；管道可借鉴、无业绩证明 |

### 执行/回测层（传统框架，成熟）
| 项目 | Stars | 要点 |
|---|---|---|
| [freqtrade](https://github.com/freqtrade/freqtrade) | 52.3k | 执行层首选：回测/hyperopt/dry-run 最完整，FreqAI 支持 ML 信号；文档直言"多数策略跑不赢市场" |
| [hummingbot](https://github.com/hummingbot/hummingbot) | 19.1k | 做市/高频向，回测弱 |
| [jesse](https://github.com/jesse-ai/jesse) | 8.2k | 无前视偏差回测 + Monte Carlo 压力测试 |
| [OctoBot](https://github.com/Drakkar-Software/OctoBot) | 6.2k | 传统框架里原生情绪插件支持最好 |

**社区收敛的组合**：LLM 做分析层（TradingAgents 式）→ 输出信号 → freqtrade 做回测/风控/执行。
**不要让 LLM 直接下单。**

**最重要的负面观察**：没有任何一个高星项目公开可审计的、跑赢买入持有的实盘记录——
头部项目集体免责（"仅教育用途"）本身就是行业结论。

## 四、Reddit / HN 社区共识

### 失败原因清单（按提及频率）
1. **速度竞争结构性输**："你不可能是第一个拿到新闻的"——5-10 秒的 LLM 分析在机构毫秒级面前毫无意义；
2. 新闻情绪信号微弱且 2-3 天衰减殆尽，还有对手方故意投放假消息污染；
3. LLM 输出噪声：措辞敏感、假阳性 70%、训练数据自带散户失败者偏见；
4. 回测过拟合 + LLM 前视泄漏，社区对 LLM 写的回测默认不信；
5. 手续费/滑点/LLM 调用成本吃掉微弱信号（有人烧 $1,500 API 费无产出）；
6. 同质化：人人问同样的 AI → 交易行为同步化 → 放大波动；
7. 24/7 运维与工程 bug 的真金代价。

### AI 在链路上真有价值 vs 幻觉（r/quant + HN 从业者共识）
- **真价值（链路上游）**：非结构化→结构化提取（财报/公告）、7×24 信息聚合与事件监控告警、
  研报摘要、策略代码生成提效（需人工复验）、细腻语境情绪打分**作为特征之一**；
- **幻觉（链路末端）**：LLM 短线择时/直接下单（"抛硬币"级）、靠公开新闻抢机构速度、
  用 LLM 预测价格方向、"情绪分>阈值就买"单信号策略。

### 新手校准（r/algotrading 标准建议）
- 时间预期以**年**计："这是赚快钱最难的方式"；"1-5 年内总体赚到 1 美元就赢过大多数活跃散户"；
- paper trading 数月起步，且明白它系统性高估收益（无滑点/无成交失败）；前向实测比回测长度重要；
- 实盘从亏光不心疼的小钱开始；对任何月收益 20%+ 的声称默认是过拟合或骗局；
- 能长期跑平 S&P 500（年化 7-10%）已属高手。

## 五、建议路线（晋级制）

| 阶段 | 内容 | 晋级条件 | 复用 |
|---|---|---|---|
| **v1 情报层** | BTC 版 Horizon：CryptoPanic + F&G + RSS + 行情异动 → LLM 摘要/警报 → 推送 | 直接做，零风险 | news agent 架构 70% |
| **v2 决策记录** | LLM 每日出结构化观点（多空/置信度/理由），**只记录不执行**，跟踪命中率与假阳性率 | 2-3 个月统计优势显著 | TradingAgents 多 agent 架构可抄 |
| **v3 模拟盘** | freqtrade dry-run 接 LLM 信号，含滑点手续费模拟 | 3-6 个月夏普为正且跑赢持有 BTC | freqtrade |
| **v4 小资金实盘** | 限额 + 硬止损 + 最大回撤熔断 + 大单人工确认 | v3 达标 | — |

**期望管理**：把 Alpha Arena（多数模型亏损）当基线预期，而不是例外。
v2/v3 的数据大概率会告诉你止步于"决策支持"是最优解——那也已经是一个有真实价值的产品。

## 附：全部调研来源

**实盘/学术**：[Alpha Arena 结果](https://www.iweaver.ai/blog/alpha-arena-ai-trading-season-1-results/) · [ForkLog 报道](https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/) · [PANews](https://www.panewslab.com/en/articles/07cbee36-3e6e-44ed-8e48-bef321b3fc3e) · [InvestorBench](https://arxiv.org/pdf/2412.18174) · [ProfitView 实盘复盘](https://profitview.net/blog/what-i-learned-when-building-an-ai-news-trading-bot)

**GitHub**：[TradingAgents](https://github.com/TauricResearch/TradingAgents) · [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) · [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) · [FinRL](https://github.com/AI4Finance-Foundation/FinRL) · [freqtrade](https://github.com/freqtrade/freqtrade) / [FreqAI](https://www.freqtrade.io/en/stable/freqai/) · [hummingbot](https://github.com/hummingbot/hummingbot) · [jesse](https://github.com/jesse-ai/jesse) · [OctoBot](https://github.com/Drakkar-Software/OctoBot) · [ccxt](https://github.com/ccxt/ccxt) · [LLM_trader](https://github.com/qrak/LLM_trader) · [LLM-TradeBot](https://github.com/EthanAlgoX/LLM-TradeBot) · [Binance-News-Sentiment-Bot](https://github.com/CyberPunkMetalHead/Binance-News-Sentiment-Bot) · [“Killed my account” issue](https://github.com/CyberPunkMetalHead/binance-trading-bot-new-coins/issues/71)

**社区讨论**：[HN: LLM as quant traders](https://news.ycombinator.com/item?id=45977382) · [HN: Show HN LLM trades stocks](https://news.ycombinator.com/item?id=40961890) · [HN: LLM trading bot](https://news.ycombinator.com/item?id=42464135) · [r/algotrading: sentiment stupid idea?](https://www.reddit.com/r/algotrading/comments/1jvftsj/sentiment_based_trading_strategy_stupid_idea/) · [r/algotrading: 15% 正确率原型](https://www.reddit.com/r/algotrading/comments/1kh84nc/sentimentbased_trading_strategy_i_built_a/) · [r/algotrading: meaningful money?](https://www.reddit.com/r/algotrading/comments/1jlax0u/do_you_make_a_meaningful_amount_of_money/) · [r/quant: LLM usage](https://www.reddit.com/r/quant/comments/1k3ezs6/llm_usage_in_trading_strategies/) · [r/CryptoCurrency: why is AI bad at trading](https://www.reddit.com/r/CryptoCurrency/comments/1iiyof9/) · [Reddit algotrading 社区扫描](https://mirror.glasslane.io/blog/what-reddits-algo-trading-community-is-actually-building-right-now)

**数据源**：[CryptoPanic API](https://cryptopanic.com/developers/api/) · [cryptopanic-mcp-server](https://github.com/kukapay/cryptopanic-mcp-server) · [crypto-sentiment-mcp](https://github.com/kukapay/crypto-sentiment-mcp) · [Alternative.me F&G](https://alternative.me/crypto/fear-and-greed-index/) · [sanpy](https://github.com/santiment/sanpy) · [LunarCrush](https://lunarcrush.com/developers/api/overview)
