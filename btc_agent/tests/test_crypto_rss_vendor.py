"""crypto_rss_vendor 离线单测:mock RSS 抓取,验证解析/过滤/容错/路由。"""

import pytest

from btc_agent.dataflows import crypto_rss_vendor as rss
from btc_agent.dataflows import interface

_SAMPLE = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Bitcoin surges past resistance</title>
    <link>https://ex.com/btc</link>
    <description>BTC rallied hard today</description>
    <pubDate>Tue, 14 Jul 2026 09:30:00 +0000</pubDate>
  </item>
  <item>
    <title>Ethereum upgrade ships</title>
    <link>https://ex.com/eth</link>
    <description>Ether network update</description>
    <pubDate>Tue, 14 Jul 2026 10:00:00 +0000</pubDate>
  </item>
  <item>
    <title>Old bitcoin story</title>
    <link>https://ex.com/old</link>
    <description>ancient</description>
    <pubDate>Wed, 01 Jan 2020 00:00:00 +0000</pubDate>
  </item>
</channel></rss>"""


@pytest.fixture
def patched_feed(monkeypatch):
    monkeypatch.setattr(rss, "_fetch_feed", lambda url: _SAMPLE)
    # 单一源,避免多源重复
    monkeypatch.setattr(rss, "DEFAULT_FEEDS", [("TestFeed", "http://x")])


def test_currency_keywords():
    assert rss._currency_keywords("BTC") == ("btc", "bitcoin")
    assert rss._currency_keywords("BTC/USDT") == ("btc", "bitcoin")
    assert rss._currency_keywords("FOO") == ("foo",)  # 未知币种回退 base


def test_parse_items():
    items = rss._parse_items(_SAMPLE, "TestFeed")
    assert len(items) == 3
    assert items[0]["title"] == "Bitcoin surges past resistance"
    assert items[0]["published"].year == 2026


def test_news_filters_by_currency_and_window(patched_feed):
    out = rss.get_crypto_rss_news("BTC", "2026-07-10", "2026-07-15")
    assert "Bitcoin surges past resistance" in out
    assert "Ethereum upgrade" not in out       # 关键词不匹配 BTC
    assert "Old bitcoin story" not in out       # 窗口外


def test_global_news_all_symbols(patched_feed):
    out = rss.get_crypto_rss_global_news("2026-07-15", look_back_days=7)
    assert "Bitcoin surges" in out
    assert "Ethereum upgrade" in out            # 全市场不按币种过滤
    assert "Old bitcoin story" not in out       # 窗口外


def test_bad_feed_degrades(monkeypatch):
    """一个源抛异常时应跳过、不崩,其它源仍返回。"""
    def _feeds():
        return [("Bad", "http://bad"), ("Good", "http://good")]
    monkeypatch.setattr(rss, "DEFAULT_FEEDS", _feeds())

    def _fetch(url):
        if "bad" in url:
            raise RuntimeError("connection reset")
        return _SAMPLE
    monkeypatch.setattr(rss, "_fetch_feed", _fetch)
    items = rss._collect_items()
    assert len(items) == 3   # 只来自 Good 源,Bad 被跳过


def test_malformed_xml_returns_empty():
    assert rss._parse_items(b"<not xml <<<", "X") == []


def test_cryptorss_registered_as_default():
    assert interface.VENDOR_METHODS["get_news"]["cryptorss"] is rss.get_crypto_rss_news
    assert "cryptorss" in interface.VENDOR_METHODS["get_global_news"]
    assert "cryptorss" in interface.VENDOR_LIST
