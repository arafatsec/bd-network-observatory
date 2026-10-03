import pytest

from probe.cli import build_parser, main
from probe.storage import append_record
from probe.summary import parse_ts


@pytest.mark.parametrize("value", ["14", "0", "-60", "abc"])
def test_rejects_bad_intervals(value, capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["run", "--interval", value])
    assert exc.value.code == 2
    assert "interval must" in capsys.readouterr().err


def test_default_and_minimum_interval():
    assert build_parser().parse_args(["run"]).interval == 60
    assert build_parser().parse_args(["run", "--interval", "15"]).interval == 15


def test_rejects_bad_date(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["summary", "--date", "03-10-2026"])
    assert "YYYY-MM-DD" in capsys.readouterr().err


def test_summary_for_missing_day(tmp_path, capsys):
    assert main(["summary", "--date", "2026-10-03", "--data-dir", str(tmp_path)]) == 1
    assert "No log for 2026-10-03" in capsys.readouterr().out


def test_summary_prints_outages(tmp_path, capsys):
    for minute, classification in [(0, "ok"), (1, "offline"), (2, "ok")]:
        ts = f"2026-10-03T05:0{minute}:00Z"
        append_record(tmp_path, {"ts": ts, "classification": classification, "interval_s": 60}, parse_ts(ts))
    assert main(["summary", "--date", "2026-10-03", "--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "offline" in out and "0:01:00" in out
