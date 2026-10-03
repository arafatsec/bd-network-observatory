import json
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import probe.storage as storage
from probe.storage import append_record, log_path, read_records

TS = datetime(2026, 10, 3, 5, 0, 0, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[1]


def record(n: int) -> dict:
    return {"v": 1, "ts": f"2026-10-03T05:{n:02d}:00Z", "classification": "ok", "n": n}


def test_file_is_named_by_utc_date(tmp_path):
    late_evening_dhaka = datetime(2026, 10, 3, 23, 30, tzinfo=timezone.utc)
    assert log_path(tmp_path, late_evening_dhaka).name == "2026-10-03.jsonl"


def test_every_line_is_valid_json(tmp_path):
    for n in range(5):
        path = append_record(tmp_path, record(n), TS)
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw
    lines = raw.decode("utf-8").splitlines()
    assert [json.loads(line)["n"] for line in lines] == [0, 1, 2, 3, 4]


def test_each_write_is_flushed_and_fsynced(tmp_path, monkeypatch):
    synced: list[int] = []
    real_fsync = storage.os.fsync
    monkeypatch.setattr(storage.os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd)))
    append_record(tmp_path, record(1), TS)
    append_record(tmp_path, record(2), TS)
    assert len(synced) >= 2  # one per record (plus the directory on POSIX)


def test_creates_missing_data_dir(tmp_path):
    path = append_record(tmp_path / "nested" / "data", record(1), TS)
    assert path.exists()


def test_recovers_from_a_write_cut_off_mid_line(tmp_path):
    append_record(tmp_path, record(1), TS)
    append_record(tmp_path, record(2), TS)
    path = log_path(tmp_path, TS)
    with open(path, "ab") as fh:  # simulate power loss halfway through a write
        fh.write(b'{"v":1,"ts":"2026-10-03T05:03')
    append_record(tmp_path, record(4), TS)

    result = read_records(path)
    assert [r["n"] for r in result.records] == [1, 2, 4]
    assert result.skipped_lines == 1
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[2] == '{"v":1,"ts":"2026-10-03T05:03'  # fragment isolated on its own line
    assert json.loads(lines[3])["n"] == 4


def test_records_survive_a_process_crash_between_writes(tmp_path):
    """A real process writes 3 records then dies without cleanup (os._exit).

    This covers a process crash. Power-loss durability relies on fsync, which
    test_each_write_is_flushed_and_fsynced checks.
    """
    script = textwrap.dedent(f"""
        import os, sys
        from datetime import datetime, timezone
        from pathlib import Path
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from probe.storage import append_record
        ts = datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc)
        for n in range(3):
            append_record(Path({str(tmp_path)!r}), {{"ts": f"2026-10-03T05:0{{n}}:00Z", "classification": "ok", "n": n}}, ts)
        os._exit(1)
    """)
    completed = subprocess.run([sys.executable, "-c", script], timeout=60)
    assert completed.returncode == 1

    result = read_records(log_path(tmp_path, TS))
    assert [r["n"] for r in result.records] == [0, 1, 2]
    assert result.skipped_lines == 0


def test_reader_skips_records_missing_required_keys(tmp_path):
    path = tmp_path / "2026-10-03.jsonl"
    path.write_bytes(b'{"ts":"2026-10-03T05:00:00Z","classification":"ok"}\n[1,2]\n{"ts":"x"}\n\n')
    result = read_records(path)
    assert len(result.records) == 1
    assert result.skipped_lines == 2


def test_reader_skips_records_the_summary_cannot_use(tmp_path):
    path = tmp_path / "2026-10-03.jsonl"
    lines = [
        '{"ts":"2026-10-03T05:00:00Z","classification":"ok","interval_s":60}',
        '{"ts":"2026-10-03 05:01","classification":"ok"}',
        '{"ts":null,"classification":"ok"}',
        '{"ts":"2026-10-03T05:02:00Z","classification":"ok","interval_s":null}',
        '{"ts":"2026-10-03T05:03:00Z","classification":"ok","interval_s":0}',
        '{"ts":"2026-10-03T05:04:00Z","classification":5}',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = read_records(path)
    assert len(result.records) == 1
    assert result.skipped_lines == 5
