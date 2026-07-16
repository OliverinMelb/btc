"""sqlite-ledger 子任务: 事件驱动结算器单测(G6 四口径,零网络: ohlcv_provider 注入)。"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field

import pandas as pd
import pytest

from btc_agent import ledger as ledger_mod
from btc_agent import settlement as settlement_mod


@dataclass
class _FakeSnapshot:
    snapshot_id: str
    asset: str = "BTC"
    curr_date: str = "2026-07-16"
    frozen_at_utc: str = "2026-07-16T00:00:00Z"
    health: dict = field(default_factory=lambda: {"ohlcv": "ok"})


@dataclass
class _FakeRegimeResult:
    regime: str = "range"
    blank_sheet: bool = False
    observations: dict = field(default_factory=dict)


def _db(tmp_path):
    return ledger_mod.connect(str(tmp_path / "ledger.sqlite3"))


def _insert_candidate(
    conn,
    snapshot_id: str,
    verdict: str = "accept",
    entry_ref: float = 100.0,
    invalidation: float = 90.0,
    target_zone: tuple[float, float] = (105.0, 110.0),
    expires_utc: str = "2026-07-21T00:00:00Z",
    creation_date: str = "2026-07-16",
) -> None:
    snapshot = _FakeSnapshot(snapshot_id=snapshot_id, curr_date=creation_date)
    regime_result = _FakeRegimeResult()
    candidates = {
        "candidate_type": "range_lower_long",
        "verdict": verdict,
        "reason": "test",
        "entry_ref": entry_ref,
        "invalidation": invalidation,
        "target_zone": target_zone,
        "expires_utc": expires_utc,
    }
    ledger_mod.record_daily(conn, snapshot, regime_result, None, None, None, candidates)


def _provider_from(rows: dict[str, tuple[float, float, float]]):
    """``rows``: date -> (Low, High, Close)。返回一个注入用 ohlcv_provider。"""

    def provider(asset: str, start_date: str, end_date: str) -> pd.DataFrame:
        data = []
        for date_str, (low, high, close) in sorted(rows.items()):
            if start_date <= date_str <= end_date:
                data.append(
                    {
                        "Date": pd.Timestamp(date_str),
                        "Open": close,
                        "High": high,
                        "Low": low,
                        "Close": close,
                        "Volume": 1.0,
                    }
                )
        return pd.DataFrame(data)

    return provider


def test_g6a_intraday_invalidation(tmp_path):
    conn = _db(tmp_path)
    _insert_candidate(conn, "BTC-1")
    provider = _provider_from({"2026-07-17": (85.0, 95.0, 92.0)})

    settled = settlement_mod.settle_due_candidates(
        conn, ohlcv_provider=provider, as_of_utc="2026-07-17T00:00:00Z"
    )

    assert len(settled) == 1
    row = conn.execute(
        "SELECT outcome, settle_price, market_return FROM settlements"
    ).fetchone()
    assert row[0] == "invalidated"
    assert row[1] == pytest.approx(90.0)
    assert row[2] == pytest.approx(-0.1)


def test_g6a_intraday_target(tmp_path):
    conn = _db(tmp_path)
    _insert_candidate(conn, "BTC-2")
    provider = _provider_from({"2026-07-17": (95.0, 108.0, 106.0)})

    settled = settlement_mod.settle_due_candidates(
        conn, ohlcv_provider=provider, as_of_utc="2026-07-17T00:00:00Z"
    )

    assert len(settled) == 1
    row = conn.execute(
        "SELECT outcome, settle_price, market_return FROM settlements"
    ).fetchone()
    assert row[0] == "target"
    assert row[1] == pytest.approx(105.0)
    assert row[2] == pytest.approx(0.05)


def test_g6c_same_day_double_touch_invalidation_wins(tmp_path):
    conn = _db(tmp_path)
    _insert_candidate(conn, "BTC-3")
    # 同一日: Low <= 90(失效) 且 High >= 105(目标) 双触。
    provider = _provider_from({"2026-07-17": (85.0, 108.0, 95.0)})

    settlement_mod.settle_due_candidates(
        conn, ohlcv_provider=provider, as_of_utc="2026-07-17T00:00:00Z"
    )

    outcome, settle_price = conn.execute(
        "SELECT outcome, settle_price FROM settlements"
    ).fetchone()
    assert outcome == "invalidated"
    assert settle_price == pytest.approx(90.0)


def test_g6d_expiry_close_settlement_when_untouched(tmp_path):
    conn = _db(tmp_path)
    _insert_candidate(conn, "BTC-4", expires_utc="2026-07-21T00:00:00Z")
    # 07-17 ~ 07-21 全程不触任何位。
    rows = {
        "2026-07-17": (95.0, 100.0, 97.0),
        "2026-07-18": (94.0, 101.0, 96.0),
        "2026-07-19": (93.0, 102.0, 95.0),
        "2026-07-20": (92.0, 103.0, 94.0),
        "2026-07-21": (93.0, 102.0, 98.0),
    }
    provider = _provider_from(rows)

    settled = settlement_mod.settle_due_candidates(
        conn, ohlcv_provider=provider, as_of_utc="2026-07-22T00:00:00Z"
    )

    assert len(settled) == 1
    outcome, settle_price, market_return = conn.execute(
        "SELECT outcome, settle_price, market_return FROM settlements"
    ).fetchone()
    assert outcome == "expired"
    assert settle_price == pytest.approx(98.0)  # 到期日(07-21)收盘价
    assert market_return == pytest.approx(-0.02)


def test_creation_day_double_touch_is_not_settled(tmp_path):
    """contract-backfill 子任务 F1: 创建当日即双触(Low<=失效位 且 High>=目标)不应
    被计入结算窗口(前视防护)——``ohlcv_provider`` 只有创建当日这一根 K 线可用时,
    ``settle_due_candidates`` 必须不产生任何结算行(次日起才是有效结算窗口起点)。"""
    conn = _db(tmp_path)
    _insert_candidate(conn, "BTC-creation-day", creation_date="2026-07-16")
    # 创建当日(07-16)本身双触: Low<=90(失效) 且 High>=105(目标)。若前视防护被
    # 回退,结算器会在创建当日就把这根 K 线判定为 invalidated。
    provider = _provider_from({"2026-07-16": (85.0, 108.0, 95.0)})

    settled = settlement_mod.settle_due_candidates(
        conn, ohlcv_provider=provider, as_of_utc="2026-07-18T00:00:00Z"
    )

    assert settled == []
    assert conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0] == 0


def test_settlement_not_due_yet_is_skipped(tmp_path):
    """未到期且未触位: 本轮不结算(不产生 settlements 行)。"""
    conn = _db(tmp_path)
    _insert_candidate(conn, "BTC-5", expires_utc="2026-07-21T00:00:00Z")
    provider = _provider_from({"2026-07-17": (95.0, 100.0, 97.0)})

    settled = settlement_mod.settle_due_candidates(
        conn, ohlcv_provider=provider, as_of_utc="2026-07-17T00:00:00Z"
    )

    assert settled == []
    assert conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0] == 0


def test_settlement_fields_match_settlement_math_long_contract(tmp_path):
    """direction_hit/strategy_return/alpha 与 settlement_math.spot_settle(long,...) 口径一致。"""
    from btc_agent.settlement_math import spot_settle

    conn = _db(tmp_path)
    _insert_candidate(conn, "BTC-6")
    provider = _provider_from({"2026-07-17": (95.0, 108.0, 106.0)})

    settlement_mod.settle_due_candidates(
        conn, ohlcv_provider=provider, as_of_utc="2026-07-17T00:00:00Z"
    )

    market_return = (105.0 - 100.0) / 100.0
    expected = spot_settle("long", market_return=market_return, bench_return=market_return)

    strategy_return, alpha, direction_hit = conn.execute(
        "SELECT strategy_return, alpha, direction_hit FROM settlements"
    ).fetchone()
    assert strategy_return == pytest.approx(expected["strategy_return"])
    assert alpha == pytest.approx(expected["alpha"])
    assert bool(direction_hit) == expected["direction_hit"]


def test_veto_candidate_is_settled_same_as_accepted_and_counterfactual_report(tmp_path):
    """反事实归因: veto 候选照常结算; counterfactual_report 输出 accepted vs vetoed 对比。"""
    conn = _db(tmp_path)
    _insert_candidate(conn, "BTC-accept", verdict="accept")
    _insert_candidate(conn, "BTC-veto", verdict="veto")
    provider = _provider_from({"2026-07-17": (95.0, 108.0, 106.0)})  # 两者同日触目标

    settled = settlement_mod.settle_due_candidates(
        conn, ohlcv_provider=provider, as_of_utc="2026-07-17T00:00:00Z"
    )
    assert len(settled) == 2  # veto 候选照常结算,不因裁决被跳过

    report = settlement_mod.counterfactual_report(conn)
    by_group = {r["group"]: r for r in report}
    assert by_group["accepted"]["count"] == 1
    assert by_group["vetoed_or_observed"]["count"] == 1
    assert by_group["accepted"]["avg_strategy_return"] == pytest.approx(0.05)
    assert by_group["vetoed_or_observed"]["avg_strategy_return"] == pytest.approx(0.05)
    assert by_group["accepted"]["hit_rate"] == pytest.approx(1.0)


def test_settlement_module_does_not_import_graph():
    """G2 硬约束: settlement.py 源码不含对 graph 包的 import。"""
    src = inspect.getsource(settlement_mod)
    assert "import btc_agent.graph" not in src
    assert "from btc_agent.graph" not in src
    assert "from btc_agent import graph" not in src


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
