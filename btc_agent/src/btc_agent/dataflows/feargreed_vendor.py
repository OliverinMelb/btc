"""Crypto Fear & Greed 指数 vendor(BTC agent v1 情报层)。

数据源 alternative.me 的免费 Fear & Greed 指数(0=极度恐惧, 100=极度贪婪),
**无需 API key**。市场情绪的单一标量,极值处常是反向信号,喂给情报仪表盘/告警规则。

网络出口集中在 ``_request``——测试 monkeypatch 该函数即可离线跑。
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

# alternative.me 免费 F&G 端点。limit=N 返回最近 N 天(含当天)。
FNG_API_BASE = "https://api.alternative.me/fng/"
REQUEST_TIMEOUT = 30


def _request(limit: int) -> dict:
    """GET alternative.me F&G 端点。网络唯一出口(测试 patch 此函数)。"""
    response = requests.get(
        FNG_API_BASE, params={"limit": limit, "format": "json"}, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def get_fear_greed_value(curr_date: str | None = None, look_back_days: int = 0) -> dict:
    """返回最新一条 F&G 结构化数据:``{"value": int, "classification": str, "date": str}``。

    ``look_back_days`` > 0 时会取更长窗口,但本函数只返回窗口内最新一条(<= curr_date)。
    纯数据形态,供仪表盘/规则引擎消费(区别于给 LLM 的格式化文本)。
    """
    cutoff = datetime.strptime(curr_date, "%Y-%m-%d") if curr_date else None
    # 该 API 从今天向过去返回 limit 条。历史 as-of 查询必须覆盖今天到 cutoff
    # 的距离，否则 limit=1 只会拿到今天并造成前视回退。
    history_days = (
        max(0, (datetime.now(timezone.utc).date() - cutoff.date()).days) + 2
        if cutoff
        else 1
    )
    limit = max(1, look_back_days + 1, history_days)
    data = _request(limit)
    rows = data.get("data", [])
    if not rows:
        raise ValueError("Fear & Greed API returned no data.")

    chosen = None
    for row in rows:  # 端点按时间倒序返回,第一条满足 <= cutoff 的即最新
        ts = row.get("timestamp")
        row_dt = (
            datetime.fromtimestamp(int(ts), timezone.utc).replace(tzinfo=None)
            if ts is not None
            else None
        )
        if cutoff is not None:
            if row_dt is None or row_dt > cutoff:
                continue
        chosen = (row, row_dt)
        break
    if chosen is None:
        raise ValueError(f"Fear & Greed API has no data on/before {curr_date}.")

    row, row_dt = chosen
    return {
        "value": int(row["value"]),
        "classification": row.get("value_classification", ""),
        "date": row_dt.strftime("%Y-%m-%d") if row_dt else (curr_date or ""),
    }


def get_fear_greed(curr_date: str | None = None, look_back_days: int = 0) -> str:
    """F&G 的格式化文本(供 LLM/报告消费)。"""
    fng = get_fear_greed_value(curr_date, look_back_days)
    return (
        f"## Crypto Fear & Greed Index ({fng['date']})\n\n"
        f"- Value: **{fng['value']}/100**\n"
        f"- Classification: **{fng['classification']}**\n\n"
        f"极值处常为反向信号:接近 0(极度恐惧)历史上偏底部区,接近 100(极度贪婪)偏顶部区。"
    )
