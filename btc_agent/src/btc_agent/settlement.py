"""事件驱动结算器(BTC agent v2 ST6)。

**硬约束(G2)**:本模块新写事件驱动逻辑,只复用 ``settlement_math`` 的口径
契约(纯函数,零依赖),**不 import ``graph`` 包**。OHLCV 通过 ``ohlcv_provider``
注入(生产路径默认包一层 ``ccxt_vendor._ohlcv_dataframe``;测试永远注入构造好
的 DataFrame,零网络)。

G6 候选结算三口径(定死,任一变更即新策略版本——见 ``ledger.SETTLEMENT_PARAM_KEYS``):
(a) 触及判定——日内触及即算:``day.Low <= 失效位`` → 失效,
    ``day.High >= 目标下沿`` → 到达目标;
(b) 触发日按被触及的价位本身结算(失效按失效位价、目标按目标下沿价),非当日收盘;
(c) 同一日线双触 → 保守 tie-break:**失效先触发**;
(d) 有效期到期未触任何位 → 按到期日收盘结算。

**反事实归因**:候选的结算方向恒定为 ``"long"``(候选类型 ``range_lower_long``
的结构性方向),与 LLM 裁决(accept/observe/veto)无关——被否决的候选照常按同一
口径结算,``counterfactual_report`` 按裁决分组对比,量化"如果都按 accept 执行"
与"实际被接受的"两组结果差异,这是 LLM 增量价值的证据来源。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from btc_agent.settlement_math import spot_settle

OhlcvProvider = Callable[[str, str, str], pd.DataFrame]


def _default_ohlcv_provider(asset: str, start_date: str, end_date: str) -> pd.DataFrame:
    """生产默认 provider:包一层 ``ccxt_vendor._ohlcv_dataframe``(有 as-of 前视防护)。"""
    from btc_agent.dataflows.ccxt_vendor import _ohlcv_dataframe

    df = _ohlcv_dataframe(asset, curr_date=end_date)
    return df[df["Date"] >= pd.to_datetime(start_date)]


def _next_day(date_str: str) -> str:
    return (
        datetime.strptime(date_str, "%Y-%m-%d") + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")


def _scan_touches(
    ohlcv: pd.DataFrame, invalidation: float, target_low: float
) -> tuple[str | None, float | None, str | None]:
    """按 G6(a)(c) 逐日扫描:返回 ``(outcome, settle_price, settled_date)`` 或全 None。"""
    df = ohlcv.sort_values("Date")
    for _, day in df.iterrows():
        low = float(day["Low"])
        high = float(day["High"])
        date_str = pd.Timestamp(day["Date"]).strftime("%Y-%m-%d")
        hit_invalid = low <= invalidation
        hit_target = high >= target_low
        if hit_invalid:
            # G6(c): 同日双触 → 保守 tie-break,失效先触发(即便 hit_target 也一并成立)。
            return "invalidated", float(invalidation), date_str
        if hit_target:
            return "target", float(target_low), date_str
    return None, None, None


def _row_on_or_before(ohlcv: pd.DataFrame, date_str: str) -> pd.Series | None:
    df = ohlcv.sort_values("Date")
    df = df[pd.to_datetime(df["Date"]) <= pd.to_datetime(date_str)]
    if df.empty:
        return None
    return df.iloc[-1]


def settle_due_candidates(
    conn: sqlite3.Connection,
    ohlcv_provider: OhlcvProvider | None = None,
    as_of_utc: str | None = None,
) -> list[dict[str, Any]]:
    """扫描全部未结算候选,按 G6 四口径逐一结算(veto/observe 候选同口径照常结算)。

    每个候选从「创建日的次日」起算(候选创建当日的 entry_ref 本就取自该日收盘,
    用同一日的 High/Low 判定触及会构成前视;次日起才是"之后行情是否触位")。
    """
    if ohlcv_provider is None:
        ohlcv_provider = _default_ohlcv_provider
    as_of_utc = as_of_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    as_of_date = as_of_utc[:10]

    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT c.id, c.entry_ref, c.invalidation, c.target_zone_json, c.expires_utc,
               s.asset, s.trade_date, s.frozen_at_utc, v.verdict
        FROM candidates c
        JOIN snapshots s ON s.snapshot_id = c.snapshot_id
        LEFT JOIN verdicts v ON v.candidate_id = c.id
        LEFT JOIN settlements st ON st.candidate_id = c.id
        WHERE st.id IS NULL
        """
    ).fetchall()

    settled: list[dict[str, Any]] = []
    for row in rows:
        (
            candidate_id,
            entry_ref,
            invalidation,
            target_zone_json,
            expires_utc,
            asset,
            trade_date,
            frozen_at_utc,
            verdict,
        ) = row
        target_zone = json.loads(target_zone_json)
        target_low = float(target_zone[0])

        creation_date = trade_date or (frozen_at_utc[:10] if frozen_at_utc else None)
        if not creation_date:
            continue  # 无法确定起算日,跳过(不应发生,防御性处理)。
        start_date = _next_day(creation_date)
        expiry_date = expires_utc[:10]
        window_end = min(expiry_date, as_of_date)

        if window_end < start_date:
            continue  # 创建日次日尚未到来,本轮不结算(避免前视 / 避免不必要取数)。

        ohlcv = ohlcv_provider(asset, start_date, window_end)
        if ohlcv is None or len(ohlcv) == 0:
            continue  # 数据尚不可用,下一轮再试。

        outcome, settle_price, settled_date = _scan_touches(ohlcv, invalidation, target_low)
        if outcome is None:
            if as_of_date < expiry_date:
                continue  # 未到期且未触位:本轮不结算。
            expiry_row = _row_on_or_before(ohlcv, expiry_date)
            if expiry_row is None:
                continue  # 到期日日线尚不可用,下一轮再试。
            outcome = "expired"
            settle_price = float(expiry_row["Close"])
            settled_date = expiry_date

        market_return = (settle_price - entry_ref) / entry_ref
        # 结算方向恒为 "long"(候选结构性方向),与裁决无关——veto/observe 同口径
        # 照常结算,反事实归因才有意义(counterfactual_report 按裁决分组对比)。
        result = spot_settle("long", market_return=market_return, bench_return=market_return)

        detail = {"outcome": outcome, "settled_date": settled_date, "verdict": verdict}
        direction_hit = result["direction_hit"]
        direction_hit_db = None if direction_hit is None else (1 if direction_hit else 0)

        cur.execute(
            "INSERT INTO settlements (candidate_id, settled_at_utc, outcome, settle_price, "
            "market_return, strategy_return, alpha, direction_hit, settlement_basis, "
            "detail_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                candidate_id,
                as_of_utc,
                outcome,
                settle_price,
                market_return,
                result["strategy_return"],
                result["alpha"],
                direction_hit_db,
                result["settlement_basis"],
                json.dumps(detail),
            ),
        )
        settled.append(
            {
                "candidate_id": candidate_id,
                "outcome": outcome,
                "settle_price": settle_price,
                "market_return": market_return,
                **result,
            }
        )

    conn.commit()
    return settled


def counterfactual_report(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """反事实归因查询:accepted vs vetoed/observed 结算对比(数量/均值收益/命中率)。

    两组的结算价位/结算方式完全同口径(见 ``settle_due_candidates``);唯一差异是
    裁决标签——这正是量化"LLM 裁决增量价值"的证据:若 accepted 组均值/命中率显著
    优于 vetoed/observed 组,说明裁决点确有过滤价值。
    """
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT v.verdict, st.strategy_return, st.direction_hit
        FROM settlements st
        JOIN candidates c ON c.id = st.candidate_id
        LEFT JOIN verdicts v ON v.candidate_id = c.id
        """
    ).fetchall()

    groups: dict[str, list[tuple[float, int | None]]] = {
        "accepted": [],
        "vetoed_or_observed": [],
    }
    for verdict, strategy_return, direction_hit in rows:
        key = "accepted" if verdict == "accept" else "vetoed_or_observed"
        groups[key].append((strategy_return, direction_hit))

    report: list[dict[str, Any]] = []
    for group, items in groups.items():
        count = len(items)
        avg_return = (sum(r for r, _ in items) / count) if count else None
        hits = [h for _, h in items if h is not None]
        hit_rate = (sum(hits) / len(hits)) if hits else None
        report.append(
            {
                "group": group,
                "count": count,
                "avg_strategy_return": avg_return,
                "hit_rate": hit_rate,
            }
        )
    return report
