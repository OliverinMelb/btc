"""机械交易价位规则（BTC agent v0 / ST4）。

铁律:**交易价位由确定性规则算，LLM 只出方向评级，绝不报买卖数字。**
本模块是纯函数,输入 OHLCV + 方向,输出 {entry, stop, target}。不接触任何 LLM 文本,
改 LLM 输出不会改变这里的价位(由单测固化)。

v0 用最简单可解释的一种:以最近收盘为基准 + ATR(14) 定风险距离。
- 看多(long)：entry=现价; stop=entry - k_stop*ATR; target=entry + k_target*ATR
- 看空(short)：对称
- 中性(flat/hold)：不给方向性价位,entry=现价,stop=target=None
风险回报比默认 1:2(k_stop=1.5, k_target=3.0),留 v2 精修。
"""

from __future__ import annotations

import pandas as pd

# 方向归一:5 档评级 → long / short / flat
LONG_RATINGS = {"buy", "overweight"}
SHORT_RATINGS = {"sell", "underweight"}
FLAT_RATINGS = {"hold"}

DEFAULT_ATR_PERIOD = 14
DEFAULT_K_STOP = 1.5
DEFAULT_K_TARGET = 3.0


def rating_to_direction(rating: str) -> str:
    """把评级(大小写不敏感)映射到 long/short/flat。未知评级按 flat 处理。"""
    r = (rating or "").strip().lower()
    if r in LONG_RATINGS:
        return "long"
    if r in SHORT_RATINGS:
        return "short"
    return "flat"


def compute_atr(ohlcv: pd.DataFrame, period: int = DEFAULT_ATR_PERIOD) -> float:
    """Wilder True Range 的简单均值 ATR。列名需含 High/Low/Close。"""
    if len(ohlcv) < 2:
        raise ValueError("compute_atr 需要至少 2 根 K 线")
    high = ohlcv["High"].astype(float)
    low = ohlcv["Low"].astype(float)
    close = ohlcv["Close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    window = min(period, len(tr.dropna()))
    return float(tr.dropna().tail(window).mean())


def compute_trade_levels(
    ohlcv: pd.DataFrame,
    direction: str,
    *,
    atr_period: int = DEFAULT_ATR_PERIOD,
    k_stop: float = DEFAULT_K_STOP,
    k_target: float = DEFAULT_K_TARGET,
) -> dict:
    """由 OHLCV + 方向机械算出 {entry, stop, target, atr}。

    ``direction`` ∈ {"long","short","flat"}（用 ``rating_to_direction`` 从评级转）。
    flat 不给方向性 stop/target。返回值四舍五入到 2 位,纯确定性。
    """
    if direction not in {"long", "short", "flat"}:
        raise ValueError(f"未知方向: {direction!r}")

    entry = round(float(ohlcv["Close"].iloc[-1]), 2)
    if direction == "flat":
        return {"entry": entry, "stop": None, "target": None, "atr": None}

    atr = compute_atr(ohlcv, atr_period)
    if direction == "long":
        stop = entry - k_stop * atr
        target = entry + k_target * atr
    else:  # short
        stop = entry + k_stop * atr
        target = entry - k_target * atr

    return {
        "entry": entry,
        "stop": round(stop, 2),
        "target": round(target, 2),
        "atr": round(atr, 2),
    }
