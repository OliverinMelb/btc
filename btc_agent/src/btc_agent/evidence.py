"""统一证据快照(BTC agent v2 决策卡基座)。

在此之前,仪表盘取数、交易价位取数(以及研判图 ToolNode 取数)是三条各自独立的
机械取数路径,同一次运行可能各调各的 vendor,理论上能取到不完全一致的数据
(比如仪表盘看到的收盘价与交易价位算出来的收盘价不是同一根 K 线)。

本模块把"行情 OHLCV / 新闻 / 恐慌贪婪指数 / 衍生品盘面"收敛成一次性冻结的
``EvidenceSnapshot``——同一次运行只触发一次 vendor 调用,仪表盘装配与机械交易
价位计算处处消费同一份数据。

**范围裁定(设计门 G3)**:研判图 ToolNode 图内取数本次不改线(它已有独立的
as-of 前视防护,且与快照调同一个 vendor);只收敛 intel 仪表盘 + run.py 的机械
价位两条路径,记 backlog v2.5。

单源失败哲学与 ``intel/dashboard.py`` 现有降级哲学一致:任一源取数失败只记
``health`` 里的错误原因,快照本身不因单源失败而整体崩——是否容忍某源缺失由
消费方决定(仪表盘容忍;``run.py`` 的机械价位计算离不开 OHLCV,缺失时会据此
重新抛出失败)。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

logger = logging.getLogger(__name__)

_OK = "ok"


@dataclass
class EvidenceSnapshot:
    """一份冻结的 UTC as-of 证据快照。"""

    asset: str
    curr_date: str | None
    ohlcv: pd.DataFrame | None
    news: str | None
    fear_greed: dict | None
    derivatives: dict | None
    health: dict = field(default_factory=dict)
    snapshot_id: str = ""
    frozen_at_utc: str = ""


def _snapshot_id(asset: str, curr_date: str | None, frozen_at_utc: str) -> str:
    """``BTC-2026-07-16-<短hash>``:日期用 ``curr_date``(缺省退回冻结日),短 hash 保证
    同资产同日多次快照仍可区分(hash 覆盖冻结时点,不同秒生成的快照 id 不同)。
    """
    day = curr_date or frozen_at_utc[:10]
    digest = hashlib.sha256(
        f"{asset}|{curr_date}|{frozen_at_utc}".encode()
    ).hexdigest()[:8]
    return f"{asset}-{day}-{digest}"


def build_evidence_snapshot(
    asset: str = "BTC", curr_date: str | None = None
) -> EvidenceSnapshot:
    """取一次、处处用:装配统一证据快照。

    每个源各自 try/except 记 ``health``;单源失败不影响其它源装配。``ohlcv``
    是最关键的一路——它是否成功体现在 ``health["ohlcv"]``,由调用方自行决定是否
    可容忍缺失(dashboard 容忍并降级;``run.py`` 的机械价位计算不容忍)。
    """
    frozen_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    health: dict[str, str] = {}

    ohlcv = None
    try:
        from btc_agent.dataflows.ccxt_vendor import _ohlcv_dataframe

        ohlcv = _ohlcv_dataframe(asset, curr_date=curr_date)
        health["ohlcv"] = _OK
    except Exception as exc:  # noqa: BLE001 — 单源失败降级,原样记 health
        health["ohlcv"] = f"error:{exc}"
        logger.warning("快照取 OHLCV 失败:%s", exc)

    news = None
    try:
        from btc_agent.dataflows.config import get_config
        from btc_agent.dataflows.crypto_rss_vendor import get_crypto_rss_news

        end_date = curr_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lookback_days = get_config().get("global_news_lookback_days", 7)
        start_date = (
            datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%d")
        news = get_crypto_rss_news(asset, start_date, end_date)
        health["news"] = _OK
    except Exception as exc:  # noqa: BLE001
        health["news"] = f"error:{exc}"
        logger.warning("快照取新闻失败:%s", exc)

    fear_greed = None
    try:
        from btc_agent.dataflows.feargreed_vendor import get_fear_greed_value

        fear_greed = get_fear_greed_value(curr_date)
        health["fear_greed"] = _OK
    except Exception as exc:  # noqa: BLE001
        health["fear_greed"] = f"error:{exc}"
        logger.warning("快照取 F&G 失败:%s", exc)

    derivatives = None
    try:
        from btc_agent.dataflows.derivatives_vendor import get_derivatives_snapshot_data

        derivatives = get_derivatives_snapshot_data(asset, curr_date)
        health["derivatives"] = _OK
    except Exception as exc:  # noqa: BLE001
        health["derivatives"] = f"error:{exc}"
        logger.warning("快照取衍生品盘面失败:%s", exc)

    return EvidenceSnapshot(
        asset=asset,
        curr_date=curr_date,
        ohlcv=ohlcv,
        news=news,
        fear_greed=fear_greed,
        derivatives=derivatives,
        health=health,
        snapshot_id=_snapshot_id(asset, curr_date, frozen_at_utc),
        frozen_at_utc=frozen_at_utc,
    )
