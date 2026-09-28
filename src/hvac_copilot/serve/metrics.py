"""Lightweight metrics registry with Prometheus text rendering.

Deliberately dependency-free: the deployment surface is one ``/metrics``
endpoint, and pulling in a full client library for five counters is overhead.
Counters + per-stage latency samples (p50/p95) cover the latency budget story.
"""

from __future__ import annotations

import time
from collections import defaultdict


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._help: dict[str, str] = {}
        self._started = time.time()

    # -- recording -------------------------------------------------------------
    def inc(self, name: str, amount: float = 1.0, help_doc: str = "") -> None:
        self._counters[name] += amount
        if help_doc:
            self._help.setdefault(name, help_doc)

    def observe(self, stage: str, ms: float) -> None:
        samples = self._latencies[stage]
        samples.append(float(ms))
        if len(samples) > 2000:  # bounded memory for long-lived processes
            del samples[:1000]

    # -- reading -----------------------------------------------------------------
    def counter(self, name: str) -> float:
        return self._counters.get(name, 0.0)

    @staticmethod
    def _percentile(sorted_values: list[float], q: float) -> float:
        if not sorted_values:
            return 0.0
        idx = min(len(sorted_values) - 1, max(0, round(q * (len(sorted_values) - 1))))
        return sorted_values[idx]

    def percentile(self, stage: str, q: float) -> float:
        return self._percentile(sorted(self._latencies.get(stage, [])), q)

    # -- rendering ------------------------------------------------------------------
    def render(self) -> str:
        lines: list[str] = []
        emitted: set[str] = set()
        for name, value in sorted(self._counters.items()):
            base = name.split("{")[0]
            if base not in emitted:
                lines.append(f"# HELP {base} {self._help.get(base, base)}")
                lines.append(f"# TYPE {base} counter")
                emitted.add(base)
            lines.append(f"{name} {value}")
        stage_base = "hvac_stage_latency_ms"
        if self._latencies and stage_base not in emitted:
            lines.append(f"# HELP {stage_base} Per-stage latency in milliseconds")
            lines.append(f"# TYPE {stage_base} summary")
            emitted.add(stage_base)
        for stage in sorted(self._latencies):
            lines.append(f'{stage_base}{{stage="{stage}",quantile="0.5"}} {self.percentile(stage, 0.50):.2f}')
            lines.append(f'{stage_base}{{stage="{stage}",quantile="0.95"}} {self.percentile(stage, 0.95):.2f}')
        lines.append("# HELP hvac_uptime_seconds Process uptime in seconds")
        lines.append("# TYPE hvac_uptime_seconds gauge")
        lines.append(f"hvac_uptime_seconds {time.time() - self._started:.1f}")
        return "\n".join(lines) + "\n"
