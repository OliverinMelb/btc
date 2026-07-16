"""BTC agent v0 运行入口。

`python -m btc_agent.run --asset BTC --date 2026-07-15`

流程:构造 market-only crypto 图 → propagate(记忆日志落 rating+reasoning) →
机械规则算交易价位 → 汇成一条结构化 JSON 记录写盘。

**LLM 只出方向评级+理由;交易价位一律由 `trade_levels` 机械算(不信 LLM 数字)。**
真实运行需环境变量 `DEEPSEEK_API_KEY`;离线单测通过注入 graph + mock ccxt 覆盖。
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from btc_agent.agents.utils.rating import extract_rating
from btc_agent.default_config import DEFAULT_CONFIG
from btc_agent.evidence import build_evidence_snapshot
from btc_agent.trade_levels import compute_trade_levels, rating_to_direction


def build_structured_record(
    asset: str,
    trade_date: str,
    final_trade_decision: str,
    ohlcv,
    generated_at: str | None = None,
) -> dict:
    """纯函数:把 LLM 决策文本 + OHLCV 组装成结构化记录。

    评级由 `parse_rating` 从决策文本抽取;方向性交易价位由 `compute_trade_levels`
    **纯机械**算出——与决策文本的具体措辞无关(只有 rating 决定 long/short/flat)。
    """
    extracted_rating = extract_rating(final_trade_decision)
    rating = extracted_rating or "Hold"
    direction = rating_to_direction(rating)
    levels = compute_trade_levels(ohlcv, direction)
    return {
        "asset": asset,
        "trade_date": trade_date,
        "generated_at_utc": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rating": rating,
        "rating_source": "explicit" if extracted_rating else "fallback_hold_unparseable",
        "direction": direction,
        "reasoning": final_trade_decision,
        "levels": {
            "entry": levels["entry"],
            "stop": levels["stop"],
            "target": levels["target"],
            "atr": levels["atr"],
        },
        "price_source": "mechanical (ATR-based), not LLM",
    }


def write_record(record: dict, results_dir: str) -> Path:
    """把结构化记录写成 JSON 文件,返回路径。"""
    out_dir = Path(results_dir) / "records"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{record['asset']}_{record['trade_date']}.json"
    path = out_dir / fname
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def run(
    asset: str = "BTC",
    trade_date: str | None = None,
    config: dict | None = None,
    graph=None,
    snapshot=None,
) -> dict:
    """跑一次 v0 研判并落一条结构化记录,返回该记录。

    ``graph`` 可注入(测试用);为 None 时按 config 构造 market-only crypto 图。
    ``snapshot`` 可注入一份已冻结的 ``EvidenceSnapshot``(测试用,或与其它路径共用
    同一份取数结果);为 None 时按 ``asset``/``trade_date`` 自建一份。机械交易价位
    离不开真实 OHLCV,快照取数失败时原样重新抛出(不像仪表盘那样降级)。
    """
    cfg = dict(config or DEFAULT_CONFIG)
    trade_date = trade_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if graph is None:
        # 延迟 import:构造真图会初始化 LLM 客户端,测试路径注入 graph 绕过。
        from btc_agent.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph(selected_analysts=["market"], config=cfg)

    # propagate 返回 (final_state, processed_signal);记忆日志的 pending 记录已在
    # propagate 内部由 store_decision 写好(rating+reasoning)。
    final_state, _signal = graph.propagate(asset, trade_date, asset_type="crypto")
    final_trade_decision = final_state["final_trade_decision"]

    if snapshot is None:
        snapshot = build_evidence_snapshot(asset, trade_date)
    if snapshot.ohlcv is None:
        reason = snapshot.health.get("ohlcv", "unknown")
        raise RuntimeError(f"evidence snapshot has no OHLCV, cannot compute trade levels: {reason}")

    ohlcv = snapshot.ohlcv
    record = build_structured_record(asset, trade_date, final_trade_decision, ohlcv)
    path = write_record(record, cfg["results_dir"])
    record["_record_path"] = str(path)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="btc_agent.run",
        description="BTC agent v0: 单资产日度研判 → 结构化记录(机械价位)",
    )
    parser.add_argument("--asset", default="BTC", help="资产符号(默认 BTC)")
    parser.add_argument(
        "--date",
        default=None,
        help="UTC 交易日 yyyy-mm-dd(默认今日 UTC)",
    )
    args = parser.parse_args(argv)

    if not os.environ.get("DEEPSEEK_API_KEY"):
        parser.exit(
            2,
            "错误: 未设置 DEEPSEEK_API_KEY 环境变量(真实运行需要);"
            "离线测试请走 btc_agent.run.run(graph=<mock>)。\n",
        )

    record = run(asset=args.asset, trade_date=args.date)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
