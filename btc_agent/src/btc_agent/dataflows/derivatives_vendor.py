"""衍生品盘面 vendor(BTC agent v1 情报层):资金费率 + 未平仓合约(OI)。

crypto 原生盘面指标——现货没有的、能反映杠杆多空拥挤度的信号。只读交易所公开的
永续合约接口(``fetchFundingRate`` / ``fetchOpenInterest``),**不带 key、不下单**。

资金费率(funding rate):正值=多头付费给空头(市场偏多、可能拥挤);负值反之。
未平仓合约(OI):未平仓永续合约名义量,反映杠杆规模。

网络出口集中在 ``_fetch_funding_raw`` / ``_fetch_open_interest_raw``——测试 monkeypatch
即可离线跑。永续所(``ccxt_derivatives_exchange``,默认 binance)与代理经 config 覆盖:
现货默认所 binance.us 无永续,故盘面数据单独取所。
"""

from __future__ import annotations

from datetime import datetime, timezone

import ccxt

from .ccxt_proxy import call_with_proxy_failover
from .config import get_config
from .errors import NoMarketDataError

DEFAULT_DERIVATIVES_EXCHANGE = "binance"
DEFAULT_QUOTE = "USDT"


def _perp_symbol(symbol: str) -> str:
    """把 ``BTC`` 归一到 ccxt 永续统一符号 ``BTC/USDT:USDT``;已含 ``:`` 的原样返回。"""
    s = symbol.strip().upper()
    if ":" in s:
        return s
    base = s.split("/")[0]
    return f"{base}/{DEFAULT_QUOTE}:{DEFAULT_QUOTE}"


def _derivatives_exchange(exchange_id: str):
    """构造 ccxt 永续交易所实例；代理由公共 failover 层逐次注入。"""
    return getattr(ccxt, exchange_id)(
        {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    )


def _derivatives_request(request):
    cfg = get_config()
    exchange_id = cfg.get("ccxt_derivatives_exchange") or DEFAULT_DERIVATIVES_EXCHANGE
    return call_with_proxy_failover(
        cfg,
        lambda: _derivatives_exchange(exchange_id),
        request,
    )


def _fetch_funding_raw(pair: str) -> dict:
    """拉资金费率原始结构。网络出口之一(测试 patch 此函数)。"""
    return _derivatives_request(lambda exchange: exchange.fetch_funding_rate(pair))


def _fetch_open_interest_raw(pair: str) -> dict:
    """拉未平仓合约原始结构。网络出口之一(测试 patch 此函数)。"""
    return _derivatives_request(lambda exchange: exchange.fetch_open_interest(pair))


def get_derivatives_snapshot_data(symbol: str, curr_date: str | None = None) -> dict:
    """返回结构化盘面快照:``{"funding_rate": float, "open_interest": float|None, "symbol": str}``。

    纯数据形态,供仪表盘/规则引擎消费。任一子项取数失败不整体崩:缺失记为 None。
    """
    if curr_date is not None:
        requested = datetime.strptime(curr_date, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        if requested != today:
            raise NoMarketDataError(
                symbol,
                _perp_symbol(symbol),
                "historical funding/OI snapshot is unavailable; refusing current-data fallback",
            )

    pair = _perp_symbol(symbol)
    funding = _fetch_funding_raw(pair)
    rate = funding.get("fundingRate") if isinstance(funding, dict) else None
    if rate is None:
        raise NoMarketDataError(symbol, pair, "no funding rate from derivatives vendor")

    open_interest = None
    try:
        oi = _fetch_open_interest_raw(pair)
        if isinstance(oi, dict):
            open_interest = oi.get("openInterestValue") or oi.get("openInterestAmount")
    except Exception:  # noqa: BLE001 — OI 缺失不应让整份快照失败
        open_interest = None

    return {
        "symbol": pair,
        "funding_rate": float(rate),
        "open_interest": float(open_interest) if open_interest is not None else None,
    }


def get_derivatives_snapshot(symbol: str, curr_date: str | None = None) -> str:
    """盘面快照的格式化文本(供 LLM/报告消费)。``curr_date`` 仅用于表头,盘面数据取当下。"""
    snap = get_derivatives_snapshot_data(symbol, curr_date)
    rate_pct = snap["funding_rate"] * 100
    bias = "偏多(多头付费,警惕拥挤)" if snap["funding_rate"] > 0 else "偏空(空头付费)"
    oi = snap["open_interest"]
    oi_line = f"{oi:,.0f}" if oi is not None else "N/A"
    header_date = f" ({curr_date})" if curr_date else ""
    return (
        f"## Derivatives snapshot for {snap['symbol']}{header_date}\n\n"
        f"- Funding rate: **{rate_pct:.4f}%** — {bias}\n"
        f"- Open interest (notional): **{oi_line}**\n\n"
        f"资金费率正=多头付费给空头(偏多、可能拥挤),负=反之;OI 升=杠杆增仓。"
    )
