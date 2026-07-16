"""swing-candidate 子任务:波段候选引擎 + LLM 裁决单测(零网络零 LLM,fake llm)。

覆盖:regime=range 且触及下沿带 → 产出机械候选;非 range(四分支)/数据缺失 → None;
CANDIDATE_PARAMS json 可序列化且与 params_used 一致;CandidateVerdict schema
无数值字段且三个既有 schema 类不动;裁决解析(accept/observe/veto/歧义→observe,
LLM 调用异常→observe);default_candidate_provider 组装。
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from btc_agent.agents.schemas import (
    CandidateVerdict,
    PortfolioDecision,
    ResearchPlan,
    TraderProposal,
)
from btc_agent.candidates import (
    CANDIDATE_PARAMS,
    Candidate,
    default_candidate_provider,
    find_swing_candidate,
    judge_candidate,
)


class _FakeRegime:
    def __init__(self, regime: str, blank_sheet: bool):
        self.regime = regime
        self.blank_sheet = blank_sheet


class _FakeSnapshot:
    def __init__(self, ohlcv, curr_date="2026-07-16", frozen_at_utc="2026-07-16T00:00:00Z"):
        self.ohlcv = ohlcv
        self.curr_date = curr_date
        self.frozen_at_utc = frozen_at_utc
        self.asset = "BTC"
        self.fear_greed = {"value": 40, "classification": "Fear"}
        self.derivatives = {"funding_rate": 0.0001, "open_interest": 1e9}


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


def _touching_range_ohlcv(n: int = 40) -> pd.DataFrame:
    """构造一份区间震荡的 OHLCV,最后一根 K 线的 Low 是全窗口新低(必然触及下沿带)。"""
    import math

    def close_fn(i: int) -> float:
        if i == n - 1:
            return 92.0  # 最后一根明显下探
        return 100 + 2 * math.sin(2 * math.pi * i / 10)

    def width_fn(i: int) -> float:
        return 1.0

    return _make_ohlcv(n, close_fn, width_fn)


# ---------------------------------------------------------------------------
# find_swing_candidate
# ---------------------------------------------------------------------------


def test_range_and_touch_produces_candidate_with_mechanical_fields():
    ohlcv = _touching_range_ohlcv()
    snapshot = _FakeSnapshot(ohlcv)
    regime_result = _FakeRegime("range", False)

    candidate = find_swing_candidate(snapshot, regime_result)

    assert isinstance(candidate, Candidate)
    assert candidate.candidate_type == "range_lower_long"
    assert isinstance(candidate.entry_ref, float)
    assert isinstance(candidate.invalidation, float)
    assert candidate.invalidation < candidate.entry_ref
    assert isinstance(candidate.target_zone, tuple)
    assert len(candidate.target_zone) == 2
    assert candidate.target_zone[0] < candidate.target_zone[1]
    assert candidate.expires_utc.endswith("Z")
    assert candidate.params_used == CANDIDATE_PARAMS


@pytest.mark.parametrize("regime", ["trend_up", "trend_down", "chaos", "insufficient_data"])
def test_non_range_regime_never_produces_candidate(regime):
    ohlcv = _touching_range_ohlcv()
    snapshot = _FakeSnapshot(ohlcv)
    blank_sheet = regime in ("chaos", "insufficient_data")
    regime_result = _FakeRegime(regime, blank_sheet)

    assert find_swing_candidate(snapshot, regime_result) is None


def test_missing_ohlcv_produces_no_candidate():
    snapshot = _FakeSnapshot(None)
    regime_result = _FakeRegime("range", False)
    assert find_swing_candidate(snapshot, regime_result) is None


def test_insufficient_bars_produces_no_candidate():
    ohlcv = _make_ohlcv(5, lambda i: 100 + i, lambda i: 1.0)
    snapshot = _FakeSnapshot(ohlcv)
    regime_result = _FakeRegime("range", False)
    assert find_swing_candidate(snapshot, regime_result) is None


def test_range_but_not_touching_lower_band_produces_no_candidate():
    """区间下沿只出现在回看窗口早段,最后一根远离下沿带 → 白卷,不硬凑。"""

    def close_fn(i: int) -> float:
        # 窗口(最后 20 根,即 i=20..39)前半段(20..29)探到低点 200,
        # 后半段(30..39)一路拉升到 260,最后一根远离区间下沿。
        if i < 20:
            return 260.0
        if i < 30:
            return 260.0 - (i - 20) * 6.0  # 260 -> 206
        return 206.0 + (i - 29) * 6.0  # 206 -> 260

    ohlcv = _make_ohlcv(40, close_fn, lambda i: 1.0)
    snapshot = _FakeSnapshot(ohlcv)
    regime_result = _FakeRegime("range", False)
    assert find_swing_candidate(snapshot, regime_result) is None


def test_candidate_params_json_serializable_and_consistent_with_params_used():
    serialized = json.dumps(CANDIDATE_PARAMS, sort_keys=True)
    assert serialized

    ohlcv = _touching_range_ohlcv()
    snapshot = _FakeSnapshot(ohlcv)
    candidate = find_swing_candidate(snapshot, _FakeRegime("range", False))
    assert candidate.params_used == CANDIDATE_PARAMS
    assert json.dumps(candidate.params_used, sort_keys=True)


# ---------------------------------------------------------------------------
# CandidateVerdict schema contract
# ---------------------------------------------------------------------------


def test_candidate_verdict_has_no_numeric_fields():
    field_types = set()
    for f in CandidateVerdict.model_fields.values():
        field_types.add(f.annotation)
    for t in field_types:
        assert t not in (int, float)
    # explicit field-name contract too
    assert set(CandidateVerdict.model_fields) == {"verdict", "reason"}


def test_candidate_verdict_accepts_only_three_labels():
    v = CandidateVerdict(verdict="accept", reason="evidence supports it")
    assert v.verdict == "accept"
    with pytest.raises(Exception):
        CandidateVerdict(verdict="strong_buy", reason="x")


def test_existing_three_schemas_untouched():
    """契约不变式: ResearchPlan/TraderProposal/PortfolioDecision 字段集合一字未动。"""
    assert set(ResearchPlan.model_fields) == {"recommendation", "rationale", "strategic_actions"}
    assert set(TraderProposal.model_fields) == {"action", "reasoning"}
    assert set(PortfolioDecision.model_fields) == {
        "rating", "executive_summary", "investment_thesis",
    }


# ---------------------------------------------------------------------------
# judge_candidate LLM verdict parsing (fake llm, zero network)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        return _FakeResponse(self._content)


class _BoomLLM:
    def invoke(self, prompt):
        raise RuntimeError("boom: fake network failure")


def _make_candidate() -> Candidate:
    return Candidate(
        candidate_type="range_lower_long",
        entry_ref=92.0,
        invalidation=85.0,
        target_zone=(98.0, 105.0),
        expires_utc="2026-07-21T00:00:00Z",
        params_used=dict(CANDIDATE_PARAMS),
        observations={"range_low": 90.0, "range_high": 105.0},
    )


@pytest.mark.parametrize(
    "label,text",
    [
        ("accept", "Verdict: accept\nReason: evidence lines up with the mechanical setup."),
        ("observe", "Verdict: observe\nReason: evidence is thin, wait for confirmation."),
        ("veto", "Verdict: veto\nReason: evidence clearly contradicts this candidate."),
    ],
)
def test_judge_candidate_parses_explicit_labels(label, text):
    candidate = _make_candidate()
    snapshot = _FakeSnapshot(_touching_range_ohlcv())
    llm = _FakeLLM(text)

    verdict = judge_candidate(candidate, snapshot, llm=llm)

    assert isinstance(verdict, CandidateVerdict)
    assert verdict.verdict == label
    assert llm.calls == 1


def test_judge_candidate_ambiguous_text_degrades_to_observe():
    candidate = _make_candidate()
    snapshot = _FakeSnapshot(_touching_range_ohlcv())
    llm = _FakeLLM("This looks interesting but I'm not sure, maybe good maybe not.")

    verdict = judge_candidate(candidate, snapshot, llm=llm)

    assert verdict.verdict == "observe"


def test_judge_candidate_llm_failure_degrades_to_observe_not_exception():
    candidate = _make_candidate()
    snapshot = _FakeSnapshot(_touching_range_ohlcv())

    verdict = judge_candidate(candidate, snapshot, llm=_BoomLLM())

    assert verdict.verdict == "observe"


def test_judge_candidate_prompt_forbids_numbers_and_states_blank_sheet_culture():
    """Prompt 文案契约: 明确禁数字 + 写白卷文化关键字(裁决模块自身,不依赖真实网络)。"""
    from btc_agent.candidates import _build_verdict_prompt

    candidate = _make_candidate()
    snapshot = _FakeSnapshot(_touching_range_ohlcv())
    prompt = _build_verdict_prompt(candidate, snapshot)
    assert "白卷" in prompt
    assert "数字" in prompt


# ---------------------------------------------------------------------------
# default_candidate_provider
# ---------------------------------------------------------------------------


def test_default_candidate_provider_returns_none_when_no_mechanical_candidate():
    snapshot = _FakeSnapshot(_touching_range_ohlcv())
    regime_result = _FakeRegime("trend_up", False)
    assert default_candidate_provider(snapshot, regime_result, llm=_FakeLLM("Verdict: accept")) is None


def test_default_candidate_provider_wires_mechanical_and_verdict_together():
    snapshot = _FakeSnapshot(_touching_range_ohlcv())
    regime_result = _FakeRegime("range", False)
    llm = _FakeLLM("Verdict: accept\nReason: setup lines up with mechanical evidence.")

    result = default_candidate_provider(snapshot, regime_result, llm=llm)

    assert result is not None
    assert result["candidate_type"] == "range_lower_long"
    assert result["verdict"] == "accept"
    assert "reason" in result
    assert "entry_ref" in result and "invalidation" in result
    assert "target_zone" in result and "expires_utc" in result
    assert llm.calls == 1


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
