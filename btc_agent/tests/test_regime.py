"""regime-detector-subtask: 纯规则市场环境识别单测(零 LLM/零网络/构造 OHLCV)。

覆盖五分支(上升趋势/下降趋势/震荡/高波动/数据不足)、blank_sheet 标志、
REGIME_PARAMS 的 json 可序列化性 + params_used 一致性,以及"不 import
graph/intel/llm"的模块边界断言。
"""

from __future__ import annotations

import inspect
import json
import math

import pandas as pd
import pytest

from btc_agent.regime import REGIME_PARAMS, RegimeResult, detect_regime


class _FakeSnapshot:
    """替身快照:只提供 detect_regime 消费的两个字段(ohlcv/health),
    不依赖 evidence.py 的网络取数路径——保持本模块单测零网络。"""

    def __init__(self, ohlcv, health):
        self.ohlcv = ohlcv
        self.health = health


def _make_ohlcv(n: int, close_fn, width_fn) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    rows = []
    for i in range(n):
        close = close_fn(i)
        width = width_fn(i)
        rows.append(
            {
                "Date": dates[i],
                "Open": close,
                "High": close + width / 2,
                "Low": close - width / 2,
                "Close": close,
                "Volume": 10.0,
            }
        )
    return pd.DataFrame(rows)


# 波动宽度随时间递减,确保上升/下降趋势用例里最新一根 K 线的波动率不会
# 意外撞进 chaos 分位(与趋势方向解耦,只有 chaos 用例专门反向构造尖峰)。
def _shrinking_width(i: int) -> float:
    return max(0.5, 5.0 - i * 0.1)


N_BARS = 40  # > REGIME_PARAMS["min_bars"](30)


def test_trend_up_detected():
    ohlcv = _make_ohlcv(N_BARS, lambda i: 100 + i * 1.0, _shrinking_width)
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "ok"}))
    assert result.regime == "trend_up"
    assert result.blank_sheet is False
    assert result.observations["sma_slope"] > 0
    assert result.observations["last_close"] > result.observations["sma"]


def test_trend_down_detected():
    ohlcv = _make_ohlcv(N_BARS, lambda i: 200 - i * 1.0, _shrinking_width)
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "ok"}))
    assert result.regime == "trend_down"
    assert result.blank_sheet is False
    assert result.observations["sma_slope"] < 0
    assert result.observations["last_close"] < result.observations["sma"]


def test_range_detected():
    ohlcv = _make_ohlcv(
        N_BARS,
        lambda i: 100 + 2 * math.sin(2 * math.pi * i / 10),
        _shrinking_width,
    )
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "ok"}))
    assert result.regime == "range"
    assert result.blank_sheet is False


def test_chaos_detected_on_late_volatility_spike():
    """前面波动平稳,最后一根 K 线突然放量巨幅震荡 → 当前波动率碰到近端历史高分位。"""

    def width(i: int) -> float:
        return 1.0 if i < N_BARS - 1 else 50.0

    ohlcv = _make_ohlcv(N_BARS, lambda i: 100.0, width)
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "ok"}))
    assert result.regime == "chaos"
    assert result.blank_sheet is True
    assert (
        result.observations["atr_over_close"]
        >= result.observations["atr_over_close_chaos_threshold"]
    )


def test_insufficient_data_when_ohlcv_missing():
    result = detect_regime(_FakeSnapshot(None, {"ohlcv": "error:exchange down"}))
    assert result.regime == "insufficient_data"
    assert result.blank_sheet is True


def test_insufficient_data_when_too_few_bars():
    ohlcv = _make_ohlcv(10, lambda i: 100 + i, lambda i: 1.0)
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "ok"}))
    assert result.regime == "insufficient_data"
    assert result.blank_sheet is True
    assert result.observations["bars_available"] == 10


def test_insufficient_data_when_health_not_ok_despite_data_present():
    """OHLCV 对象存在但 health 标记非 ok(比如上游降级)也要白卷,不能只看 df 非空。"""
    ohlcv = _make_ohlcv(N_BARS, lambda i: 100 + i, _shrinking_width)
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "error:stale"}))
    assert result.regime == "insufficient_data"
    assert result.blank_sheet is True


def test_blank_sheet_flag_only_true_for_chaos_and_insufficient_data():
    trend_up = detect_regime(
        _FakeSnapshot(_make_ohlcv(N_BARS, lambda i: 100 + i, _shrinking_width), {"ohlcv": "ok"})
    )
    trend_down = detect_regime(
        _FakeSnapshot(_make_ohlcv(N_BARS, lambda i: 200 - i, _shrinking_width), {"ohlcv": "ok"})
    )
    range_ = detect_regime(
        _FakeSnapshot(
            _make_ohlcv(N_BARS, lambda i: 100 + 2 * math.sin(2 * math.pi * i / 10), _shrinking_width),
            {"ohlcv": "ok"},
        )
    )
    chaos = detect_regime(
        _FakeSnapshot(
            _make_ohlcv(N_BARS, lambda i: 100.0, lambda i: 1.0 if i < N_BARS - 1 else 50.0),
            {"ohlcv": "ok"},
        )
    )
    insufficient = detect_regime(_FakeSnapshot(None, {"ohlcv": "error:x"}))

    assert trend_up.blank_sheet is False
    assert trend_down.blank_sheet is False
    assert range_.blank_sheet is False
    assert chaos.blank_sheet is True
    assert insufficient.blank_sheet is True


def test_regime_params_json_serializable_and_wired_into_result():
    # 集中式参数字典本身必须能整体 json 序列化(canonical json 的前提)。
    serialized = json.dumps(REGIME_PARAMS, sort_keys=True)
    assert serialized

    ohlcv = _make_ohlcv(N_BARS, lambda i: 100 + i, _shrinking_width)
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "ok"}))
    assert result.params_used == REGIME_PARAMS
    # params_used 也必须独立可序列化(不能悄悄塞进不可 json 化的对象,比如 DataFrame)。
    assert json.dumps(result.params_used, sort_keys=True)


def test_custom_params_override_default_and_are_echoed_back():
    """显式传参(单测/版本管理用途)时,params_used 反映实际使用的参数,而非默认值。"""
    custom = {
        "min_bars": 15,
        "sma_period": 5,
        "slope_lookback": 2,
        "atr_period": 3,
        "atr_lookback": 10,
        "chaos_percentile": 0.90,
    }
    ohlcv = _make_ohlcv(15, lambda i: 100 + i, _shrinking_width)
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "ok"}), params=custom)
    assert result.params_used == custom
    assert result.regime != "insufficient_data"


def test_regime_result_is_dataclass_with_expected_fields():
    ohlcv = _make_ohlcv(N_BARS, lambda i: 100 + i, _shrinking_width)
    result = detect_regime(_FakeSnapshot(ohlcv, {"ohlcv": "ok"}))
    assert isinstance(result, RegimeResult)
    assert set(vars(result)) == {"regime", "blank_sheet", "observations", "params_used"}


def test_regime_module_does_not_import_graph_intel_or_llm():
    """机械环境识别不得依赖研判图/情报层/LLM——纯规则消费快照数据。

    只检查 import 语句(不扫全源码),因为模块文档字符串里出于说明目的会提到
    "LLM"/"graph" 等词,那不构成依赖。
    """
    import btc_agent.regime as regime_mod

    src = inspect.getsource(regime_mod)
    import_lines = [
        line.strip()
        for line in src.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    assert import_lines  # 确保确实扫到了 import 语句,不是空跑
    for line in import_lines:
        assert "graph" not in line
        assert "intel" not in line
        assert "llm" not in line.lower()


def test_detect_regime_accepts_evidence_snapshot_instance():
    """确保真实 EvidenceSnapshot(而不只是替身)也能被消费——字段名对齐。"""
    from btc_agent.evidence import EvidenceSnapshot

    ohlcv = _make_ohlcv(N_BARS, lambda i: 100 + i, _shrinking_width)
    snap = EvidenceSnapshot(
        asset="BTC",
        curr_date="2026-07-16",
        ohlcv=ohlcv,
        news=None,
        fear_greed=None,
        derivatives=None,
        health={"ohlcv": "ok"},
        snapshot_id="BTC-2026-07-16-deadbeef",
        frozen_at_utc="2026-07-16T00:00:00Z",
    )
    result = detect_regime(snap)
    assert result.regime == "trend_up"
    assert result.blank_sheet is False


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
