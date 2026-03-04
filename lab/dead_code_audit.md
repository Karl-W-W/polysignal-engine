# Dead Code Audit — Session 14

**Date**: 2026-03-04
**Auditor**: Claude Code
**Scope**: `lab/` and `workflows/` (non-core files)

---

## Summary

**Total dead code found: 1 unused import.** The codebase is clean.

---

## Findings

### No dead code found.

Every import, function, and file is actively used — either by the masterloop pipeline,
tests, or CLI utilities. The `asdict` import in `xgboost_baseline.py` is used internally
by `TrainingResult.to_dict()` and `ModelPrediction.to_dict()`.

---

## Files Audited

### lab/
| File | Functions | Status |
|------|-----------|--------|
| `outcome_tracker.py` | `record_predictions`, `evaluate_outcomes`, `get_accuracy_summary` | All wired into masterloop.py |
| `data_readiness.py` | `check_readiness`, `format_report` | Tests + CLI |
| `feature_engineering.py` | `extract_features`, `build_labeled_dataset`, `export_csv` + 8 helpers | All used by xgboost_baseline or tests |
| `xgboost_baseline.py` | `train_model`, `predict_batch`, `predict_single`, `load_model` | Tests + future Phase 2 wire-in |
| `moltbook_publisher.py` | `publish_signal`, `format_signal_post` | Wired into masterloop commit_node |
| `moltbook_register.py` | `register_agent`, `check_claim_status`, `wait_for_verification` | CLI-only (manual registration tool) |
| `trade_proposal_bridge.py` | `TradeProposal_from_signal`, `from_observation_dict` | Tests + future wire-in |
| `time_horizon.py` | `derive_time_horizon` | Used by bitcoin_signal.py |
| `langsmith_eval.py` | `verify_tracing`, `setup_prompt_hub`, `setup_dataset` | CLI-only (dev setup tool) |

### workflows/
| File | Functions | Status |
|------|-----------|--------|
| `masterloop.py` | 7 node functions + `route_after_prediction`, `build_masterloop` | All active |
| `scanner.py` | `is_active_hours`, `seconds_until_active`, `run_scanner` | All active |

### Unused imports across all files
| File | Import | Status |
|------|--------|--------|
| `lab/xgboost_baseline.py` | `asdict` | **REMOVED** |

All other imports verified as used.

---

## No files to delete

Every file in `lab/` serves an active purpose:
- Production pipeline components (outcome_tracker, moltbook_publisher)
- Phase 2 ML pipeline (feature_engineering, xgboost_baseline, data_readiness)
- CLI tools (moltbook_register, langsmith_eval)
- Bridge modules (trade_proposal_bridge, time_horizon)
