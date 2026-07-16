"""ST2 ccxt vendor 离线单测。

不打真实交易所网络：monkeypatch `_fetch_ohlcv_raw`（唯一网络出口）返回录制蜡烛。
覆盖：OHLCV/指标结构、route_to_vendor 对 BTC 路由到 ccxt、fundamentals 已禁用。
"""

from datetime import datetime, timezone

import pytest

from btc_agent.dataflows import ccxt_vendor, interface


def _fake_candles(days: int = 60):
    """构造 `days` 根日线蜡烛：[ms_ts, open, high, low, close, volume]。"""
    base_ms = 1_600_000_000_000  # 固定起点（2020-09），避免依赖当前时间
    day_ms = 86_400_000
    candles = []
    price = 10000.0
    for i in range(days):
        o = price
        h = price * 1.02
        low = price * 0.98
        c = price * 1.01
        candles.append([base_ms + i * day_ms, o, h, low, c, 1000.0 + i])
        price = c
    return candles


@pytest.fixture
def patched_ohlcv(monkeypatch):
    candles = _fake_candles(60)
    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", lambda *a, **k: candles)
    return candles


def test_resolve_pair_defaults_to_usdt():
    assert ccxt_vendor._resolve_pair("BTC") == "BTC/USDT"
    assert ccxt_vendor._resolve_pair("eth") == "ETH/USDT"
    assert ccxt_vendor._resolve_pair("BTC/USD") == "BTC/USD"


def test_asof_cutoff_excludes_same_day_candle(monkeypatch):
    """日线 timestamp 是开盘时刻；决策日当天完整 OHLC 不可在开盘前可见。"""
    day_ms = 86_400_000
    base = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    candles = [
        [base, 100, 110, 90, 105, 1],
        [base + day_ms, 105, 999, 1, 888, 1],
    ]
    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", lambda *a, **k: candles)
    df = ccxt_vendor._ohlcv_dataframe("BTC", curr_date="2021-01-02")
    assert df["Close"].tolist() == [105]
    rendered = ccxt_vendor.get_ccxt_data("BTC", "2021-01-01", "2021-01-02")
    assert "105" in rendered
    assert "888" not in rendered


def test_indicator_asof_does_not_compute_from_same_day_candle(monkeypatch):
    day_ms = 86_400_000
    base = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    candles = [
        [base, 100, 110, 90, 105, 1],
        [base + day_ms, 105, 999, 1, 888, 1],
    ]
    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", lambda *a, **k: candles)
    out = ccxt_vendor.get_ccxt_indicators_window("BTC", "rsi", "2021-01-02", 1)
    assert "2021-01-02: N/A" in out


def test_get_ccxt_data_returns_ohlcv_csv(patched_ohlcv):
    out = ccxt_vendor.get_ccxt_data("BTC", "2020-09-15", "2020-10-20")
    assert "Crypto OHLCV for BTC/USDT" in out
    assert "Date,Open,High,Low,Close,Volume" in out
    # 表头 + 至少一行数据
    assert "Total records:" in out


def test_get_ccxt_indicators_window(patched_ohlcv):
    out = ccxt_vendor.get_ccxt_indicators_window("BTC", "close_10_ema", "2020-10-20", 5)
    assert "close_10_ema values" in out
    # 窗口内每天一行
    assert "2020-10-20:" in out


def test_unsupported_indicator_raises(patched_ohlcv):
    with pytest.raises(ValueError):
        ccxt_vendor.get_ccxt_indicators_window("BTC", "not_an_indicator", "2020-10-20", 5)


def test_route_to_vendor_uses_ccxt_for_get_stock_data(patched_ohlcv):
    """默认 config 下 get_stock_data 应路由到 ccxt 实现（返回 crypto OHLCV）。"""
    out = interface.route_to_vendor("get_stock_data", "BTC", "2020-09-15", "2020-10-20")
    assert "Crypto OHLCV for BTC/USDT" in out


def test_fundamentals_routes_disabled():
    """fundamentals 四方法应被显式禁用，不回退到股票财报。"""
    for method in ("get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"):
        assert method not in interface.VENDOR_METHODS
        with pytest.raises(ValueError):
            interface.route_to_vendor(method, "BTC")


def test_ccxt_registered_in_vendor_list():
    assert "ccxt" in interface.VENDOR_LIST
    assert "ccxt" in interface.VENDOR_METHODS["get_stock_data"]
    assert "ccxt" in interface.VENDOR_METHODS["get_indicators"]
