"""纯规则市场环境识别器(BTC agent v2 ST3)。

铁律延伸:环境识别全程零 LLM、零网络——只消费 ``EvidenceSnapshot`` 里已经装配
好的 OHLCV,不重新触发任何 vendor 调用。

五分类(``detect_regime`` 唯一入口):

- ``insufficient_data``:OHLCV 缺失、``health["ohlcv"]`` 非 ``"ok"``、或 K 线数
  不足 ``REGIME_PARAMS["min_bars"]`` → 白卷。
- ``chaos``:近端波动率(ATR/Close)处于近端历史高百分位 → 白卷。
- ``trend_up`` / ``trend_down``:收盘价相对 SMA 的位置与 SMA 斜率方向一致。
- ``range``:以上皆非(震荡)。

``blank_sheet`` 只在 ``chaos``/``insufficient_data`` 为真——这是下游(决策卡/
候选生成)判断"是否可以继续机械+LLM 裁决流程"的唯一开关。

``REGIME_PARAMS`` 是策略版本 hash(设计门 G5)的输入之一:任何参数改动都等价于
产生一版新策略,因此必须集中在这一处、可 ``json.dumps`` 序列化,不许散落在
函数体内的字面量里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# 集中式规则参数——策略版本 hash 输入之一(设计门 G5)。改动即视为新策略版本。
REGIME_PARAMS: dict[str, Any] = {
    "min_bars": 30,  # 判定所需的最少已完成 K 线数,不足则白卷(insufficient_data)
    "sma_period": 20,  # 趋势基准均线窗口
    "slope_lookback": 5,  # 均线斜率回看天数(sma[-1] - sma[-1-lookback])
    "atr_period": 14,  # ATR(True Range 简单均值)窗口
    "atr_lookback": 60,  # 波动率(ATR/Close)历史百分位计算的回看窗口
    "chaos_percentile": 0.90,  # 当前波动率 >= 该历史分位数 → 判为 chaos
}


@dataclass
class RegimeResult:
    """一次环境识别的结果。"""

    regime: str
    blank_sheet: bool
    observations: dict[str, Any] = field(default_factory=dict)
    params_used: dict[str, Any] = field(default_factory=dict)


def _true_range(ohlcv: pd.DataFrame) -> pd.Series:
    """Wilder True Range(逐日),与 ``trade_levels.compute_atr`` 同口径。"""
    high = ohlcv["High"].astype(float)
    low = ohlcv["Low"].astype(float)
    close = ohlcv["Close"].astype(float)
    prev_close = close.shift(1)
    return pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def detect_regime(snapshot: Any, params: dict[str, Any] | None = None) -> RegimeResult:
    """从 ``EvidenceSnapshot`` 机械识别市场环境。

    ``params`` 默认取 ``REGIME_PARAMS``;显式传参仅供单测/未来版本管理使用,
    生产路径应始终使用模块级默认值,使 ``params_used`` 与 ``REGIME_PARAMS`` 一致。
    """
    p = dict(params) if params is not None else dict(REGIME_PARAMS)

    health = getattr(snapshot, "health", None) or {}
    ohlcv = getattr(snapshot, "ohlcv", None)
    ohlcv_health = health.get("ohlcv")

    if ohlcv is None or ohlcv_health != "ok" or len(ohlcv) < p["min_bars"]:
        return RegimeResult(
            regime="insufficient_data",
            blank_sheet=True,
            observations={
                "bars_available": 0 if ohlcv is None else len(ohlcv),
                "ohlcv_health": ohlcv_health,
                "min_bars_required": p["min_bars"],
            },
            params_used=p,
        )

    close = ohlcv["Close"].astype(float)
    sma = close.rolling(p["sma_period"]).mean()
    last_close = float(close.iloc[-1])
    last_sma = float(sma.iloc[-1])
    prev_sma = float(sma.iloc[-1 - p["slope_lookback"]])
    slope = last_sma - prev_sma

    tr = _true_range(ohlcv)
    atr_series = tr.rolling(p["atr_period"]).mean()
    vol_ratio = (atr_series / close).dropna()
    lookback = vol_ratio.tail(p["atr_lookback"])
    current_vol_ratio = float(lookback.iloc[-1])
    chaos_threshold = float(lookback.quantile(p["chaos_percentile"]))

    observations: dict[str, Any] = {
        "last_close": last_close,
        "sma": last_sma,
        "sma_prev": prev_sma,
        "sma_slope": slope,
        "atr_over_close": current_vol_ratio,
        "atr_over_close_chaos_threshold": chaos_threshold,
        "bars_available": len(ohlcv),
    }

    if current_vol_ratio >= chaos_threshold:
        return RegimeResult(
            regime="chaos", blank_sheet=True, observations=observations, params_used=p
        )

    if last_close > last_sma and slope > 0:
        return RegimeResult(
            regime="trend_up", blank_sheet=False, observations=observations, params_used=p
        )
    if last_close < last_sma and slope < 0:
        return RegimeResult(
            regime="trend_down", blank_sheet=False, observations=observations, params_used=p
        )

    return RegimeResult(
        regime="range", blank_sheet=False, observations=observations, params_used=p
    )
