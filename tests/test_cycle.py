import getpass
import json
import socket
from datetime import datetime, timezone

from probe import uploader
from probe.cycle import run_cycle, run_loop
from probe.storage import read_records
from tests.conftest import make_results

NOW = datetime(2026, 10, 3, 5, 0, 0, tzinfo=timezone.utc)
ALLOWED_TOP_LEVEL_KEYS = {"v", "ts", "interval_s", "classification", "latency_ms", "baseline_ms", "dns", "tcp", "http"}


def cycle(results, samples=()):
    return run_cycle(60, samples, checker=lambda: results, now=lambda: NOW)


def test_record_shape_and_utc_timestamp():
    ts, record, _ = cycle(make_results())
    assert ts == NOW
    assert record["ts"] == "2026-10-03T05:00:00Z"
    assert set(record) == ALLOWED_TOP_LEVEL_KEYS
    assert set(record["dns"][0]) == {"resolver", "name", "ok", "ms", "answers", "error"}
    assert set(record["tcp"][0]) == {"target", "ok", "ms", "error"}
    assert set(record["http"][0]) == {"url", "ok", "status", "ms", "error"}
    json.dumps(record)


def test_record_contains_nothing_about_the_host():
    _, record, _ = cycle(make_results())
    text = json.dumps(record).lower()
    for private in {socket.gethostname().lower(), getpass.getuser().lower()}:
        assert private not in text
    resolvers = {entry["resolver"] for entry in record["dns"]}
    assert resolvers <= {"1.1.1.1", "8.8.8.8", "9.9.9.9", "system"}


def test_cycle_classifies_failures():
    assert cycle(make_results(dns_ok=False, tcp_ok=False, http_ok=False))[1]["classification"] == "offline"
    assert cycle(make_results(tcp_ok=False))[1]["classification"] == "tcp_fail"


def test_degraded_once_baseline_exists():
    warm = (20.0,) * 5
    _, record, samples = cycle(make_results(tcp_ms=900.0), warm)
    assert record["classification"] == "degraded"
    assert record["baseline_ms"] == 20.0
    assert samples == warm  # a degraded cycle does not move the baseline


def test_ok_cycle_extends_baseline():
    _, record, samples = cycle(make_results(tcp_ms=22.0))
    assert record["classification"] == "ok"
    assert record["baseline_ms"] is None
    assert samples == (22.0,)


def test_loop_writes_one_line_per_cycle_and_never_uploads(tmp_path, monkeypatch):
    upload_results: list[int] = []
    real_stub = uploader.upload_pending

    def spy(data_dir):
        result = real_stub(data_dir)
        upload_results.append(result)
        return result

    monkeypatch.setattr(uploader, "upload_pending", spy)
    sleeps: list[float] = []
    output: list[str] = []

    completed = run_loop(
        15, tmp_path, checker=make_results, sleep=sleeps.append, clock=lambda: 0.0,
        out=output.append, max_cycles=3,
    )

    assert completed == 3
    (log_file,) = tmp_path.glob("*.jsonl")
    assert len(read_records(log_file).records) == 3
    assert upload_results == [0, 0, 0]
    assert sleeps == [15.0, 15.0]
    assert all(" ok " in line for line in output)


def test_uploader_stub_does_nothing(tmp_path):
    assert uploader.upload_pending(tmp_path) == 0
    assert list(tmp_path.iterdir()) == []


def test_failed_write_is_reported_and_the_loop_continues(tmp_path, monkeypatch):
    import probe.cycle as cycle_module

    calls = {"n": 0}
    real_append = cycle_module.append_record

    def flaky_append(data_dir, record, ts):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("locked")
        return real_append(data_dir, record, ts)

    monkeypatch.setattr(cycle_module, "append_record", flaky_append)
    output: list[str] = []
    completed = run_loop(15, tmp_path, checker=make_results, sleep=lambda s: None, clock=lambda: 0.0,
                         out=output.append, max_cycles=2)

    assert completed == 2
    assert "WARNING: cycle not saved (PermissionError)" in output[0]
    assert str(tmp_path) not in output[0]
    (log_file,) = tmp_path.glob("*.jsonl")
    assert len(read_records(log_file).records) == 1
