"""盘面仪表盘装配(BTC agent v1 情报层)。

从各 vendor 取**结构化**信号,拼成一份供规则引擎消费的 dict。设计铁律:任一 vendor
取数失败(缺 key、网络、地域封锁)只把该字段记为 None 并附 ``errors``,**绝不整体崩**——
情报层要"能出多少出多少",而非一个信号挂掉就交白卷。

价格动量(RSI / 日内涨跌)复用 ccxt OHLCV + stockstats,和决策图同源($64k 现货)。
"""

from __future__ import annotations

import logging

from stockstats import wrap

logger = logging.getLogger(__name__)


def _price_signals(asset: str, curr_date: str | None) -> dict:
    """从 ccxt OHLCV 算最新收盘价、RSI、日内涨跌%。失败抛出交给上层记 error。"""
    from btc_agent.dataflows.ccxt_vendor import _ohlcv_dataframe

    df = _ohlcv_dataframe(asset, curr_date=curr_date)
    if len(df) < 2:
        raise ValueError("not enough candles for price signals")
    stats = wrap(df.copy())
    rsi = float(stats["rsi"].iloc[-1])
    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    move_pct = (last_close - prev_close) / prev_close * 100 if prev_close else None
    return {"close": last_close, "rsi": rsi, "price_move_pct": move_pct}


def build_dashboard(asset: str = "BTC", curr_date: str | None = None) -> dict:
    """装配盘面快照。返回 dict:``fear_greed``/``derivatives``/``rsi``/``price_move_pct``/``close``
    + ``errors``(记录哪些信号取数失败及原因)。规则引擎只依赖前四者,缺失即跳过对应规则。
    """
    dashboard: dict = {
        "asset": asset,
        "curr_date": curr_date,
        "fear_greed": None,
        "derivatives": None,
        "rsi": None,
        "price_move_pct": None,
        "close": None,
        "errors": {},
    }

    # Fear & Greed(免 key)
    try:
        from btc_agent.dataflows.feargreed_vendor import get_fear_greed_value
        dashboard["fear_greed"] = get_fear_greed_value(curr_date)
    except Exception as exc:  # noqa: BLE001 — 单信号失败降级
        dashboard["errors"]["fear_greed"] = str(exc)
        logger.warning("F&G 取数失败:%s", exc)

    # 衍生品盘面(资金费率/OI)
    try:
        from btc_agent.dataflows.derivatives_vendor import get_derivatives_snapshot_data
        dashboard["derivatives"] = get_derivatives_snapshot_data(asset)
    except Exception as exc:  # noqa: BLE001
        dashboard["errors"]["derivatives"] = str(exc)
        logger.warning("衍生品盘面取数失败:%s", exc)

    # 价格动量(ccxt + stockstats)
    try:
        signals = _price_signals(asset, curr_date)
        dashboard["close"] = signals["close"]
        dashboard["rsi"] = signals["rsi"]
        dashboard["price_move_pct"] = signals["price_move_pct"]
    except Exception as exc:  # noqa: BLE001
        dashboard["errors"]["price"] = str(exc)
        logger.warning("价格信号取数失败:%s", exc)

    return dashboard
