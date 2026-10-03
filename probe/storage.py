"""Append-only JSONL storage that survives power loss between writes.

One file per UTC day: data/YYYY-MM-DD.jsonl, one JSON object per line.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class ReadResult:
    records: tuple[dict, ...]
    skipped_lines: int


def log_path(data_dir: Path, ts: datetime) -> Path:
    return data_dir / f"{ts.astimezone(timezone.utc):%Y-%m-%d}.jsonl"


def append_record(data_dir: Path, record: dict, ts: datetime) -> Path:
    """Append one record, then flush and fsync before returning."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = log_path(data_dir, ts)
    is_new_file = not path.exists()
    line = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    # Binary mode: identical LF line endings on Windows and Linux.
    with open(path, "a+b") as fh:
        if _ends_mid_line(fh):
            # A crash interrupted the previous write. Terminate that fragment so
            # this record starts on its own line instead of being glued to it.
            line = b"\n" + line
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())

    if is_new_file:
        _fsync_directory(data_dir)
    return path


def _ends_mid_line(fh) -> bool:
    fh.seek(0, os.SEEK_END)
    size = fh.tell()
    if size == 0:
        return False
    fh.seek(size - 1)
    return fh.read(1) != b"\n"


def _fsync_directory(directory: Path) -> None:
    # On POSIX a new file's directory entry is only durable once the directory is
    # synced. Windows cannot open directories this way and does not need it.
    if os.name != "posix":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_records(path: Path) -> ReadResult:
    """Read every valid record, counting (not hiding) lines that cannot be parsed."""
    records: list[dict] = []
    skipped = 0
    with open(path, "rb") as fh:
        for raw in fh:
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not is_valid_record(record):
                skipped += 1
                continue
            records.append(record)
    return ReadResult(tuple(records), skipped)


def is_valid_record(record: object) -> bool:
    """Just enough structure for the summary to rely on."""
    if not isinstance(record, dict) or not isinstance(record.get("classification"), str):
        return False
    try:
        datetime.strptime(record.get("ts"), TS_FORMAT)
    except (TypeError, ValueError):
        return False
    interval = record.get("interval_s", 60)
    return isinstance(interval, int) and not isinstance(interval, bool) and interval > 0
