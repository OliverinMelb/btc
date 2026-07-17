# Independent Verification: contract-backfill

- task: 20260716-173324-v2-decision-card
- workflow: agent-change
- worktree: C:\Users\admin\Desktop\wt-contract-backfill
- run at: 2026-07-16 23:08:31 (re-run by orchestrator/reviewer, NOT subagent self-report)
- overall: PASS

## ruff: PASS (exit 0)
```
All checks passed!
```

## pytest: PASS (exit 0)
```
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\admin\Desktop\wt-contract-backfill\btc_agent
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.2, langsmith-0.10.4
collected 183 items

tests\test_calendar_benchmark.py ..........                              [  5%]
tests\test_candidates.py ....................                            [ 16%]
tests\test_ccxt_vendor.py .........                                      [ 21%]
tests\test_crypto_rss_vendor.py .......                                  [ 25%]
tests\test_daily.py ...............                                      [ 33%]
tests\test_decision_card.py ..............                               [ 40%]
tests\test_decision_safety.py ....                                       [ 43%]
tests\test_evidence.py ......                                            [ 46%]
tests\test_intel_rules_push.py .......................                   [ 59%]
tests\test_intel_run.py ....                                             [ 61%]
tests\test_intel_vendors.py ............                                 [ 67%]
tests\test_ledger.py .......                                             [ 71%]
tests\test_memory_log.py ........                                        [ 75%]
tests\test_regime.py .............                                       [ 83%]
tests\test_run_record.py ....                                            [ 85%]
tests\test_settlement.py .........                                       [ 90%]
tests\test_settlement_math.py ........                                   [ 94%]
tests\test_smoke.py .                                                    [ 95%]
tests\test_trade_levels.py .......                                       [ 98%]
tests\test_vendored_import.py ..                                         [100%]

============================ 183 passed in 40.09s =============================
```

