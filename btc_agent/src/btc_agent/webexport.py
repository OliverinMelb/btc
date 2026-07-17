"""Web 仪表盘数据导出(BTC agent v2)。

``python -m btc_agent.webexport [--out web/data/dashboard.json]``

从 ledger.sqlite3 **只读**导出静态站点(``web/``)要渲染的全部数据:
近 N 天日线(收盘/环境/评级/白卷)、全窗口虚拟账户净值回放(复用
``report.replay_dates``——回放公式唯一真源,本模块不写第二遍)、候选记录
(裁决/机械价位/结算)、反事实汇总、最近月份评级统计。

零网络、零 LLM;凭据/账本本体绝不出仓库,发布的只有这份聚合 JSON。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from btc_agent.default_config import DEFAULT_CONFIG
from btc_agent.report import (
    REPORT_PARAMS,
    _fetch_close_series,
    _fetch_ratings,
    candidate_group_report,
    rating_stats,
    replay_dates,
)

# 仪表盘日线窗口(天)。纯展示参数,不进任何策略版本 hash。
EXPORT_WINDOW_DAYS = 90


def _fetch_days(conn: sqlite3.Connection, asset: str, limit: int) -> list[dict[str, Any]]:
    """近 ``limit`` 天 (date, close, regime, blank_sheet, rating),升序。"""
    rows = conn.execute(
        "SELECT s.trade_date, s.observations_json, s.regime, s.blank_sheet, tl.rating "
        "FROM snapshots s "
        "LEFT JOIN trade_levels tl ON tl.snapshot_id = s.snapshot_id "
        "WHERE s.asset = ? AND s.trade_date IS NOT NULL "
        "ORDER BY s.trade_date DESC LIMIT ?",
        (asset, limit),
    ).fetchall()
    days: list[dict[str, Any]] = []
    for trade_date, obs_json, regime, blank_sheet, rating in rows:
        close = None
        if obs_json:
            close = json.loads(obs_json).get("last_close")
        days.append(
            {
                "date": trade_date,
                "close": close,
                "regime": regime,
                "blank_sheet": bool(blank_sheet),
                "rating": rating,
            }
        )
    return list(reversed(days))


def _fetch_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """候选全量(含裁决与结算,可能为 NULL),按创建时间倒序。"""
    rows = conn.execute(
        "SELECT c.id, c.candidate_type, c.entry_ref, c.invalidation, c.target_zone_json, "
        "       c.expires_utc, c.created_at_utc, v.verdict, v.reason, "
        "       st.outcome, st.settle_price, st.strategy_return, st.direction_hit, "
        "       st.settled_at_utc "
        "FROM candidates c "
        "LEFT JOIN verdicts v ON v.candidate_id = c.id "
        "LEFT JOIN settlements st ON st.candidate_id = c.id "
        "ORDER BY c.created_at_utc DESC",
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        target_zone = json.loads(r[4]) if r[4] else None
        out.append(
            {
                "id": r[0],
                "candidate_type": r[1],
                "entry_ref": r[2],
                "invalidation": r[3],
                "target_zone": target_zone,
                "expires_utc": r[5],
                "created_at_utc": r[6],
                "verdict": r[7],
                "reason": r[8],
                "outcome": r[9],
                "settle_price": r[10],
                "strategy_return": r[11],
                "direction_hit": None if r[12] is None else bool(r[12]),
                "settled_at_utc": r[13],
            }
        )
    return out


def build_dashboard_data(
    conn: sqlite3.Connection,
    asset: str = "BTC",
    window_days: int = EXPORT_WINDOW_DAYS,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """组装 dashboard.json 的完整 dict(纯函数,便于离线单测)。"""
    days = _fetch_days(conn, asset, window_days)

    closes = _fetch_close_series(conn, asset)
    ratings = dict(_fetch_ratings(conn, asset, None))
    window_dates = [d["date"] for d in days if d["close"] is not None]
    nav = replay_dates(closes, ratings, window_dates)

    latest_month = days[-1]["date"][:7] if days else None
    stats = rating_stats(conn, latest_month, asset=asset) if latest_month else None

    return {
        "asset": asset,
        "generated_at_utc": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": window_days,
        "days": days,
        "latest": days[-1] if days else None,
        "nav": {
            "curve": nav["curve"],
            "final_nav": nav["final_nav"],
            "total_return": nav["total_return"],
            "capital": nav["capital"],
            "missing_days": nav["missing_days"],
        },
        "report_params": REPORT_PARAMS,
        "rating_stats_month": latest_month,
        "rating_stats": stats,
        "candidates": _fetch_candidates(conn),
        "counterfactual": candidate_group_report(conn),
    }


def export_dashboard(
    db_path: str | Path,
    out_path: str | Path,
    asset: str = "BTC",
) -> Path:
    """读 ledger → 写 dashboard.json,返回输出路径。"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        data = build_dashboard_data(conn, asset=asset)
    finally:
        conn.close()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="btc_agent.webexport",
        description="导出 web 仪表盘数据(只读 ledger → web/data/dashboard.json)",
    )
    parser.add_argument("--asset", default="BTC")
    parser.add_argument(
        "--db",
        default=None,
        help="ledger 路径(默认 results_dir/ledger.sqlite3)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="输出路径(默认 <repo>/web/data/dashboard.json,按本文件位置推导)",
    )
    args = parser.parse_args(argv)

    db = args.db or str(Path(DEFAULT_CONFIG["results_dir"]) / "ledger.sqlite3")
    # src/btc_agent/webexport.py → 仓库根 = parents[3]
    default_out = Path(__file__).resolve().parents[3] / "web" / "data" / "dashboard.json"
    out = Path(args.out) if args.out else default_out

    if not Path(db).exists():
        print(f"[webexport] ledger 不存在: {db}(先跑一次 daily)")
        return 1
    path = export_dashboard(db, out, asset=args.asset)
    print(f"[webexport] 已导出 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
