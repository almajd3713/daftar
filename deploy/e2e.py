"""WP-14's check: bundle a fixture, start it, set up the owner, then back up, wipe and restore.

    uv run python deploy/e2e.py [--tag TAG] [--keep]

Needs Docker, and images from deploy/build-images.sh. It uses its own Compose project and port.
"""

import argparse
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/worker/tests"))
PORT = 18091
PROJECT = "daftar-e2e"


def run(command: list[str], cwd: Path | None = None) -> str:
    done = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "COMPOSE_PROJECT_NAME": PROJECT},
    )
    if done.returncode != 0:
        raise SystemExit(
            f"{' '.join(command)} failed:\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}"
        )
    return done.stdout


class Client:
    def __init__(self) -> None:
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(self, path: str, body: dict[str, object] | None = None) -> object:
        request = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.opener.open(request, timeout=30) as response:
            return json.loads(response.read() or b"null")


def all_rows(client: Client, keys: list[str]) -> dict[str, object]:
    return {key: client.call(f"e/{key}?limit=1000") for key in keys}


def count(payload: object) -> int:
    assert isinstance(payload, dict)
    rows = payload.get("rows", payload.get("items", payload.get("records")))
    assert isinstance(rows, list), list(payload)
    return len(rows)


def check(condition: bool, message: str) -> None:
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="e2e")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    import workbook_builders as builders  # noqa: PLC0415 - from the tests folder, added above

    work = Path(tempfile.mkdtemp(prefix="daftar-e2e-"))
    bundle = work / "bundle"
    try:
        book = builders.tutoring_workbook(work / "centre.xlsx")
        project = work / "project"
        daftar = ["uv", "run", "--project", str(ROOT), "daftar"]
        run([*daftar, "project", "init", str(project), "--file", str(book), "--no-llm"])
        analysis = json.loads((project / "analysis.json").read_text(encoding="utf-8"))
        accepted = [part for item in analysis["findings"] for part in ("--accept", item["id"])]
        run([*daftar, "project", "decide", str(project), *accepted])
        run([*daftar, "project", "generate", str(project)])
        run([*daftar, "bundle", str(project), "-o", str(bundle), "--tag", args.tag])

        environment = (bundle / ".env").read_text(encoding="utf-8")
        check((bundle / ".env").stat().st_mode & 0o077 == 0, ".env is private to its owner")
        check(
            "POSTGRES_PASSWORD=" in environment and "changeme" not in environment,
            "secrets were generated",
        )
        (bundle / ".env").write_text(
            environment.replace("DAFTAR_PORT=8080", f"DAFTAR_PORT={PORT}"), encoding="utf-8"
        )

        seed = {
            path.stem: len(path.read_text(encoding="utf-8").splitlines())
            for path in (bundle / "seed").glob("*.jsonl")
        }
        check(sum(seed.values()) > 0, f"the bundle holds seed data: {seed}")

        run(["./start"], bundle)
        for module in ("analyser", "llm", "project"):
            found = subprocess.run(
                ["docker", "compose", "exec", "-T", "worker", "python", "-c", f"import daftar_worker.{module}"],
                cwd=bundle, check=False, capture_output=True, env={**os.environ, "COMPOSE_PROJECT_NAME": PROJECT},
            )  # fmt: skip
            check(found.returncode != 0, f"the client worker has no {module}")
        ports = run(["docker", "compose", "ps", "--format", "{{.Service}} {{.Publishers}}"], bundle)
        exposed = [
            line.split()[0]
            for line in ports.splitlines()
            if "127.0.0.1" in line or "0.0.0.0" in line
        ]
        check(exposed == ["proxy"], f"only the proxy is published: {exposed}")

        client = Client()
        status = client.call("auth/status")
        check(status == {"needsSetup": True}, "first start asks for setup")
        try:
            Client().call("e/" + next(iter(seed)))
            check(False, "data needs a login")
        except urllib.error.HTTPError as error:
            check(error.code == 401, "data needs a login")
        client.call("auth/setup", {"username": "patronne", "password": "un-long-mot-de-passe-1"})
        before = all_rows(client, list(seed))
        for key, expected in seed.items():
            check(count(before[key]) == expected, f"{key}: {expected} rows are loaded")
        client.call(
            "auth/users",
            {"username": "comptable", "password": "un-autre-mot-de-passe-2", "role": "accountant"},
        )

        dump = run(["./backup"], bundle).strip()
        check((bundle / dump).stat().st_size > 0, f"backup written: {dump}")

        run(["docker", "compose", "down", "-v"], bundle)
        run(["./start"], bundle)
        check(Client().call("auth/status") == {"needsSetup": True}, "the wipe left no owner")

        run(["./restore", dump, "--yes"], bundle)
        restored = Client()
        restored.call("auth/login", {"username": "patronne", "password": "un-long-mot-de-passe-1"})
        check(all_rows(restored, list(seed)) == before, "restore gives the same data")
        other = Client()
        other.call("auth/login", {"username": "comptable", "password": "un-autre-mot-de-passe-2"})
        check(True, "a user added after setup can log in again after the restore")
        print("all checks passed")
    finally:
        if bundle.exists():
            subprocess.run(
                ["docker", "compose", "down", "-v"], cwd=bundle, check=False, capture_output=True,
                env={**os.environ, "COMPOSE_PROJECT_NAME": PROJECT},
            )  # fmt: skip
        if args.keep:
            print(f"kept {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
