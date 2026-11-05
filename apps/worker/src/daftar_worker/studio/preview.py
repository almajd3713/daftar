"""Start and stop the Runtime that previews a generated app (R-14, D-9)."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from typing import Any


START_TIMEOUT_SECONDS = 180
STOP_TIMEOUT_SECONDS = 30


class PreviewError(Exception):
    pass


@dataclass
class Running:
    process: subprocess.Popen[str]
    port: int
    cookie: str
    folder: tempfile.TemporaryDirectory[str]


def _first_line(process: subprocess.Popen[str]) -> str:
    """The line the preview prints when it's ready. Empty if it ends or takes too long first."""
    lines: list[str] = []
    assert process.stdout is not None
    reader = threading.Thread(target=lambda: lines.append(process.stdout.readline()), daemon=True)  # type: ignore[union-attr]
    reader.start()
    reader.join(START_TIMEOUT_SECONDS)
    return lines[0] if lines else ""


class Previews:
    """One running preview per project. It works from a copy, so generating again can't disturb it."""

    def __init__(self, command: list[str], admin_url: str) -> None:
        self.command = command
        self.admin_url = admin_url
        self._lock = threading.Lock()
        self._running: dict[str, Running] = {}

    def _environment(self, project: str, spec: Path) -> dict[str, str]:
        # Only what it needs: the Studio's environment can hold a model's address and other secrets.
        return {
            "PATH": os.environ.get("PATH", ""),
            "DAFTAR_PREVIEW_ADMIN_URL": self.admin_url,
            "DAFTAR_PREVIEW_DATABASE": f"daftar_preview_{project}",
            "DAFTAR_SPEC_PATH": str(spec),
        }

    def start(self, project: str, folder: Path) -> Running:
        self.stop(project)
        holding = tempfile.TemporaryDirectory(prefix="daftar-preview-")
        copy = Path(holding.name)
        shutil.copy(folder / "daftar.spec.json", copy / "daftar.spec.json")
        if (folder / "seed").exists():
            shutil.copytree(folder / "seed", copy / "seed")
        try:
            process = subprocess.Popen(  # noqa: S603
                self.command,
                env=self._environment(project, copy / "daftar.spec.json"),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError as error:
            holding.cleanup()
            raise PreviewError(type(error).__name__) from error
        line = _first_line(process)
        try:
            ready: dict[str, Any] = json.loads(line)
            running = Running(process, int(ready["port"]), str(ready["cookie"]), holding)
        except (ValueError, KeyError, TypeError) as error:
            self._end(process)
            holding.cleanup()
            raise PreviewError("the preview didn't start") from error
        with self._lock:
            self._running[project] = running
        return running

    def running(self, project: str) -> Running | None:
        with self._lock:
            found = self._running.get(project)
        return found if found is not None and found.process.poll() is None else None

    @staticmethod
    def _end(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()

    def stop(self, project: str) -> None:
        with self._lock:
            running = self._running.pop(project, None)
        if running is not None:
            self._end(running.process)
            running.folder.cleanup()

    def stop_all(self) -> None:
        with self._lock:
            projects = list(self._running)
        for project in projects:
            self.stop(project)


__all__ = ["PreviewError", "Previews", "Running"]
