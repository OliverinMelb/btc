"""ST3: 7×24 UTC 日历 + BTC-HODL 基准的离线单测。

不打真实交易所网络：monkeypatch ccxt vendor 的 `_fetch_ohlcv_raw`。
覆盖：基准解析为 BTC-HODL、结算取价走 ccxt(非 yfinance)、连续 UTC 天不跳周末、
alpha 标签读 BTC-HODL。
"""

from datetime import datetime, timedelta, timezone

import pytest

from btc_agent.dataflows import ccxt_vendor
from btc_agent.default_config import DEFAULT_CONFIG
from btc_agent.graph.trading_graph import TradingAgentsGraph


def _daily_candles(start="2021-01-01", days=30, start_price=10000.0, step=0.01):
    """连续日线蜡烛(含周末)：[ms_ts, o, h, l, c, v]。时间戳按 UTC 午夜。"""
    dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_ms = 86_400_000
    base_ms = int(dt.timestamp() * 1000)
    out = []
    price = start_price
    for i in range(days):
        c = price * (1 + step)
        out.append([base_ms + i * day_ms, price, c, price * 0.99, c, 1000.0])
        price = c
    return out


@pytest.fixture
def patched_ohlcv(monkeypatch):
    candles = _daily_candles(days=40)
    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", lambda *a, **k: candles)
    return candles


def test_default_benchmark_is_btc_hodl():
    """默认 config 的基准是 BTC 现货 + BTC-HODL 标签，不是 SPY/区域指数。"""
    assert DEFAULT_CONFIG["benchmark_ticker"] == "BTC/USDT"
    assert DEFAULT_CONFIG["benchmark_label"] == "BTC-HODL"


def test_resolve_benchmark_returns_crypto(tmp_path):
    cfg = dict(DEFAULT_CONFIG)
    cfg["results_dir"] = str(tmp_path)
    cfg["memory_log_path"] = str(tmp_path / "mem.md")
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = cfg
    resolved = graph._resolve_benchmark("BTC")
    assert resolved == "BTC/USDT"
    assert "SPY" not in resolved


def test_fetch_returns_uses_ccxt_not_yfinance(patched_ohlcv, tmp_path):
    """asset 与 benchmark 取价都走 ccxt(mock 后不打网络)，返回连续天的 raw/alpha。"""
    cfg = dict(DEFAULT_CONFIG)
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = cfg
    raw, alpha, days = graph._fetch_returns(
        "BTC", "2021-01-05", holding_days=5, benchmark="BTC/USDT"
    )
    assert raw is not None
    assert days == 5  # 连续 5 个 UTC 天，无周末跳过
    # BTC 资产 vs BTC-HODL 基准在 v0 退化：raw≈benchmark → alpha≈0（已知局限）
    assert abs(alpha) < 1e-9


def test_settlement_window_is_continuous_no_weekend_skip(patched_ohlcv, tmp_path):
    """含周六的窗口：holding_days=5 覆盖连续 5 天，不因'非交易日'缩短。

    2021-01-05 是周二，+5 连续天含 01-09(周六)、01-10(周日)。
    """
    cfg = dict(DEFAULT_CONFIG)
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = cfg
    # trade_date 周二；若按股票日历会跳周末导致 actual_days<5，crypto 应正好 5
    _, _, days = graph._fetch_returns(
        "BTC", "2021-01-05", holding_days=5, benchmark="BTC/USDT"
    )
    weekday_sat = datetime.strptime("2021-01-05", "%Y-%m-%d") + timedelta(days=4)
    assert weekday_sat.weekday() == 5  # 确认窗口内确有周六
    assert days == 5


def test_no_yfinance_in_fetch_returns_source():
    """回归守卫：trading_graph 不再 import yfinance。"""
    import btc_agent.graph.trading_graph as tg
    assert not hasattr(tg, "yf")
