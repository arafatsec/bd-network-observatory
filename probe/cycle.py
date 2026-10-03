"""One measurement cycle, and the loop that repeats it."""

import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Callable

from probe import uploader
from probe.checks import CheckResults, run_checks
from probe.classify import LayerOutcome, classify, rolling_baseline, update_samples
from probe.storage import append_record

SCHEMA_VERSION = 1


def layer_outcome(results: CheckResults) -> LayerOutcome:
    tcp_times = [r.ms for r in results.tcp if r.ok and r.ms is not None]
    return LayerOutcome(
        dns_ok=any(r.ok for r in results.dns),
        tcp_ok=any(r.ok for r in results.tcp),
        http_ok=any(r.ok for r in results.http),
        latency_ms=round(median(tcp_times), 1) if tcp_times else None,
    )


def format_ts(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_record(
    ts: datetime,
    interval_s: int,
    results: CheckResults,
    classification: str,
    latency_ms: float | None,
    baseline_ms: float | None,
) -> dict:
    """The complete record. Nothing about the host (IP, hostname, user, Wi-Fi,
    location) is collected anywhere, so nothing of the kind can end up here."""
    return {
        "v": SCHEMA_VERSION,
        "ts": format_ts(ts),
        "interval_s": interval_s,
        "classification": classification,
        "latency_ms": latency_ms,
        "baseline_ms": baseline_ms,
        "dns": [_as_json(r) for r in results.dns],
        "tcp": [_as_json(r) for r in results.tcp],
        "http": [_as_json(r) for r in results.http],
    }


def _as_json(result) -> dict:
    data = asdict(result)
    if "answers" in data:
        data["answers"] = list(data["answers"])
    return data


def run_cycle(
    interval_s: int,
    samples: tuple[float, ...],
    *,
    checker: Callable[[], CheckResults] = run_checks,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> tuple[datetime, dict, tuple[float, ...]]:
    """Measure once. Returns (timestamp, record, new baseline samples)."""
    ts = now()
    results = checker()
    outcome = layer_outcome(results)
    baseline_ms = rolling_baseline(samples)
    classification = classify(outcome, baseline_ms)
    record = build_record(ts, interval_s, results, classification, outcome.latency_ms, baseline_ms)
    return ts, record, update_samples(samples, classification, outcome.latency_ms)


def status_line(record: dict) -> str:
    latency = record["latency_ms"]
    baseline = record["baseline_ms"]
    latency_text = f"tcp {latency} ms" if latency is not None else "tcp -"
    baseline_text = f"baseline {baseline} ms" if baseline is not None else "baseline warming up"
    return f"{record['ts']}  {record['classification']:<9} {latency_text}, {baseline_text}"


def run_loop(
    interval_s: int,
    data_dir: Path,
    *,
    checker: Callable[[], CheckResults] = run_checks,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    out: Callable[[str], None] = print,
    max_cycles: int | None = None,
) -> int:
    """Run until interrupted (or max_cycles, for tests). Returns cycles completed."""
    samples: tuple[float, ...] = ()
    completed = 0
    while max_cycles is None or completed < max_cycles:
        started = clock()
        ts, record, samples = run_cycle(interval_s, samples, checker=checker)
        try:
            append_record(data_dir, record, ts)
        except OSError as exc:
            # Keep measuring (e.g. disk briefly full or file locked by antivirus);
            # this cycle is lost and the console says so.
            out(f"{record['ts']}  WARNING: cycle not saved ({type(exc).__name__})")
        else:
            uploader.upload_pending(data_dir)
            out(status_line(record))
        completed += 1
        if max_cycles is not None and completed >= max_cycles:
            break
        sleep(max(0.0, interval_s - (clock() - started)))
    return completed
