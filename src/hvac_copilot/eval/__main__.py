"""``python -m hvac_copilot.eval`` — offline golden-set evaluation CLI.

Builds a fully offline service (mock providers, bundled corpus), runs the
golden QA set, prints a markdown report, and exits non-zero below thresholds —
so it can gate CI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hvac_copilot.config import Settings
from hvac_copilot.eval.runner import (
    DEFAULT_THRESHOLDS,
    check_thresholds,
    format_report,
    load_golden,
    run_eval,
)
from hvac_copilot.service import HVACCopilot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline eval for HVAC-Copilot.")
    parser.add_argument("--golden", type=Path, default=Settings().golden_path)
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--mode", choices=["hybrid", "bm25"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--compare-bm25",
        action="store_true",
        help="also run bm25-only mode and include its recall in the report",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if args.corpus:
        settings.corpus_dir = args.corpus
    if args.index_dir:
        settings.index_dir = args.index_dir
    service = HVACCopilot(settings)
    service.ingest()

    golden = load_golden(args.golden)
    report = run_eval(service, golden, mode=args.mode, top_k=args.top_k)
    print(format_report(report))
    passed = check_thresholds(report, DEFAULT_THRESHOLDS)

    if args.compare_bm25:
        # Baseline definition: *raw* Okapi BM25 — no fusion, no reranker. This
        # is the standard ablation: the proposed system (dense + BM25 + RRF +
        # reranker) against the lexical baseline it replaces.
        bm25_report = run_eval(service, golden, mode="bm25", top_k=args.top_k, reranker=None)
        print(
            f"\nBM25-only baseline recall@{args.top_k}: {bm25_report.recall:.3f} "
            f"(hybrid: {report.recall:.3f}, delta {report.recall - bm25_report.recall:+.3f})"
        )

    print(
        f"\nthresholds: {DEFAULT_THRESHOLDS}\nresult: {'PASS' if passed else 'FAIL'}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
