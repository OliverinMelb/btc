"""spot-settlement-subtask: memory.py 的 legacy/spot tag 解析回归单测。

覆盖:
- pending 行格式完全不动(endswith("| pending]"));
- 旧格式(6 字段)已结算条目按 legacy 解析,新格式(7/8 字段)读出 basis/hit;
- past context 渲染里 legacy 已结算条目带 "(legacy short-basis)" 标注;
- _resolve_pending_entries 端到端(fake reflector,不触网不调 LLM)。
"""

from btc_agent.agents.utils.memory import TradingMemoryLog
from btc_agent.default_config import DEFAULT_CONFIG
from btc_agent.graph.trading_graph import TradingAgentsGraph


def _mem(tmp_path, cfg_extra=None):
    cfg = {"memory_log_path": str(tmp_path / "mem.md")}
    if cfg_extra:
        cfg.update(cfg_extra)
    return TradingMemoryLog(cfg)


def test_pending_tag_format_unchanged(tmp_path):
    mem = _mem(tmp_path)
    mem.store_decision(
        ticker="BTC", trade_date="2021-01-05",
        final_trade_decision="**Rating**: Buy\n\nStrong momentum.",
    )
    raw = (tmp_path / "mem.md").read_text(encoding="utf-8")
    assert "[2021-01-05 | BTC | Buy | pending]" in raw
    pending = mem.get_pending_entries()
    assert len(pending) == 1
    assert pending[0]["pending"] is True
    assert pending[0]["date"] == "2021-01-05"
    assert pending[0]["ticker"] == "BTC"


def test_legacy_resolved_entry_parses_with_legacy_basis(tmp_path):
    """旧格式(6 字段,无 basis/hit 尾巴)照常解析,标注为 legacy。"""
    log_path = tmp_path / "mem.md"
    log_path.write_text(
        "[2021-01-01 | BTC | Sell | -3.0% | +1.0% | 5d]\n\n"
        "DECISION:\nSell due to overbought.\n\n"
        "REFLECTION:\nCall was wrong.",
        encoding="utf-8",
    )
    mem = TradingMemoryLog({"memory_log_path": str(log_path)})
    entries = mem.load_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["pending"] is False
    assert e["raw"] == "-3.0%"
    assert e["alpha"] == "+1.0%"
    assert e["holding"] == "5d"
    assert e["settlement_basis"] == "legacy"
    assert e["direction_hit"] is None


def test_new_spot_entry_with_hit_parses_basis_and_hit(tmp_path):
    log_path = tmp_path / "mem.md"
    log_path.write_text(
        "[2021-01-01 | BTC | Sell | +0.0% | +3.0% | 5d | basis=spot | hit=1]\n\n"
        "DECISION:\nSell, bear thesis.\n\n"
        "REFLECTION:\nDirection was right, spot can't monetize the short.",
        encoding="utf-8",
    )
    mem = TradingMemoryLog({"memory_log_path": str(log_path)})
    entries = mem.load_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["settlement_basis"] == "spot"
    assert e["direction_hit"] is True


def test_new_spot_entry_without_hit_omits_hit_field(tmp_path):
    """flat/Hold 结算:hit=None 时尾部只有 basis,无 hit 段。"""
    log_path = tmp_path / "mem.md"
    log_path.write_text(
        "[2021-01-01 | BTC | Hold | +0.0% | -2.0% | 5d | basis=spot]\n\n"
        "DECISION:\nHold, unclear regime.\n\n"
        "REFLECTION:\nNo directional call made.",
        encoding="utf-8",
    )
    mem = TradingMemoryLog({"memory_log_path": str(log_path)})
    entries = mem.load_entries()
    e = entries[0]
    assert e["settlement_basis"] == "spot"
    assert e["direction_hit"] is None


def test_pending_matching_still_endswith_pending_after_spot_update(tmp_path):
    """更新后 tag 不再以 '| pending]' 结尾(已结算),pending 匹配行为保持不变。"""
    log_path = tmp_path / "mem.md"
    mem = TradingMemoryLog({"memory_log_path": str(log_path)})
    mem.store_decision(
        ticker="BTC", trade_date="2021-01-05",
        final_trade_decision="**Rating**: Sell\n\nBear thesis.",
    )
    mem.update_with_outcome(
        ticker="BTC", trade_date="2021-01-05",
        raw_return=0.0, alpha_return=0.03, holding_days=5,
        reflection="Correct bearish call, spot settles to zero.",
        direction_hit=True, settlement_basis="spot",
    )
    raw = log_path.read_text(encoding="utf-8")
    assert "| pending]" not in raw
    assert "| basis=spot | hit=1]" in raw
    pending = mem.get_pending_entries()
    assert pending == []


def test_get_past_context_annotates_legacy_entries(tmp_path):
    log_path = tmp_path / "mem.md"
    log_path.write_text(
        "[2021-01-01 | BTC | Sell | -3.0% | +1.0% | 5d]\n\n"
        "DECISION:\nSell, overbought.\n\n"
        "REFLECTION:\nLegacy short-basis call.",
        encoding="utf-8",
    )
    mem = TradingMemoryLog({"memory_log_path": str(log_path)})
    ctx = mem.get_past_context("BTC")
    assert "(legacy short-basis)" in ctx


def test_get_past_context_does_not_annotate_spot_entries(tmp_path):
    log_path = tmp_path / "mem.md"
    log_path.write_text(
        "[2021-01-01 | BTC | Sell | +0.0% | +3.0% | 5d | basis=spot | hit=1]\n\n"
        "DECISION:\nSell, bear thesis.\n\n"
        "REFLECTION:\nDirection right, spot return zero.",
        encoding="utf-8",
    )
    mem = TradingMemoryLog({"memory_log_path": str(log_path)})
    ctx = mem.get_past_context("BTC")
    assert "(legacy short-basis)" not in ctx


class _FakeReflector:
    """假反思器:记录调用参数,返回固定文本,不触网不调 LLM。"""

    def __init__(self):
        self.calls = []

    def reflect_on_final_decision(self, **kwargs):
        self.calls.append(kwargs)
        return "fake reflection"


def test_resolve_pending_entries_records_direction_hit_and_spot_basis(tmp_path):
    """端到端:_resolve_pending_entries 用 spot 口径结算并落盘 basis/hit,reflector 全假。"""
    cfg = dict(DEFAULT_CONFIG)
    cfg["memory_log_path"] = str(tmp_path / "mem.md")
    cfg["results_dir"] = str(tmp_path)

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = cfg
    graph.memory_log = TradingMemoryLog(cfg)
    graph.reflector = _FakeReflector()

    graph.memory_log.store_decision(
        ticker="BTC", trade_date="2021-01-05",
        final_trade_decision="**Rating**: Sell\n\nBear thesis.",
    )

    def _fake_fetch_returns(ticker, trade_date, holding_days=5, benchmark="BTC/USDT", rating="Buy"):
        # 市场下跌:Sell 方向命中,但现货口径 strategy_return 仍为 0。
        return 0.0, 0.05, 5, True, "spot"

    graph._fetch_returns = _fake_fetch_returns

    graph._resolve_pending_entries("BTC")

    assert len(graph.reflector.calls) == 1
    assert graph.reflector.calls[0]["direction_hit"] is True

    entries = graph.memory_log.load_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["pending"] is False
    assert e["settlement_basis"] == "spot"
    assert e["direction_hit"] is True
    assert e["raw"] == "+0.0%"
