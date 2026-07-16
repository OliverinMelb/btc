"""decision-card 子任务: daily 编排离线单测(fake graph + fake snapshot,零网络零 LLM)。

覆盖:白卷路径不调图(fake graph 零调用断言);非白卷路径 graph.propagate 恰调用
一次;全程 vendor 零调用(monkeypatch build_evidence_snapshot 计数);推送失败/
部分送达 → 非零退出码,全部送达 → 0;daily.py 源码含 compute_trade_levels 调用
与白卷语义关键字;fake graph 文本里的价格数字不泄漏进价位字段。
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from btc_agent import daily as daily_mod
from btc_agent.evidence import EvidenceSnapshot
from btc_agent.intel.push import Sink


class _FakeGraph:
    """假图: propagate 返回固定 final_state,记调用次数,不跑真图/不调 LLM。"""

    def __init__(self, decision_text: str):
        self._decision = decision_text
        self.calls = 0

    def propagate(self, asset, trade_date, asset_type="crypto"):
        assert asset_type == "crypto"
        self.calls += 1
        return {"final_trade_decision": self._decision}, self._decision


class _RejectingGraph:
    """白卷路径断言零调用: propagate 被调用即失败测试。"""

    def propagate(self, *a, **k):  # pragma: no cover - 不应被调用
        raise AssertionError("blank_sheet 路径不应构造/调用研判图")


class _FakeSink(Sink):
    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail
        self.sent: list[str] = []

    def send(self, message: str) -> None:
        if self.should_fail:
            raise RuntimeError(f"{self.name} sink 故意失败(测试)")
        self.sent.append(message)


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


def _snapshot(ohlcv=None, health=None) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        asset="BTC",
        curr_date="2026-07-16",
        ohlcv=ohlcv if ohlcv is not None else _make_ohlcv(),
        news=None,
        fear_greed=None,
        derivatives=None,
        health=health or {"ohlcv": "ok"},
        snapshot_id="BTC-2026-07-16-deadbeef",
        frozen_at_utc="2026-07-16T00:00:00Z",
    )


@pytest.fixture(autouse=True)
def _no_vendor_calls(monkeypatch):
    """全程 vendor 零调用: build_evidence_snapshot 若被调用即失败测试。

    每个测试都显式注入 snapshot,所以这条路径本不该被触发;monkeypatch 成
    "调用即报错" 而不是简单计数,能立刻在断言失败处定位问题。
    """

    def _boom(*a, **k):
        raise AssertionError("daily 不应在已注入 snapshot 时触发 vendor 取数")

    monkeypatch.setattr(daily_mod, "build_evidence_snapshot", _boom)


def test_blank_sheet_path_skips_graph(monkeypatch):
    """insufficient_data 环境 → 不构造/不调用研判图,卡片明示白卷。"""
    snapshot = _snapshot(ohlcv=None, health={"ohlcv": "error:timeout"})
    monkeypatch.setattr(daily_mod, "build_sinks_from_config", lambda cfg: [_FakeSink("stdout")])

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout"]},
        graph=_RejectingGraph(),
        snapshot=snapshot,
    )

    assert result["regime_result"].blank_sheet is True
    assert result["rating"] is None
    assert "白卷" in result["card"]
    assert result["delivery_complete"] is True


def test_non_blank_path_calls_graph_exactly_once():
    """趋势环境 → 恰调用一次 graph.propagate,产出机械价位。"""
    ohlcv = _make_ohlcv()
    # 构造递增收盘价使其判为 trend_up(与 test_regime.py 同构造手法)。
    snapshot = _snapshot(ohlcv=ohlcv, health={"ohlcv": "ok"})
    fake_graph = _FakeGraph("**Rating**: Buy\n\nBreakout confirmed, momentum strong.")

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout"]},
        graph=fake_graph,
        snapshot=snapshot,
    )

    assert fake_graph.calls == 1
    assert result["regime_result"].blank_sheet is False
    assert result["rating"] == "Buy"
    assert result["levels"] is not None
    assert result["levels"]["entry"] is not None


def test_fake_graph_price_number_does_not_leak_into_levels_field():
    """铁律断言: fake graph 返回文本里埋的价格数字绝不出现在关注位/价位字段。"""
    leaked_price = "424242.99"
    ohlcv = _make_ohlcv()
    snapshot = _snapshot(ohlcv=ohlcv, health={"ohlcv": "ok"})
    fake_graph = _FakeGraph(
        f"**Rating**: Buy\n\nLLM 幻觉价位: entry {leaked_price}, ignore mechanical levels."
    )

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout"]},
        graph=fake_graph,
        snapshot=snapshot,
    )

    # 机械价位字段本身不含该数字。
    assert leaked_price not in str(result["levels"])
    # 卡片的关注位 section 也不含该数字(理由段可以含,那不是价位字段)。
    levels_section = result["card"].split("关注位:")[-1]
    assert leaked_price not in levels_section


def test_delivery_failure_triggers_nonzero_exit(monkeypatch):
    snapshot = _snapshot(ohlcv=None, health={"ohlcv": "error:timeout"})
    monkeypatch.setattr(
        daily_mod, "build_sinks_from_config", lambda cfg: [_FakeSink("stdout", should_fail=True)]
    )

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout"]},
        graph=_RejectingGraph(),
        snapshot=snapshot,
    )

    assert result["delivered"] == 0
    assert result["delivery_complete"] is False


def test_all_sinks_delivered_yields_success(monkeypatch):
    snapshot = _snapshot(ohlcv=None, health={"ohlcv": "error:timeout"})
    monkeypatch.setattr(
        daily_mod, "build_sinks_from_config", lambda cfg: [_FakeSink("stdout"), _FakeSink("email")]
    )

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout", "email"]},
        graph=_RejectingGraph(),
        snapshot=snapshot,
    )

    assert result["delivered"] == 2
    assert result["delivery_complete"] is True


def test_cli_exit_code_nonzero_when_delivery_incomplete(monkeypatch):
    monkeypatch.setattr(
        daily_mod,
        "run_daily",
        lambda **kwargs: {
            "card": "BTC 每日决策卡",
            "requested_sinks": ["stdout", "email"],
            "active_sinks": ["stdout"],
            "delivery_complete": False,
        },
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-cli-gate-only")
    assert daily_mod.main(["--asset", "BTC", "--date", "2026-07-16"]) == 1


def test_cli_exit_code_zero_when_delivery_complete(monkeypatch):
    monkeypatch.setattr(
        daily_mod,
        "run_daily",
        lambda **kwargs: {
            "card": "BTC 每日决策卡",
            "requested_sinks": ["stdout"],
            "active_sinks": ["stdout"],
            "delivery_complete": True,
        },
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-cli-gate-only")
    assert daily_mod.main(["--asset", "BTC", "--date", "2026-07-16"]) == 0


def test_cli_exits_nonzero_without_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        daily_mod.main([])
    assert exc_info.value.code == 2


class _FakeVerdictLLM:
    """swing-candidate 子任务: fake llm, 供 daily 全流程注入式测试用(零网络)。"""

    def __init__(self, content: str):
        self._content = content
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        return type("_R", (), {"content": self._content})()


def _touching_range_ohlcv(n: int = 40) -> pd.DataFrame:
    import math

    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    rows = []
    for i in range(n):
        close = 92.0 if i == n - 1 else 100 + 2 * math.sin(2 * math.pi * i / 10)
        rows.append(
            {
                "Date": dates[i],
                "Open": close,
                "High": close + 0.5,
                "Low": close - 0.5,
                "Close": close,
                "Volume": 10.0,
            }
        )
    return pd.DataFrame(rows)


def test_range_environment_produces_candidate_card(monkeypatch):
    """swing-candidate 子任务: range 环境 → 默认 candidate_provider 出候选卡(fake llm,零网络)。"""
    from btc_agent.candidates import default_candidate_provider
    from functools import partial

    ohlcv = _touching_range_ohlcv()
    snapshot = _snapshot(ohlcv=ohlcv, health={"ohlcv": "ok"})
    monkeypatch.setattr(daily_mod, "detect_regime", lambda snap: _RangeRegime())
    monkeypatch.setattr(daily_mod, "build_sinks_from_config", lambda cfg: [_FakeSink("stdout")])
    fake_llm = _FakeVerdictLLM("Verdict: accept\nReason: mechanical evidence lines up.")
    fake_graph = _FakeGraph("**Rating**: Hold\n\nRange-bound, mixed signals.")

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout"]},
        graph=fake_graph,
        snapshot=snapshot,
        candidate_provider=partial(default_candidate_provider, llm=fake_llm),
    )

    assert result["candidates"] is not None
    assert result["candidates"]["verdict"] == "accept"
    assert "本次操作候选:" in result["card"]
    assert "候选类型: range_lower_long" in result["card"]
    assert fake_llm.calls == 1


def test_blank_sheet_path_never_produces_candidates(monkeypatch):
    """swing-candidate 子任务: 白卷路径 candidate_provider 恒不产候选(regime != range)。"""
    snapshot = _snapshot(ohlcv=None, health={"ohlcv": "error:timeout"})
    monkeypatch.setattr(daily_mod, "build_sinks_from_config", lambda cfg: [_FakeSink("stdout")])

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout"]},
        graph=_RejectingGraph(),
        snapshot=snapshot,
    )

    assert result["candidates"] is None
    assert "本次操作候选: 无" in result["card"]


class _RangeRegime:
    regime = "range"
    blank_sheet = False
    observations = {"last_close": 92.0, "sma": 100.0, "sma_slope": 0.0}
    params_used = {}


def test_explicit_candidate_provider_none_skips_even_in_range_environment(monkeypatch):
    """ST5 reviewer 备注 A: 显式传 candidate_provider=None 时,即便环境允许(range)
    也恒跳过候选——不构造候选、不调用 default_candidate_provider。"""
    from btc_agent import candidates as candidates_mod

    def _boom(*a, **k):  # pragma: no cover - 不应被调用
        raise AssertionError("candidate_provider=None 时不应调用默认候选引擎")

    monkeypatch.setattr(candidates_mod, "default_candidate_provider", _boom)
    monkeypatch.setattr(daily_mod, "detect_regime", lambda snap: _RangeRegime())
    monkeypatch.setattr(daily_mod, "build_sinks_from_config", lambda cfg: [_FakeSink("stdout")])

    ohlcv = _touching_range_ohlcv()
    snapshot = _snapshot(ohlcv=ohlcv, health={"ohlcv": "ok"})
    fake_graph = _FakeGraph("**Rating**: Hold\n\nRange-bound, mixed signals.")

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout"]},
        graph=fake_graph,
        snapshot=snapshot,
        candidate_provider=None,
    )

    assert result["candidates"] is None
    assert "本次操作候选: 无" in result["card"]


def test_ledger_recorder_full_pipeline_records_all_tables(tmp_path, monkeypatch):
    """sqlite-ledger 子任务: daily 全流程(fake 一切)落库——
    snapshots/candidates/verdicts/trade_levels 各有行,离线零网络。"""
    from functools import partial

    from btc_agent import ledger as ledger_mod
    from btc_agent.candidates import default_candidate_provider

    conn = ledger_mod.connect(str(tmp_path / "ledger.sqlite3"))

    def fake_ledger_recorder(snapshot, regime_result, rating, reasoning, levels, candidates):
        ledger_mod.record_daily(conn, snapshot, regime_result, rating, reasoning, levels, candidates)

    ohlcv = _touching_range_ohlcv()
    snapshot = _snapshot(ohlcv=ohlcv, health={"ohlcv": "ok"})
    monkeypatch.setattr(daily_mod, "detect_regime", lambda snap: _RangeRegime())
    monkeypatch.setattr(daily_mod, "build_sinks_from_config", lambda cfg: [_FakeSink("stdout")])
    fake_llm = _FakeVerdictLLM("Verdict: accept\nReason: mechanical evidence lines up.")
    fake_graph = _FakeGraph("**Rating**: Hold\n\nRange-bound, mixed signals.")

    result = daily_mod.run_daily(
        asset="BTC",
        trade_date="2026-07-16",
        config={"intel_push_sinks": ["stdout"]},
        graph=fake_graph,
        snapshot=snapshot,
        candidate_provider=partial(default_candidate_provider, llm=fake_llm),
        ledger_recorder=fake_ledger_recorder,
    )

    assert result["candidates"] is not None
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM trade_levels").fetchone()[0] == 1


def test_daily_module_source_contains_mechanical_levels_and_blank_sheet_keywords():
    """契约延伸(ST7 会指到这里): daily.py 源码须含 compute_trade_levels 调用与白卷语义关键字。"""
    src = inspect.getsource(daily_mod)
    assert "compute_trade_levels" in src
    assert "blank_sheet" in src


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
