"""v1 情报层 vendor 离线单测:CryptoPanic / Fear&Greed / 衍生品盘面。

不打真实网络:monkeypatch 各 vendor 的唯一网络出口函数返回录制样本。
覆盖:格式化输出、结构化数据、缺 key 抛 NotConfigured、route_to_vendor 路由。
"""

from datetime import datetime, timezone

import pytest

from btc_agent.dataflows import (
    cryptopanic_vendor,
    derivatives_vendor,
    feargreed_vendor,
    interface,
)
from btc_agent.dataflows.cryptopanic_vendor import CryptoPanicNotConfiguredError


# ---------------- CryptoPanic ----------------

def _fake_cp_response():
    return {
        "results": [
            {
                "title": "BTC breaks resistance",
                "published_at": "2026-07-14T09:30:00Z",
                "url": "https://example.com/a",
                "source": {"title": "CoinDesk"},
                "votes": {"positive": 12, "negative": 1},
            },
            {
                "title": "Old news outside window",
                "published_at": "2020-01-01T00:00:00Z",
                "url": "https://example.com/b",
                "source": {"title": "X"},
            },
        ]
    }


def test_cryptopanic_currency_code():
    assert cryptopanic_vendor._currency_code("BTC") == "BTC"
    assert cryptopanic_vendor._currency_code("BTC/USDT") == "BTC"
    assert cryptopanic_vendor._currency_code("eth-usd") == "ETH"


def test_cryptopanic_news_filters_window(monkeypatch):
    monkeypatch.setattr(cryptopanic_vendor, "_request", lambda params: _fake_cp_response())
    out = cryptopanic_vendor.get_cryptopanic_news("BTC", "2026-07-10", "2026-07-15")
    assert "BTC breaks resistance" in out
    assert "votes positive:12" in out
    assert "Old news outside window" not in out  # 窗口外被过滤


def test_cryptopanic_missing_token_raises(monkeypatch):
    monkeypatch.delenv("CRYPTOPANIC_API_TOKEN", raising=False)
    with pytest.raises(CryptoPanicNotConfiguredError):
        cryptopanic_vendor.get_api_token()


def test_cryptopanic_registered():
    assert "cryptopanic" in interface.VENDOR_METHODS["get_news"]
    assert "cryptopanic" in interface.VENDOR_METHODS["get_global_news"]
    assert "cryptopanic" in interface.VENDOR_LIST


# ---------------- Fear & Greed ----------------

def _fake_fng():
    return {
        "data": [
            {"value": "15", "value_classification": "Extreme Fear", "timestamp": "1752537600"},
        ]
    }


def test_fear_greed_value(monkeypatch):
    monkeypatch.setattr(feargreed_vendor, "_request", lambda limit: _fake_fng())
    fng = feargreed_vendor.get_fear_greed_value()
    assert fng["value"] == 15
    assert fng["classification"] == "Extreme Fear"


def test_fear_greed_text(monkeypatch):
    monkeypatch.setattr(feargreed_vendor, "_request", lambda limit: _fake_fng())
    out = feargreed_vendor.get_fear_greed()
    assert "15/100" in out
    assert "Extreme Fear" in out


def test_fear_greed_historical_query_never_falls_back_to_future(monkeypatch):
    """只有 cutoff 之后的数据时应白卷，而不是伪装成历史值。"""
    future = datetime(2026, 7, 16, tzinfo=timezone.utc)
    monkeypatch.setattr(
        feargreed_vendor,
        "_request",
        lambda limit: {
            "data": [{
                "value": "88",
                "value_classification": "Extreme Greed",
                "timestamp": str(int(future.timestamp())),
            }]
        },
    )
    with pytest.raises(ValueError, match="no data on/before"):
        feargreed_vendor.get_fear_greed_value("2020-01-01")


# ---------------- Derivatives ----------------

def test_perp_symbol():
    assert derivatives_vendor._perp_symbol("BTC") == "BTC/USDT:USDT"
    assert derivatives_vendor._perp_symbol("ETH/USDT:USDT") == "ETH/USDT:USDT"


def test_derivatives_snapshot_data(monkeypatch):
    monkeypatch.setattr(derivatives_vendor, "_fetch_funding_raw",
                        lambda pair: {"fundingRate": 0.0012})
    monkeypatch.setattr(derivatives_vendor, "_fetch_open_interest_raw",
                        lambda pair: {"openInterestValue": 5_000_000_000})
    snap = derivatives_vendor.get_derivatives_snapshot_data("BTC")
    assert snap["funding_rate"] == pytest.approx(0.0012)
    assert snap["open_interest"] == 5_000_000_000


def test_derivatives_oi_failure_degrades(monkeypatch):
    """OI 取数失败不该让整份快照崩,funding 仍返回。"""
    monkeypatch.setattr(derivatives_vendor, "_fetch_funding_raw",
                        lambda pair: {"fundingRate": -0.0003})
    def _boom(pair):
        raise RuntimeError("OI endpoint down")
    monkeypatch.setattr(derivatives_vendor, "_fetch_open_interest_raw", _boom)
    snap = derivatives_vendor.get_derivatives_snapshot_data("BTC")
    assert snap["funding_rate"] == pytest.approx(-0.0003)
    assert snap["open_interest"] is None


def test_derivatives_historical_snapshot_refuses_current_fallback():
    with pytest.raises(Exception, match="historical funding/OI snapshot is unavailable"):
        derivatives_vendor.get_derivatives_snapshot_data("BTC", "2020-01-01")


def test_new_categories_registered():
    assert "get_fear_greed_index" in interface.VENDOR_METHODS
    assert "get_derivatives" in interface.VENDOR_METHODS
    assert "sentiment_index" in interface.OPTIONAL_CATEGORIES
    assert "derivatives" in interface.OPTIONAL_CATEGORIES
