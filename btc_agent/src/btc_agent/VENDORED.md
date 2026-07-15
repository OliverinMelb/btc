# VENDORED.md — TradingAgents 源码归属与拷贝清单（ST1 vendor-core）

## 来源
- 项目：[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- 分支：`main`
- 获取方式：编排者预先下载该分支的 tarball 并解压到本机临时目录（子代理未联网抓取），
  解压路径（本机、非仓库内）：
  `C:\Users\admin\AppData\Local\Temp\claude\C--Users-admin-Desktop-btc\149325a3-6d36-44c3-b415-4d10bc82d3a8\scratchpad\TradingAgents`
- 具体 commit hash 未随 tarball 保留（非 git clone，无 `.git` 元数据），仅能确认对应
  `main` 分支在下载时的快照；若需精确复现，应改为 `git clone` 后记录 `git rev-parse HEAD`
  （留待后续需要精确追溯时补充，v0 不阻塞）。
- 许可证：原样保留在 `THIRD_PARTY_LICENSES/TradingAgents-LICENSE`。

## 拷入清单
从上游 `tradingagents/` 包目录选择性拷贝，整包拷入（未做业务逻辑改写，仅包名重命名）：

- `tradingagents/__init__.py` → `btc_agent/__init__.py`（保留原有 .env 加载 / 警告过滤样板逻辑，
  详见该文件内注释）
- `tradingagents/graph/` → `btc_agent/graph/`：
  `__init__.py`, `analyst_execution.py`, `checkpointer.py`, `conditional_logic.py`,
  `propagation.py`, `reflection.py`, `setup.py`, `signal_processing.py`, `trading_graph.py`
- `tradingagents/agents/` → `btc_agent/agents/`（整包，含子目录）：
  `__init__.py`, `schemas.py`,
  `analysts/`（`fundamentals_analyst.py`, `market_analyst.py`, `news_analyst.py`,
  `sentiment_analyst.py`, `social_media_analyst.py`）,
  `managers/`（`portfolio_manager.py`, `research_manager.py`）,
  `researchers/`（`bull_researcher.py`, `bear_researcher.py`）,
  `risk_mgmt/`（`aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`）,
  `trader/`（`trader.py`）,
  `utils/`（`agent_states.py`, `agent_utils.py`, `core_stock_tools.py`,
  `fundamental_data_tools.py`, `macro_data_tools.py`, `market_data_validation_tools.py`,
  `memory.py`, `news_data_tools.py`, `prediction_markets_tools.py`, `rating.py`,
  `structured.py`, `technical_indicators_tools.py`）
- `tradingagents/dataflows/` → `btc_agent/dataflows/`（整包，含现有 vendor 文件，后续
  ST2 视需要精简/替换为 crypto vendor）：
  `__init__.py`, `alpha_vantage.py`, `alpha_vantage_common.py`, `alpha_vantage_fundamentals.py`,
  `alpha_vantage_indicator.py`, `alpha_vantage_news.py`, `alpha_vantage_stock.py`, `config.py`,
  `errors.py`, `fred.py`, `interface.py`, `market_data_validator.py`, `polymarket.py`,
  `reddit.py`, `stockstats_utils.py`, `stocktwits.py`, `symbol_utils.py`, `utils.py`,
  `y_finance.py`, `yfinance_news.py`
- `tradingagents/llm_clients/` → `btc_agent/llm_clients/`（整包）：
  `__init__.py`, `anthropic_client.py`, `api_key_env.py`, `azure_client.py`, `base_client.py`,
  `bedrock_client.py`, `capabilities.py`, `factory.py`, `google_client.py`, `model_catalog.py`,
  `openai_client.py`, `validators.py`
- `tradingagents/default_config.py` → `btc_agent/default_config.py`
- `tradingagents/reporting.py` → `btc_agent/reporting.py`
- 许可证文件 → `btc_agent/THIRD_PARTY_LICENSES/TradingAgents-LICENSE`

## 删除 / 未拷清单
上游仓库中以下路径**未拷入**（不属于 `tradingagents/` 包本体，是仓库级工具/文档/测试脚手架，
与"vendor 核心业务模块"的子任务范围无关）：

- `cli/`（TradingAgents 自带的命令行工具，v0 用不到，run 入口另在 ST4 自行设计）
- `main.py`, `test.py`, `scripts/`, `tests/`（上游自己的测试/脚本，不复用；本项目测试在
  `btc_agent/tests/` 下自行编写）
- `assets/`, `README.md`, `CHANGELOG.md`, `Dockerfile`, `docker-compose.yml`,
  `requirements.txt`, 上游 `pyproject.toml`（项目级元数据，本项目沿用自己的
  `btc_agent/pyproject.toml`，依赖已按最小子集重新声明）

## 包名处理方式
选择**全量改名**（而非作为子包引入）：所有 `tradingagents` import 路径全部替换为
`btc_agent`，即 `from tradingagents.xxx import yyy` → `from btc_agent.xxx import yyy`。
已核实仓库内 `tradingagents` 字符串残留为 0（`Grep tradingagents src/` 无匹配）。

## 已知未验证风险（留给后续子任务）
- 上游 `pyproject.toml` 原 pin 的 `langgraph` 版本为 0.4.x 系列；本项目 `btc_agent/pyproject.toml`
  声明的是不锁版本的 `langgraph`（当前装入共享 venv 的实际版本为 1.2.9），**graph 编排在
  1.x 下的运行时行为未做端到端验证**（本子任务只验证 import 成功，不实例化/不跑图）。
  若 ST4 跑通编排时出现 API 不兼容，需要回来这里补丁或锁版本。
- `dataflows/` 整包拷入含大量 vendored 但 v0 不用的路由（alpha_vantage/fred/reddit/
  polymarket/stocktwits 等），ST2 会视需要替换/精简为 crypto vendor（ccxt/CryptoPanic/F&G），
  当前只保证它们能被 import，不保证其内部逻辑在无对应 API key 时可运行。
