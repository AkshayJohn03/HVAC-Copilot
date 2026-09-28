"""Evaluation layer: offline golden-set metrics (recall, precision, grounding, safety)."""

from hvac_copilot.eval.runner import (
    EvalReport,
    GoldenItem,
    check_thresholds,
    chunk_matches,
    format_report,
    load_golden,
    run_eval,
)

__all__ = [
    "EvalReport",
    "GoldenItem",
    "check_thresholds",
    "chunk_matches",
    "format_report",
    "load_golden",
    "run_eval",
]
