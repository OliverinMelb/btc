"""CryptoPanic 新闻 vendor(BTC agent v1 情报层)。

替代 yfinance 成为 crypto 的新闻数据源。CryptoPanic 聚合各交易所/媒体/推特的
crypto 头条,按币种(currencies=BTC)过滤,自带看涨/看跌投票信号。与其它 vendor 同构:
- ``get_cryptopanic_news`` 对应 ``get_news``,按 ticker + 日期窗口返回格式化字符串;
- ``get_cryptopanic_global_news`` 对应 ``get_global_news``,取全市场 crypto 头条。

网络出口集中在 ``_request``——测试 monkeypatch 该函数即可离线跑。免费 token 从
``CRYPTOPANIC_API_TOKEN`` 读;未设置时抛 ``CryptoPanicNotConfiguredError``,
路由层据此视为"该 vendor 不可用"而非硬崩。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests
from dateutil.relativedelta import relativedelta

from .config import get_config
from .errors import VendorNotConfiguredError

# CryptoPanic 免费公开 API(posts 端点)。public=true 返回公共时间线。
CRYPTOPANIC_API_BASE = "https://cryptopanic.com/api/v1/posts/"

# 网络超时(秒),与 fred/alpha_vantage 客户端一致,避免请求悬挂拖住流程。
REQUEST_TIMEOUT = 30


class CryptoPanicNotConfiguredError(VendorNotConfiguredError):
    """选了 CryptoPanic 但未配置 API token 时抛出。

    继承 VendorNotConfiguredError(也是 ValueError),路由层"vendor 不可用"
    处理与既有 ValueError 调用方都能继续工作。
    """


def get_api_token() -> str:
    """从环境变量读取 CryptoPanic API token(免费注册即得)。"""
    token = os.getenv("CRYPTOPANIC_API_TOKEN")
    if not token:
        raise CryptoPanicNotConfiguredError(
            "CRYPTOPANIC_API_TOKEN environment variable is not set. Get a free "
            "token at https://cryptopanic.com/developers/api/."
        )
    return token


def _request(params: dict[str, Any]) -> dict:
    """GET CryptoPanic posts 端点,附带 auth_token。网络唯一出口(测试 patch 此函数)。"""
    api_params = {**params, "auth_token": get_api_token(), "public": "true"}
    response = requests.get(
        CRYPTOPANIC_API_BASE, params=api_params, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def _currency_code(ticker: str) -> str:
    """把 ``BTC`` / ``BTC/USDT`` / ``BTC-USD`` 归一到 CryptoPanic 的币种代码 ``BTC``。"""
    s = ticker.strip().upper()
    for sep in ("/", "-"):
        if sep in s:
            s = s.split(sep)[0]
            break
    return s


def _parse_published(value: str | None) -> datetime | None:
    """解析 CryptoPanic 的 ISO 时间(``2026-07-14T09:30:00Z``)为 naive datetime。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _vote_summary(votes: dict | None) -> str:
    """把 CryptoPanic 的投票字典压成一行看涨/看跌信号,无则空串。"""
    if not isinstance(votes, dict):
        return ""
    parts = []
    for key in ("positive", "negative", "important"):
        val = votes.get(key)
        if val:
            parts.append(f"{key}:{val}")
    return f" [votes {', '.join(parts)}]" if parts else ""


def _render_posts(posts: list[dict], start_dt: datetime, end_dt: datetime) -> tuple[str, int]:
    """渲染落在 [start_dt, end_dt] 窗口内的帖子,返回(正文, 计数)。防前视:窗口右界含 end 当天。"""
    body = ""
    kept = 0
    for post in posts:
        pub = _parse_published(post.get("published_at") or post.get("created_at"))
        if pub is not None and not (start_dt <= pub <= end_dt + relativedelta(days=1)):
            continue
        title = post.get("title", "No title")
        source = (post.get("source") or {}).get("title", "Unknown")
        url = post.get("url", "")
        votes = _vote_summary(post.get("votes"))
        date_str = pub.strftime("%Y-%m-%d") if pub else "n/d"
        body += f"### {title} (source: {source}, {date_str}){votes}\n"
        if url:
            body += f"Link: {url}\n"
        body += "\n"
        kept += 1
    return body, kept


def get_cryptopanic_news(ticker: str, start_date: str, end_date: str) -> str:
    """``get_news`` 的 CryptoPanic 实现:按币种 + 日期窗口返回格式化新闻。"""
    currency = _currency_code(ticker)
    limit = get_config().get("news_article_limit", 20)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    data = _request({"currencies": currency, "kind": "news"})
    posts = data.get("results", [])[:limit]
    if not posts:
        return f"No CryptoPanic news found for {currency}"

    body, kept = _render_posts(posts, start_dt, end_dt)
    if kept == 0:
        return f"No CryptoPanic news found for {currency} between {start_date} and {end_date}"
    return f"## {currency} News (CryptoPanic), from {start_date} to {end_date}:\n\n{body}"


def get_cryptopanic_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """``get_global_news`` 的 CryptoPanic 实现:全市场 crypto 头条(不按单一币种过滤)。"""
    config = get_config()
    if look_back_days is None:
        look_back_days = config.get("global_news_lookback_days", 7)
    if limit is None:
        limit = config.get("global_news_article_limit", 10)

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    data = _request({"kind": "news", "filter": "hot"})
    posts = data.get("results", [])[:limit]
    if not posts:
        return f"No CryptoPanic global news found for {curr_date}"

    body, kept = _render_posts(posts, start_dt, curr_dt)
    if kept == 0:
        return f"No CryptoPanic global news found between {start_date} and {curr_date}"
    return f"## Global Crypto News (CryptoPanic), from {start_date} to {curr_date}:\n\n{body}"
