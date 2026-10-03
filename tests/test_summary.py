from datetime import timedelta

from probe.summary import NO_DATA, format_summary, group_periods, parse_ts


def rec(minute: int, classification: str, interval_s: int = 60, hour: int = 5) -> dict:
    return {"ts": f"2026-10-03T{hour:02d}:{minute:02d}:00Z", "classification": classification, "interval_s": interval_s}


def test_all_ok_has_no_periods():
    assert group_periods([rec(m, "ok") for m in range(10)]) == ()


def test_outage_runs_from_first_failure_to_recovery():
    records = [rec(0, "ok"), rec(1, "offline"), rec(2, "offline"), rec(3, "offline"), rec(4, "ok")]
    (period,) = group_periods(records)
    assert period.classification == "offline"
    assert period.start == parse_ts("2026-10-03T05:01:00Z")
    assert period.end == parse_ts("2026-10-03T05:04:00Z")
    assert period.duration == timedelta(minutes=3)
    assert period.cycles == 3
    assert not period.open_ended


def test_change_of_failure_type_starts_a_new_period():
    records = [rec(0, "dns_fail"), rec(1, "dns_fail"), rec(2, "offline"), rec(3, "ok")]
    first, second = group_periods(records)
    assert (first.classification, first.cycles, first.end) == ("dns_fail", 2, parse_ts("2026-10-03T05:02:00Z"))
    assert (second.classification, second.cycles, second.duration) == ("offline", 1, timedelta(minutes=1))


def test_separate_outages_of_same_type_stay_separate():
    records = [rec(0, "tcp_fail"), rec(1, "ok"), rec(2, "tcp_fail"), rec(3, "ok")]
    assert [p.cycles for p in group_periods(records)] == [1, 1]


def test_degraded_is_reported_as_a_period():
    records = [rec(0, "ok"), rec(1, "degraded"), rec(2, "degraded"), rec(3, "ok")]
    (period,) = group_periods(records)
    assert (period.classification, period.cycles) == ("degraded", 2)


def test_outage_still_running_at_end_of_log_is_open_ended():
    records = [rec(0, "ok"), rec(1, "http_fail"), rec(2, "http_fail")]
    (period,) = group_periods(records)
    assert period.open_ended
    assert period.end == parse_ts("2026-10-03T05:02:00Z")


def test_gap_in_log_is_no_data_not_outage():
    records = [rec(0, "ok"), rec(1, "ok"), rec(30, "ok")]
    (gap,) = group_periods(records)
    assert gap.classification == NO_DATA
    assert gap.duration == timedelta(minutes=29)


def test_gap_closes_a_running_outage_as_open_ended():
    records = [rec(0, "offline"), rec(1, "offline"), rec(40, "ok")]
    outage, gap = group_periods(records)
    assert (outage.classification, outage.open_ended, outage.end) == ("offline", True, parse_ts("2026-10-03T05:01:00Z"))
    assert gap.classification == NO_DATA


def test_short_delay_is_not_a_gap():
    records = [rec(0, "ok"), rec(3, "ok")]  # 3 min at 60 s interval: exactly GAP_FACTOR, not more
    assert group_periods(records) == ()


def test_records_out_of_order_are_sorted():
    records = [rec(4, "ok"), rec(2, "offline"), rec(1, "offline"), rec(0, "ok")]
    (period,) = group_periods(records)
    assert period.cycles == 2


def test_formatted_summary():
    records = [rec(0, "ok"), rec(1, "offline"), rec(2, "offline"), rec(3, "ok"), rec(4, "dns_fail")]
    text = format_summary("2026-10-03", records, skipped_lines=1)
    assert "5 cycles (dns_fail=1, offline=2, ok=2)" in text
    assert "1 unreadable line(s)" in text
    assert "2026-10-03 05:01:00   2026-10-03 05:03:00   0:02:00    offline" in text
    assert "0:00:00+" in text


def test_formatted_summary_when_all_ok():
    text = format_summary("2026-10-03", [rec(0, "ok")], skipped_lines=0)
    assert "No outage periods" in text
