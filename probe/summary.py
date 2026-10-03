"""Group a day's cycles into outage periods."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from probe.classify import OK
from probe.storage import TS_FORMAT

NO_DATA = "no_data"

# A gap longer than this many intervals means the probe was not running
# (it keeps logging locally during a blackout, so silence is not an outage).
GAP_FACTOR = 3

DEFAULT_INTERVAL_S = 60


@dataclass(frozen=True)
class Period:
    start: datetime
    end: datetime
    classification: str
    cycles: int
    # True when the period was still going when the log ended or the probe
    # stopped, so the real duration is at least `duration`.
    open_ended: bool

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, TS_FORMAT).replace(tzinfo=timezone.utc)


def group_periods(records: Sequence[dict]) -> tuple[Period, ...]:
    """Consecutive non-ok cycles with the same classification form one period.

    A period starts at its first failing cycle and ends at the first cycle that
    shows a different state. Gaps in the log become no_data periods.
    """
    ordered = sorted(records, key=lambda r: r["ts"])
    periods: list[Period] = []
    run_start: datetime | None = None
    run_class: str | None = None
    run_cycles = 0
    prev_ts: datetime | None = None
    prev_interval = DEFAULT_INTERVAL_S

    for record in ordered:
        ts = parse_ts(record["ts"])
        classification = record["classification"]
        gap = prev_ts is not None and (ts - prev_ts).total_seconds() > GAP_FACTOR * prev_interval

        if run_class is not None and (gap or classification != run_class):
            end = prev_ts if gap else ts
            periods.append(Period(run_start, end, run_class, run_cycles, open_ended=gap))
            run_class = None
        if gap:
            periods.append(Period(prev_ts, ts, NO_DATA, 0, open_ended=False))
        if classification != OK and run_class is None:
            run_start, run_class, run_cycles = ts, classification, 0
        if run_class is not None:
            run_cycles += 1

        prev_ts = ts
        prev_interval = record.get("interval_s", DEFAULT_INTERVAL_S)

    if run_class is not None:
        periods.append(Period(run_start, prev_ts, run_class, run_cycles, open_ended=True))
    return tuple(periods)


def _format_duration(period: Period) -> str:
    total = int(period.duration.total_seconds())
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    text = f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{text}+" if period.open_ended else text


def format_summary(day: str, records: Sequence[dict], skipped_lines: int) -> str:
    periods = group_periods(records)
    counts = Counter(r["classification"] for r in records)
    by_class = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    lines = [
        f"Summary for {day} (UTC): {len(records)} cycles ({by_class or 'none'})",
    ]
    if skipped_lines:
        lines.append(f"Warning: {skipped_lines} unreadable line(s) skipped (e.g. a write cut off by power loss).")
    if not periods:
        lines.append("No outage periods: every recorded cycle was ok.")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"{'START (UTC)':<22}{'END (UTC)':<22}{'DURATION':<11}{'CLASSIFICATION':<16}CYCLES")
    for period in periods:
        lines.append(
            f"{period.start:%Y-%m-%d %H:%M:%S}   "
            f"{period.end:%Y-%m-%d %H:%M:%S}   "
            f"{_format_duration(period):<11}"
            f"{period.classification:<16}"
            f"{period.cycles}"
        )
    if any(p.open_ended for p in periods):
        lines.append("")
        lines.append("+ = still failing when the log ends or the probe stopped; the real duration is at least this.")
    return "\n".join(lines)
