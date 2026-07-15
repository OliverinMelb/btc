# v1 起步待办（清空上下文后从这里接）

v0 已完成并端到端跑通（见 `BTC-DESIGN-REVIEW.md` 路线、`workflow/tasks/20260715-133420-v0-fork-ta/summary.md`、
项目记忆 `v0-status.md`）。v1 是「情报层」，但**第一步先做最便宜最高价值的 crypto prompt 适配**。

## ✅ 第一个任务：crypto prompt 适配 —— 已完成（2026-07-15）

**改了**:market/多空/风控三辩 prompt 去股票化;真跑暴露两处数据层根因一并修复——
(1) `resolve_instrument_context` 对 crypto 跳过 yfinance 身份解析(原把 `BTC` 认成
Grayscale ETF 注入全链);(2) verified snapshot 对 crypto 改走 ccxt(原硬编码 yfinance
返回 ETF 的 $28)。验收:reasoning stock/ETF 关键词=0、价位 $64–66k、25 单测全绿、端到端 exit 0。
`default_config` 模型名改 `deepseek-v3.2`(link3.top 无 `deepseek-chat` 部署)。

<details><summary>原始任务描述(存档)</summary>

### 第一个任务：crypto prompt 适配（单会话、不用子代理、不用完整 workflow 仪式）

**问题**（v0 真跑发现）：vendored 的 TradingAgents prompt 面向股票——LLM 把 BTC 说成 "ETF"、
把技术指标数值当成价格量级。不影响机械价位，但研判文本质量差，是 v1 首要打磨点。

**做什么**：把 `btc_agent/src/btc_agent/agents/` 下各 prompt（market 分析师、研究经理、
交易员、风控三辩、基金经理）里的股票语境改成 crypto/BTC 语境——去掉"公司/财报/ETF/股价"
之类措辞，改成"资产/链上/永续/现货价"等；明确告诉分析师喂进来的是技术指标数值而非价格。

**验收**：改完真跑一次 `cd btc_agent; DEEPSEEK_API_KEY=<见 .env> PYTHONPATH=src .venv/Scripts/python.exe
-m btc_agent.run --asset BTC --date <今日UTC>`，确认新记录的 reasoning 不再把 BTC 当股票/ETF；
离线 25 个单测仍全绿（`.venv/Scripts/python.exe -m pytest`）。

**省额度**：单会话直接改（别开子代理）；机械文本改动可 `/model` 切 Sonnet 5；真跑端到端只在最后一次。

</details>

## ✅ 之后的 v1 情报层 —— 已完成（2026-07-15）
- ✅ CryptoPanic 新闻 vendor（`cryptopanic_vendor.py`，和 ccxt 同构，token 走 `CRYPTOPANIC_API_TOKEN`，
  注册为 `get_news`/`get_global_news` 的 crypto 默认）
- ✅ F&G 指数 vendor（`feargreed_vendor.py`，alternative.me 免 key）+ 衍生品盘面 vendor
  （`derivatives_vendor.py`，ccxt 永续资金费率/OI；默认所 okx，binance/bybit 本机被 451/403）
- ✅ 告警推送管道（`intel/`：`dashboard` 装配 → `rules` 纯规则引擎 → `push` 可插拔 sink
  stdout/Telegram）。入口 `python -m btc_agent.intel --asset BTC`,真跑三组信号全取到、优雅降级。
- ✅ 回填 `workflow/config.json` 的 contract_touchpoints + env_consistency（并修了该文件的
  UTF-8 BOM,使契约漂移检查首次能跑通）

验收:51 离线单测全绿(v1 情报层新增 26)、ruff 全过、契约漂移检查 OK、intel CLI 真数据端到端。

**v1 晋级条件「稳定推送」剩最后一步(需你):** 配 `TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID`
后把 `intel_push_sinks` 加 "telegram",再挂个定时器(Windows 计划任务 / cron)定时跑
`python -m btc_agent.intel`。新闻 vendor 真跑需 `CRYPTOPANIC_API_TOKEN`(免费注册)。

## 原始 v1 待办（存档）
- CryptoPanic 新闻 vendor（和 ccxt vendor 同构）
- F&G 指数 + 盘面指标（资金费率/OI/爆仓）vendor
- 告警推送管道（规则引擎 → 推送）
- 回填 `workflow/config.json` 的 contract_touchpoints
