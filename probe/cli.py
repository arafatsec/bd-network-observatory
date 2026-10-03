"""Command line: `python -m probe run` and `python -m probe summary`."""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Sequence

from probe.cycle import run_loop
from probe.storage import read_records
from probe.summary import format_summary

DEFAULT_INTERVAL_S = 60
MIN_INTERVAL_S = 15
DEFAULT_DATA_DIR = Path("data")


def interval_arg(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"interval must be a whole number of seconds, got {value!r}") from None
    if seconds < MIN_INTERVAL_S:
        raise argparse.ArgumentTypeError(
            f"interval must be at least {MIN_INTERVAL_S} seconds (got {seconds}); "
            "shorter intervals add load to the test servers without adding much information"
        )
    return seconds


def date_arg(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"date must be YYYY-MM-DD, got {value!r}") from None
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m probe",
        description="v0 blackout-resilient connectivity logger. Logs locally; uploads nothing.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="measure every INTERVAL seconds until Ctrl+C")
    run.add_argument("--interval", type=interval_arg, default=DEFAULT_INTERVAL_S,
                     help=f"seconds between cycles (default {DEFAULT_INTERVAL_S}, minimum {MIN_INTERVAL_S})")
    run.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="where to write logs (default: data)")

    summary = commands.add_parser("summary", help="print outage periods for one UTC day")
    summary.add_argument("--date", type=date_arg, required=True, help="UTC date, YYYY-MM-DD")
    summary.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="where logs are (default: data)")
    return parser


def cmd_run(interval_s: int, data_dir: Path) -> int:
    print(f"Logging to {data_dir}/ every {interval_s} s. Nothing is uploaded. Press Ctrl+C to stop.")
    try:
        run_loop(interval_s, data_dir)
    except KeyboardInterrupt:
        print("\nStopped. Every completed cycle is already saved.")
    return 0


def cmd_summary(day: str, data_dir: Path) -> int:
    path = data_dir / f"{day}.jsonl"
    if not path.exists():
        print(f"No log for {day}: {path} does not exist.")
        return 1
    result = read_records(path)
    print(format_summary(day, result.records, result.skipped_lines))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args.interval, args.data_dir)
    return cmd_summary(args.date, args.data_dir)
