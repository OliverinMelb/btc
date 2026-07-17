# Subagent Launch Prompt

You are the implementation subagent for this subtask.

## Identity
- parent task id: `20260716-173324-v2-decision-card`
- subtask id: `contract-backfill`
- workflow class: `agent-change`

## Workspace
- repository root: `C:\Users\admin\Desktop\btc`
- assigned worktree: `C:\Users\admin\Desktop\wt-contract-backfill`
- assigned branch: `subtask/contract-backfill`

## Read First
1. `C:\Users\admin\Desktop\btc\AGENTS.md`
2. `C:\Users\admin\Desktop\btc\workflow\README.md`
3. `C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\subtasks\contract-backfill.md`
4. `C:\Users\admin\Desktop\btc\workflow\README.md`
5. `C:\Users\admin\Desktop\btc\workflow\checks\verification.md`

## Inputs
- parent brief: `C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\brief.md`
- parent spec: `C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\spec.md`
- task plan: `C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\plan.md`
- subtask spec: `C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\subtasks\contract-backfill.md`

## Scope Guardrails
- only work inside: `C:\Users\admin\Desktop\wt-contract-backfill`
- only touch surfaces allowed by the subtask spec
- do not edit another subtask's worktree
- stop and escalate if acceptance criteria require cross-subtask ownership changes

## Required Outcome
- make the smallest viable change for this subtask
- satisfy the subtask acceptance criteria
- run the required maker checks and checker gates
- write the final result to `C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\subtask-summaries\contract-backfill.md`

## Required Writeback
Write the final summary using this exact file path:
`C:\Users\admin\Desktop\btc\workflow\tasks\20260716-173324-v2-decision-card\subtask-summaries\contract-backfill.md`

Use this template:
`C:\Users\admin\Desktop\btc\workflow\templates\subtask-summary.md`

## Checks To Run
- from `btc_agent` run:
  - `python -m ruff check .`
  - `python -m pytest`

## Completion Contract
Before you stop, ensure the summary includes:
- what changed
- files touched
- checks run and pass/fail status
- open risks or follow-ups
- reviewer recommendation: `pass`, `fail`, or `needs follow-up`

