"""spot-settlement-subtask: 现货结算数学的纯函数单测(不触网/不调 LLM/不 import graph)。"""

import pytest

from btc_agent.settlement_math import spot_settle


def test_spot_settle_long_tracks_market_return():
    result = spot_settle("long", market_return=0.05, bench_return=0.02)
    assert result["strategy_return"] == pytest.approx(0.05)
    assert result["alpha"] == pytest.approx(0.03)
    assert result["direction_hit"] is True
    assert result["settlement_basis"] == "spot"


def test_spot_settle_long_market_down_is_a_miss():
    result = spot_settle("long", market_return=-0.05, bench_return=0.0)
    assert result["direction_hit"] is False


def test_spot_settle_short_never_earns_a_return():
    """现货空仓:Sell 不能靠做空获利,strategy_return 恒为 0,alpha=-bench_return。"""
    result = spot_settle("short", market_return=-0.08, bench_return=-0.08)
    assert result["strategy_return"] == 0.0
    assert result["alpha"] == pytest.approx(0.08)
    assert result["settlement_basis"] == "spot"


def test_spot_settle_short_direction_hit_independent_of_return():
    """方向命中与收益分离:Sell 且市场下跌 → hit=True,return 仍为 0。"""
    result = spot_settle("short", market_return=-0.03, bench_return=0.0)
    assert result["direction_hit"] is True
    assert result["strategy_return"] == 0.0
    assert result["alpha"] == 0.0


def test_spot_settle_short_market_up_is_a_miss():
    result = spot_settle("short", market_return=0.03, bench_return=0.0)
    assert result["direction_hit"] is False
    assert result["strategy_return"] == 0.0


def test_spot_settle_market_return_zero_is_never_a_hit():
    long_result = spot_settle("long", market_return=0.0, bench_return=0.0)
    short_result = spot_settle("short", market_return=0.0, bench_return=0.0)
    assert long_result["direction_hit"] is False
    assert short_result["direction_hit"] is False


def test_spot_settle_flat_has_no_direction_hit():
    result = spot_settle("flat", market_return=0.04, bench_return=0.01)
    assert result["strategy_return"] == 0.0
    assert result["alpha"] == pytest.approx(-0.01)
    assert result["direction_hit"] is None


def test_spot_settle_unknown_direction_treated_as_flat():
    result = spot_settle("bogus", market_return=0.04, bench_return=0.01)
    assert result["strategy_return"] == 0.0
    assert result["direction_hit"] is None
    assert result["settlement_basis"] == "spot"
