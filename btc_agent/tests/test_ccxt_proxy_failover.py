"""CCXT 代理候选切换的离线行为测试。"""

import importlib
from datetime import datetime, timezone

import ccxt
import pytest

import btc_agent.default_config as default_config
from btc_agent.dataflows import ccxt_vendor, derivatives_vendor


PRIMARY_PROXY = "http://127.0.0.1:6696"
FALLBACK_PROXY = "http://127.0.0.1:7890"


def _candles() -> list[list[float]]:
    start = int(datetime(2026, 8, 18, tzinfo=timezone.utc).timestamp() * 1000)
    return [[start, 100.0, 110.0, 90.0, 105.0, 1_000.0]]


def test_spot_market_data_switches_proxy_after_network_error(monkeypatch):
    attempts = []

    class FakeExchange:
        httpsProxy = None

        def fetch_ohlcv(self, pair, timeframe, limit):
            attempts.append(self.httpsProxy)
            if self.httpsProxy == PRIMARY_PROXY:
                raise ccxt.NetworkError("primary proxy unavailable")
            return _candles()

    monkeypatch.setattr(
        ccxt_vendor,
        "get_config",
        lambda: {
            "ccxt_exchange": "binanceus",
            "ccxt_proxy": PRIMARY_PROXY,
            "ccxt_proxy_fallbacks": [FALLBACK_PROXY],
        },
    )
    monkeypatch.setattr(ccxt, "binanceus", lambda _options: FakeExchange())

    result = ccxt_vendor.get_ccxt_data("BTC", "2026-08-18", "2026-08-20")

    assert attempts == [PRIMARY_PROXY, FALLBACK_PROXY]
    assert "Crypto OHLCV for BTC/USDT" in result


def test_derivatives_switch_proxy_for_funding_and_open_interest(monkeypatch):
    attempts = {"funding": [], "open_interest": []}

    class FakeExchange:
        httpsProxy = None

        def fetch_funding_rate(self, pair):
            attempts["funding"].append(self.httpsProxy)
            if self.httpsProxy == PRIMARY_PROXY:
                raise ccxt.NetworkError("primary proxy unavailable")
            return {"fundingRate": 0.0005}

        def fetch_open_interest(self, pair):
            attempts["open_interest"].append(self.httpsProxy)
            if self.httpsProxy == PRIMARY_PROXY:
                raise ccxt.NetworkError("primary proxy unavailable")
            return {"openInterestValue": 2_000_000.0}

    monkeypatch.setattr(
        derivatives_vendor,
        "get_config",
        lambda: {
            "ccxt_derivatives_exchange": "okx",
            "ccxt_proxy": PRIMARY_PROXY,
            "ccxt_proxy_fallbacks": [FALLBACK_PROXY],
        },
    )
    monkeypatch.setattr(ccxt, "okx", lambda _options: FakeExchange())

    result = derivatives_vendor.get_derivatives_snapshot_data("BTC")

    assert attempts == {
        "funding": [PRIMARY_PROXY, FALLBACK_PROXY],
        "open_interest": [PRIMARY_PROXY, FALLBACK_PROXY],
    }
    assert result["funding_rate"] == 0.0005
    assert result["open_interest"] == 2_000_000.0


def test_spot_market_data_does_not_retry_business_error(monkeypatch):
    attempts = []

    class FakeExchange:
        httpsProxy = None

        def fetch_ohlcv(self, pair, timeframe, limit):
            attempts.append(self.httpsProxy)
            raise ccxt.BadSymbol(pair)

    monkeypatch.setattr(
        ccxt_vendor,
        "get_config",
        lambda: {
            "ccxt_exchange": "binanceus",
            "ccxt_proxy": PRIMARY_PROXY,
            "ccxt_proxy_fallbacks": [FALLBACK_PROXY],
        },
    )
    monkeypatch.setattr(ccxt, "binanceus", lambda _options: FakeExchange())

    with pytest.raises(ccxt.BadSymbol):
        ccxt_vendor.get_ccxt_data("INVALID", "2026-08-18", "2026-08-20")

    assert attempts == [PRIMARY_PROXY]


def test_default_proxy_order_and_environment_override(monkeypatch):
    assert default_config.DEFAULT_CONFIG["ccxt_proxy"] == PRIMARY_PROXY
    assert default_config.DEFAULT_CONFIG["ccxt_proxy_fallbacks"] == [FALLBACK_PROXY]

    with monkeypatch.context() as env:
        env.setenv("TRADINGAGENTS_CCXT_PROXY", "http://127.0.0.1:10809")
        env.setenv(
            "TRADINGAGENTS_CCXT_PROXY_FALLBACKS",
            "http://127.0.0.1:7890, http://127.0.0.1:1080",
        )
        reloaded = importlib.reload(default_config)
        assert reloaded.DEFAULT_CONFIG["ccxt_proxy"] == "http://127.0.0.1:10809"
        assert reloaded.DEFAULT_CONFIG["ccxt_proxy_fallbacks"] == [
            "http://127.0.0.1:7890",
            "http://127.0.0.1:1080",
        ]

    importlib.reload(default_config)
