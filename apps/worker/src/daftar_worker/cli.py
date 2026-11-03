"""The `daftar` command (C-5). Exit codes: 0 ok, 2 unreadable input, 3 validation error."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from daftar_worker.census import render_markdown, run_census
from daftar_worker.errors import MESSAGES, WorkerError
from daftar_worker.reader import read_file


EXIT_UNREADABLE = 2


def _write_atomic(path: Path, text: str) -> None:
    """Write through a temporary file, so a failure never leaves a partial output behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def _read(args: argparse.Namespace) -> int:
    try:
        snapshot = read_file(args.file)
    except WorkerError as error:
        message = MESSAGES[error.code]
        print(f"{error.code}: {message['fr']}\n{message['ar']}", file=sys.stderr)
        return EXIT_UNREADABLE
    _write_atomic(Path(args.output), _dump(snapshot))
    return 0


def _census(args: argparse.Namespace) -> int:
    missing = [path for path in args.paths if not Path(path).exists()]
    if missing:
        print(f"not found: {', '.join(missing)}", file=sys.stderr)
        return EXIT_UNREADABLE
    census = run_census(args.paths)
    output = Path(args.output)
    _write_atomic(output, _dump(census))
    _write_atomic(output.with_suffix(".md"), render_markdown(census))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daftar")
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("read", help="read a workbook into a snapshot")
    read.add_argument("file")
    read.add_argument("-o", "--output", required=True)
    read.set_defaults(run=_read)
    census = commands.add_parser("census", help="count workbook features over files and folders")
    census.add_argument("paths", nargs="+", metavar="PATH")
    census.add_argument("-o", "--output", required=True)
    census.set_defaults(run=_census)
    args = parser.parse_args(argv)
    code: int = args.run(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
