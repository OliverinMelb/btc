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
    raw, alpha, days, direction_hit, basis = graph._fetch_returns(
        "BTC", "2021-01-05", holding_days=5, benchmark="BTC/USDT"
    )
    assert raw is not None
    assert days == 5  # 连续 5 个 UTC 天，无周末跳过
    # BTC 资产 vs BTC-HODL 基准在 v0 退化：raw≈benchmark → alpha≈0（已知局限）
    assert abs(alpha) < 1e-9
    assert direction_hit is True  # 默认 rating="Buy"，市场上涨 → 命中
    assert basis == "spot"


@pytest.mark.parametrize(
    ("rating", "strategy_sign"),
    [("Buy", 1), ("Sell", 0), ("Hold", 0)],
)
def test_fetch_returns_applies_spot_settlement(
    patched_ohlcv, tmp_path, rating, strategy_sign
):
    """现货口径:Sell/Hold 均结算为 0 收益(不能靠做空获利),仅 Buy 吃到市场收益。"""
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = dict(DEFAULT_CONFIG)
    strategy_return, alpha, days, direction_hit, basis = graph._fetch_returns(
        "BTC", "2021-01-05", holding_days=5, benchmark="BTC/USDT", rating=rating
    )
    market_return = (1.01 ** 5) - 1
    assert strategy_return == pytest.approx(strategy_sign * market_return)
    if rating == "Buy":
        assert alpha == pytest.approx(strategy_return - market_return)
        assert direction_hit is True
    else:
        # short/flat 现货口径:alpha = -bench_return(踏空成本)
        assert alpha == pytest.approx(-market_return)
        if rating == "Sell":
            assert direction_hit is False  # 市场上涨,做空方向判断错误
        else:
            assert direction_hit is None  # Hold/flat 未做方向判断
    assert days == 5
    assert basis == "spot"


def test_return_window_starts_at_same_close_as_mechanical_entry(patched_ohlcv):
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = dict(DEFAULT_CONFIG)
    strategy_return, _, _, _, _ = graph._fetch_returns(
        "BTC", "2021-01-05", holding_days=1, benchmark="BTC/USDT", rating="Buy"
    )
    # Entry at start of Jan 5 equals Jan 4 completed close; one day later uses Jan 5 close.
    assert strategy_return == pytest.approx(0.01)


def test_fetch_returns_waits_for_full_holding_window(monkeypatch):
    candles = _daily_candles(days=3)
    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", lambda *a, **k: candles)
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = dict(DEFAULT_CONFIG)
    assert graph._fetch_returns(
        "BTC", "2021-01-01", holding_days=5, benchmark="BTC/USDT", rating="Buy"
    ) == (None, None, None, None, None)


def test_settlement_window_is_continuous_no_weekend_skip(patched_ohlcv, tmp_path):
    """含周六的窗口：holding_days=5 覆盖连续 5 天，不因'非交易日'缩短。

    2021-01-05 是周二，+5 连续天含 01-09(周六)、01-10(周日)。
    """
    cfg = dict(DEFAULT_CONFIG)
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = cfg
    # trade_date 周二；若按股票日历会跳周末导致 actual_days<5，crypto 应正好 5
    _, _, days, _, _ = graph._fetch_returns(
        "BTC", "2021-01-05", holding_days=5, benchmark="BTC/USDT"
    )
    weekday_sat = datetime.strptime("2021-01-05", "%Y-%m-%d") + timedelta(days=4)
    assert weekday_sat.weekday() == 5  # 确认窗口内确有周六
    assert days == 5


def test_no_yfinance_in_fetch_returns_source():
    """回归守卫：trading_graph 不再 import yfinance。"""
    import btc_agent.graph.trading_graph as tg
    assert not hasattr(tg, "yf")
