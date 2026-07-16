"""decision-card 子任务:决策卡渲染纯函数单测(零网络零 LLM)。

覆盖:五种环境各渲染一张卡字段齐全;白卷卡明示原因;超长截断 <=4096 且首行仍是
主题短句;卡片数字只来自机械计算(reasoning 里埋的价格数字不泄漏进关注位字段)。
"""

from __future__ import annotations

import pandas as pd
import pytest

from btc_agent.decision_card import MAX_MESSAGE_LENGTH, render_decision_card
from btc_agent.evidence import EvidenceSnapshot
from btc_agent.regime import RegimeResult


def _make_ohlcv(n: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    rows = []
    for i in range(n):
        close = 100 + i
        rows.append(
            {
                "Date": dates[i],
                "Open": close,
                "High": close + 2,
                "Low": close - 2,
                "Close": close,
                "Volume": 10.0,
            }
        )
    return pd.DataFrame(rows)


def _snapshot(**overrides) -> EvidenceSnapshot:
    base = dict(
        asset="BTC",
        curr_date="2026-07-16",
        ohlcv=_make_ohlcv(),
        news="some news",
        fear_greed={"value": 42, "classification": "Fear"},
        derivatives={"funding_rate": 0.0005, "open_interest": 1e9},
        health={"ohlcv": "ok", "news": "ok", "fear_greed": "ok", "derivatives": "ok"},
        snapshot_id="BTC-2026-07-16-deadbeef",
        frozen_at_utc="2026-07-16T00:00:00Z",
    )
    base.update(overrides)
    return EvidenceSnapshot(**base)


def _regime(regime: str, blank_sheet: bool, **obs_overrides) -> RegimeResult:
    observations = {
        "last_close": 139.0,
        "sma": 120.0,
        "sma_slope": 1.0,
        "atr_over_close": 0.02,
        "atr_over_close_chaos_threshold": 0.05,
        "bars_available": 40,
    }
    observations.update(obs_overrides)
    return RegimeResult(
        regime=regime,
        blank_sheet=blank_sheet,
        observations=observations,
        params_used={},
    )


_LEVELS = {"entry": 139.0, "stop": 130.0, "target": 160.0, "atr": 6.0}


@pytest.mark.parametrize(
    "regime,blank_sheet",
    [
        ("trend_up", False),
        ("trend_down", False),
        ("range", False),
        ("chaos", True),
        ("insufficient_data", True),
    ],
)
def test_all_five_regimes_render_full_fields(regime, blank_sheet):
    snapshot = _snapshot()
    regime_result = _regime(regime, blank_sheet)
    levels = None if blank_sheet else _LEVELS
    rating = None if blank_sheet else "Buy"
    reasoning = None if blank_sheet else "Momentum confirmed, breakout."

    card = render_decision_card(snapshot, regime_result, rating, reasoning, levels)

    assert "BTC市场环境" in card
    assert "证据完整度" in card
    assert "机械观察" in card
    assert "本次操作候选: 无" in card
    assert "空仓建议" in card and "持仓建议" in card
    assert "关注位" in card
    if blank_sheet:
        assert "白卷" in card
    else:
        assert "TradingAgents评级" in card
        assert "Buy" in card


def test_blank_sheet_card_states_reason_and_no_levels():
    snapshot = _snapshot(health={"ohlcv": "error:timeout"}, ohlcv=None)
    regime_result = _regime("insufficient_data", True)
    card = render_decision_card(snapshot, regime_result, None, None, None)
    assert "白卷" in card
    assert "数据不足" in card or "insufficient_data" not in card
    assert "TradingAgents评级: 白卷" in card


def test_evidence_completeness_reports_missing_sources():
    snapshot = _snapshot(health={"ohlcv": "ok", "news": "error:boom", "fear_greed": "ok", "derivatives": "ok"})
    regime_result = _regime("range", False)
    card = render_decision_card(snapshot, regime_result, "Hold", "flat regime", None)
    assert "数据不完整" in card
    assert "news" in card


def test_reasoning_price_number_does_not_leak_into_levels_section():
    """铁律断言: reasoning 里的价格数字绝不出现在关注位段(关注位只信 levels 参数)。"""
    leaked_price = "987654.32"
    snapshot = _snapshot()
    regime_result = _regime("trend_up", False)
    reasoning = f"LLM 幻觉价位提示: entry should be {leaked_price} according to some prose."
    levels = {"entry": 139.0, "stop": 130.0, "target": 160.0, "atr": 6.0}

    card = render_decision_card(snapshot, regime_result, "Buy", reasoning, levels)

    # 理由段允许包含该数字(纯文本展示),但关注位段绝不能包含它。
    levels_section = card.split("关注位:")[-1]
    assert leaked_price not in levels_section
    assert str(levels["entry"]) in levels_section


def test_subject_line_is_first_line_and_short():
    snapshot = _snapshot()
    regime_result = _regime("range", False)
    card = render_decision_card(snapshot, regime_result, "Hold", "flat", None)
    first_line = card.splitlines()[0]
    assert "BTC" in first_line
    assert len(first_line) < 120


def test_long_card_is_truncated_to_telegram_limit_and_keeps_subject():
    snapshot = _snapshot()
    regime_result = _regime("range", False)
    huge_reasoning = "详细理由。" * 3000  # 远超 4096
    card = render_decision_card(snapshot, regime_result, "Hold", huge_reasoning, _LEVELS)

    assert len(card) <= MAX_MESSAGE_LENGTH
    # 首行主题句仍然存在且完整(未被截断逻辑破坏)。
    first_line = card.splitlines()[0]
    assert "BTC" in first_line
    assert "TradingAgents评级" in card or "白卷" in card


def test_short_card_is_not_truncated():
    snapshot = _snapshot()
    regime_result = _regime("range", False)
    card = render_decision_card(snapshot, regime_result, "Hold", "short reason", _LEVELS)
    assert len(card) <= MAX_MESSAGE_LENGTH
    assert "[... 理由/观察段已截断" not in card


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
