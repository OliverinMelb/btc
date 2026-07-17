"""月度成绩单报表(BTC agent v2)。

``python -m btc_agent.report --month YYYY-MM``:三段式月度成绩单,**只读**
``ledger.sqlite3``(SELECT only),零网络、零 LLM、无新依赖(stdlib
``sqlite3``/``json``/``argparse`` + 已有的 ``settlement.counterfactual_report``)。

三段:

1. **月度评级统计**——``trade_levels.rating`` 与 ``snapshots.observations_json``
   (``last_close``)按 ``trade_date`` join 出 (date, rating, close) 序列,5 日持有
   收益/命中率/alpha 自算(不依赖 markdown 记忆日志的结算,那份不是统计真源)。
   **结算口径只有一个 source of truth**:``settlement_math.spot_settle``——本模块
   不手写第二套结算数学。``market_return = close[t+horizon]/close[t]-1``;方向用
   ``trade_levels.rating_to_direction(rating)`` 映射到 ``long``/``short``/``flat``
   (``Buy``/``Overweight``→long,``Underweight``/``Sell``→short,``Hold``→flat);
   逐条调用 ``spot_settle(direction, market_return, bench_return=market_return)``
   (基准=同期 BTC 现货买入持有,呼应 ``settlement.py`` 文档里提到的 ST1 "整仓评级
   vs BTC-HODL" 概念,候选层的 ``counterfactual_report`` 不做这件事)。**现货系统
   不能靠"看空"获利**:``short``/``flat`` 的 ``strategy_return`` 恒为 0,
   ``alpha = -bench_return``(踏空的机会成本);``direction_hit`` 只在
   ``long``(``market_return>0``)/``short``(``market_return<0``)时给出真值,
   ``flat``(Hold)恒为 ``None``,不计入命中率分母。t+horizon 若在 ledger 里还没有
   收盘数据(尾部/近期条目)记 ``pending``,不计入统计——**为此评级统计的 close
   序列查询不按月份过滤**(月份只过滤"评级发生日"这一端,前视窗口允许跨月)。

2. **候选分组对比**——直接复用 ``settlement.counterfactual_report``(accept vs
   vetoed/observed),账本全量口径,不做月度切片(候选的结算时点与创建时点本就
   可能跨月,切片会破坏反事实对比的完整性,报表文案里明确标注)。

3. **虚拟账户净值回放**——机械仓位规则,模块级 ``REPORT_PARAMS`` 集中(json 可
   序列化,与 ``regime.REGIME_PARAMS``/``candidates.CANDIDATE_PARAMS`` 同构风格,
   但**不进策略版本 hash**,报表参数与策略参数是两个独立概念)。口径:

   - 仓位 = 当日 rating 映射 ``REPORT_PARAMS["position_weights"]``;``Hold``/
     未知评级/当日无收盘数据一律 **carry**(维持上一次仓位)。
   - 逐日复利:``nav_t = nav_{t-1} * (1 + position_t * day_return) *
     (1 - friction_per_rebalance * |position_t - position_{t-1}|)``。
     ``day_return`` 用序列里相邻两个"有收盘数据"的交易日算——缺日(计划任务漏跑)
     顺延到下一个有数据的日子,不当成 0 收益、也不算独立摩擦事件。
   - 首日:没有前一日收盘,不计收益;若首日仓位非 0(如 Buy)仍按
     ``turnover=|position|`` 扣一次建仓摩擦。
   - 缺日数:月内首末两个"有收盘数据"的自然日之间,没有出现在 close 序列里的
     自然日计数(计划任务漏跑的近似口径,不含月份边界之外)。

   **这是无摩擦仿真近似,不是 v3 模拟盘/回测**——``REPORT_PARAMS`` 的仓位规则、
   摩擦假设都是报表层的简化建模,不代表任何已验证的执行策略。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, timedelta
from typing import Any

from btc_agent.settlement_math import spot_settle
from btc_agent.trade_levels import rating_to_direction

# 报表层机械仓位参数——json 可序列化,与策略版本 hash 无关(报表口径,非策略口径)。
REPORT_PARAMS: dict[str, Any] = {
    "position_weights": {
        "Buy": 1.0,
        "Overweight": 0.5,
        "Hold": "carry",
        "Underweight": 0.25,
        "Sell": 0.0,
    },
    "friction_per_rebalance": 0.001,
    "capital": 1_000_000,
    "hit_horizon_days": 5,
}

_RATING_ORDER = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]


def _validate_month(month: str) -> str:
    """校验 ``--month`` 为 ``YYYY-MM`` 格式,返回原值(不合法则抛 ``ValueError``)。"""
    parts = month.split("-")
    if len(parts) != 2:
        raise ValueError(f"--month 需为 YYYY-MM 格式,收到: {month!r}")
    year_s, month_s = parts
    if not (year_s.isdigit() and month_s.isdigit() and len(year_s) == 4 and len(month_s) == 2):
        raise ValueError(f"--month 需为 YYYY-MM 格式,收到: {month!r}")
    if not (1 <= int(month_s) <= 12):
        raise ValueError(f"--month 月份需在 01-12,收到: {month!r}")
    return month


def _shift_date(date_str: str, days: int) -> str:
    y, m, d = (int(x) for x in date_str.split("-"))
    return (date(y, m, d) + timedelta(days=days)).strftime("%Y-%m-%d")


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _fetch_close_series(conn: sqlite3.Connection, asset: str) -> dict[str, float]:
    """ledger 全量(不按月份过滤,供跨月前视窗口查询)``trade_date -> last_close``。"""
    rows = conn.execute(
        "SELECT trade_date, observations_json FROM snapshots "
        "WHERE asset = ? AND trade_date IS NOT NULL",
        (asset,),
    ).fetchall()
    closes: dict[str, float] = {}
    for trade_date, obs_json in rows:
        if not obs_json:
            continue
        obs = json.loads(obs_json)
        last_close = obs.get("last_close")
        if last_close is not None:
            closes[trade_date] = float(last_close)
    return closes


def _fetch_ratings(
    conn: sqlite3.Connection, asset: str, month: str | None
) -> list[tuple[str, str | None]]:
    """``(trade_date, rating)`` 序列,按 trade_date 升序;白卷等无 trade_levels 行记 ``None``。

    ``month`` 为 None 时取全量(webexport 全窗口回放用),否则只取当月。
    """
    pattern = f"{month}-%" if month else "%"
    rows = conn.execute(
        "SELECT s.trade_date, tl.rating FROM snapshots s "
        "LEFT JOIN trade_levels tl ON tl.snapshot_id = s.snapshot_id "
        "WHERE s.asset = ? AND s.trade_date LIKE ? "
        "ORDER BY s.trade_date",
        (asset, pattern),
    ).fetchall()
    return [(trade_date, rating) for trade_date, rating in rows]


def rating_stats(
    conn: sqlite3.Connection,
    month: str,
    asset: str = "BTC",
    horizon_days: int | None = None,
) -> dict[str, Any]:
    """月度评级统计(见模块 docstring 第 1 段口径)。"""
    horizon_days = horizon_days if horizon_days is not None else REPORT_PARAMS["hit_horizon_days"]
    closes = _fetch_close_series(conn, asset)
    ratings = _fetch_ratings(conn, asset, month)

    groups: dict[str, list[dict[str, float]]] = {r: [] for r in _RATING_ORDER}
    pending = 0
    no_close = 0
    for trade_date, rating in ratings:
        if rating not in _RATING_ORDER:
            continue  # 未知/None 评级(白卷等),不计入评级统计
        entry_close = closes.get(trade_date)
        if entry_close is None:
            no_close += 1
            continue
        target_date = _shift_date(trade_date, horizon_days)
        exit_close = closes.get(target_date)
        if exit_close is None:
            pending += 1
            continue
        market_return = (exit_close - entry_close) / entry_close
        direction = rating_to_direction(rating)
        settled = spot_settle(direction, market_return, bench_return=market_return)
        groups[rating].append(
            {
                "market_return": market_return,
                "strategy_return": settled["strategy_return"],
                "alpha": settled["alpha"],
                "hit": settled["direction_hit"],
            }
        )

    per_rating: dict[str, dict[str, Any]] = {}
    all_items: list[dict[str, Any]] = []
    for rating, items in groups.items():
        all_items.extend(items)
        hits = [i["hit"] for i in items if i["hit"] is not None]
        per_rating[rating] = {
            "count": len(items),
            "avg_market_return": _avg([i["market_return"] for i in items]),
            "avg_strategy_return": _avg([i["strategy_return"] for i in items]),
            "avg_alpha": _avg([i["alpha"] for i in items]),
            "hit_rate": (sum(hits) / len(hits)) if hits else None,
        }

    overall_hits = [i["hit"] for i in all_items if i["hit"] is not None]
    overall = {
        "count": len(all_items),
        "avg_market_return": _avg([i["market_return"] for i in all_items]),
        "avg_strategy_return": _avg([i["strategy_return"] for i in all_items]),
        "avg_alpha": _avg([i["alpha"] for i in all_items]),
        "hit_rate": (sum(overall_hits) / len(overall_hits)) if overall_hits else None,
    }

    return {
        "per_rating": per_rating,
        "overall": overall,
        "pending": pending,
        "no_close": no_close,
        "horizon_days": horizon_days,
    }


def candidate_group_report(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """候选分组对比(accept vs vetoed/observed)——直接复用 ``settlement.counterfactual_report``。

    账本全量口径,不做月度切片(见模块 docstring 第 2 段)。
    """
    from btc_agent.settlement import counterfactual_report

    return counterfactual_report(conn)


def _resolve_position(rating: str | None, prev_position: float, weights: dict[str, Any]) -> float:
    if rating is None:
        return prev_position
    w = weights.get(rating)
    if w is None or w == "carry":
        return prev_position
    return float(w)


def _count_missing_days(sorted_dates: list[str]) -> int:
    if len(sorted_dates) < 2:
        return 0
    have = set(sorted_dates)
    start = date.fromisoformat(sorted_dates[0])
    end = date.fromisoformat(sorted_dates[-1])
    total_span = (end - start).days + 1
    return total_span - len(have)


def replay_dates(
    closes: dict[str, float],
    ratings: dict[str, str | None],
    dates: list[str],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """在给定日期序列上做虚拟账户净值回放(口径见模块 docstring 第 3 段)。

    ``nav_replay``(月度)与 webexport(全窗口)共用本函数——回放公式只此一份,
    与结算口径同理:不许在别处再写第二遍。``dates`` 必须升序且都在 ``closes`` 里。
    """
    p = dict(params) if params is not None else REPORT_PARAMS
    weights = p["position_weights"]
    friction = p["friction_per_rebalance"]
    capital = p["capital"]

    if not dates:
        return {
            "curve": [],
            "final_nav": capital,
            "total_return": 0.0,
            "missing_days": 0,
            "capital": capital,
            "params": p,
        }

    missing_days = _count_missing_days(dates)

    nav = float(capital)
    curve: list[dict[str, Any]] = []
    prev_position = 0.0
    prev_close: float | None = None
    for d in dates:
        rating = ratings.get(d)
        position = _resolve_position(rating, prev_position, weights)
        turnover = abs(position - prev_position)
        if prev_close is None:
            nav *= 1 - friction * turnover
        else:
            day_return = (closes[d] - prev_close) / prev_close
            nav = nav * (1 + position * day_return) * (1 - friction * turnover)
        curve.append({"date": d, "nav": nav, "position": position, "rating": rating})
        prev_position = position
        prev_close = closes[d]

    total_return = (nav - capital) / capital
    return {
        "curve": curve,
        "final_nav": nav,
        "total_return": total_return,
        "missing_days": missing_days,
        "capital": capital,
        "params": p,
    }


def nav_replay(
    conn: sqlite3.Connection,
    month: str,
    asset: str = "BTC",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """月度虚拟账户净值回放(见模块 docstring 第 3 段口径)。"""
    closes = _fetch_close_series(conn, asset)
    ratings = dict(_fetch_ratings(conn, asset, month))
    month_dates = sorted(d for d in closes if d.startswith(f"{month}-"))
    return replay_dates(closes, ratings, month_dates, params)


def _fmt_money(value: float) -> str:
    return f"{value:,.0f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def render_report(
    conn: sqlite3.Connection,
    month: str,
    asset: str = "BTC",
    params: dict[str, Any] | None = None,
) -> str:
    """渲染完整可读文本报表(推送/终端两用)。"""
    p = dict(params) if params is not None else REPORT_PARAMS
    stats = rating_stats(conn, month, asset=asset, horizon_days=p["hit_horizon_days"])
    candidates = candidate_group_report(conn)
    nav = nav_replay(conn, month, asset=asset, params=p)

    lines = [f"===== {asset} 月度成绩单 {month} =====", ""]

    lines.append(f"[1] 评级统计({p['hit_horizon_days']} 日持有,close 序列自算)")
    if stats["overall"]["count"] == 0:
        lines.append("  本月无可统计的评级(候选评级为空,或收盘数据不足)。")
    else:
        o = stats["overall"]
        lines.append(
            f"  整体: n={o['count']}  命中率={_fmt_pct(o['hit_rate'])}  "
            f"平均现货收益={_fmt_pct(o['avg_market_return'])}  平均alpha={_fmt_pct(o['avg_alpha'])}"
        )
        for rating in _RATING_ORDER:
            r = stats["per_rating"][rating]
            if r["count"] == 0:
                continue
            lines.append(
                f"  - {rating}: n={r['count']}  命中率={_fmt_pct(r['hit_rate'])}  "
                f"平均现货收益={_fmt_pct(r['avg_market_return'])}  平均alpha={_fmt_pct(r['avg_alpha'])}"
            )
    if stats["pending"]:
        lines.append(f"  (pending, t+{p['hit_horizon_days']} 尚无数据的尾部条目: {stats['pending']} 条,未计入)")
    if stats["no_close"]:
        lines.append(f"  (评级日无收盘数据,跳过: {stats['no_close']} 条)")
    lines.append("")

    lines.append("[2] 候选分组对比(accept vs vetoed/observed,账本全量口径,非月度切片)")
    if not candidates or all(g["count"] == 0 for g in candidates):
        lines.append("  暂无已结算候选。")
    else:
        for g in candidates:
            lines.append(
                f"  - {g['group']}: n={g['count']}  平均策略收益={_fmt_pct(g['avg_strategy_return'])}  "
                f"命中率={_fmt_pct(g['hit_rate'])}"
            )
    lines.append("")

    lines.append(
        f"[3] 虚拟账户净值回放(本金 {_fmt_money(nav['capital'])},机械仓位+复利,"
        f"固定摩擦假设 {p['friction_per_rebalance'] * 100:.2f}%/次换仓)"
    )
    if not nav["curve"]:
        lines.append("  本月无收盘数据,无法回放。")
    else:
        lines.append(
            f"  期末净值={_fmt_money(nav['final_nav'])}  总收益={_fmt_pct(nav['total_return'])}  "
            f"缺日数={nav['missing_days']}"
        )
    lines.append("")
    lines.append(
        "口径注记: 以上为无摩擦仿真近似(报表层固定假设摩擦成本 + 简化仓位规则),"
        "非 v3 模拟盘/实盘回测,仅供月度自查参考。"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="btc_agent.report",
        description="BTC agent v2: 月度成绩单(评级统计/候选对比/净值回放,只读 ledger,零网络)",
    )
    parser.add_argument("--month", required=True, help="统计月份 YYYY-MM")
    parser.add_argument("--asset", default="BTC", help="资产符号(默认 BTC)")
    parser.add_argument("--db-path", default=None, help="ledger.sqlite3 路径(默认按 results_dir 推导)")
    parser.add_argument("--results-dir", default=None, help="results_dir(用于推导默认 db 路径)")
    parser.add_argument(
        "--capital", type=float, default=None, help="虚拟账户本金(默认 REPORT_PARAMS['capital'])"
    )
    args = parser.parse_args(argv)

    try:
        _validate_month(args.month)
    except ValueError as exc:
        parser.exit(2, f"错误: {exc}\n")

    from btc_agent.ledger import connect, default_db_path

    db_path = args.db_path or default_db_path(args.results_dir)
    conn = connect(db_path)

    params = dict(REPORT_PARAMS)
    if args.capital is not None:
        params["capital"] = args.capital

    print(render_report(conn, args.month, asset=args.asset, params=params))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
