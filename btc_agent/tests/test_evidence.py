"""evidence.py 离线单测:统一证据快照。

不打真实网络:monkeypatch 每个 vendor 的唯一网络出口(与其它 vendor 单测同构)。
覆盖:
- 一次快照,dashboard 路径与 trade_levels 路径消费同一份 OHLCV(vendor 只调用一次);
- 单源失败(F&G)只记 health,其余源正常,dashboard errors 同步呈现,不崩;
- run.py 契约不变式(compute_trade_levels / mechanical 字样 / DEEPSEEK_API_KEY)原样保留。
"""

from __future__ import annotations

import pytest

from btc_agent import run as run_mod
from btc_agent.dataflows import ccxt_vendor, crypto_rss_vendor, derivatives_vendor, feargreed_vendor
from btc_agent.evidence import build_evidence_snapshot
from btc_agent.intel import dashboard as dash_mod
from btc_agent.trade_levels import compute_trade_levels


def _fake_candles(days: int = 30):
    day_ms = 86_400_000
    base = 1_600_000_000_000
    return [
        [base + i * day_ms, 100.0 + i, 105.0 + i, 95.0 + i, 100.0 + i, 10.0]
        for i in range(days)
    ]


@pytest.fixture
def counted_ohlcv(monkeypatch):
    """OHLCV vendor 网络出口打计数,断言同一次运行只被调用一次。"""
    calls = {"n": 0}

    def _fake(*a, **k):
        calls["n"] += 1
        return _fake_candles(30)

    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", _fake)
    return calls


@pytest.fixture
def patched_news(monkeypatch):
    monkeypatch.setattr(crypto_rss_vendor, "_fetch_feed", lambda url: b"<rss><channel></channel></rss>")
    monkeypatch.setattr(crypto_rss_vendor, "DEFAULT_FEEDS", [("TestFeed", "http://x")])


@pytest.fixture
def patched_fear_greed(monkeypatch):
    monkeypatch.setattr(
        feargreed_vendor,
        "_request",
        lambda limit: {"data": [{"value": "42", "value_classification": "Fear", "timestamp": "1600000000"}]},
    )


@pytest.fixture
def patched_derivatives(monkeypatch):
    monkeypatch.setattr(derivatives_vendor, "_fetch_funding_raw", lambda pair: {"fundingRate": 0.0007})
    monkeypatch.setattr(derivatives_vendor, "_fetch_open_interest_raw", lambda pair: {"openInterestValue": 1_000_000.0})


@pytest.fixture
def all_sources_ok(counted_ohlcv, patched_news, patched_fear_greed, patched_derivatives):
    return counted_ohlcv


def test_build_evidence_snapshot_all_ok(all_sources_ok):
    # 衍生品 vendor 拒绝历史快照(拒绝当前数据伪装成历史);用 curr_date=None(当下)
    # 才能让四个源都成功,验证 health 全绿的路径。
    snap = build_evidence_snapshot("BTC", curr_date=None)
    assert snap.health == {"ohlcv": "ok", "news": "ok", "fear_greed": "ok", "derivatives": "ok"}
    assert snap.ohlcv is not None and len(snap.ohlcv) > 0
    assert snap.fear_greed["value"] == 42
    assert snap.derivatives["funding_rate"] == pytest.approx(0.0007)
    assert snap.asset == "BTC"
    assert snap.curr_date is None
    assert snap.snapshot_id.startswith("BTC-")
    assert snap.frozen_at_utc.endswith("Z")


def test_snapshot_shared_between_dashboard_and_trade_levels(all_sources_ok):
    """同一快照对象:dashboard 路径读到的 close 与 trade_levels 消费的 OHLCV 最后收盘价一致,
    且 OHLCV vendor 在整个测试期间只被调用一次(快照装配那一次)。"""
    snap = build_evidence_snapshot("BTC", curr_date=None)
    assert all_sources_ok["n"] == 1

    dashboard = dash_mod.build_dashboard("BTC", None, snapshot=snap)
    levels = compute_trade_levels(snap.ohlcv, "long")

    last_close_from_trade_levels = float(snap.ohlcv["Close"].iloc[-1])
    assert dashboard["close"] == pytest.approx(last_close_from_trade_levels)
    assert levels["entry"] == pytest.approx(last_close_from_trade_levels)
    # 装配 dashboard、算 trade_levels 都没有再次触发 vendor 取数
    assert all_sources_ok["n"] == 1


def test_single_source_failure_recorded_in_health_others_ok(counted_ohlcv, patched_news, patched_derivatives, monkeypatch):
    """F&G 抛异常 → health 记 error,其余源正常,不崩,dashboard errors 同步呈现。"""
    def _boom(limit):
        raise RuntimeError("F&G endpoint down")

    monkeypatch.setattr(feargreed_vendor, "_request", _boom)

    snap = build_evidence_snapshot("BTC", curr_date=None)
    assert snap.health["fear_greed"] == "error:F&G endpoint down"
    assert snap.health["ohlcv"] == "ok"
    assert snap.health["derivatives"] == "ok"
    assert snap.ohlcv is not None
    assert snap.fear_greed is None

    dashboard = dash_mod.build_dashboard("BTC", None, snapshot=snap)
    assert dashboard["errors"]["fear_greed"] == "F&G endpoint down"
    assert dashboard["fear_greed"] is None
    assert "derivatives" not in dashboard["errors"]
    assert dashboard["derivatives"] is not None
    assert dashboard["close"] is not None  # 价格信号不受 F&G 失败影响


def test_ohlcv_failure_recorded_and_dashboard_degrades(patched_news, patched_fear_greed, patched_derivatives, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("exchange unreachable")

    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", _boom)

    snap = build_evidence_snapshot("BTC", curr_date="2020-10-01")
    assert snap.health["ohlcv"].startswith("error:")
    assert snap.ohlcv is None

    dashboard = dash_mod.build_dashboard("BTC", "2020-10-01", snapshot=snap)
    assert "price" in dashboard["errors"]
    assert dashboard["close"] is None
    assert dashboard["fear_greed"] is not None  # 其余源不受影响


def test_run_raises_when_snapshot_has_no_ohlcv(patched_news, patched_fear_greed, patched_derivatives, monkeypatch, tmp_path):
    """机械交易价位离不开真实 OHLCV;快照取数失败时 run() 原样重新抛出,不静默产出坏记录。"""
    def _boom(*a, **k):
        raise RuntimeError("exchange unreachable")

    monkeypatch.setattr(ccxt_vendor, "_fetch_ohlcv_raw", _boom)

    class _FakeGraph:
        def propagate(self, asset, trade_date, asset_type="crypto"):
            return {"final_trade_decision": "**Rating**: Buy"}, "Buy"

    cfg = {"results_dir": str(tmp_path)}
    with pytest.raises(RuntimeError, match="cannot compute trade levels"):
        run_mod.run(asset="BTC", trade_date="2020-10-01", config=cfg, graph=_FakeGraph())


def test_run_contract_invariants_present():
    """契约不变式原样保留:compute_trade_levels、mechanical 字样、DEEPSEEK_API_KEY 校验。"""
    import inspect

    src = inspect.getsource(run_mod)
    assert "compute_trade_levels" in src
    assert "mechanical (ATR-based), not LLM" in src
    assert "DEEPSEEK_API_KEY" in src
