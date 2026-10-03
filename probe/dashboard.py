"""Self-contained HTML dashboard built from the local logs.

One file, inline SVG charts, no JavaScript and no external resources, so it
opens offline in any browser and can be archived next to the data it shows.
"""

import html
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Sequence

from probe.classify import DEGRADED, DNS_FAIL, HTTP_FAIL, OFFLINE, OK, TCP_FAIL
from probe.storage import read_records
from probe.summary import DEFAULT_INTERVAL_S, GAP_FACTOR, NO_DATA, Period, format_duration, group_periods, parse_ts

STATUS_ORDER = (OK, DEGRADED, HTTP_FAIL, TCP_FAIL, DNS_FAIL, OFFLINE, NO_DATA)
STATUS_LABELS = {
    OK: "ok",
    DEGRADED: "degraded (slow)",
    HTTP_FAIL: "HTTP fail",
    TCP_FAIL: "TCP fail",
    DNS_FAIL: "DNS fail",
    OFFLINE: "offline",
    NO_DATA: "no data",
}
OUTAGE_CLASSES = (HTTP_FAIL, TCP_FAIL, DNS_FAIL, OFFLINE)
OTHER = "other"  # CSS class for a classification this version does not know
# Higher = worse. A timeline column shows the worst status that occurred in it.
SEVERITY = {OK: 1, DEGRADED: 3, HTTP_FAIL: 4, TCP_FAIL: 5, DNS_FAIL: 6, OFFLINE: 7}
UNKNOWN_SEVERITY = 2
TIMELINE_COLUMNS = 1000
EDGE_LABEL_MARGIN = 40

CHART_WIDTH = 1000
TIMELINE_HEIGHT = 46
LATENCY_HEIGHT = 220
AXIS_HEIGHT = 22
LATENCY_PAD_TOP = 16
TICK_STEPS_MIN = (5, 10, 15, 30, 60, 180, 360, 720, 1440, 2880, 4320, 10080)
MAX_TICKS = 12


@dataclass(frozen=True)
class LoadedLogs:
    records: tuple[dict, ...]
    skipped_lines: int
    missing_days: tuple[str, ...]
    first_day: date
    last_day: date


@dataclass(frozen=True)
class TargetStat:
    layer: str
    target: str
    attempts: int
    successes: int
    median_ms: float | None

    @property
    def success_pct(self) -> float:
        return 100.0 * self.successes / self.attempts if self.attempts else 0.0


@dataclass(frozen=True)
class Headline:
    cycles: int
    ok_pct: float
    outages: int
    outage_seconds: int
    slowdowns: int
    median_latency_ms: float | None
    coverage_pct: float


# ------------------------------------------------------------------ load ---

def load_days(data_dir: Path, last_day: date, days: int) -> LoadedLogs:
    first_day = last_day - timedelta(days=days - 1)
    records: list[dict] = []
    skipped = 0
    missing: list[str] = []
    for offset in range(days):
        day = (first_day + timedelta(days=offset)).isoformat()
        path = data_dir / f"{day}.jsonl"
        if not path.exists():
            missing.append(day)
            continue
        result = read_records(path)
        records.extend(result.records)
        skipped += result.skipped_lines
    ordered = tuple(sorted(records, key=lambda r: r["ts"]))
    return LoadedLogs(ordered, skipped, tuple(missing), first_day, last_day)


# ---------------------------------------------------------------- compute ---

def interval_of(record: dict) -> int:
    return int(record.get("interval_s", DEFAULT_INTERVAL_S))


def headline(records: Sequence[dict], periods: Sequence[Period]) -> Headline:
    counts = Counter(r["classification"] for r in records)
    outages = [p for p in periods if p.classification in OUTAGE_CLASSES]
    latencies = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
    span_s = time_span_seconds(records)
    covered_s = sum(interval_of(r) for r in records)
    return Headline(
        cycles=len(records),
        ok_pct=100.0 * counts[OK] / len(records) if records else 0.0,
        outages=len(outages),
        outage_seconds=sum(interval_of(r) for r in records if r["classification"] in OUTAGE_CLASSES),
        slowdowns=sum(1 for p in periods if p.classification == DEGRADED),
        median_latency_ms=round(median(latencies), 1) if latencies else None,
        coverage_pct=min(100.0, 100.0 * covered_s / span_s) if span_s else 0.0,
    )


def time_span_seconds(records: Sequence[dict]) -> float:
    if not records:
        return 0.0
    start = parse_ts(records[0]["ts"])
    end = parse_ts(records[-1]["ts"]) + timedelta(seconds=interval_of(records[-1]))
    return (end - start).total_seconds()


def target_stats(records: Sequence[dict]) -> tuple[TargetStat, ...]:
    """Success rate per DNS resolver (all names together), TCP target and HTTP URL."""
    attempts: dict[tuple[str, str], int] = defaultdict(int)
    successes: dict[tuple[str, str], int] = defaultdict(int)
    times: dict[tuple[str, str], list[float]] = defaultdict(list)
    for record in records:
        for layer, field in (("DNS", "resolver"), ("TCP", "target"), ("HTTP", "url")):
            checks = record.get(layer.lower())
            # A hand-edited or damaged line must not abort the whole dashboard.
            for check in checks if isinstance(checks, list) else []:
                if not isinstance(check, dict):
                    continue
                key = (layer, str(check.get(field, "?")))
                attempts[key] += 1
                if check.get("ok") is True:
                    successes[key] += 1
                    ms = check.get("ms")
                    if isinstance(ms, (int, float)) and not isinstance(ms, bool):
                        times[key].append(float(ms))
    return tuple(
        TargetStat(layer, target, attempts[(layer, target)], successes[(layer, target)],
                   round(median(times[(layer, target)]), 1) if times[(layer, target)] else None)
        for layer, target in sorted(attempts, key=lambda k: (("DNS", "TCP", "HTTP").index(k[0]), k[1]))
    )


# ------------------------------------------------------------------- svg ---

def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def css_class(status: str) -> str:
    return status if status in STATUS_LABELS else OTHER


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, f"other ({status})")


class TimeScale:
    def __init__(self, start: datetime, end: datetime, width: float = CHART_WIDTH) -> None:
        self.start = start
        self.seconds = max((end - start).total_seconds(), 1.0)
        self.width = width

    def x(self, moment: datetime) -> float:
        return round((moment - self.start).total_seconds() / self.seconds * self.width, 2)


def time_ticks(start: datetime, end: datetime) -> list[datetime]:
    minutes = max((end - start).total_seconds() / 60, 1)
    # Both ends can carry a tick, so a span of N steps has up to N + 1 ticks.
    step = next((m for m in TICK_STEPS_MIN if minutes / m <= MAX_TICKS - 1), TICK_STEPS_MIN[-1])
    # Ticks fall on whole multiples of the step (e.g. 06:15, 06:30 or 00:00, 06:00);
    # steps of a day or more fall on midnight UTC.
    align = min(step, 1440)
    first = start.replace(second=0, microsecond=0)
    first += timedelta(minutes=(-(first.hour * 60 + first.minute)) % align)
    if first < start:
        first += timedelta(minutes=align)
    ticks = []
    moment = first
    while moment <= end:
        ticks.append(moment)
        moment += timedelta(minutes=step)
    return ticks or [start]


def tick_label(moment: datetime, span_hours: float) -> str:
    if span_hours > 36:
        return moment.strftime("%b %d %H:%M") if moment.hour else moment.strftime("%b %d")
    return moment.strftime("%H:%M")


def axis_svg(scale: TimeScale, ticks: Sequence[datetime], top: float, height: float) -> str:
    span_hours = scale.seconds / 3600
    parts = []
    for tick in ticks:
        x = scale.x(tick)
        parts.append(f'<line class="grid" x1="{x}" y1="{top}" x2="{x}" y2="{top + height}"/>')
        anchor = "start" if x < EDGE_LABEL_MARGIN else "end" if x > CHART_WIDTH - EDGE_LABEL_MARGIN else "middle"
        parts.append(f'<text class="tick" x="{x}" y="{top + height + 15}" text-anchor="{anchor}">{esc(tick_label(tick, span_hours))}</text>')
    return "".join(parts)


def timeline_columns(records: Sequence[dict], start: datetime, end: datetime,
                     columns: int = TIMELINE_COLUMNS) -> list[str | None]:
    """Worst status per column (None = no record). Every cycle fills at least one
    column, so a single failed minute stays visible on a month-long timeline."""
    span = max((end - start).total_seconds(), 1.0)
    cells: list[str | None] = [None] * columns
    for record in records:
        status = record["classification"]
        offset = (parse_ts(record["ts"]) - start).total_seconds()
        first = min(columns - 1, max(0, int(offset / span * columns)))
        last = min(columns, max(first + 1, math.ceil((offset + interval_of(record)) / span * columns)))
        rank = SEVERITY.get(status, UNKNOWN_SEVERITY)
        for column in range(first, last):
            current = cells[column]
            if current is None or rank > SEVERITY.get(current, UNKNOWN_SEVERITY):
                cells[column] = status
    return cells


def timeline_svg(records: Sequence[dict]) -> str:
    start = parse_ts(records[0]["ts"])
    end = parse_ts(records[-1]["ts"]) + timedelta(seconds=interval_of(records[-1]))
    scale = TimeScale(start, end)
    cells = timeline_columns(records, start, end)
    column_s = scale.seconds / len(cells)
    column_w = CHART_WIDTH / len(cells)
    rects = []
    run_start = 0
    for column in range(1, len(cells) + 1):
        if column < len(cells) and cells[column] == cells[run_start]:
            continue
        status = cells[run_start]
        if status is not None:
            t0 = start + timedelta(seconds=run_start * column_s)
            t1 = start + timedelta(seconds=column * column_s)
            rects.append(
                f'<rect class="s-{esc(css_class(status))}" x="{round(run_start * column_w, 2)}" y="0" '
                f'width="{round((column - run_start) * column_w, 2)}" height="{TIMELINE_HEIGHT}">'
                f'<title>{t0:%Y-%m-%d %H:%M} to {t1:%H:%M} UTC: {esc(status_label(status))}</title></rect>'
            )
        run_start = column
    total_h = TIMELINE_HEIGHT + AXIS_HEIGHT
    return (
        f'<svg viewBox="0 0 {CHART_WIDTH} {total_h}" shape-rendering="crispEdges" role="img" aria-label="Status of every cycle over time">'
        f'<rect class="s-{NO_DATA}" x="0" y="0" width="{CHART_WIDTH}" height="{TIMELINE_HEIGHT}"/>'
        + "".join(rects)
        + axis_svg(scale, time_ticks(start, end), 0, TIMELINE_HEIGHT)
        + "</svg>"
    )


def latency_ceiling(values: Sequence[float]) -> float:
    """Top of the y axis: 1.5x the 95th percentile, so one spike does not flatten the chart."""
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return max(10.0, round(p95 * 1.5, -1) or 10.0)


def latency_svg(records: Sequence[dict]) -> tuple[str, float]:
    start = parse_ts(records[0]["ts"])
    end = parse_ts(records[-1]["ts"]) + timedelta(seconds=interval_of(records[-1]))
    scale = TimeScale(start, end)
    values = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
    ceiling = latency_ceiling(values) if values else 100.0

    def y(ms: float) -> float:
        return round(LATENCY_PAD_TOP + LATENCY_HEIGHT - min(ms, ceiling) / ceiling * LATENCY_HEIGHT, 2)

    lines: list[list[str]] = [[]]
    baseline: list[list[str]] = [[]]
    previous: dict | None = None
    for record in records:
        if previous is not None:
            gap = (parse_ts(record["ts"]) - parse_ts(previous["ts"])).total_seconds()
            if gap > GAP_FACTOR * interval_of(previous):
                lines.append([])
                baseline.append([])
        x = scale.x(parse_ts(record["ts"]))
        if record.get("latency_ms") is not None:
            lines[-1].append(f"{x},{y(record['latency_ms'])}")
        elif lines[-1]:
            lines.append([])  # no measurement: do not draw a line across it
        if record.get("baseline_ms") is not None:
            baseline[-1].append(f"{x},{y(record['baseline_ms'])}")
        previous = record

    grid = []
    labels = []
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        ms = ceiling * fraction
        gy = y(ms)
        grid.append(f'<line class="grid" x1="0" y1="{gy}" x2="{CHART_WIDTH}" y2="{gy}"/>')
        labels.append(f'<text class="tick y-label" x="4" y="{gy - 3}">{ms:g} ms</text>')
    paths = "".join(f'<polyline class="lat" points="{" ".join(p)}"/>' for p in lines if len(p) > 1)
    dots = "".join(f'<circle class="lat-dot" cx="{p[0].split(",")[0]}" cy="{p[0].split(",")[1]}" r="2"/>' for p in lines if len(p) == 1)
    base = "".join(f'<polyline class="base" points="{" ".join(p)}"/>' for p in baseline if len(p) > 1)
    total_h = LATENCY_PAD_TOP + LATENCY_HEIGHT + AXIS_HEIGHT
    svg = (
        f'<svg viewBox="0 0 {CHART_WIDTH} {total_h}" role="img" aria-label="TCP connect latency over time">'
        + "".join(grid) + base + paths + dots
        + axis_svg(scale, time_ticks(start, end), LATENCY_PAD_TOP, LATENCY_HEIGHT)
        + "".join(labels)
        + "</svg>"
    )
    return svg, ceiling


# ------------------------------------------------------------------ html ---

def tile(label: str, value: str, note: str = "") -> str:
    return (f'<div class="tile"><div class="tile-label">{esc(label)}</div>'
            f'<div class="tile-value">{esc(value)}</div><div class="tile-note">{esc(note)}</div></div>')


def tiles_html(head: Headline) -> str:
    latency = f"{head.median_latency_ms:g} ms" if head.median_latency_ms is not None else "-"
    return '<section class="tiles">' + "".join((
        tile("Cycles recorded", f"{head.cycles:,}"),
        tile("Fully ok", f"{head.ok_pct:.1f}%", "of recorded cycles"),
        tile("Outages", str(head.outages), format_duration_seconds(head.outage_seconds) + " of failing cycles" if head.outages else "none"),
        tile("Slowdowns", str(head.slowdowns), "periods marked degraded"),
        tile("Median latency", latency, "TCP connect"),
        tile("Data coverage", f"{head.coverage_pct:.1f}%", "between first and last record"),
    )) + "</section>"


def format_duration_seconds(seconds: int) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def legend_html() -> str:
    items = "".join(f'<span class="key"><span class="swatch s-{s}"></span>{esc(STATUS_LABELS[s])}</span>' for s in STATUS_ORDER)
    return f'<div class="legend">{items}</div>'


def targets_html(stats: Sequence[TargetStat]) -> str:
    rows = "".join(
        f"<tr><td>{esc(s.layer)}</td><td>{esc(s.target)}</td><td class=num>{s.successes:,} / {s.attempts:,}</td>"
        f'<td class=num><span class="{"good" if s.success_pct >= 99 else "warn" if s.success_pct >= 90 else "bad"}">{s.success_pct:.1f}%</span></td>'
        f"<td class=num>{f'{s.median_ms:g} ms' if s.median_ms is not None else '-'}</td></tr>"
        for s in stats
    )
    return ("<div class=table-wrap><table><thead><tr><th>Layer</th><th>Resolver / target</th><th class=num>Succeeded</th>"
            f"<th class=num>Success</th><th class=num>Median time</th></tr></thead><tbody>{rows}</tbody></table></div>")


def periods_html(periods: Sequence[Period]) -> str:
    if not periods:
        return '<p class="empty">No outages, slowdowns or gaps: every recorded cycle was ok.</p>'
    rows = "".join(
        f'<tr><td><span class="swatch s-{esc(css_class(p.classification))}"></span>{esc(status_label(p.classification))}</td>'
        f"<td>{p.start:%Y-%m-%d %H:%M}</td><td>{p.end:%Y-%m-%d %H:%M}</td>"
        f"<td class=num>{esc(format_duration(p))}</td><td class=num>{p.cycles}</td></tr>"
        for p in periods
    )
    return ("<div class=table-wrap><table><thead><tr><th>What</th><th>Start (UTC)</th><th>End (UTC)</th><th class=num>Duration</th>"
            f"<th class=num>Cycles</th></tr></thead><tbody>{rows}</tbody></table></div>"
            '<p class="note">A duration ending in + was still ongoing when the log ended or the probe stopped. '
            "No data means the probe was not running (e.g. power cut), which is not the same as an outage.</p>")


def render(logs: LoadedLogs, generated_at: datetime) -> str:
    records = logs.records
    periods = group_periods(records)
    head = headline(records, periods)
    days = (f"{logs.first_day.isoformat()} to {logs.last_day.isoformat()}"
            if logs.first_day != logs.last_day else logs.first_day.isoformat())
    latency_chart, ceiling = latency_svg(records)
    warnings = []
    if logs.missing_days:
        warnings.append(f"No log file for: {', '.join(logs.missing_days)}.")
    if logs.skipped_lines:
        warnings.append(f"{logs.skipped_lines} unreadable line(s) skipped (e.g. a write cut off by power loss).")
    warning_html = "".join(f'<p class="warning">{esc(w)}</p>' for w in warnings)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Probe dashboard {esc(days)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<header>
<h1>Probe dashboard</h1>
<p class="sub">Bangladesh Network Interference Observatory &middot; v0 connectivity logger &middot; {esc(days)} (UTC)</p>
<p class="sub">One probe, local logs only. Generated {generated_at:%Y-%m-%d %H:%M} UTC.</p>
{warning_html}
</header>
{tiles_html(head)}
<section>
<h2>Status of every cycle</h2>
{legend_html()}
<div class="chart">{timeline_svg(records)}</div>
</section>
<section>
<h2>TCP connect latency</h2>
<p class="note"><span class="line-key lat-key"></span>median TCP connect time per cycle
<span class="line-key base-key"></span>rolling baseline. Values above {ceiling:g} ms are drawn at the top.</p>
<div class="chart">{latency_chart}</div>
</section>
<section>
<h2>Success by resolver and target</h2>
{targets_html(target_stats(records))}
</section>
<section>
<h2>Outages, slowdowns and gaps</h2>
{periods_html(periods)}
</section>
<footer>
<p>Each cycle checks DNS (3 public resolvers + the system resolver), TCP to 3 addresses and HTTP to 2 test URLs.
The log records only timestamps, targets, results and timings: no IP address, hostname, username, Wi-Fi name or location of the host.
See docs/PROBE.md.</p>
</footer>
</main>
</body>
</html>
"""


CSS = """
:root{--bg:#f7f7f5;--card:#fff;--text:#1d2125;--muted:#5f6b76;--line:#e3e5e8;
--ok:#2f9e5d;--degraded:#e0a400;--http:#f08c3a;--tcp:#d9480f;--dns:#8e44ad;--offline:#c92a2a;--nodata:#d5d8dc;
--lat:#1971c2;--base:#868e96}
@media (prefers-color-scheme:dark){:root{--bg:#141618;--card:#1d2023;--text:#e9ecef;--muted:#9aa4ae;--line:#30353a;
--nodata:#3a3f44;--lat:#4dabf7;--base:#adb5bd}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 48px}
h1{margin:0 0 4px;font-size:26px}h2{font-size:17px;margin:0 0 10px}
.sub,.note,.empty,footer{color:var(--muted)}.sub{margin:2px 0}.note{font-size:13px}
.warning{background:#fff3bf;color:#5c4400;padding:8px 12px;border-radius:6px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-top:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;background:none;border:0;padding:0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile-label{font-size:13px;color:var(--muted)}.tile-value{font-size:24px;font-weight:650;margin:2px 0}
.tile-note{font-size:12px;color:var(--muted);min-height:1em}
.chart,.table-wrap{overflow-x:auto}
.chart svg{width:100%;min-width:640px;height:auto;display:block}
.grid{stroke:var(--line);stroke-width:1}.tick{fill:var(--muted);font-size:13px}
.y-label{paint-order:stroke;stroke:var(--card);stroke-width:4px;stroke-linejoin:round}
.s-ok{fill:var(--ok);background:var(--ok)}.s-degraded{fill:var(--degraded);background:var(--degraded)}
.s-http_fail{fill:var(--http);background:var(--http)}.s-tcp_fail{fill:var(--tcp);background:var(--tcp)}
.s-dns_fail{fill:var(--dns);background:var(--dns)}.s-offline{fill:var(--offline);background:var(--offline)}
.s-no_data{fill:var(--nodata);background:var(--nodata)}.s-other{fill:var(--muted);background:var(--muted)}
.lat{fill:none;stroke:var(--lat);stroke-width:1.4}.lat-dot{fill:var(--lat)}
.base{fill:none;stroke:var(--base);stroke-width:1.4;stroke-dasharray:5 4}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;margin-bottom:8px}
.key{display:inline-flex;align-items:center;gap:6px}
.swatch{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.line-key{display:inline-block;width:22px;height:0;border-top:2px solid var(--lat);margin:0 6px 3px 10px}
.base-key{border-top:2px dashed var(--base)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:600}
.num{text-align:right;font-variant-numeric:tabular-nums}
.good{color:var(--ok)}.warn{color:var(--degraded)}.bad{color:var(--offline)}
footer{font-size:13px;margin-top:20px}
@media (max-width:600px){.tile-value{font-size:20px}th,td{padding:5px 4px}}
"""


def write_dashboard(logs: LoadedLogs, out_path: Path, generated_at: datetime | None = None) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    moment = generated_at or datetime.now(timezone.utc)
    out_path.write_text(render(logs, moment), encoding="utf-8")
    return out_path
