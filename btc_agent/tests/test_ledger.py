"""sqlite-ledger 子任务: 账本单测(stdlib sqlite3, tmp_path, 零网络)。

覆盖:策略版本 hash 复用/新建 + 旧版本行只读;record_daily 幂等;候选/裁决/
机械价位入库;白卷/无候选路径不插候选行;ledger.py 不 import graph(G2 硬约束)。
"""

from __future__ import annotations

import inspect
import sqlite3
from dataclasses import dataclass, field
from typing import Any

import pytest

from btc_agent import ledger as ledger_mod


@dataclass
class _FakeSnapshot:
    snapshot_id: str
    asset: str = "BTC"
    curr_date: str | None = "2026-07-16"
    frozen_at_utc: str = "2026-07-16T00:00:00Z"
    health: dict = field(default_factory=lambda: {"ohlcv": "ok"})


@dataclass
class _FakeRegimeResult:
    regime: str = "range"
    blank_sheet: bool = False
    observations: dict = field(default_factory=dict)


def _db(tmp_path) -> sqlite3.Connection:
    return ledger_mod.connect(str(tmp_path / "ledger.sqlite3"))


def _candidate_payload(**overrides: Any) -> dict:
    payload = {
        "candidate_type": "range_lower_long",
        "verdict": "accept",
        "reason": "机械依据支持",
        "entry_ref": 100.0,
        "invalidation": 90.0,
        "target_zone": (105.0, 110.0),
        "expires_utc": "2026-07-21T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_get_or_create_strategy_version_reuses_same_hash(tmp_path):
    conn = _db(tmp_path)
    regime_params = {"a": 1}
    candidate_params = {"b": 2, "touch_basis": "intraday", "settle_price": "level", "tie_break": "stop_first"}

    id1 = ledger_mod.get_or_create_strategy_version(conn, "rule", regime_params, candidate_params)
    id2 = ledger_mod.get_or_create_strategy_version(conn, "rule", regime_params, candidate_params)

    assert id1 == id2
    rows = conn.execute("SELECT COUNT(*) FROM strategy_versions").fetchone()
    assert rows[0] == 1


def test_changing_candidate_params_creates_new_version_and_old_row_stays_readonly(tmp_path):
    conn = _db(tmp_path)
    regime_params = {"a": 1}
    candidate_params_v1 = {"b": 2, "touch_basis": "intraday", "settle_price": "level", "tie_break": "stop_first"}
    candidate_params_v2 = dict(candidate_params_v1, b=999)  # 拷贝改值

    old_id = ledger_mod.get_or_create_strategy_version(conn, "rule", regime_params, candidate_params_v1)
    old_row_before = conn.execute(
        "SELECT rule_name, params_json, params_hash, status, created_at_utc "
        "FROM strategy_versions WHERE id = ?",
        (old_id,),
    ).fetchone()

    new_id = ledger_mod.get_or_create_strategy_version(conn, "rule", regime_params, candidate_params_v2)

    assert new_id != old_id

    old_row_after = conn.execute(
        "SELECT rule_name, params_json, params_hash, status, created_at_utc "
        "FROM strategy_versions WHERE id = ?",
        (old_id,),
    ).fetchone()
    assert old_row_after == old_row_before  # 旧版本行原样不变

    both = conn.execute("SELECT COUNT(*) FROM strategy_versions").fetchone()[0]
    assert both == 2


def test_record_daily_is_idempotent_on_same_snapshot_id(tmp_path):
    conn = _db(tmp_path)
    snapshot = _FakeSnapshot(snapshot_id="BTC-2026-07-16-abc123")
    regime_result = _FakeRegimeResult()
    candidates = _candidate_payload()
    levels = {"entry": 100.0, "stop": 90.0, "target": 120.0, "atr": 5.0}

    ledger_mod.record_daily(conn, snapshot, regime_result, "Buy", "理由", levels, candidates)
    ledger_mod.record_daily(conn, snapshot, regime_result, "Buy", "理由", levels, candidates)

    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM trade_levels").fetchone()[0] == 1


def test_record_daily_inserts_candidate_verdict_and_trade_levels(tmp_path):
    conn = _db(tmp_path)
    snapshot = _FakeSnapshot(snapshot_id="BTC-2026-07-16-def456")
    regime_result = _FakeRegimeResult()
    candidates = _candidate_payload(verdict="veto", reason="证据不支持")
    levels = {"entry": 100.0, "stop": 90.0, "target": 120.0, "atr": 5.0}

    ledger_mod.record_daily(conn, snapshot, regime_result, "Hold", "观望", levels, candidates)

    snap_row = conn.execute(
        "SELECT asset, regime, blank_sheet FROM snapshots WHERE snapshot_id = ?",
        (snapshot.snapshot_id,),
    ).fetchone()
    assert snap_row == ("BTC", "range", 0)

    cand_row = conn.execute(
        "SELECT candidate_type, entry_ref, invalidation FROM candidates WHERE snapshot_id = ?",
        (snapshot.snapshot_id,),
    ).fetchone()
    assert cand_row == ("range_lower_long", 100.0, 90.0)

    verdict_row = conn.execute(
        "SELECT verdict, reason FROM verdicts v "
        "JOIN candidates c ON c.id = v.candidate_id WHERE c.snapshot_id = ?",
        (snapshot.snapshot_id,),
    ).fetchone()
    assert verdict_row == ("veto", "证据不支持")

    levels_row = conn.execute(
        "SELECT rating, direction, entry, stop, target, atr FROM trade_levels WHERE snapshot_id = ?",
        (snapshot.snapshot_id,),
    ).fetchone()
    assert levels_row == ("Hold", "flat", 100.0, 90.0, 120.0, 5.0)


def test_record_daily_without_candidates_skips_candidate_rows(tmp_path):
    """白卷/未产候选路径: candidates=None → 不插候选/裁决行,快照行仍入库。"""
    conn = _db(tmp_path)
    snapshot = _FakeSnapshot(snapshot_id="BTC-2026-07-16-ghi789", health={"ohlcv": "error:timeout"})
    regime_result = _FakeRegimeResult(regime="insufficient_data", blank_sheet=True)

    ledger_mod.record_daily(conn, snapshot, regime_result, None, None, None, None)

    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM trade_levels").fetchone()[0] == 0


def test_ledger_module_does_not_import_graph():
    """G2 硬约束: ledger.py 源码不含对 graph 包的 import。"""
    src = inspect.getsource(ledger_mod)
    assert "import btc_agent.graph" not in src
    assert "from btc_agent.graph" not in src
    assert "from btc_agent import graph" not in src


def test_ledger_db_file_created_with_missing_parent_dir(tmp_path):
    db_path = tmp_path / "nested" / "does" / "not" / "exist" / "ledger.sqlite3"
    conn = ledger_mod.connect(str(db_path))
    assert db_path.exists()
    conn.execute("SELECT 1")


if __name__ == "__main__":
    pytest.main([__file__, "-q"])


def test_record_daily_same_trade_date_different_snapshot_id_is_idempotent(tmp_path):
    """同 (asset, trade_date) 不同 snapshot_id(同日重跑)也必须去重——
    snapshot_id 含运行时刻 hash,不能作为唯一幂等键(2026-07-17 生产事故回归)。"""
    conn = ledger_mod.connect(str(tmp_path / "ledger.sqlite3"))
    for run_hash in ("aaa", "bbb", "ccc"):
        snapshot = _FakeSnapshot(
            snapshot_id=f"BTC-2026-07-17-{run_hash}",
            curr_date="2026-07-17",
        )
        rr = _FakeRegimeResult(observations={"last_close": 100.0})
        ledger_mod.record_daily(
            conn, snapshot, rr, "Hold",
            "理由", {"entry": 100.0, "stop": None, "target": None, "atr": None}, None,
        )
    n_snap = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    n_levels = conn.execute("SELECT COUNT(*) FROM trade_levels").fetchone()[0]
    assert n_snap == 1 and n_levels == 1
