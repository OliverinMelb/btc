"""web-dashboard 任务: webexport 导出器单测(tmp_path ledger, 零网络)。"""

from __future__ import annotations

import inspect
import json
import sqlite3
from dataclasses import dataclass, field

from btc_agent import ledger as ledger_mod
from btc_agent import webexport as webexport_mod


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


def _seed_day(conn, trade_date, close, rating=None, regime="range", blank=False):
    snapshot = _FakeSnapshot(
        snapshot_id=f"BTC-{trade_date}",
        curr_date=trade_date,
        frozen_at_utc=f"{trade_date}T00:00:00Z",
    )
    rr = _FakeRegimeResult(regime=regime, blank_sheet=blank, observations={"last_close": close})
    levels = {"entry": close, "stop": None, "target": None, "atr": None} if rating else None
    ledger_mod.record_daily(conn, snapshot, rr, rating, "理由", levels, None)


def _db(tmp_path) -> sqlite3.Connection:
    return ledger_mod.connect(str(tmp_path / "ledger.sqlite3"))


def test_build_dashboard_data_fields_and_order(tmp_path):
    conn = _db(tmp_path)
    _seed_day(conn, "2026-07-01", 100.0, rating="Buy", regime="trend_up")
    _seed_day(conn, "2026-07-02", 110.0, rating="Hold")
    _seed_day(conn, "2026-07-03", 105.0, regime="chaos", blank=True)  # 白卷日无评级

    data = webexport_mod.build_dashboard_data(conn, generated_at="2026-07-03T01:00:00Z")

    assert data["asset"] == "BTC"
    assert data["generated_at_utc"] == "2026-07-03T01:00:00Z"
    dates = [d["date"] for d in data["days"]]
    assert dates == sorted(dates) == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert data["latest"]["regime"] == "chaos" and data["latest"]["blank_sheet"] is True
    assert data["latest"]["rating"] is None
    # NAV 曲线覆盖三个有 close 的日子;Buy 首日建仓有摩擦
    assert len(data["nav"]["curve"]) == 3
    assert data["nav"]["curve"][0]["position"] == 1.0
    assert data["nav"]["final_nav"] != data["nav"]["capital"]
    assert data["rating_stats_month"] == "2026-07"
    # 整份可 json 序列化
    json.dumps(data)


def test_empty_ledger_graceful(tmp_path):
    conn = _db(tmp_path)
    data = webexport_mod.build_dashboard_data(conn, generated_at="x")
    assert data["days"] == [] and data["latest"] is None
    assert data["nav"]["curve"] == []
    assert data["rating_stats"] is None and data["rating_stats_month"] is None
    assert data["candidates"] == []
    json.dumps(data)


def test_export_writes_valid_json_file(tmp_path):
    db = tmp_path / "ledger.sqlite3"
    conn = ledger_mod.connect(str(db))
    _seed_day(conn, "2026-07-01", 100.0, rating="Buy")
    conn.close()
    out = webexport_mod.export_dashboard(db, tmp_path / "web" / "data" / "dashboard.json")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["days"][0]["close"] == 100.0


def test_window_limit(tmp_path):
    conn = _db(tmp_path)
    for i in range(1, 10):
        _seed_day(conn, f"2026-07-{i:02d}", 100.0 + i)
    data = webexport_mod.build_dashboard_data(conn, window_days=5, generated_at="x")
    assert len(data["days"]) == 5
    assert data["days"][0]["date"] == "2026-07-05"  # 取最近 5 天且升序


def test_no_forbidden_imports_and_no_second_replay_formula():
    src = inspect.getsource(webexport_mod)
    for banned in ("from btc_agent.graph", "import btc_agent.graph",
                   "from btc_agent.intel", "btc_agent.llm_clients"):
        assert banned not in src
    # 回放公式唯一真源在 report.replay_dates,导出器不得自写
    assert "replay_dates" in src
    assert "1 + position * day_return" not in src
