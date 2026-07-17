import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".btc_agent")

# Single source of truth for env-var → config-key overrides. To expose
# a new config key for environment-based override, add a row here — no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER":         "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM":       "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM":      "quick_think_llm",
    "TRADINGAGENTS_LLM_BACKEND_URL":      "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE":      "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS":    "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS":      "max_risk_discuss_rounds",
    "TRADINGAGENTS_CHECKPOINT_ENABLED":   "checkpoint_enabled",
    "TRADINGAGENTS_BENCHMARK_TICKER":     "benchmark_ticker",
    "TRADINGAGENTS_TEMPERATURE":          "temperature",
    "TRADINGAGENTS_LLM_MAX_RETRIES":      "llm_max_retries",
    # Provider-specific reasoning/thinking knobs (None = each provider's own
    # default). Settable here for non-interactive runs; the CLI also offers an
    # interactive choice, which is skipped when the matching var is set.
    "TRADINGAGENTS_GOOGLE_THINKING_LEVEL":   "google_thinking_level",
    "TRADINGAGENTS_OPENAI_REASONING_EFFORT": "openai_reasoning_effort",
    "TRADINGAGENTS_ANTHROPIC_EFFORT":        "anthropic_effort",
}


_BOOL_TRUE = ("true", "1", "yes", "on")
_BOOL_FALSE = ("false", "0", "no", "off")


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value.

    Invalid values raise ``ValueError`` rather than silently falling back to a
    default — a misspelled boolean (e.g. ``treu``) or non-numeric int should fail
    loudly at startup, not quietly misconfigure an unattended run.
    """
    if isinstance(reference, bool):
        normalized = value.strip().lower()
        if normalized in _BOOL_TRUE:
            return True
        if normalized in _BOOL_FALSE:
            return False
        raise ValueError(
            f"expected a boolean ({'/'.join(_BOOL_TRUE + _BOOL_FALSE)}), got {value!r}"
        )
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply TRADINGAGENTS_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        try:
            config[key] = _coerce(raw, config.get(key))
        except ValueError as exc:
            raise ValueError(f"Invalid value for {env_var}: {exc}") from exc
    return config


DEFAULT_CONFIG = _apply_env_overrides({
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings — BTC agent v0 用 DeepSeek(内置 provider, key 走 DEEPSEEK_API_KEY)。
    # deep=旗舰裁决, quick=快模型取数/交易员。
    # 模型名必须是 backend_url 中转站实际部署的 ID(先打 `/v1/models` 查):link3.top
    # 把别名 `deepseek-chat` 转发成上游 `DeepSeek-V3.2-Exp`,该站无此部署 → 429。
    # 用站里真实存在的 `deepseek-v3.2`。换中转站/直连官方 API 时按该端点的清单回改。
    "llm_provider": "deepseek",
    "deep_think_llm": "deepseek-v3.2",
    "quick_think_llm": "deepseek-v3.2",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    # BTC agent v0: 走中转站(OpenAI 兼容),覆盖 deepseek 默认 base_url。
    "backend_url": "https://link3.top/v1",
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Sampling temperature, forwarded to every provider when set. None leaves
    # each provider at its own default. Lower values reduce run-to-run
    # variation on models that honor it; reasoning models largely ignore it
    # and no setting makes LLM output bit-identical across runs (see README).
    "temperature": None,
    # SDK retry budget forwarded to every provider chat client. None leaves each
    # provider/SDK at its own default (usually 2). Raise it to ride out bursty
    # 429 throttling on rate-limited deployments instead of aborting a run (#1091).
    "llm_max_retries": None,
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # News / data fetching parameters
    # Increase for longer lookback strategies or to broaden macro coverage;
    # decrease to reduce token usage in agent prompts.
    "news_article_limit": 20,             # max articles per ticker (ticker-news)
    "global_news_article_limit": 10,      # max articles for global/macro news
    "global_news_lookback_days": 7,       # macro news lookback window
    # Search queries used by get_global_news for macro headlines. Extend or
    # replace to broaden geographic / sector coverage.
    "global_news_queries": [
        "Federal Reserve interest rates inflation",
        "S&P 500 earnings GDP economic outlook",
        "geopolitical risk trade war sanctions",
        "ECB Bank of England BOJ central bank policy",
        "oil commodities supply chain energy",
    ],
    # Data vendor configuration
    # Category-level configuration (default for all tools in category).
    # The configured value is the exact vendor chain — requests are NOT silently
    # routed to vendors you didn't choose. For ordered fallback, list several,
    # e.g. "yfinance,alpha_vantage". "default" uses all available vendors.
    # ccxt vendor 设置(BTC agent v0)。本机 binance 主站被地域封锁(451)且直连交易所
    # 普遍不可达，故默认用 binance.us + 本地 Clash 代理(实测 kraken/binance.us 经该代理可达)。
    # 换机器/网络时按需改这两项。
    "ccxt_exchange": "binanceus",
    "ccxt_proxy": "http://127.0.0.1:7890",
    # 永续盘面(资金费率/OI)单独取所:现货默认所 binance.us 无永续合约。
    # binance/bybit 本机被地域封锁(451/403);实测 okx/gate 经 ccxt_proxy 可达,默认 okx。
    # 换机器/网络时按需改。
    "ccxt_derivatives_exchange": "okx",
    "data_vendors": {
        "core_stock_apis": "ccxt",           # BTC agent v0: crypto 行情走 ccxt
        "technical_indicators": "ccxt",      # BTC agent v0: 指标基于 ccxt OHLCV
        "fundamental_data": "yfinance",      # 已禁用(DISABLED_METHODS)，值保留仅占位
        "news_data": "cryptorss",            # BTC agent v1: crypto 新闻走免费 RSS(零 key);cryptopanic 免费层 2026-04-01 已停,改付费
        "macro_data": "fred",                # Options: fred (needs FRED_API_KEY)
        "prediction_markets": "polymarket",  # Options: polymarket (keyless)
        "sentiment_index": "feargreed",      # BTC agent v1: Fear & Greed 指数(免 key)
        "derivatives": "derivatives",        # BTC agent v1: 资金费率/OI(ccxt 永续只读)
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # BTC agent v1 情报层:crypto 新闻 RSS 源(零 key)。None → 用 vendor 内置默认
    # (Cointelegraph + Decrypt,实测直连可达)。要加源就填 [名称, url] 列表。
    "crypto_rss_feeds": None,
    # BTC agent v1 情报层:告警阈值 + 推送 sink。
    # intel_thresholds=None 时用 rules.DEFAULT_THRESHOLDS;要改单项就填该项(其余仍用默认)。
    "intel_thresholds": None,
    # 推送渠道名列表。可选 "stdout" / "email" / "feishu" / "telegram"。
    # email 需 SMTP_USER + SMTP_PASSWORD(QQ 邮箱填授权码) + EMAIL_TO(默认 smtp.qq.com:465);
    # feishu 需 FEISHU_WEBHOOK_URL(+ 可选 FEISHU_WEBHOOK_SECRET);telegram 需
    # TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID。凭据缺失的渠道自动降级跳过(不阻断其它)。
    "intel_push_sinks": ["stdout", "email"],
    # Benchmark for alpha calculation in the reflection layer.
    # ``benchmark_ticker`` (when set) overrides the suffix map for all
    # tickers; leave it None to use ``benchmark_map`` for auto-detection
    # based on the ticker's exchange suffix. SPY remains the US default
    # so the reflection label keeps reading "Alpha vs SPY" for US tickers
    # while non-US tickers get their regional index automatically.
    # BTC agent v0: alpha 基准是 BTC 买入持有(BTC-HODL)。benchmark_ticker 指向 BTC 现货
    # 供结算取价，benchmark_label 是复盘里 "Alpha vs ..." 的人读标签。
    "benchmark_ticker": "BTC/USDT",
    "benchmark_label": "BTC-HODL",
    # v2 ST6: SQLite 账本接线开关(仅 CLI 入口 btc_agent.daily.main 读取,见
    # _build_default_ledger_recorder)。True(默认)= 每日快照/候选/裁决/价位入库 +
    # 顺带触发到期结算;False = 完全不接线(不 import ledger/settlement 模块,等价
    # 于账本功能不存在)。库函数 run_daily() 本身的 ledger_recorder 参数默认仍是
    # None,不受此键影响——这个开关只管 CLI 默认行为。
    "ledger_enabled": True,
    "benchmark_map": {
        ".NS":  "^NSEI",       # NSE India (Nifty 50)
        ".BO":  "^BSESN",      # BSE India (Sensex)
        ".T":   "^N225",       # Tokyo (Nikkei 225)
        ".HK":  "^HSI",        # Hong Kong (Hang Seng)
        ".L":   "^FTSE",       # London (FTSE 100)
        ".TO":  "^GSPTSE",     # Toronto (TSX Composite)
        ".AX":  "^AXJO",       # Australia (ASX 200)
        ".SS":  "000001.SS",   # Shanghai (SSE Composite)
        ".SZ":  "399001.SZ",   # Shenzhen (SZSE Component)
        "":     "SPY",         # default for US-listed tickers (no suffix)
    },
})
