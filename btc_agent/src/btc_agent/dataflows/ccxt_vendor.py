"""ccxt 行情 vendor（BTC agent v0 / ST2）。

替代 yfinance 成为 crypto 的 OHLCV 与技术指标数据源。只读交易所公开行情接口
（默认 binance），**不带 key、不下单**。与 yfinance vendor 同构：
- ``get_ccxt_data`` 对应 ``get_stock_data``，返回带表头的 CSV 字符串；
- ``get_ccxt_indicators_window`` 对应 ``get_indicators``，用 stockstats 计算指标。

数据源与 vendor 路由解耦：本模块只被 ``interface.py`` 的 VENDOR_METHODS 注册引用。
交易所网络调用集中在 ``_fetch_ohlcv_raw``，测试可 monkeypatch 该函数离线跑。
"""

from datetime import datetime, timezone
from typing import Annotated

import ccxt
import pandas as pd
from dateutil.relativedelta import relativedelta
from stockstats import wrap

from .config import get_config
from .symbol_utils import NoMarketDataError

# 默认交易所与计价币。BTC → BTC/USDT。crypto 7×24 连续交易，无休市日。
# 交易所与代理经 config 覆盖(ccxt_exchange / ccxt_proxy)：本机 binance 主站被地域封锁，
# 默认改用 binance.us 并走本地 Clash 代理(见 default_config)。
DEFAULT_EXCHANGE = "binanceus"
DEFAULT_QUOTE = "USDT"

# 与 yfinance 指标路径一致的受支持指标集（stockstats 列名）。
SUPPORTED_INDICATORS = {
    "close_50_sma": "50 SMA: 中期趋势，方向与动态支撑/阻力。",
    "close_200_sma": "200 SMA: 长期趋势基准，金叉/死叉。",
    "close_10_ema": "10 EMA: 短期动量，反应快但易噪声。",
    "macd": "MACD: EMA 差值动量，看交叉与背离。",
    "macds": "MACD Signal: MACD 的 EMA 平滑，交叉触发。",
    "macdh": "MACD Histogram: MACD 与信号线之差，动量强弱。",
    "rsi": "RSI: 动量，70/30 超买超卖与背离。",
    "boll": "Bollinger Middle: 20 SMA 基线。",
    "boll_ub": "Bollinger Upper: 中轨上 2 倍标准差，超买/突破。",
    "boll_lb": "Bollinger Lower: 中轨下 2 倍标准差，超卖。",
    "atr": "ATR: 波动率，用于止损与仓位。",
    "vwma": "VWMA: 成交量加权均线，价量确认趋势。",
    "mfi": "MFI: 价量资金流，>80 超买 <20 超卖。",
}


def _resolve_pair(symbol: str) -> str:
    """把 ``BTC`` 归一到 ccxt 交易对 ``BTC/USDT``；已含 ``/`` 的原样返回。"""
    s = symbol.strip().upper()
    if "/" in s:
        return s
    return f"{s}/{DEFAULT_QUOTE}"


def _fetch_ohlcv_raw(pair: str, timeframe: str = "1d", limit: int = 400) -> list:
    """拉原始 OHLCV：``[[ms_ts, open, high, low, close, volume], ...]``。

    交易所网络调用只发生在这里——测试 monkeypatch 本函数即可离线运行。
    交易所(``ccxt_exchange``)与代理(``ccxt_proxy``)从 config 读，默认见本模块常量。
    """
    cfg = get_config()
    exchange_id = cfg.get("ccxt_exchange") or DEFAULT_EXCHANGE
    proxy = cfg.get("ccxt_proxy")
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    if proxy:
        # ccxt 统一代理属性，优先于环境变量里的远程 VPN 代理(其对交易所常 RESET)。
        exchange.httpsProxy = proxy
    return exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)


def _ohlcv_dataframe(symbol: str, curr_date: str | None = None) -> pd.DataFrame:
    """取 OHLCV 并整理成带 ``Date`` 列的 DataFrame。

    ``curr_date`` 表示 UTC 决策日的开始时刻，只保留严格早于该日的已完成日线。
    日线时间戳标记的是开盘而非收盘；使用 ``<=`` 会在历史回看时把该日完整
    OHLC 当作开盘时已知，从而产生前视泄漏。
    """
    pair = _resolve_pair(symbol)
    raw = _fetch_ohlcv_raw(pair)
    if not raw:
        raise NoMarketDataError(symbol, pair, "ccxt returned no candles")

    df = pd.DataFrame(
        raw, columns=["ts", "Open", "High", "Low", "Close", "Volume"]
    )
    df["Date"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.drop(columns=["ts"])
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]

    if curr_date is not None:
        cutoff = pd.to_datetime(curr_date)
        # Exchanges normally include the currently forming UTC-day candle. Even
        # if a caller asks for a future settlement cutoff, today's partial OHLC
        # is not a completed daily bar and must not resolve a pending outcome.
        today_utc = pd.to_datetime(datetime.now(timezone.utc).date())
        cutoff = min(cutoff, today_utc)
        df = df[df["Date"] < cutoff]

    if df.empty:
        raise NoMarketDataError(symbol, pair, "no rows on/before curr_date")
    return df.reset_index(drop=True)


def get_ccxt_data(
    symbol: Annotated[str, "crypto 资产符号，如 BTC 或 BTC/USDT"],
    start_date: Annotated[str, "起始日 yyyy-mm-dd"],
    end_date: Annotated[str, "UTC 决策日 yyyy-mm-dd（不含当日未完成日线）"],
) -> str:
    """返回决策日开始时已完成的 OHLCV，不包含 ``end_date`` 当日 K 线。"""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    df = _ohlcv_dataframe(symbol, curr_date=end_date)
    df = df[df["Date"] >= pd.to_datetime(start_date)]
    if df.empty:
        raise NoMarketDataError(
            symbol, _resolve_pair(symbol), f"no rows between {start_date} and {end_date}"
        )

    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].round(2)

    out = df.copy()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    csv_string = out.to_csv(index=False)

    pair = _resolve_pair(symbol)
    header = f"# Crypto OHLCV for {pair} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_string


def get_ccxt_indicators_window(
    symbol: Annotated[str, "crypto 资产符号"],
    indicator: Annotated[str, "技术指标（stockstats 列名）"],
    curr_date: Annotated[str, "当前日 yyyy-mm-dd"],
    look_back_days: Annotated[int, "回看天数"],
) -> str:
    """``get_indicators`` 的 ccxt 实现：用 stockstats 算指标，按天回看窗口输出。"""
    if indicator not in SUPPORTED_INDICATORS:
        raise ValueError(
            f"Indicator {indicator} is not supported. "
            f"Choose from: {list(SUPPORTED_INDICATORS.keys())}"
        )

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_dt - relativedelta(days=look_back_days)

    df = _ohlcv_dataframe(symbol, curr_date=curr_date)
    stats = wrap(df.copy())
    stats[indicator]  # 触发 stockstats 计算该列
    values = dict(
        zip(df["Date"].dt.strftime("%Y-%m-%d"), stats[indicator].tolist())
    )

    lines = []
    cursor = curr_dt
    while cursor >= before:
        key = cursor.strftime("%Y-%m-%d")
        val = values.get(key, "N/A")
        lines.append(f"{key}: {val}")
        cursor = cursor - relativedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + SUPPORTED_INDICATORS[indicator]
    )
