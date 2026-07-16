# Verification Matrix

## Two Layers of Verification

1. **Maker checks**: the implementing subagent runs the matrix below inside its
   worktree and records results in its subtask summary. This is self-report.
2. **Independent re-verification**: before the reviewer packet is assembled, the
   orchestrator (or reviewer) re-runs the same matrix via
   `workflow/scripts/verify_subtask.ps1 -TaskId <id> -SubtaskId <id>`.
   Self-reported results are never trusted as review evidence; only the
   `subtask-summaries/<subtask-id>.verify.md` evidence file counts.

A subtask is not review-ready until its independent re-verification is PASS.

## Agent Change (this project's only component)
Run from `btc_agent` (shared venv, fully offline):
- `python -m pytest`
- `python -m ruff check .`

## Contract Change
Run the agent checks above, then (from the repo root, or via
`{engine}/run_contract_drift.py`):
- `python {engine}/check_contract_touchpoints.py`
- `python {engine}/check_env_consistency.py`

## Workflow-Only Change
Run from repo root:
- `python {engine}/check_env_consistency.py`
- `python {engine}/check_contract_touchpoints.py`
