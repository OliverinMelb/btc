"""ST4: run 入口离线单测。注入 mock graph + mock ccxt，不联网不调 LLM。

核心断言:
- run 写出一条结构化记录,字段含 asset/UTC 时点/5 档评级/reasoning/机械价位;
- **价位由机械规则算**:改 mock 的 LLM 决策文本(只要 rating 不变)不改变 entry/stop/target。
"""

import json

import pytest

from btc_agent import run as run_mod
from btc_agent.dataflows import ccxt_vendor


class _FakeGraph:
    """假图:propagate 返回固定 final_state,不跑真图、不调 LLM。"""

    def __init__(self, decision_text):
        self._decision = decision_text

    def propagate(self, asset, trade_date, asset_type="crypto"):
        assert asset_type == "crypto"
        # 真 propagate 返回 (final_state, processed_signal) 元组
        return {"final_trade_decision": self._decision}, self._decision


@pytest.fixture
def patched_ohlcv(monkeypatch):
    day_ms = 86_400_000
    base = 1_600_000_000_000
    candles = [
        [base + i * day_ms, 100.0 + i, 105.0 + i, 95.0 + i, 100.0 + i, 10.0]
        for i in range(30)
    ]
    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", lambda *a, **k: candles)
    return candles


def test_run_writes_structured_record(patched_ohlcv, tmp_path):
    cfg = {"results_dir": str(tmp_path)}
    decision = "**Rating**: Buy\n\nStrong bullish momentum, breakout confirmed."
    rec = run_mod.run(
        asset="BTC", trade_date="2020-10-01", config=cfg,
        graph=_FakeGraph(decision),
    )
    # 记录字段齐全
    assert rec["asset"] == "BTC"
    assert rec["trade_date"] == "2020-10-01"
    assert rec["generated_at_utc"].endswith("Z")
    assert rec["rating"] == "Buy"
    assert rec["direction"] == "long"
    assert "reasoning" in rec
    assert rec["levels"]["entry"] is not None
    assert rec["levels"]["stop"] < rec["levels"]["entry"] < rec["levels"]["target"]
    # 文件已落盘且可解析
    path = json.loads(open(rec["_record_path"], encoding="utf-8").read())
    assert path["asset"] == "BTC"


def test_price_levels_independent_of_llm_wording(patched_ohlcv, tmp_path):
    """同 date + 同 rating、不同 LLM 措辞 → 机械价位完全一致(价位不来自 LLM)。"""
    cfg = {"results_dir": str(tmp_path)}
    rec_a = run_mod.run(
        asset="BTC", trade_date="2020-10-01", config=cfg,
        graph=_FakeGraph("**Rating**: Buy\n\nReason A: whales accumulating."),
    )
    rec_b = run_mod.run(
        asset="BTC", trade_date="2020-10-01", config=cfg,
        graph=_FakeGraph("**Rating**: Buy\n\nCompletely different prose, ETF inflows."),
    )
    assert rec_a["levels"] == rec_b["levels"]


def test_hold_rating_yields_flat_levels(patched_ohlcv, tmp_path):
    """白卷/Hold → flat,无方向性 stop/target。"""
    cfg = {"results_dir": str(tmp_path)}
    rec = run_mod.run(
        asset="BTC", trade_date="2020-10-01", config=cfg,
        graph=_FakeGraph("**Rating**: Hold\n\nRegime unclear, staying flat."),
    )
    assert rec["direction"] == "flat"
    assert rec["levels"]["stop"] is None and rec["levels"]["target"] is None
