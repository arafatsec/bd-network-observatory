import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser

import pytest

from probe.cli import main
from probe.dashboard import (
    LoadedLogs, headline, latency_ceiling, latency_svg, load_days, render, target_stats, time_ticks,
    timeline_columns, write_dashboard,
)
from probe.storage import append_record
from probe.summary import group_periods, parse_ts

GENERATED = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def rec(minute: int, classification: str = "ok", latency: float | None = 20.0, *, hour: int = 5,
        day: int = 3, baseline: float | None = 20.0, dns_ok: bool = True) -> dict:
    return {
        "v": 1, "ts": f"2026-10-{day:02d}T{hour:02d}:{minute:02d}:00Z", "interval_s": 60,
        "classification": classification, "latency_ms": latency, "baseline_ms": baseline,
        "dns": [{"resolver": "1.1.1.1", "name": "example.com", "ok": dns_ok, "ms": 10.0 if dns_ok else None,
                 "answers": [], "error": None if dns_ok else "Timeout"},
                {"resolver": "system", "name": "example.com", "ok": True, "ms": 1.0, "answers": [], "error": None}],
        "tcp": [{"target": "1.1.1.1:443", "ok": latency is not None, "ms": latency, "error": None}],
        "http": [{"url": "https://cp.cloudflare.com/generate_204", "ok": True, "status": 204, "ms": 50.0, "error": None}],
    }


def logs_of(records, missing=(), skipped=0) -> LoadedLogs:
    ordered = tuple(sorted(records, key=lambda r: r["ts"]))
    return LoadedLogs(ordered, skipped, tuple(missing), date(2026, 10, 3), date(2026, 10, 3))


class StrictParser(HTMLParser):
    """Fails on mismatched tags, so broken markup is caught."""

    VOID = {"meta", "br", "img", "input", "link", "hr", "rect", "line", "circle", "polyline"}

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        assert self.stack and self.stack[-1] == tag, f"unexpected </{tag}>, open: {self.stack[-3:]}"
        self.stack.pop()


def assert_well_formed(page: str) -> None:
    parser = StrictParser()
    parser.feed(page.split("<!doctype html>", 1)[1])
    assert parser.stack == [], f"unclosed tags: {parser.stack}"


def test_headline_numbers():
    records = [rec(0), rec(1, "offline", None), rec(2, "offline", None), rec(3), rec(4, "degraded", 500.0), rec(5)]
    head = headline(records, group_periods(records))
    assert head.cycles == 6
    assert head.ok_pct == pytest.approx(50.0)
    assert (head.outages, head.outage_seconds) == (1, 120)
    assert head.slowdowns == 1
    assert head.median_latency_ms == 20.0
    assert head.coverage_pct == pytest.approx(100.0)


def test_coverage_counts_gaps():
    records = [rec(0), rec(1), rec(30), rec(31)]  # 4 cycles over a 32-minute span
    head = headline(records, group_periods(records))
    assert head.coverage_pct == pytest.approx(4 / 32 * 100)


def test_target_stats_group_by_resolver_and_target():
    stats = {(s.layer, s.target): s for s in target_stats([rec(0), rec(1, dns_ok=False), rec(2)])}
    assert set(stats) == {("DNS", "1.1.1.1"), ("DNS", "system"), ("TCP", "1.1.1.1:443"),
                          ("HTTP", "https://cp.cloudflare.com/generate_204")}
    assert (stats[("DNS", "1.1.1.1")].successes, stats[("DNS", "1.1.1.1")].attempts) == (2, 3)
    assert stats[("DNS", "1.1.1.1")].success_pct == pytest.approx(200 / 3)
    assert stats[("TCP", "1.1.1.1:443")].median_ms == 20.0


def test_latency_ceiling_ignores_single_spike():
    assert latency_ceiling([20.0] * 99 + [5000.0]) == 30.0
    assert latency_ceiling([0.5, 1.0]) == 10.0


@pytest.mark.parametrize(("start", "end", "first", "count_max"), [
    ("2026-10-03T06:18:00Z", "2026-10-03T06:36:00Z", "06:20", 12),
    ("2026-10-03T05:00:00Z", "2026-10-03T06:00:00Z", "05:00", 12),
    ("2026-10-03T05:17:00Z", "2026-10-04T05:17:00Z", "06:00", 12),
    ("2026-10-03T06:18:00Z", "2026-10-10T06:18:00Z", "2026-10-04 00:00", 12),
])
def test_time_ticks_are_aligned_and_few(start, end, first, count_max):
    ticks = time_ticks(parse_ts(start), parse_ts(end))
    assert 1 <= len(ticks) <= count_max
    assert first in ticks[0].strftime("%Y-%m-%d %H:%M")
    assert all(parse_ts(start) <= t <= parse_ts(end) for t in ticks)


def periods_table(page: str) -> str:
    return page.split("<h2>Outages, slowdowns and gaps</h2>", 1)[1]


def timeline_part(page: str) -> str:
    return page.split("<h2>Status of every cycle</h2>", 1)[1].split("<h2>", 1)[0]


def test_render_is_well_formed_and_complete():
    records = [rec(m) for m in range(5)] + [rec(5, "dns_fail", 20.0, dns_ok=False), rec(6, "offline", None),
                                            rec(40), rec(41, "degraded", 400.0), rec(42)]
    page = render(logs_of(records), GENERATED)
    assert_well_formed(page)
    for heading in ("Status of every cycle", "TCP connect latency", "Success by resolver and target",
                    "Outages, slowdowns and gaps"):
        assert heading in page
    table = periods_table(page)
    for label, start, end in (("DNS fail", "05:05", "05:06"), ("offline", "05:06", "05:06"),
                              ("no data", "05:06", "05:40"), ("degraded (slow)", "05:41", "05:42")):
        assert re.search(rf"{re.escape(label)}</td><td>2026-10-03 {start}</td><td>2026-10-03 {end}</td>", table), label
    timeline = timeline_part(page)
    for status in ("ok", "dns_fail", "offline", "degraded"):
        assert f'<rect class="s-{status}"' in timeline, status
    assert "<script" not in page.lower()
    assert not re.search(r'(src|href)="https?://', page)  # nothing loaded from the internet


def test_single_failed_minute_is_visible_on_a_week_timeline():
    records = [rec(m % 60, hour=(m // 60) % 24, day=3 + m // 1440) for m in range(7 * 1440)]
    records[5000] = rec(5000 % 60, "offline", None, hour=(5000 // 60) % 24, day=3 + 5000 // 1440)
    timeline = timeline_part(render(logs_of(records), GENERATED))
    match = re.search(r'<rect class="s-offline" x="[\d.]+" y="0" width="([\d.]+)"', timeline)
    assert match, "offline minute missing from the timeline"
    assert float(match.group(1)) >= 1.0  # at least one full column out of 1000


def test_worst_status_wins_a_shared_column():
    records = [rec(0), rec(1, "degraded", 300.0), rec(2, "dns_fail", dns_ok=False), rec(3)]
    start, end = parse_ts(records[0]["ts"]), parse_ts(records[-1]["ts"])
    assert set(timeline_columns(records, start, end, columns=1)) == {"dns_fail"}


def test_latency_line_breaks_where_latency_is_missing():
    records = [rec(0), rec(1), rec(2, "tcp_fail", None), rec(3, "tcp_fail", None), rec(4), rec(5)]
    svg, _ = latency_svg(records)
    assert svg.count('class="lat"') == 2  # two separate pieces, nothing drawn across the outage


def test_latency_line_breaks_at_time_gaps():
    svg, _ = latency_svg([rec(0), rec(1), rec(30), rec(31)])
    assert svg.count('class="lat"') == 2


def test_outage_at_end_of_log_counts_its_cycles():
    records = [rec(0), rec(1), rec(2, "offline", None)]
    head = headline(records, group_periods(records))
    assert (head.outages, head.outage_seconds) == (1, 60)


def test_unknown_classification_gets_a_visible_fallback():
    page = render(logs_of([rec(0), rec(1, "weird_new_state"), rec(2)]), GENERATED)
    assert '<rect class="s-other"' in timeline_part(page)
    assert "other (weird_new_state)" in periods_table(page)


def test_damaged_check_fields_do_not_crash():
    broken = rec(1)
    broken["tcp"] = None
    broken["dns"] = ["not a dict", {"resolver": "1.1.1.1", "ok": True, "ms": "fast"}]
    stats = {(s.layer, s.target): s for s in target_stats([rec(0), broken])}
    assert stats[("DNS", "1.1.1.1")].attempts == 2
    assert stats[("TCP", "1.1.1.1:443")].attempts == 1
    assert_well_formed(render(logs_of([rec(0), broken]), GENERATED))


def test_very_short_span_still_has_a_time_label():
    start = parse_ts("2026-10-03T06:18:00Z")
    assert time_ticks(start, parse_ts("2026-10-03T06:19:00Z")) == [start]


def test_render_escapes_untrusted_log_text():
    evil = rec(0)
    evil["tcp"][0]["target"] = '<script>alert(1)</script>'
    evil["classification"] = 'ok"><img src=x onerror=alert(1)>'
    page = render(logs_of([evil, rec(1)]), GENERATED)
    assert "<script>alert(1)" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_render_handles_all_ok_with_no_latency_at_all():
    page = render(logs_of([rec(0, latency=None, baseline=None), rec(1, latency=None, baseline=None)]), GENERATED)
    assert "every recorded cycle was ok" in page
    assert 'class="lat"' not in page
    assert_well_formed(page)


def test_render_single_record():
    page = render(logs_of([rec(0)]), GENERATED)
    assert_well_formed(page)
    assert '<rect class="s-ok"' in timeline_part(page)


def test_render_reports_missing_days_and_skipped_lines():
    page = render(logs_of([rec(0), rec(1)], missing=("2026-10-04",), skipped=2), GENERATED)
    assert "No log file for: 2026-10-04" in page
    assert "2 unreadable line(s)" in page


def test_load_days_reads_a_range_and_lists_missing(tmp_path):
    for day in (3, 5):
        for minute in (0, 1):
            r = rec(minute, day=day)
            append_record(tmp_path, r, parse_ts(r["ts"]))
    logs = load_days(tmp_path, date(2026, 10, 5), 3)
    assert len(logs.records) == 4
    assert logs.missing_days == ("2026-10-04",)
    assert logs.records[0]["ts"] < logs.records[-1]["ts"]


def test_write_dashboard_creates_file(tmp_path):
    out = write_dashboard(logs_of([rec(0), rec(1)]), tmp_path / "sub" / "d.html", GENERATED)
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_cli_dashboard_default_name(tmp_path, capsys):
    for minute in (0, 1, 2):
        r = rec(minute)
        append_record(tmp_path, r, parse_ts(r["ts"]))
    assert main(["dashboard", "--date", "2026-10-03", "--data-dir", str(tmp_path)]) == 0
    assert (tmp_path / "dashboard-2026-10-03.html").exists()
    assert "3 cycles" in capsys.readouterr().out


def test_cli_dashboard_range_name_and_out(tmp_path):
    r = rec(0)
    append_record(tmp_path, r, parse_ts(r["ts"]))
    assert main(["dashboard", "--date", "2026-10-04", "--days", "2", "--data-dir", str(tmp_path)]) == 0
    assert (tmp_path / "dashboard-2026-10-03_2026-10-04.html").exists()
    custom = tmp_path / "x.html"
    assert main(["dashboard", "--date", "2026-10-03", "--data-dir", str(tmp_path), "--out", str(custom)]) == 0
    assert custom.exists()


def test_cli_dashboard_without_data(tmp_path, capsys):
    assert main(["dashboard", "--date", "2026-10-03", "--data-dir", str(tmp_path)]) == 1
    assert "No log data" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "32", "x"])
def test_cli_dashboard_rejects_bad_days(value, capsys):
    with pytest.raises(SystemExit):
        main(["dashboard", "--days", value])
    assert "days must" in capsys.readouterr().err
