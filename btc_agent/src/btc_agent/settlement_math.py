"""Pure spot-settlement math.

Deliberately dependency-free (no ``graph``/LLM imports) so it can be reused
offline by other consumers — e.g. the sqlite ledger — without pulling in
LangGraph or any LLM client. Keep it that way.
"""

from __future__ import annotations


def spot_settle(direction: str, market_return: float, bench_return: float) -> dict:
    """Settle a single decision under spot-only accounting.

    ``direction`` is one of ``"long"`` / ``"short"`` / ``"flat"`` (see
    ``btc_agent.trade_levels.rating_to_direction``; any unrecognised value is
    treated the same as ``"flat"``).

    A spot-only system cannot profit from a short: going short (or staying
    flat) simply means no position is held, so both settle to zero strategy
    return. The alpha figure still reflects the cost of missing the
    benchmark move (``-bench_return``) — the "opportunity cost of not
    holding".

    ``direction_hit`` records whether the *directional call* was right,
    independent of the (necessarily zero, for short/flat) return figure:
    - long: hit iff ``market_return > 0``
    - short: hit iff ``market_return < 0``
    - ``market_return == 0``: never a hit (no move to have called correctly)
    - flat: ``None`` (no directional call was made; excluded from any
      direction-hit-rate denominator)

    Returns a dict with keys ``strategy_return``, ``alpha``,
    ``direction_hit``, ``settlement_basis`` (always ``"spot"``).
    """
    if direction == "long":
        strategy_return = market_return
        alpha = strategy_return - bench_return
        direction_hit = market_return > 0
    elif direction == "short":
        strategy_return = 0.0
        alpha = -bench_return
        direction_hit = market_return < 0
    else:  # flat / unknown ratings fail closed to flat
        strategy_return = 0.0
        alpha = -bench_return
        direction_hit = None

    return {
        "strategy_return": strategy_return,
        "alpha": alpha,
        "direction_hit": direction_hit,
        "settlement_basis": "spot",
    }
