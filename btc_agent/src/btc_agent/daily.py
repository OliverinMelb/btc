"""BTC agent v2 每日决策卡编排入口(ST4)。

``python -m btc_agent.daily --asset BTC --date 2026-07-16``

流程:统一证据快照 → 机械环境识别 → (环境允许时,即非白卷)研判图评级 →
``compute_trade_levels`` 机械关注位 → 渲染决策卡 → 复用 ``intel.push`` 的
sink 推送。白卷路径(chaos/insufficient_data)**不构造/不调用研判图**——直接
渲染白卷卡片。

依赖方向(设计门 G1):daily → {intel.push, graph, evidence, regime}。``intel``
包本身不 import graph;本模块只单向消费 ``intel.push`` 的 sink 协议,不反向被
``intel`` 依赖。

扩展点(留给 ST5/ST6 加挂,本子任务恒为 None 即跳过):
``candidate_provider(snapshot, regime_result) -> Any | None``、
``ledger_recorder(snapshot, regime_result, rating, reasoning, levels, candidates) -> None``。

推送失败/未完整送达 → 非零退出码(语义沿用 v1 情报层 ``run_intel``,代码独立实现,
不改 ``run_intel.py`` 本身)。
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from btc_agent.default_config import DEFAULT_CONFIG
from btc_agent.evidence import build_evidence_snapshot
from btc_agent.intel.push import build_sinks_from_config, dispatch
from btc_agent.regime import detect_regime
from btc_agent.decision_card import render_decision_card
from btc_agent.trade_levels import compute_trade_levels, rating_to_direction
from btc_agent.agents.utils.rating import extract_rating


def run_daily(
    asset: str = "BTC",
    trade_date: str | None = None,
    config: dict | None = None,
    graph=None,
    snapshot=None,
    candidate_provider=None,
    ledger_recorder=None,
) -> dict:
    """跑一次每日决策卡编排,返回
    ``{card, snapshot, regime_result, rating, reasoning, levels, candidates,
    delivered, requested_sinks, active_sinks, delivery_complete}``。

    ``graph``/``snapshot`` 可注入(测试用,或与其它路径共用同一份快照)。
    ``candidate_provider``/``ledger_recorder`` 为 None 时本子任务恒跳过
    (ST5/ST6 加挂点)。
    """
    cfg = dict(config or DEFAULT_CONFIG)
    trade_date = trade_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if snapshot is None:
        snapshot = build_evidence_snapshot(asset, trade_date)

    regime_result = detect_regime(snapshot)

    rating: str | None = None
    reasoning: str | None = None
    levels: dict | None = None

    if not regime_result.blank_sheet:
        if graph is None:
            # 延迟 import:构造真图会初始化 LLM 客户端,测试路径注入 graph 绕过。
            from btc_agent.graph.trading_graph import TradingAgentsGraph

            graph = TradingAgentsGraph(selected_analysts=["market"], config=cfg)

        final_state, _signal = graph.propagate(asset, trade_date, asset_type="crypto")
        reasoning = final_state["final_trade_decision"]
        extracted_rating = extract_rating(reasoning)
        rating = extracted_rating or "Hold"

        if snapshot.ohlcv is None:
            reason = snapshot.health.get("ohlcv", "unknown")
            raise RuntimeError(
                f"evidence snapshot has no OHLCV, cannot compute trade levels: {reason}"
            )
        direction = rating_to_direction(rating)
        levels = compute_trade_levels(snapshot.ohlcv, direction)

    candidates = None
    if candidate_provider is not None:
        candidates = candidate_provider(snapshot, regime_result)

    card = render_decision_card(
        snapshot=snapshot,
        regime_result=regime_result,
        rating=rating,
        reasoning=reasoning,
        levels=levels,
        candidates=candidates,
    )

    if ledger_recorder is not None:
        ledger_recorder(snapshot, regime_result, rating, reasoning, levels, candidates)

    sinks = build_sinks_from_config(cfg)
    delivered = dispatch(card, sinks)
    requested_sinks = list(dict.fromkeys(cfg.get("intel_push_sinks") or ["stdout"]))
    active_sinks = [getattr(sink, "name", type(sink).__name__) for sink in sinks]
    delivery_complete = delivered == len(requested_sinks)

    return {
        "card": card,
        "snapshot": snapshot,
        "regime_result": regime_result,
        "rating": rating,
        "reasoning": reasoning,
        "levels": levels,
        "candidates": candidates,
        "delivered": delivered,
        "requested_sinks": requested_sinks,
        "active_sinks": active_sinks,
        "delivery_complete": delivery_complete,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="btc_agent.daily",
        description="BTC agent v2: 每日决策卡(环境+机械观察+评级/白卷+关注位)→ 推送",
    )
    parser.add_argument("--asset", default="BTC", help="资产符号(默认 BTC)")
    parser.add_argument("--date", default=None, help="UTC 交易日 yyyy-mm-dd(默认今日 UTC)")
    args = parser.parse_args(argv)

    if not os.environ.get("DEEPSEEK_API_KEY"):
        parser.exit(
            2,
            "错误: 未设置 DEEPSEEK_API_KEY 环境变量(真实运行需要,白卷路径也统一校验);"
            "离线测试请走 btc_agent.daily.run_daily(graph=<mock>, snapshot=<mock>)。\n",
        )

    result = run_daily(asset=args.asset, trade_date=args.date)
    print(result["card"])
    if not result["delivery_complete"]:
        print(
            f"[daily] 推送未完整送达: requested={result['requested_sinks']}, "
            f"active={result['active_sinks']}"
        )
    return 0 if result["delivery_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
