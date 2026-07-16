"""波段候选引擎 + LLM 裁决(BTC agent v2 ST5)。

铁律延伸:候选的**全部价位机械计算**(区间高低点 + ATR,与 ``trade_levels``
同源思路),LLM 只在裁决点(accept/observe/veto)出场,且只准输出定性理由——
``CandidateVerdict`` 不含任何数值字段,解析失败/歧义一律降级 ``observe``
(白卷文化的延伸:证据不足不硬给结论)。

一种规则:「震荡下沿做多」(``range_lower_long``)——仅当 ``regime_result.regime
== "range"`` 且 ``blank_sheet`` 为假、且最新价格触及区间下沿带时产出候选;
否则(非 range、数据缺失、未触及)一律返回 ``None``——白卷,不硬凑。

``CANDIDATE_PARAMS`` 是策略版本 hash(设计门 G5)的输入之一,集中所有会改变
候选产出结果的参数,包括 G6 裁定的结算口径静态参数(本模块不消费,ST6 结算器
消费,但 hash 范围要求它们随候选参数一起进版本)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from btc_agent.trade_levels import compute_atr

if TYPE_CHECKING:
    from btc_agent.agents.schemas import CandidateVerdict

logger = logging.getLogger(__name__)

# 集中式候选参数——策略版本 hash 输入之一(设计门 G5)。改动即视为新策略版本。
CANDIDATE_PARAMS: dict[str, Any] = {
    "lookback_bars": 20,  # 区间高低点回看窗口(根 K 线数)
    "atr_period": 14,  # 与 trade_levels 同源的 ATR 窗口
    "lower_band_atr_mult": 0.5,  # 下沿带宽度: range_low + mult*ATR 之内算触及
    "invalidation_atr_mult": 1.0,  # 失效位 = range_low - mult*ATR
    "expiry_days": 5,  # 候选有效期(UTC 自然日数)
    # G6 候选结算三口径(本模块不消费,ST6 结算器消费;随候选参数一起进版本 hash)。
    "touch_basis": "intraday",
    "settle_price": "level",
    "tie_break": "stop_first",
}

_VERDICT_LABELS = ("accept", "observe", "veto")


@dataclass
class Candidate:
    """一次机械候选产出(全部价位字段均为确定性计算,不含任何 LLM 措辞派生数值)。"""

    candidate_type: str
    entry_ref: float
    invalidation: float
    target_zone: tuple[float, float]
    expires_utc: str
    params_used: dict[str, Any] = field(default_factory=dict)
    observations: dict[str, Any] = field(default_factory=dict)


def _expires_utc(curr_date: str | None, frozen_at_utc: str | None, expiry_days: int) -> str:
    """从快照的 as-of 日期起算 N 个 UTC 日后的到期时间戳。"""
    base = curr_date or (frozen_at_utc[:10] if frozen_at_utc else None)
    if base:
        start = datetime.strptime(base, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        start = datetime.now(timezone.utc)
    expires = start + timedelta(days=expiry_days)
    return expires.strftime("%Y-%m-%dT00:00:00Z")


def find_swing_candidate(
    snapshot: Any, regime_result: Any, params: dict[str, Any] | None = None
) -> Candidate | None:
    """从统一证据快照 + 环境识别结果机械产出一个「震荡下沿做多」候选,或 ``None``。

    产出条件(全部满足才产出,否则白卷):``regime_result.regime == "range"``、
    ``regime_result.blank_sheet`` 为假、OHLCV 数据足量、最新价格触及区间下沿带。
    """
    p = dict(params) if params is not None else dict(CANDIDATE_PARAMS)

    if getattr(regime_result, "regime", None) != "range":
        return None
    if bool(getattr(regime_result, "blank_sheet", True)):
        return None

    ohlcv = getattr(snapshot, "ohlcv", None)
    min_bars = max(p["lookback_bars"], p["atr_period"] + 1)
    if ohlcv is None or len(ohlcv) < min_bars:
        return None

    window = ohlcv.tail(p["lookback_bars"])
    range_high = float(window["High"].astype(float).max())
    range_low = float(window["Low"].astype(float).min())

    atr = compute_atr(ohlcv, p["atr_period"])
    lower_band_top = range_low + p["lower_band_atr_mult"] * atr

    last_low = float(ohlcv["Low"].astype(float).iloc[-1])
    last_close = float(ohlcv["Close"].astype(float).iloc[-1])

    touched = last_low <= lower_band_top
    if not touched:
        return None

    entry_ref = round(last_close, 2)
    invalidation = round(range_low - p["invalidation_atr_mult"] * atr, 2)
    mid = (range_low + range_high) / 2
    target_zone = (round(mid, 2), round(range_high, 2))
    expires_utc = _expires_utc(
        getattr(snapshot, "curr_date", None), getattr(snapshot, "frozen_at_utc", None),
        p["expiry_days"],
    )

    observations = {
        "range_high": round(range_high, 2),
        "range_low": round(range_low, 2),
        "lower_band_top": round(lower_band_top, 2),
        "atr": round(atr, 2),
        "last_close": entry_ref,
        "last_low": round(last_low, 2),
    }

    return Candidate(
        candidate_type="range_lower_long",
        entry_ref=entry_ref,
        invalidation=invalidation,
        target_zone=target_zone,
        expires_utc=expires_utc,
        params_used=p,
        observations=observations,
    )


def _extract_verdict_label(text: str) -> str | None:
    """安全解析(沿用 ``agents/utils/rating.py`` 的模式):只认明确标签,歧义不猜。"""
    import re

    label_re = re.compile(r"^\s*\*{0,2}verdict\*{0,2}\s*[:\-]\s*\*{0,2}(\w+)", re.IGNORECASE)
    for line in text.splitlines():
        m = label_re.search(line)
        if m and m.group(1).lower() in _VERDICT_LABELS:
            return m.group(1).lower()

    for line in text.splitlines():
        clean = line.strip().strip("*:.,").lower()
        if clean in _VERDICT_LABELS:
            return clean

    return None


def _extract_reason(text: str) -> str:
    """提取 ``Reason: ...`` 标签行;没有明确标签则退回整段裁决文本。"""
    import re

    reason_re = re.compile(r"^\s*\*{0,2}reason\*{0,2}\s*[:\-]\s*\*{0,2}(.+)$", re.IGNORECASE)
    for line in text.splitlines():
        m = reason_re.search(line)
        if m:
            return m.group(1).strip()
    stripped = text.strip()
    return stripped if stripped else "(未提供理由)"


def _default_llm() -> Any:
    """延迟构造真实 LLM 客户端(生产路径),测试路径应始终注入 fake llm。"""
    from btc_agent.default_config import DEFAULT_CONFIG
    from btc_agent.llm_clients import create_llm_client

    cfg = DEFAULT_CONFIG
    client = create_llm_client(
        provider=cfg["llm_provider"],
        model=cfg["quick_think_llm"],
        backend_url=cfg.get("backend_url"),
        temperature=cfg.get("temperature", 0.1),
    )
    return client.get_llm()


def judge_candidate(candidate: Candidate, snapshot: Any, llm: Any = None) -> CandidateVerdict:
    """LLM 裁决点:只输出 accept/observe/veto + 定性理由,零数字。

    ``llm`` 为 None 时延迟构造真实客户端(生产路径);测试永远注入 fake llm
    (对象需暴露 ``.invoke(prompt) -> 带 .content 的响应``),零网络零凭据。
    """
    from btc_agent.agents.schemas import CandidateVerdict

    if llm is None:
        llm = _default_llm()

    prompt = _build_verdict_prompt(candidate, snapshot)

    try:
        response = llm.invoke(prompt)
        text = getattr(response, "content", None) or str(response)
    except Exception as exc:  # noqa: BLE001 — 裁决失败白卷降级,不让异常打断编排
        logger.warning("候选裁决 LLM 调用失败,降级为 observe: %s", exc)
        return CandidateVerdict(verdict="observe", reason=f"LLM 调用失败,白卷降级: {exc}")

    label = _extract_verdict_label(text)
    reason = _extract_reason(text)
    if label is None:
        logger.info("候选裁决文本无法解析出明确标签,白卷降级为 observe")
        return CandidateVerdict(verdict="observe", reason=reason)

    return CandidateVerdict(verdict=label, reason=reason)


def default_candidate_provider(snapshot: Any, regime_result: Any, llm: Any = None) -> dict | None:
    """daily 编排默认接线的 candidate_provider(ST5):机械候选 +(有候选时)LLM 裁决。

    白卷/非 range/数据缺失 → ``None``(不构造候选、不调用 LLM)。产出候选时返回
    ``decision_card`` 消费的字典形态:候选类型/裁决/理由 + 四个机械字段 + 有效期。
    ``llm`` 为测试注入点,生产路径延迟构造真实客户端(见 ``judge_candidate``)。
    """
    candidate = find_swing_candidate(snapshot, regime_result)
    if candidate is None:
        return None

    verdict = judge_candidate(candidate, snapshot, llm=llm)

    return {
        "candidate_type": candidate.candidate_type,
        "verdict": verdict.verdict,
        "reason": verdict.reason,
        "entry_ref": candidate.entry_ref,
        "invalidation": candidate.invalidation,
        "target_zone": candidate.target_zone,
        "expires_utc": candidate.expires_utc,
    }


def _build_verdict_prompt(candidate: Candidate, snapshot: Any) -> str:
    """裁决 prompt:只给机械依据 + 快照要点,明确要求零数字、白卷文化。"""
    asset = getattr(snapshot, "asset", "BTC")
    curr_date = getattr(snapshot, "curr_date", None)
    fear_greed = getattr(snapshot, "fear_greed", None)
    derivatives = getattr(snapshot, "derivatives", None)

    return f"""你是波段候选裁决点。以下是一次机械规则(震荡下沿做多)产出的候选依据,
全部价位与观察均已由确定性代码计算,不需要你重新验证或复述任何数字。

资产: {asset}  日期: {curr_date}
候选类型: {candidate.candidate_type}
机械观察: {candidate.observations}
恐慌贪婪指数: {fear_greed}
资金费率/持仓量: {derivatives}

请只从三档裁决中选一个: accept(证据支持这个候选)/ observe(证据不足或喜忧参半,
先观察不行动)/ veto(证据明确反对这个候选)。

白卷文化: 证据不足、矛盾或你无法确认时,选择 observe 或 veto,不要为了给出结论而
勉强 accept。

**绝对不要输出任何价格、数量、百分比或其它数字**——裁决只需定性理由。

严格按以下格式输出两行:
Verdict: <accept|observe|veto>
Reason: <一到两句定性理由,不含任何数字>"""
