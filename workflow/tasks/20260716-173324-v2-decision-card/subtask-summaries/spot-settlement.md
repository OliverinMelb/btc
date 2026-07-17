# Subtask Summary

## Parent Task
20260716-173324-v2-decision-card

## Subtask
spot-settlement — 现货收益口径修正

## Worktree
- path: C:\Users\admin\Desktop\wt-spot-settlement
- branch: subtask/spot-settlement

## Outcome
- status: pass
- reviewer recommendation: pass

## What Changed
- Added `btc_agent/src/btc_agent/settlement_math.py` with a pure, dependency-free
  `spot_settle(direction, market_return, bench_return) -> dict` function
  (no `graph`/LLM imports) implementing spot-only settlement:
  - `long`: `strategy_return = market_return`, `alpha = strategy_return - bench_return`,
    `direction_hit = market_return > 0`.
  - `short` (spot short = no position, cannot profit from a fall):
    `strategy_return = 0.0`, `alpha = -bench_return`,
    `direction_hit = market_return < 0`.
  - `flat` / unrecognised direction: same as short's return/alpha math,
    `direction_hit = None` (excluded from any hit-rate denominator).
  - `market_return == 0` is never a hit for long or short.
- `trading_graph._fetch_returns` now calls `spot_settle` instead of the old
  `strategy_return = -market_return` short-selling path (that line is gone —
  verified via `git grep -n -- "-market_return" btc_agent/src` returning no
  matches). Its return signature grew from a 3-tuple to a 5-tuple:
  `(raw_return, alpha_return, actual_holding_days, direction_hit,
  settlement_basis)`, with the two both-price-data-unavailable early returns
  updated to `(None, None, None, None, None)`.
- `trading_graph._resolve_pending_entries` unpacks the new 5-tuple, threads
  `direction_hit` into `reflector.reflect_on_final_decision`, and adds
  `direction_hit`/`settlement_basis` to the per-entry update dict passed to
  `memory_log.batch_update_with_outcomes`.
- `reflection.py`: `Reflector.reflect_on_final_decision` gained an optional
  `direction_hit: bool | None = None` parameter. When not `None`, a
  `"Direction call: correct/incorrect"` line is injected into the human
  message ahead of the decision text, so the reflection can see the
  direction call directly instead of reverse-engineering it from a
  raw_return that is always 0 for a spot short.
- `memory.py`:
  - Added a `_build_resolved_tag` static helper that builds the existing
    6-field resolved tag and appends `| basis=<basis>` and, only when
    `direction_hit is not None`, `| hit=<0/1>` before the closing `]`.
    Pending-tag format (`store_decision`) is untouched.
  - `update_with_outcome` / `batch_update_with_outcomes` gained
    `direction_hit`/`settlement_basis` parameters (default
    `settlement_basis="spot"`, `direction_hit=None`) and now build their new
    tag via `_build_resolved_tag` instead of an inline f-string.
  - `_parse_entry` now branches on tail-field count: for resolved entries
    (`len(fields) >= 6`), any `fields[6:]` starting with `basis=`/`hit=` are
    parsed into `entry["settlement_basis"]`/`entry["direction_hit"]`; when
    absent (the old 6-field shape), `settlement_basis` defaults to
    `"legacy"` and `direction_hit` to `None`. Pending entries get
    `settlement_basis=None`. The `len(fields) < 4` reject and the
    `fields[3] == "pending"` / `endswith("| pending]")` semantics are
    unchanged.
  - `_format_full` / `_format_reflection_only` append `" (legacy
    short-basis)"` to the rendered tag when `settlement_basis == "legacy"`,
    so `get_past_context`/reflection-injection prompts flag old
    short-basis-settled entries without touching the underlying data.
  - No migration of existing log data — legacy entries keep parsing as
    `legacy` indefinitely, by design.
- Updated existing tests in `btc_agent/tests/test_calendar_benchmark.py` to
  match the new spot semantics and 5-tuple return shape (Sell/Hold both
  settle to `strategy_return == 0`, `alpha == -market_return`; Sell with a
  rising market is `direction_hit is False`; Hold is `direction_hit is
  None`), renaming the parametrized-direction test to
  `test_fetch_returns_applies_spot_settlement`.
- Added `btc_agent/tests/test_settlement_math.py`: pure unit tests for
  `spot_settle` — long/short/flat happy paths, `market_return == 0` boundary
  (never a hit), short direction-hit independent of the (zero) return, and
  unknown-direction-treated-as-flat.
- Added `btc_agent/tests/test_memory_log.py`: regression tests for pending
  tag format (`store_decision` + `get_pending_entries`), legacy 6-field
  parsing, new spot 7-field (basis only, no hit) and 8-field (basis+hit)
  parsing, that a resolved tag no longer matches `endswith("| pending]")`,
  `get_past_context` legacy annotation (present for legacy entries, absent
  for spot entries), and an end-to-end
  `_resolve_pending_entries` test with a fake reflector and a monkeypatched
  `_fetch_returns` (fully offline, no LLM/network calls) asserting the
  written entry carries `settlement_basis == "spot"` and
  `direction_hit == True` with `raw == "+0.0%"`.

## Files Touched
- `btc_agent/src/btc_agent/settlement_math.py` (new)
- `btc_agent/src/btc_agent/graph/trading_graph.py`
- `btc_agent/src/btc_agent/graph/reflection.py`
- `btc_agent/src/btc_agent/agents/utils/memory.py`
- `btc_agent/tests/test_calendar_benchmark.py`
- `btc_agent/tests/test_settlement_math.py` (new)
- `btc_agent/tests/test_memory_log.py` (new)

## Verification Run
- maker checks (from `btc_agent/`, using
  `C:\Users\admin\Desktop\btc\btc_agent\.venv\Scripts\python.exe`, offline):
  - `python -m ruff check .` → all checks passed.
  - `python -m pytest -q` → 99 passed (previous 83 + 16 new: 8 in
    `test_settlement_math.py`, 8 in `test_memory_log.py`; existing suite's
    `test_calendar_benchmark.py` updated in place, no new files there so its
    count is unchanged aside from edits), zero skipped/failed.
- `git grep -n -- "-market_return" btc_agent/src` → no matches (short-selling
  path fully removed).
- checker gates / independent re-verify: not run by this subagent per
  protocol — orchestrator runs `workflow/scripts/verify_subtask.ps1`
  independently.

## Risks / Follow-ups
- The reflection prompt's "1. Was the directional call correct? (cite the
  alpha figure)" instruction line in `reflection.py`'s system prompt was
  left unchanged (out of scope: prompt text edits were restricted to "the
  minimal change needed to reference direction_hit"); the human message now
  gives the model an explicit `direction_hit` cue via the new
  `"Direction call: correct/incorrect"` line, so the model is no longer
  forced to infer correctness from alpha, but the instruction wording itself
  wasn't touched.
- `settlement_math.spot_settle`'s field names/contract
  (`strategy_return`/`alpha`/`direction_hit`/`settlement_basis`) is the
  handoff contract for the `sqlite-ledger` subtask (ST6) per the
  `provides-to` dependency; no consumer exists yet, so this is unverified
  end-to-end beyond the unit tests here.
- No migration path exists for legacy log entries by design (per spec); they
  will always render `(legacy short-basis)` and never accumulate
  `direction_hit` data. This is an intentional, spec-mandated limitation,
  not a bug.

## Notes For Reviewer
- All acceptance criteria in the subtask spec were checked directly:
  `spot_settle` three-direction + `market_return==0` boundary + flat→None
  tests exist; Sell settles `strategy_return == 0` and
  `alpha == -bench_return`; direction_hit/return independence is asserted
  (Sell + falling market → `hit=True`, `return=0`); the `-market_return`
  grep is clean; memory parse regression (legacy/pending/new-format) and
  legacy-render tests exist; `_resolve_pending_entries` test uses a fully
  fake reflector; ruff and pytest are both green from `btc_agent/`.
- No stop-rule conditions were hit: no need to touch `agents/schemas.py` or
  `run.py` invariants, and the "pending format unchanged + tail-append"
  memory.py constraint was satisfiable simultaneously without restructuring
  the tag.
