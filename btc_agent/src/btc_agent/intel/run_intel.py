"""情报层运行入口(BTC agent v1)。

``python -m btc_agent.intel --asset BTC --date 2026-07-15``

流程:装配盘面仪表盘 → 机械规则判告警 → 渲染消息 → 推送到配置的 sink。
纯资讯产品,不做决策、不下单。定时器(cron / 计划任务)重复调用本入口即"稳定推送"。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from btc_agent.dataflows.config import get_config, set_config
from btc_agent.default_config import DEFAULT_CONFIG
from btc_agent.intel.dashboard import build_dashboard
from btc_agent.intel.push import build_sinks_from_config, dispatch, render_message
from btc_agent.intel.rules import evaluate


def run_intel(
    asset: str = "BTC",
    curr_date: str | None = None,
    config: dict | None = None,
    alerts_only: bool = False,
) -> dict:
    """跑一次情报扫描,返回 ``{dashboard, alerts, message, delivered}``。

    ``config`` 可注入(测试用);为 None 时用 DEFAULT_CONFIG。推送 sink、阈值都从 config 读。

    ``alerts_only=True`` 供高频定时任务(如每 30 分钟)使用:无告警且无取数错误时
    **跳过全部 sink 推送**(返回 dict 里 ``skipped_no_alerts=True``,送达按完整计),
    避免"无异常"消息刷屏;有告警或数据不完整时照常推送——白卷语义不受影响,
    取数失败仍然会推出去,绝不静默。
    """
    cfg = dict(config or DEFAULT_CONFIG)
    set_config(cfg)
    curr_date = curr_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    dashboard = build_dashboard(asset, curr_date)
    alerts = evaluate(dashboard, get_config().get("intel_thresholds"))
    message = render_message(asset, curr_date, alerts, dashboard.get("errors"))
    requested_sinks = list(dict.fromkeys(get_config().get("intel_push_sinks") or ["stdout"]))

    skipped_no_alerts = alerts_only and not alerts and not dashboard.get("errors")
    if skipped_no_alerts:
        sinks = []
        delivered = len(requested_sinks)  # 主动跳过按送达完整计,退出码保持 0
    else:
        sinks = build_sinks_from_config(get_config())
        delivered = dispatch(message, sinks)
    active_sinks = [getattr(sink, "name", type(sink).__name__) for sink in sinks]
    delivery_complete = delivered == len(requested_sinks)

    return {
        "dashboard": dashboard,
        "alerts": alerts,
        "message": message,
        "delivered": delivered,
        "requested_sinks": requested_sinks,
        "active_sinks": active_sinks,
        "delivery_complete": delivery_complete,
        "skipped_no_alerts": skipped_no_alerts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="btc_agent.intel",
        description="BTC agent v1 情报层:盘面仪表盘 → 规则告警 → 推送(不决策/不下单)",
    )
    parser.add_argument("--asset", default="BTC", help="资产符号(默认 BTC)")
    parser.add_argument("--date", default=None, help="UTC 日期 yyyy-mm-dd(默认今日 UTC)")
    parser.add_argument(
        "--alerts-only",
        action="store_true",
        help="无告警且无取数错误时跳过推送(高频定时任务防刷屏);告警/数据异常照常推",
    )
    args = parser.parse_args(argv)

    result = run_intel(asset=args.asset, curr_date=args.date, alerts_only=args.alerts_only)
    if result.get("skipped_no_alerts"):
        print("[intel] 无告警且数据健康,按 --alerts-only 跳过推送。")
    # 消息已由 stdout sink 打印(若启用);这里补一行送达统计到 stderr 友好提示。
    errors = result["dashboard"].get("errors")
    if errors:
        print(f"\n[intel] 部分信号取数失败(已降级): {list(errors.keys())}")
    print(f"[intel] 触发告警 {len(result['alerts'])} 条,送达 {result['delivered']} 个 sink。")
    if not result["delivery_complete"]:
        print(
            f"[intel] 推送未完整送达: requested={result['requested_sinks']}, "
            f"active={result['active_sinks']}"
        )
    # 无任何 sink 成功时让计划任务看到失败，而不是静默返回 0。
    return 0 if result["delivery_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
