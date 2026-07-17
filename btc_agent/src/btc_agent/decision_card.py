"""每日 BTC 决策卡渲染(BTC agent v2 ST4)。

纯函数模块:输入证据快照 + 环境识别结果 + (可选)研判图评级/理由 + 机械关注位 +
候选段文本,输出一份可直接推送的结构化文本卡。**卡片里的一切数字只能来自机械计算
(``regime_result``/``levels``),绝不来自 LLM 措辞**——``reasoning`` 只作为纯文本
理由展示,不从中解析或复制任何数字到价位类字段。

白卷语义:``regime_result.blank_sheet`` 为真(chaos/insufficient_data)时,评级段
直接写"白卷: <原因>",不展示 rating/reasoning、不展示关注位(机械价位本身也没有
意义的方向性 ATR 位)。

消息约束(Telegram 4096 字符上限):首行是可作邮件主题的短句;超长时按 section
截断——保留环境/证据完整度/评级(或白卷)/候选/关注位,只裁"机械观察"与"理由"两个
可变长度最大的自由文本段。
"""

from __future__ import annotations

from typing import Any

# 五分类 → 中文名(卡片展示用,不改变 regime.py 的内部标识符)。
_REGIME_CN = {
    "trend_up": "趋势上涨",
    "trend_down": "趋势下跌",
    "range": "震荡",
    "chaos": "高波动",
    "insufficient_data": "数据不足",
}

# 白卷原因的展示文案。
_BLANK_SHEET_REASON = {
    "chaos": "近端波动率处于历史高位,方向性判断不可靠",
    "insufficient_data": "行情数据不足或取数失败,无法机械识别环境",
}

# 空仓/持仓建议的机械纪律表——按环境查表,不涉及任何 LLM 判断。
_POSITION_ADVICE = {
    "trend_up": "空仓建议: 可考虑顺势轻仓试探; 持仓建议: 沿均线持有, 跌破关注位再评估。",
    "trend_down": "空仓建议: 保持观望, 不逆势抄底; 持仓建议: 若仍持多单, 关注位失守应减仓。",
    "range": "空仓建议: 等待区间边界信号, 不追涨杀跌; 持仓建议: 区间内高抛低吸, 严守失效位。",
    "chaos": "空仓建议: 观望, 不新开仓; 持仓建议: 降低仓位或对冲, 避免在高波动中扩大暴露。",
    "insufficient_data": "空仓建议: 交白卷, 不开新仓; 持仓建议: 维持现状, 待数据恢复后再评估。",
}

# Telegram 单条消息长度上限。
MAX_MESSAGE_LENGTH = 4096
_TRUNCATION_NOTE = "\n[... 理由/观察段已截断,余下内容因长度限制未展示 ...]"


def _evidence_completeness(snapshot: Any) -> tuple[str, list[str]]:
    """从 ``snapshot.health`` 汇总证据完整度:"完整" 或 "数据不完整"(附缺失源)。"""
    health = getattr(snapshot, "health", None) or {}
    missing = [src for src, status in health.items() if status != "ok"]
    if not missing:
        return "完整", missing
    return "数据不完整", missing


def _mechanical_observations(regime_result: Any, snapshot: Any) -> list[str]:
    """机械观察择要:regime 的 observations 关键字段 + 快照里的 F&G/资金费率信号。"""
    lines: list[str] = []
    obs = getattr(regime_result, "observations", None) or {}
    if "last_close" in obs:
        lines.append(f"- 最新收盘: {obs['last_close']}")
    if "sma" in obs:
        lines.append(f"- SMA: {obs['sma']} (斜率 {obs.get('sma_slope')})")
    if "atr_over_close" in obs:
        lines.append(
            f"- 波动率(ATR/Close): {obs['atr_over_close']} "
            f"(chaos 阈值 {obs.get('atr_over_close_chaos_threshold')})"
        )
    if "bars_available" in obs:
        lines.append(f"- 可用K线数: {obs['bars_available']}")

    fear_greed = getattr(snapshot, "fear_greed", None)
    if fear_greed:
        lines.append(f"- 恐慌贪婪指数: {fear_greed}")
    derivatives = getattr(snapshot, "derivatives", None)
    if derivatives:
        lines.append(f"- 资金费率/OI: {derivatives}")

    if not lines:
        lines.append("- (无可用机械观察)")
    return lines


def _levels_lines(levels: dict | None) -> list[str]:
    """关注位段:levels 是 ``compute_trade_levels`` 的输出(entry/stop/target/atr)。

    只展示传入的机械数值,不做任何解析或推断——这里没有别的数字来源。
    """
    if not levels:
        return ["- (无关注位: 未计算机械价位)"]
    lines = [f"- 现价参考: {levels.get('entry')}"]
    if levels.get("stop") is not None:
        lines.append(f"- 下沿观察位(stop): {levels.get('stop')}")
    if levels.get("target") is not None:
        lines.append(f"- 突破确认位(target): {levels.get('target')}")
    if levels.get("atr") is not None:
        lines.append(f"- ATR: {levels.get('atr')}")
    return lines


def _candidate_field(candidates: Any, key: str, default: Any = None) -> Any:
    """兼容 dict 或带属性对象两种 candidates 载体形态的字段读取。"""
    if isinstance(candidates, dict):
        return candidates.get(key, default)
    return getattr(candidates, key, default)


def _candidate_section(candidates: Any) -> str:
    """候选段渲染(ST5 加挂):非 None 时展示 候选类型/裁决/四个机械字段/有效期/理由。

    候选价位全部来自机械计算,渲染层只做取值,不做任何解析或推断。
    """
    if not candidates:
        return "本次操作候选: 无"

    lines = [
        "本次操作候选:",
        f"- 候选类型: {_candidate_field(candidates, 'candidate_type', '(未知)')}",
        f"- 裁决: {_candidate_field(candidates, 'verdict', '(未裁决)')}",
        f"- 机械入场参考: {_candidate_field(candidates, 'entry_ref')}",
        f"- 机械失效位置: {_candidate_field(candidates, 'invalidation')}",
        f"- 机械目标区域: {_candidate_field(candidates, 'target_zone')}",
        f"- 候选有效期: {_candidate_field(candidates, 'expires_utc')}",
    ]
    reason = _candidate_field(candidates, "reason")
    if reason:
        lines.append(f"- 理由: {reason}")
    return "\n".join(lines)


def _subject_line(asset: str, curr_date: str | None, regime_cn: str, blank_sheet: bool) -> str:
    """首行短句,可直接作邮件主题。"""
    date_part = curr_date or "今日"
    tag = "白卷" if blank_sheet else regime_cn
    return f"{asset} 每日决策卡 {date_part} [{tag}]"


def render_decision_card(
    snapshot: Any,
    regime_result: Any,
    rating: str | None,
    reasoning: str | None,
    levels: dict | None,
    candidates: Any = None,
) -> str:
    """渲染一张每日决策卡(纯函数,零网络零 LLM 调用)。

    ``rating``/``reasoning`` 为 None 或 ``regime_result.blank_sheet`` 为真时,
    评级段展示白卷及原因,不展示 rating 文本本身(白卷路径调用方本就不应传入 rating)。
    ``candidates`` 为 None 时展示"无"(ST5 加挂候选段)。
    """
    asset = getattr(snapshot, "asset", "BTC")
    curr_date = getattr(snapshot, "curr_date", None)
    regime = getattr(regime_result, "regime", "insufficient_data")
    blank_sheet = bool(getattr(regime_result, "blank_sheet", True))
    regime_cn = _REGIME_CN.get(regime, regime)

    completeness, missing = _evidence_completeness(snapshot)

    subject = _subject_line(asset, curr_date, regime_cn, blank_sheet)

    sections: list[tuple[str, str]] = []

    env_lines = [f"BTC市场环境: {regime_cn}", f"证据完整度: {completeness}"]
    if missing:
        env_lines.append(f"缺失源: {', '.join(sorted(missing))}")
    sections.append(("env", "\n".join(env_lines)))

    obs_lines = ["机械观察:"] + _mechanical_observations(regime_result, snapshot)
    sections.append(("observations", "\n".join(obs_lines)))

    if blank_sheet:
        reason = _BLANK_SHEET_REASON.get(regime, "环境不明确")
        rating_lines = [f"TradingAgents评级: 白卷: {reason}"]
    else:
        rating_lines = [f"TradingAgents评级: {rating or '(未评级)'}"]
        if reasoning:
            rating_lines.append(f"理由: {reasoning}")
    sections.append(("rating", "\n".join(rating_lines)))

    sections.append(("candidates", _candidate_section(candidates)))

    advice = _POSITION_ADVICE.get(regime, _POSITION_ADVICE["insufficient_data"])
    sections.append(("advice", advice))

    if blank_sheet:
        levels_lines = ["关注位: 白卷路径不给关注位"]
    else:
        levels_lines = ["关注位:"] + _levels_lines(levels)
    sections.append(("levels", "\n".join(levels_lines)))

    body = "\n\n".join(text for _key, text in sections)
    message = f"{subject}\n\n{body}"

    if len(message) <= MAX_MESSAGE_LENGTH:
        return message

    return _truncate_by_section(subject, sections)


def _truncate_by_section(subject: str, sections: list[tuple[str, str]]) -> str:
    """超长时按 section 截断:优先保留 env/rating/candidates/levels,裁 observations/理由段。

    策略:先把 observations 段整体替换为省略提示;若仍超长,再裁 rating 段里的
    "理由: ..." 长文(保留 "TradingAgents评级: ..." 首行)。首行主题永远保留。
    """
    trimmed: list[tuple[str, str]] = []
    for key, text in sections:
        if key == "observations":
            trimmed.append((key, "机械观察: (因长度限制已截断)"))
        else:
            trimmed.append((key, text))

    body = "\n\n".join(t for _k, t in trimmed)
    message = f"{subject}\n\n{body}"
    if len(message) <= MAX_MESSAGE_LENGTH:
        return message

    # 仍超长:裁 rating 段的理由长文,只留评级行(或白卷行)。
    final_sections: list[tuple[str, str]] = []
    for key, text in trimmed:
        if key == "rating":
            first_line = text.splitlines()[0]
            final_sections.append((key, first_line))
        else:
            final_sections.append((key, text))

    body = "\n\n".join(t for _k, t in final_sections)
    message = f"{subject}\n\n{body}{_TRUNCATION_NOTE}"

    if len(message) <= MAX_MESSAGE_LENGTH:
        return message

    # 极端情况(env/candidates/levels 本身就超长):硬截断到上限,保留首行主题。
    keep_len = MAX_MESSAGE_LENGTH - len(subject) - 1
    truncated_body = message[len(subject) + 1 :][: max(keep_len, 0)]
    return f"{subject}\n{truncated_body}"[:MAX_MESSAGE_LENGTH]
