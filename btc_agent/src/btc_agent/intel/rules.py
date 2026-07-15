"""盯盘规则引擎(BTC agent v1 情报层)。

**纯函数、无网络、无 LLM**——输入一份仪表盘快照 dict + 阈值 dict,输出 ``Alert`` 列表。
这是"机械规则出信号"的情报层版本:所有告警都由确定性阈值判定,便于离线单测与复现。

规则覆盖(缺失字段自动跳过,不误报):
- Fear & Greed 极值(极度恐惧/极度贪婪,常为反向信号)
- 资金费率极值(多空拥挤,潜在挤压)
- RSI 超买/超卖
- 日内价格大幅波动
"""

from __future__ import annotations

from dataclasses import dataclass

# 告警级别:info < warning < critical。用于推送时排序/过滤。
LEVELS = ("info", "warning", "critical")


@dataclass(frozen=True)
class Alert:
    """一条确定性告警。``code`` 机器可读,``message`` 人读,``value`` 触发值。"""

    level: str
    code: str
    message: str
    value: float | None = None


# 阈值默认值。可由 config["intel_thresholds"] 覆盖(见 default_config)。
DEFAULT_THRESHOLDS = {
    "fng_extreme_fear": 20,     # F&G <= 此值:极度恐惧
    "fng_extreme_greed": 80,    # F&G >= 此值:极度贪婪
    "funding_abs_warn": 0.0005,  # |资金费率| >= 0.05%/期:偏拥挤(warning)
    "funding_abs_crit": 0.001,   # |资金费率| >= 0.10%/期:严重拥挤(critical)
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "price_move_warn_pct": 5.0,   # 日内 |涨跌| >= 5%:warning
    "price_move_crit_pct": 10.0,  # 日内 |涨跌| >= 10%:critical
}


def _merge_thresholds(overrides: dict | None) -> dict:
    merged = dict(DEFAULT_THRESHOLDS)
    if overrides:
        merged.update({k: v for k, v in overrides.items() if v is not None})
    return merged


def _rule_fear_greed(fng: dict | None, t: dict) -> list[Alert]:
    if not fng or fng.get("value") is None:
        return []
    v = int(fng["value"])
    cls = fng.get("classification", "")
    if v <= t["fng_extreme_fear"]:
        return [Alert("warning", "fng_extreme_fear",
                      f"Fear & Greed {v}/100 ({cls}) — 极度恐惧,常为反向偏底信号", v)]
    if v >= t["fng_extreme_greed"]:
        return [Alert("warning", "fng_extreme_greed",
                      f"Fear & Greed {v}/100 ({cls}) — 极度贪婪,常为反向偏顶信号", v)]
    return []


def _rule_funding(deriv: dict | None, t: dict) -> list[Alert]:
    if not deriv or deriv.get("funding_rate") is None:
        return []
    rate = float(deriv["funding_rate"])
    pct = rate * 100
    bias = "多头拥挤" if rate > 0 else "空头拥挤"
    if abs(rate) >= t["funding_abs_crit"]:
        return [Alert("critical", "funding_extreme",
                      f"资金费率 {pct:.4f}% — {bias}(极端),挤压风险高", rate)]
    if abs(rate) >= t["funding_abs_warn"]:
        return [Alert("warning", "funding_elevated",
                      f"资金费率 {pct:.4f}% — {bias}(偏高)", rate)]
    return []


def _rule_rsi(rsi: float | None, t: dict) -> list[Alert]:
    if rsi is None:
        return []
    rsi = float(rsi)
    if rsi >= t["rsi_overbought"]:
        return [Alert("info", "rsi_overbought", f"RSI {rsi:.1f} — 超买", rsi)]
    if rsi <= t["rsi_oversold"]:
        return [Alert("info", "rsi_oversold", f"RSI {rsi:.1f} — 超卖", rsi)]
    return []


def _rule_price_move(move_pct: float | None, t: dict) -> list[Alert]:
    if move_pct is None:
        return []
    move_pct = float(move_pct)
    direction = "上涨" if move_pct >= 0 else "下跌"
    if abs(move_pct) >= t["price_move_crit_pct"]:
        return [Alert("critical", "price_move_large",
                      f"日内{direction} {abs(move_pct):.2f}% — 剧烈波动", move_pct)]
    if abs(move_pct) >= t["price_move_warn_pct"]:
        return [Alert("warning", "price_move",
                      f"日内{direction} {abs(move_pct):.2f}% — 显著波动", move_pct)]
    return []


def evaluate(dashboard: dict, thresholds: dict | None = None) -> list[Alert]:
    """对一份仪表盘快照跑全部规则,返回按级别降序排列的 ``Alert`` 列表。

    ``dashboard`` 期望键(任一缺失/为 None 则对应规则跳过):
    ``fear_greed``(dict), ``derivatives``(dict), ``rsi``(float), ``price_move_pct``(float)。
    """
    t = _merge_thresholds(thresholds)
    alerts: list[Alert] = []
    alerts += _rule_fear_greed(dashboard.get("fear_greed"), t)
    alerts += _rule_funding(dashboard.get("derivatives"), t)
    alerts += _rule_rsi(dashboard.get("rsi"), t)
    alerts += _rule_price_move(dashboard.get("price_move_pct"), t)
    alerts.sort(key=lambda a: LEVELS.index(a.level), reverse=True)
    return alerts
