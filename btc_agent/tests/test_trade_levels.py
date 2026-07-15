"""ST4: 机械交易价位规则单测。核心断言:价位纯确定性、与 LLM 文本无关。"""

import pandas as pd
import pytest

from btc_agent.trade_levels import (
    compute_atr,
    compute_trade_levels,
    rating_to_direction,
)


def _ohlcv(closes, spread=100.0):
    return pd.DataFrame(
        {
            "High": [c + spread for c in closes],
            "Low": [c - spread for c in closes],
            "Close": closes,
        }
    )


def test_rating_to_direction():
    assert rating_to_direction("Buy") == "long"
    assert rating_to_direction("overweight") == "long"
    assert rating_to_direction("Sell") == "short"
    assert rating_to_direction("Underweight") == "short"
    assert rating_to_direction("Hold") == "flat"
    assert rating_to_direction("garbage") == "flat"


def test_compute_atr_positive():
    df = _ohlcv([100, 110, 105, 120, 115])
    atr = compute_atr(df, period=14)
    assert atr > 0


def test_long_levels_bracket_entry():
    df = _ohlcv([100, 110, 105, 120, 130])
    lv = compute_trade_levels(df, "long")
    assert lv["entry"] == 130.0
    assert lv["stop"] < lv["entry"] < lv["target"]  # 多头:止损<入场<目标


def test_short_levels_mirror():
    df = _ohlcv([130, 120, 125, 110, 100])
    lv = compute_trade_levels(df, "short")
    assert lv["entry"] == 100.0
    assert lv["target"] < lv["entry"] < lv["stop"]  # 空头:目标<入场<止损


def test_flat_has_no_directional_levels():
    df = _ohlcv([100, 110, 105])
    lv = compute_trade_levels(df, "flat")
    assert lv["entry"] == 105.0
    assert lv["stop"] is None and lv["target"] is None


def test_levels_are_deterministic():
    df = _ohlcv([100, 110, 105, 120, 130])
    assert compute_trade_levels(df, "long") == compute_trade_levels(df, "long")


def test_invalid_direction_raises():
    with pytest.raises(ValueError):
        compute_trade_levels(_ohlcv([100, 110]), "sideways")
