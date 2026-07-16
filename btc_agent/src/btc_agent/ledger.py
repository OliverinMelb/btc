"""SQLite 账本(BTC agent v2 ST6)。

前向统计的唯一真源(设计门 G4):快照/候选/裁决/机械价位/结算全部落这一份
SQLite,JSON records 与 markdown 记忆日志只是运行痕迹,不进统计。

**硬约束(G2)**:本模块不 import ``graph`` 包——策略版本 hash 只消费
``regime.REGIME_PARAMS`` / ``candidates.CANDIDATE_PARAMS`` 两个纯数据字典,
不触发任何 LLM/图构造。

版本状态机(设计门 G5):``strategy_versions.params_hash`` 由 regime 参数 +
候选参数 + 结算口径参数(canonical json)算出;同 hash 复用同一版本行,
改参数即新增一行(``experimental``),**旧版本行及其结算数据只读**——本模块
不提供任何 update/delete 版本行的 API。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_versions (
    id INTEGER PRIMARY KEY,
    rule_name TEXT NOT NULL,
    params_json TEXT NOT NULL,
    params_hash TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'experimental'
        CHECK(status IN ('experimental', 'forward_validated', 'validated')),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    trade_date TEXT,
    frozen_at_utc TEXT,
    health_json TEXT,
    regime TEXT,
    blank_sheet INTEGER,
    observations_json TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL,
    strategy_version_id INTEGER NOT NULL,
    candidate_type TEXT NOT NULL,
    entry_ref REAL NOT NULL,
    invalidation REAL NOT NULL,
    target_zone_json TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    position_context TEXT DEFAULT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY (strategy_version_id) REFERENCES strategy_versions(id)
);

CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    reason TEXT,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);

CREATE TABLE IF NOT EXISTS trade_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL,
    rating TEXT,
    direction TEXT,
    entry REAL,
    stop REAL,
    target REAL,
    atr REAL,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER UNIQUE NOT NULL,
    settled_at_utc TEXT NOT NULL,
    outcome TEXT NOT NULL,
    settle_price REAL NOT NULL,
    market_return REAL NOT NULL,
    strategy_return REAL NOT NULL,
    alpha REAL NOT NULL,
    direction_hit INTEGER,
    settlement_basis TEXT NOT NULL,
    detail_json TEXT,
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);
"""

# 结算口径三参数(G6 裁定)——已集中在 candidates.CANDIDATE_PARAMS 里,这里只做
# 提取,进策略版本 hash 的独立 ``settlement_params`` 分组。
SETTLEMENT_PARAM_KEYS = ("touch_basis", "settle_price", "tie_break")


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_db_path(results_dir: str | None = None) -> str:
    """默认账本文件路径:``<results_dir>/ledger.sqlite3``。

    ``results_dir`` 缺省时退回 ``default_config.DEFAULT_CONFIG["results_dir"]``。
    """
    if results_dir is None:
        from btc_agent.default_config import DEFAULT_CONFIG

        results_dir = DEFAULT_CONFIG["results_dir"]
    return os.path.join(results_dir, "ledger.sqlite3")


def init_schema(conn: sqlite3.Connection) -> None:
    """创建全部表(幂等:``CREATE TABLE IF NOT EXISTS``)。"""
    conn.executescript(_SCHEMA)
    conn.commit()


def connect(db_path: str) -> sqlite3.Connection:
    """打开(或新建)账本文件,缺目录自动建,返回已初始化 schema 的连接。"""
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def _canonical_json(obj: Any) -> str:
    """确定性 JSON 序列化(排序键,无空白差异),用作 hash 输入。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def settlement_params_from(candidate_params: dict[str, Any]) -> dict[str, Any]:
    """从 ``candidates.CANDIDATE_PARAMS`` 提取 G6 结算口径三参数子集。"""
    return {k: candidate_params[k] for k in SETTLEMENT_PARAM_KEYS if k in candidate_params}


def params_hash(
    regime_params: dict[str, Any],
    candidate_params: dict[str, Any],
    settlement_params: dict[str, Any] | None = None,
) -> str:
    """``sha256(canonical_json({regime_params, candidate_params, settlement_params}))``。

    regime 参数、候选参数、结算口径参数任一变更即产生新 hash(设计门 G5)。
    """
    if settlement_params is None:
        settlement_params = settlement_params_from(candidate_params)
    payload = {
        "regime_params": regime_params,
        "candidate_params": candidate_params,
        "settlement_params": settlement_params,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def get_or_create_strategy_version(
    conn: sqlite3.Connection,
    rule_name: str,
    regime_params: dict[str, Any],
    candidate_params: dict[str, Any],
    settlement_params: dict[str, Any] | None = None,
) -> int:
    """按参数 hash 复用或新建策略版本行。

    hash 已存在 → 返回既有行 id,**不改写该行任何字段**(旧版本行只读不变式)。
    新 hash → 插入新行,``status`` 恒为 ``experimental``(状态推进条件本任务不实现,
    只在此注释:``forward_validated`` 需要前向样本量与命中率门槛达标,
    ``validated`` 需要人工复核确认,均留待后续任务)。
    """
    if settlement_params is None:
        settlement_params = settlement_params_from(candidate_params)
    h = params_hash(regime_params, candidate_params, settlement_params)

    cur = conn.cursor()
    row = cur.execute(
        "SELECT id FROM strategy_versions WHERE params_hash = ?", (h,)
    ).fetchone()
    if row is not None:
        return int(row[0])

    params_json = _canonical_json(
        {
            "regime_params": regime_params,
            "candidate_params": candidate_params,
            "settlement_params": settlement_params,
        }
    )
    cur.execute(
        "INSERT INTO strategy_versions (rule_name, params_json, params_hash, status, "
        "created_at_utc) VALUES (?, ?, ?, 'experimental', ?)",
        (rule_name, params_json, h, _utcnow()),
    )
    conn.commit()
    return int(cur.lastrowid)


def default_strategy_version_id(conn: sqlite3.Connection) -> int:
    """daily 接线的默认版本:直接消费 regime/candidates 模块级默认参数字典。"""
    from btc_agent.candidates import CANDIDATE_PARAMS
    from btc_agent.regime import REGIME_PARAMS

    return get_or_create_strategy_version(
        conn, "btc_agent_v2_range_lower_long", REGIME_PARAMS, CANDIDATE_PARAMS
    )


def record_daily(
    conn: sqlite3.Connection,
    snapshot: Any,
    regime_result: Any,
    rating: str | None,
    reasoning: str | None,
    levels: dict | None,
    candidates: Any,
    strategy_version_id: int | None = None,
) -> None:
    """一次 daily 运行的 快照/候选/裁决/机械价位 一并入库。

    幂等:同 ``snapshot.snapshot_id`` 重跑直接返回,不重复插入(账本以
    ``snapshots.snapshot_id`` 为幂等键,候选/裁决/价位跟随快照一起判重)。
    ``candidates`` 为 ``None``(白卷/非 range/候选被显式跳过)时不插候选/裁决行,
    只插快照(+ 有 levels 时的机械价位行)。
    """
    snapshot_id = getattr(snapshot, "snapshot_id", None)
    if not snapshot_id:
        raise ValueError("record_daily 需要 snapshot.snapshot_id")

    cur = conn.cursor()
    existing = cur.execute(
        "SELECT 1 FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()
    if existing is not None:
        return  # 幂等: 同 snapshot_id 已入库,不重复插入。

    if strategy_version_id is None:
        strategy_version_id = default_strategy_version_id(conn)

    now = _utcnow()
    health = getattr(snapshot, "health", None) or {}
    regime = getattr(regime_result, "regime", None)
    blank_sheet = bool(getattr(regime_result, "blank_sheet", True))
    observations = getattr(regime_result, "observations", None) or {}

    cur.execute(
        "INSERT INTO snapshots (snapshot_id, asset, trade_date, frozen_at_utc, "
        "health_json, regime, blank_sheet, observations_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            snapshot_id,
            getattr(snapshot, "asset", None),
            getattr(snapshot, "curr_date", None),
            getattr(snapshot, "frozen_at_utc", None),
            _canonical_json(health),
            regime,
            1 if blank_sheet else 0,
            _canonical_json(observations),
        ),
    )

    if candidates:
        candidate_type = _field(candidates, "candidate_type")
        entry_ref = _field(candidates, "entry_ref")
        invalidation = _field(candidates, "invalidation")
        target_zone = _field(candidates, "target_zone")
        expires_utc = _field(candidates, "expires_utc")
        verdict = _field(candidates, "verdict")
        reason = _field(candidates, "reason")

        cur.execute(
            "INSERT INTO candidates (snapshot_id, strategy_version_id, candidate_type, "
            "entry_ref, invalidation, target_zone_json, expires_utc, position_context, "
            "created_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)",
            (
                snapshot_id,
                strategy_version_id,
                candidate_type,
                entry_ref,
                invalidation,
                _canonical_json(list(target_zone) if target_zone is not None else None),
                expires_utc,
                now,
            ),
        )
        candidate_id = cur.lastrowid

        if verdict is not None:
            cur.execute(
                "INSERT INTO verdicts (candidate_id, verdict, reason, created_at_utc) "
                "VALUES (?, ?, ?, ?)",
                (candidate_id, verdict, reason, now),
            )

    if levels:
        from btc_agent.trade_levels import rating_to_direction

        direction = rating_to_direction(rating) if rating else "flat"
        cur.execute(
            "INSERT INTO trade_levels (snapshot_id, rating, direction, entry, stop, "
            "target, atr) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                rating,
                direction,
                levels.get("entry"),
                levels.get("stop"),
                levels.get("target"),
                levels.get("atr"),
            ),
        )

    conn.commit()


def _field(candidates: Any, key: str, default: Any = None) -> Any:
    """兼容 dict 或带属性对象两种 candidates 载体形态的字段读取(与 decision_card 同构)。"""
    if isinstance(candidates, dict):
        return candidates.get(key, default)
    return getattr(candidates, key, default)
