"""Crypto 新闻 vendor —— 官方 RSS 聚合(BTC agent v1 情报层)。

**为什么不是 CryptoPanic**:CryptoPanic 的免费 Developer API 已于 2026-04-01 停用
(改为付费)。RSS 是**零 key、零成本、无失效风险**的替代:直接抓各大 crypto 媒体的
官方 RSS(默认 Cointelegraph + Decrypt),用 stdlib 解析,不加依赖。

与其它 vendor 同构:``get_crypto_rss_news`` 对应 ``get_news``(按币种关键词 + 日期窗口
过滤),``get_crypto_rss_global_news`` 对应 ``get_global_news``(全市场头条)。网络出口
集中在 ``_fetch_feed``——测试 monkeypatch 该函数即可离线跑。单个源抓取/解析失败只跳过
该源,不拖垮整体(RSS 偶发畸形实体/连接重置很常见)。
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
from dateutil.relativedelta import relativedelta

from .config import get_config

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15

# 默认 RSS 源(实测直连可达、标准 RSS 2.0)。可由 config["crypto_rss_feeds"] 覆盖。
DEFAULT_FEEDS = [
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
]

# 币种 → 标题/摘要匹配关键词(get_news 按此过滤;大小写不敏感)。
_CURRENCY_KEYWORDS = {
    "BTC": ("btc", "bitcoin"),
    "ETH": ("eth", "ethereum", "ether"),
    "SOL": ("sol", "solana"),
    "XRP": ("xrp", "ripple"),
    "DOGE": ("doge", "dogecoin"),
}


def _fetch_feed(url: str) -> bytes:
    """抓一个 RSS 源返回原始 XML 字节。网络唯一出口(测试 patch 此函数)。"""
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.content


_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str) -> str:
    """去掉 RSS 摘要里的 HTML 标签并反转义实体,压成干净一行(喂 LLM 无噪声)。"""
    stripped = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()


def _parse_published(value: str | None) -> datetime | None:
    """解析 RSS 的 RFC-822 pubDate(``Wed, 15 Jul 2026 11:05:46 +0000``)为 naive datetime。"""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except (TypeError, ValueError):
        return None


def _parse_items(xml_bytes: bytes, source: str) -> list[dict]:
    """把一个源的 XML 解析成 [{title, link, summary, published, source}]。畸形 XML 返回 []。"""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning("RSS 源 %s 解析失败,跳过:%s", source, exc)
        return []
    items = []
    for item in root.findall(".//item"):
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "summary": _clean_html(item.findtext("description") or ""),
            "published": _parse_published(item.findtext("pubDate")),
            "source": source,
        })
    return items


def _collect_items() -> list[dict]:
    """抓取所有配置的源并汇总条目。逐源容错:一个源失败只记 warning 不影响其它。"""
    feeds = get_config().get("crypto_rss_feeds") or DEFAULT_FEEDS
    collected: list[dict] = []
    for source, url in feeds:
        try:
            collected += _parse_items(_fetch_feed(url), source)
        except Exception as exc:  # noqa: BLE001 — 单源失败不该拖垮聚合
            logger.warning("RSS 源 %s (%s) 抓取失败,跳过:%s", source, url, exc)
    return collected


def _currency_keywords(ticker: str) -> tuple[str, ...]:
    """把 ``BTC`` / ``BTC/USDT`` 归一到匹配关键词;未知币种回退到 base 符号本身。"""
    base = ticker.strip().upper().split("/")[0].split("-")[0]
    return _CURRENCY_KEYWORDS.get(base, (base.lower(),))


def _in_window(pub: datetime | None, start: datetime, end: datetime) -> bool:
    """条目是否落在 [start, end] 窗口(右界含 end 当天)。无日期的条目:窗口触及当下才保留(防前视)。"""
    if pub is not None:
        return start <= pub <= end + relativedelta(days=1)
    return end >= datetime.now() - relativedelta(days=1)


def _render(items: list[dict], header: str) -> str:
    body = ""
    for it in items:
        date_str = it["published"].strftime("%Y-%m-%d") if it["published"] else "n/d"
        body += f"### {it['title']} (source: {it['source']}, {date_str})\n"
        if it["summary"]:
            body += f"{it['summary'][:400]}\n"
        if it["link"]:
            body += f"Link: {it['link']}\n"
        body += "\n"
    return f"{header}\n\n{body}"


def get_crypto_rss_news(ticker: str, start_date: str, end_date: str) -> str:
    """``get_news`` 的 RSS 实现:按币种关键词 + 日期窗口过滤。"""
    currency = ticker.strip().upper().split("/")[0].split("-")[0]
    keywords = _currency_keywords(ticker)
    limit = get_config().get("news_article_limit", 20)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    matched = []
    for it in _collect_items():
        if not _in_window(it["published"], start_dt, end_dt):
            continue
        text = f"{it['title']} {it['summary']}".lower()
        if any(kw in text for kw in keywords):
            matched.append(it)
        if len(matched) >= limit:
            break

    if not matched:
        return f"No crypto RSS news found for {currency} between {start_date} and {end_date}"
    return _render(matched, f"## {currency} News (Crypto RSS), from {start_date} to {end_date}:")


def get_crypto_rss_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """``get_global_news`` 的 RSS 实现:全市场 crypto 头条(不按币种过滤)。"""
    config = get_config()
    if look_back_days is None:
        look_back_days = config.get("global_news_lookback_days", 7)
    if limit is None:
        limit = config.get("global_news_article_limit", 10)

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    items = [it for it in _collect_items() if _in_window(it["published"], start_dt, curr_dt)]
    items.sort(key=lambda it: it["published"] or datetime.min, reverse=True)
    items = items[:limit]

    if not items:
        return f"No crypto RSS global news found between {start_date} and {curr_date}"
    return _render(items, f"## Global Crypto News (RSS), from {start_date} to {curr_date}:")
