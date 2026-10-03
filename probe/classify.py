"""Pure classification of one cycle. No I/O, so every branch is unit-testable."""

from dataclasses import dataclass
from statistics import median
from typing import Sequence

OK = "ok"
DEGRADED = "degraded"
DNS_FAIL = "dns_fail"
TCP_FAIL = "tcp_fail"
HTTP_FAIL = "http_fail"
OFFLINE = "offline"

CLASSIFICATIONS: tuple[str, ...] = (OK, DEGRADED, DNS_FAIL, TCP_FAIL, HTTP_FAIL, OFFLINE)

# "Well above baseline" means BOTH at least 3x the baseline AND at least 100 ms
# slower, so a fast link's normal jitter (e.g. 10 ms -> 35 ms) is not flagged.
DEGRADED_FACTOR = 3.0
DEGRADED_MIN_EXTRA_MS = 100.0

MIN_BASELINE_SAMPLES = 5
MAX_BASELINE_SAMPLES = 30


@dataclass(frozen=True)
class LayerOutcome:
    """A layer is up if at least one of its targets succeeded."""

    dns_ok: bool
    tcp_ok: bool
    http_ok: bool
    latency_ms: float | None


def classify(outcome: LayerOutcome, baseline_ms: float | None) -> str:
    """Name the lowest failing layer, or check latency if every layer is up.

    The lower layers are checked first because the higher ones depend on them:
    HTTP needs DNS and TCP, so a DNS failure explains a following HTTP failure.
    """
    if not (outcome.dns_ok or outcome.tcp_ok or outcome.http_ok):
        return OFFLINE
    if not outcome.dns_ok:
        return DNS_FAIL
    if not outcome.tcp_ok:
        return TCP_FAIL
    if not outcome.http_ok:
        return HTTP_FAIL
    if is_degraded(outcome.latency_ms, baseline_ms):
        return DEGRADED
    return OK


def is_degraded(latency_ms: float | None, baseline_ms: float | None) -> bool:
    if latency_ms is None or baseline_ms is None:
        return False
    threshold = max(baseline_ms * DEGRADED_FACTOR, baseline_ms + DEGRADED_MIN_EXTRA_MS)
    return latency_ms > threshold


def rolling_baseline(samples: Sequence[float]) -> float | None:
    """Median latency of recent ok cycles, or None until there are enough of them."""
    if len(samples) < MIN_BASELINE_SAMPLES:
        return None
    return round(median(samples), 1)


def update_samples(
    samples: tuple[float, ...], classification: str, latency_ms: float | None
) -> tuple[float, ...]:
    """Return the new baseline window. Only ok cycles count, so a slow period
    cannot drag the baseline up and hide itself."""
    if classification != OK or latency_ms is None:
        return samples
    return (*samples, latency_ms)[-MAX_BASELINE_SAMPLES:]
