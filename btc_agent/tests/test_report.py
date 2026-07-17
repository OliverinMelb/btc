"""v2-monthly-report 子任务: 月度成绩单单测(stdlib sqlite3, tmp_path, 零网络)。

覆盖: 净值回放(Hold carry / Sell 空仓 / 换仓摩擦 / 缺日顺延)手算核对;评级统计
命中率/pending 尾部;--month 过滤;候选分组对比(accept vs veto);REPORT_PARAMS
json 可序列化;report.py 不 import graph/intel/llm。
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from dataclasses import dataclass, field

import pandas as pd
import pytest

from btc_agent import ledger as ledger_mod
from btc_agent import report as report_mod
from btc_agent import settlement as settlement_mod


@dataclass
class _FakeSnapshot:
    snapshot_id: str
    asset: str = "BTC"
    curr_date: str | None = "2026-07-01"
    frozen_at_utc: str = "2026-07-01T00:00:00Z"
    health: dict = field(default_factory=lambda: {"ohlcv": "ok"})


@dataclass
class _FakeRegimeResult:
    regime: str = "range"
    blank_sheet: bool = False
    observations: dict = field(default_factory=dict)


def _db(tmp_path) -> sqlite3.Connection:
    return ledger_mod.connect(str(tmp_path / "ledger.sqlite3"))


def _seed_day(
    conn: sqlite3.Connection,
    trade_date: str,
    close: float,
    rating: str | None = None,
    asset: str = "BTC",
) -> None:
    """种一天的快照(带 last_close 观察值),可选 rating(→ 插 trade_levels 行)。"""
    snapshot = _FakeSnapshot(
        snapshot_id=f"{asset}-{trade_date}",
        asset=asset,
        curr_date=trade_date,
        frozen_at_utc=f"{trade_date}T00:00:00Z",
    )
    regime_result = _FakeRegimeResult(observations={"last_close": close})
    levels = {"entry": close, "stop": None, "target": None, "atr": None} if rating else None
    ledger_mod.record_daily(conn, snapshot, regime_result, rating, "理由", levels, None)


def _seed_candidate(
    conn: sqlite3.Connection,
    snapshot_id: str,
    creation_date: str,
    verdict: str,
    entry_ref: float = 100.0,
    invalidation: float = 90.0,
    target_zone: tuple[float, float] = (105.0, 110.0),
    expires_utc: str = "2026-07-21T00:00:00Z",
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


def _ohlcv_provider_from(rows: dict[str, tuple[float, float, float]]):
    """``rows``: date -> (Low, High, Close)。零网络 settlement provider。"""

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


# ---------------------------------------------------------------------------
# REPORT_PARAMS / 依赖边界
# ---------------------------------------------------------------------------


def test_report_params_json_serializable():
    json.dumps(report_mod.REPORT_PARAMS)  # 不抛异常即通过


def test_report_module_does_not_import_graph_intel_llm():
    src = inspect.getsource(report_mod)
    for forbidden in ("import btc_agent.graph", "from btc_agent.graph", "btc_agent.intel", "btc_agent.llm_clients"):
        assert forbidden not in src


def test_report_does_not_hand_roll_settlement_math():
    """结算口径只有一个 source of truth: settlement_math.spot_settle。

    防回归: report.py 不得手写第二套结算数学(如 sign*market_return 的做空口径),
    必须 import settlement_math 并复用 spot_settle。
    """
    src = inspect.getsource(report_mod)
    assert "settlement_math" in src
    assert "spot_settle" in src
    for forbidden in ("sign * market_return", "sign*market_return", "_DIRECTION_SIGN"):
        assert forbidden not in src


# ---------------------------------------------------------------------------
# 净值回放
# ---------------------------------------------------------------------------


def test_nav_replay_hand_calc_hold_carry_sell_flat_friction_and_missing_day(tmp_path):
    conn = _db(tmp_path)
    # 07-01 Buy close=100 (首日建仓,扣一次摩擦)
    # 07-02 Hold close=110 (carry 仓位=1.0,无摩擦)
    # 07-03 缺(计划任务漏跑)
    # 07-04 Sell close=99 (仓位归零,扣一次摩擦)
    _seed_day(conn, "2026-07-01", 100.0, rating="Buy")
    _seed_day(conn, "2026-07-02", 110.0, rating="Hold")
    _seed_day(conn, "2026-07-04", 99.0, rating="Sell")

    params = dict(report_mod.REPORT_PARAMS)
    result = report_mod.nav_replay(conn, "2026-07", params=params)

    friction = params["friction_per_rebalance"]
    capital = params["capital"]

    nav1 = capital * (1 - friction * 1.0)  # 首日建仓摩擦, turnover=1.0
    day2_return = (110.0 - 100.0) / 100.0
    nav2 = nav1 * (1 + 1.0 * day2_return) * (1 - friction * 0.0)  # Hold carry, 无摩擦
    day3_return = (99.0 - 110.0) / 110.0
    nav3 = nav2 * (1 + 0.0 * day3_return) * (1 - friction * 1.0)  # Sell 空仓, 换仓摩擦

    assert result["final_nav"] == pytest.approx(nav3)
    assert result["total_return"] == pytest.approx((nav3 - capital) / capital)
    assert result["missing_days"] == 1  # 07-03 缺
    assert [c["date"] for c in result["curve"]] == ["2026-07-01", "2026-07-02", "2026-07-04"]
    assert [c["position"] for c in result["curve"]] == [1.0, 1.0, 0.0]


def test_nav_replay_empty_month_returns_capital_unchanged(tmp_path):
    conn = _db(tmp_path)
    result = report_mod.nav_replay(conn, "2026-08")
    assert result["final_nav"] == report_mod.REPORT_PARAMS["capital"]
    assert result["total_return"] == 0.0
    assert result["missing_days"] == 0
    assert result["curve"] == []


def test_nav_replay_month_filter_excludes_other_months(tmp_path):
    conn = _db(tmp_path)
    _seed_day(conn, "2026-06-30", 50.0, rating="Buy")
    _seed_day(conn, "2026-07-01", 100.0, rating="Buy")
    _seed_day(conn, "2026-07-02", 105.0, rating="Hold")

    result = report_mod.nav_replay(conn, "2026-07")
    assert [c["date"] for c in result["curve"]] == ["2026-07-01", "2026-07-02"]


# ---------------------------------------------------------------------------
# 评级统计
# ---------------------------------------------------------------------------


def test_rating_stats_hit_rate_alpha_and_pending_tail(tmp_path):
    conn = _db(tmp_path)
    # 起点
    _seed_day(conn, "2026-07-01", 100.0, rating="Buy")
    _seed_day(conn, "2026-07-02", 105.0, rating="Underweight")
    _seed_day(conn, "2026-07-03", 110.0, rating="Hold")
    # t+5 目标日(为 07-01/07-02/07-03 提供收盘)
    _seed_day(conn, "2026-07-06", 120.0)
    _seed_day(conn, "2026-07-07", 95.0)
    _seed_day(conn, "2026-07-08", 115.0)
    # 尾部条目: t+5 (08-02) 无数据 → pending,不计入
    _seed_day(conn, "2026-07-28", 130.0, rating="Buy")

    stats = report_mod.rating_stats(conn, "2026-07")

    buy_market = (120.0 - 100.0) / 100.0
    assert stats["per_rating"]["Buy"]["count"] == 1
    assert stats["per_rating"]["Buy"]["avg_market_return"] == pytest.approx(buy_market)
    assert stats["per_rating"]["Buy"]["avg_strategy_return"] == pytest.approx(buy_market)
    assert stats["per_rating"]["Buy"]["avg_alpha"] == pytest.approx(0.0)
    assert stats["per_rating"]["Buy"]["hit_rate"] == pytest.approx(1.0)

    # 现货口径(settlement_math.spot_settle):Underweight/Sell 映射到 short,
    # 现货系统不能靠"看空"获利 → strategy_return 恒为 0,alpha=-market_return
    # (踏空机会成本),direction_hit = market_return < 0。
    uw_market = (95.0 - 105.0) / 105.0
    assert stats["per_rating"]["Underweight"]["count"] == 1
    assert stats["per_rating"]["Underweight"]["avg_market_return"] == pytest.approx(uw_market)
    assert stats["per_rating"]["Underweight"]["avg_strategy_return"] == pytest.approx(0.0)
    assert stats["per_rating"]["Underweight"]["avg_alpha"] == pytest.approx(-uw_market)
    assert stats["per_rating"]["Underweight"]["hit_rate"] == pytest.approx(1.0)  # uw_market < 0

    # Hold → flat: strategy_return=0, alpha=-market_return, direction_hit=None(不计入命中分母)。
    hold_market = (115.0 - 110.0) / 110.0
    assert stats["per_rating"]["Hold"]["count"] == 1
    assert stats["per_rating"]["Hold"]["avg_market_return"] == pytest.approx(hold_market)
    assert stats["per_rating"]["Hold"]["avg_strategy_return"] == pytest.approx(0.0)
    assert stats["per_rating"]["Hold"]["avg_alpha"] == pytest.approx(-hold_market)
    assert stats["per_rating"]["Hold"]["hit_rate"] is None  # Hold 无方向, 不计入命中分母

    assert stats["pending"] == 1  # 07-28 的 Buy, t+5 (08-02) 无数据
    assert stats["overall"]["count"] == 3
    overall_hit_rate = 2 / 2  # 只有 Buy/Underweight 两条计入命中分母, 均命中
    assert stats["overall"]["hit_rate"] == pytest.approx(overall_hit_rate)


def test_rating_stats_month_filter_only_counts_current_month(tmp_path):
    conn = _db(tmp_path)
    _seed_day(conn, "2026-06-25", 100.0, rating="Buy")
    _seed_day(conn, "2026-06-30", 110.0)  # t+5 目标
    _seed_day(conn, "2026-07-01", 200.0, rating="Sell")
    _seed_day(conn, "2026-07-06", 180.0)

    stats = report_mod.rating_stats(conn, "2026-07")
    assert stats["overall"]["count"] == 1
    assert stats["per_rating"]["Sell"]["count"] == 1
    assert stats["per_rating"]["Buy"]["count"] == 0


def test_rating_stats_empty_month_graceful(tmp_path):
    conn = _db(tmp_path)
    stats = report_mod.rating_stats(conn, "2026-09")
    assert stats["overall"]["count"] == 0
    assert stats["overall"]["hit_rate"] is None
    assert stats["pending"] == 0


# ---------------------------------------------------------------------------
# 候选分组对比
# ---------------------------------------------------------------------------


def test_candidate_group_report_accept_vs_veto(tmp_path):
    conn = _db(tmp_path)
    _seed_candidate(conn, "BTC-cand-accept", "2026-07-01", verdict="accept")
    _seed_candidate(conn, "BTC-cand-veto", "2026-07-01", verdict="veto")

    provider = _ohlcv_provider_from(
        {
            "2026-07-02": (95.0, 108.0, 106.0),  # 触及目标下沿 105 → target
        }
    )
    settlement_mod.settle_due_candidates(conn, ohlcv_provider=provider, as_of_utc="2026-07-02T00:00:00Z")

    report = report_mod.candidate_group_report(conn)
    groups = {g["group"]: g for g in report}
    assert groups["accepted"]["count"] == 1
    assert groups["vetoed_or_observed"]["count"] == 1
    assert groups["accepted"]["hit_rate"] == pytest.approx(1.0)
    assert groups["vetoed_or_observed"]["hit_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# render_report / CLI 边界
# ---------------------------------------------------------------------------


def test_render_report_empty_month_does_not_crash(tmp_path):
    conn = _db(tmp_path)
    text = report_mod.render_report(conn, "2026-12")
    assert "2026-12" in text
    assert "本月无" in text
    assert "非 v3 模拟盘" in text


def test_render_report_with_data_contains_all_three_sections(tmp_path):
    conn = _db(tmp_path)
    _seed_day(conn, "2026-07-01", 100.0, rating="Buy")
    _seed_day(conn, "2026-07-02", 110.0, rating="Hold")
    _seed_candidate(conn, "BTC-cand-1", "2026-07-01", verdict="accept")

    text = report_mod.render_report(conn, "2026-07")
    assert "[1]" in text and "[2]" in text and "[3]" in text
    assert "期末净值" in text


def test_validate_month_rejects_bad_format():
    with pytest.raises(ValueError):
        report_mod._validate_month("2026/07")
    with pytest.raises(ValueError):
        report_mod._validate_month("2026-13")


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
