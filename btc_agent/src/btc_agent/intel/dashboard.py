"""盘面仪表盘装配(BTC agent v1 情报层)。

从统一证据快照(``evidence.EvidenceSnapshot``)装配一份供规则引擎消费的 dict。
设计铁律:任一信号源缺失(快照 health 记录了取数失败、缺 key、网络、地域封锁)
只把该字段记为 None 并附 ``errors``,**绝不整体崩**——情报层要"能出多少出多少",
而非一个信号挂掉就交白卷。

价格动量(RSI / 日内涨跌)复用快照里的 OHLCV(ccxt + stockstats),和决策图同源
($64k 现货),且与 ``run.py`` 机械交易价位消费同一份快照——同一次运行只取一次数。
"""

from __future__ import annotations

import logging

from stockstats import wrap

logger = logging.getLogger(__name__)


def _price_signals_from_ohlcv(df) -> dict:
    """从快照里的 OHLCV DataFrame 算最新收盘价、RSI、日内涨跌%。失败抛出交给上层记 error。"""
    if df is None or len(df) < 2:
        raise ValueError("not enough candles for price signals")
    stats = wrap(df.copy())
    rsi = float(stats["rsi"].iloc[-1])
    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    move_pct = (last_close - prev_close) / prev_close * 100 if prev_close else None
    return {"close": last_close, "rsi": rsi, "price_move_pct": move_pct}


def _health_reason(health_value: str | None) -> str:
    """把快照 health 里的 ``error:<reason>`` 剥成纯 reason 文本(与旧 errors 字段格式一致)。"""
    if not health_value:
        return "unknown"
    if health_value.startswith("error:"):
        return health_value.split("error:", 1)[1]
    return health_value


def build_dashboard(asset: str = "BTC", curr_date: str | None = None, snapshot=None) -> dict:
    """装配盘面快照。返回 dict:``fear_greed``/``derivatives``/``rsi``/``price_move_pct``/``close``
    + ``errors``(记录哪些信号取数失败及原因)。规则引擎只依赖前四者,缺失即跳过对应规则。

    ``snapshot`` 可注入一份已冻结的 ``EvidenceSnapshot``(与 ``run.py`` 的机械价位
    计算共用同一份取数结果);缺省时按 ``asset``/``curr_date`` 自建一份。
    """
    if snapshot is None:
        from btc_agent.evidence import build_evidence_snapshot

        snapshot = build_evidence_snapshot(asset, curr_date)

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
    if snapshot.health.get("fear_greed") == "ok":
        dashboard["fear_greed"] = snapshot.fear_greed
    else:
        reason = _health_reason(snapshot.health.get("fear_greed"))
        dashboard["errors"]["fear_greed"] = reason
        logger.warning("F&G 取数失败:%s", reason)

    # 衍生品盘面(资金费率/OI)
    if snapshot.health.get("derivatives") == "ok":
        dashboard["derivatives"] = snapshot.derivatives
    else:
        reason = _health_reason(snapshot.health.get("derivatives"))
        dashboard["errors"]["derivatives"] = reason
        logger.warning("衍生品盘面取数失败:%s", reason)

    # 价格动量(快照里的 ccxt OHLCV + stockstats)
    if snapshot.health.get("ohlcv") == "ok":
        try:
            signals = _price_signals_from_ohlcv(snapshot.ohlcv)
            dashboard["close"] = signals["close"]
            dashboard["rsi"] = signals["rsi"]
            dashboard["price_move_pct"] = signals["price_move_pct"]
        except Exception as exc:  # noqa: BLE001 — 单信号失败降级
            dashboard["errors"]["price"] = str(exc)
            logger.warning("价格信号计算失败:%s", exc)
    else:
        reason = _health_reason(snapshot.health.get("ohlcv"))
        dashboard["errors"]["price"] = reason
        logger.warning("价格信号取数失败:%s", reason)

    return dashboard
