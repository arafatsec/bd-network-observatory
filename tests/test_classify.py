import pytest

from probe.classify import (
    CLASSIFICATIONS, DEGRADED, DNS_FAIL, HTTP_FAIL, MAX_BASELINE_SAMPLES, MIN_BASELINE_SAMPLES,
    OFFLINE, OK, TCP_FAIL, LayerOutcome, classify, is_degraded, rolling_baseline, update_samples,
)


def outcome(dns=True, tcp=True, http=True, latency=20.0):
    return LayerOutcome(dns_ok=dns, tcp_ok=tcp, http_ok=http, latency_ms=latency if tcp else None)


@pytest.mark.parametrize(
    ("layers", "baseline", "expected"),
    [
        (outcome(), 20.0, OK),
        (outcome(latency=500.0), 20.0, DEGRADED),
        (outcome(dns=False), 20.0, DNS_FAIL),
        (outcome(tcp=False), 20.0, TCP_FAIL),
        (outcome(http=False), 20.0, HTTP_FAIL),
        (outcome(dns=False, tcp=False, http=False), 20.0, OFFLINE),
    ],
)
def test_every_classification(layers, baseline, expected):
    assert classify(layers, baseline) == expected


def test_all_six_classes_are_covered_above():
    assert set(CLASSIFICATIONS) == {OK, DEGRADED, DNS_FAIL, TCP_FAIL, HTTP_FAIL, OFFLINE}


def test_lowest_failing_layer_wins():
    assert classify(outcome(dns=False, http=False), 20.0) == DNS_FAIL
    assert classify(outcome(tcp=False, http=False), 20.0) == TCP_FAIL


def test_dns_and_tcp_down_but_http_up_is_still_dns_fail():
    # Odd, but possible with a local cache and a proxy-free path; not "offline".
    assert classify(outcome(dns=False, tcp=False, http=True), 20.0) == DNS_FAIL


def test_failure_beats_slow_latency():
    assert classify(outcome(http=False, latency=5000.0), 20.0) == HTTP_FAIL


def test_no_baseline_yet_means_never_degraded():
    assert classify(outcome(latency=5000.0), None) == OK


@pytest.mark.parametrize(
    ("latency", "baseline", "expected"),
    [
        (60.0, 20.0, False),    # 3x but only +40 ms: normal jitter on a fast link
        (120.0, 20.0, False),   # exactly at threshold max(60, 120)
        (120.1, 20.0, True),
        (600.0, 200.0, False),  # exactly 3x on a slow link
        (600.1, 200.0, True),
        (None, 20.0, False),
    ],
)
def test_degraded_threshold(latency, baseline, expected):
    assert is_degraded(latency, baseline) is expected


def test_baseline_needs_minimum_samples():
    assert rolling_baseline((20.0,) * (MIN_BASELINE_SAMPLES - 1)) is None
    assert rolling_baseline((10.0, 20.0, 30.0, 40.0, 1000.0)) == 30.0


def test_only_ok_cycles_feed_the_baseline():
    samples = (20.0,)
    assert update_samples(samples, DEGRADED, 900.0) == samples
    assert update_samples(samples, TCP_FAIL, None) == samples
    assert update_samples(samples, OK, 25.0) == (20.0, 25.0)


def test_baseline_window_is_capped_and_input_unchanged():
    samples = tuple(float(i) for i in range(MAX_BASELINE_SAMPLES))
    updated = update_samples(samples, OK, 999.0)
    assert len(updated) == MAX_BASELINE_SAMPLES
    assert updated[-1] == 999.0
    assert samples[-1] == MAX_BASELINE_SAMPLES - 1
