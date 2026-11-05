"""WP-14's check on Docker: first start, owner setup, backup, wipe and restore, then recovery on a new
install, off-machine copies, HTTPS on the firm's-box target and a valid config for the server target.

    uv run python deploy/e2e.py [--tag TAG] [--keep]

Needs Docker, and images from deploy/build-images.sh. It uses its own Compose project and port.
"""

import argparse
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/worker/tests"))
PORT = 18091
HTTPS_PORT = 18443
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
    def __init__(
        self, base: str = f"http://127.0.0.1:{PORT}", context: ssl.SSLContext | None = None
    ) -> None:
        self.base = base
        self.jar = CookieJar()
        handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPCookieProcessor(self.jar)]
        if context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=context))
        self.opener = urllib.request.build_opener(*handlers)

    def call(self, path: str, body: dict[str, object] | None = None) -> object:
        request = urllib.request.Request(
            f"{self.base}/api/{path}",
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


def stop(folder: Path) -> None:
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=folder,
        check=False,
        capture_output=True,
        env={**os.environ, "COMPOSE_PROJECT_NAME": PROJECT},
    )


def check_firm_box(work: Path, project: Path, daftar: list[str], tag: str, keys: list[str]) -> None:
    folder = work / "box"
    run(
        [
            *daftar,
            "bundle",
            str(project),
            "-o",
            str(folder),
            "--tag",
            tag,
            "--target",
            "lan",
            "--host",
            "127.0.0.1",
        ]
    )
    settings = (folder / ".env").read_text(encoding="utf-8")
    settings = settings.replace("DAFTAR_HTTP_PORT=80", f"DAFTAR_HTTP_PORT={PORT}")
    (folder / ".env").write_text(
        settings.replace("DAFTAR_HTTPS_PORT=443", f"DAFTAR_HTTPS_PORT={HTTPS_PORT}"),
        encoding="utf-8",
    )
    try:
        run(["./start"], folder)
        base = f"https://127.0.0.1:{HTTPS_PORT}"
        # Caddy issues the certificate just after it starts. Until then, a TLS error is expected.
        authority = None
        for _ in range(30):
            try:
                run(["./export-ca"], folder)
                authority = ssl.create_default_context(cafile=str(folder / "daftar-root-ca.crt"))
                with socket.create_connection(("127.0.0.1", HTTPS_PORT), timeout=5) as raw:
                    with authority.wrap_socket(raw, server_hostname="127.0.0.1"):
                        break
            except (OSError, SystemExit, ssl.SSLError):
                time.sleep(2)
        check(authority is not None, "./export-ca gives the private root")
        assert authority is not None
        untrusting = ssl.create_default_context()
        try:
            Client(base, untrusting).call("auth/status")
            check(False, "a device without the root is warned")
        except urllib.error.URLError:
            check(True, "a device without the root is warned")
        client = Client(base, authority)
        check(
            client.call("auth/status")["needsSetup"] is True,
            "a device with the root connects over HTTPS",
        )
        client.call("auth/setup", {"username": "patronne", "password": "un-long-mot-de-passe-1"})
        check(
            all(cookie.secure for cookie in client.jar) and len(client.jar) > 0,
            "the session cookie is HTTPS-only",
        )
        check(
            all(count(client.call(f"e/{key}?limit=1000")) > 0 for key in keys),
            "data loads over HTTPS",
        )
        request = urllib.request.Request(f"http://127.0.0.1:{PORT}/")
        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(request, timeout=10)
            check(False, "plain HTTP moves to HTTPS")
        except urllib.error.HTTPError as error:
            check(
                error.code in (301, 302, 307, 308)
                and error.headers["Location"].startswith("https://"),
                "plain HTTP moves to HTTPS",
            )
    finally:
        stop(folder)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: object, **__: object) -> None:
        return None


def check_server_config(work: Path, project: Path, daftar: list[str], tag: str) -> None:
    """A real certificate needs a real domain, so this stops at Caddy accepting the configuration."""
    folder = work / "server"
    run(
        [
            *daftar,
            "bundle",
            str(project),
            "-o",
            str(folder),
            "--tag",
            tag,
            "--target",
            "vps",
            "--host",
            "app.example.dz",
            "--email",
            "ops@example.dz",
        ]
    )
    image = next(
        line.split("image:")[1].strip()
        for line in (folder / "compose.yaml").read_text(encoding="utf-8").splitlines()
        if "caddy:" in line
    )
    run([
        "docker", "run", "--rm", "-e", "DAFTAR_HOST=app.example.dz", "-e", "DAFTAR_ACME_EMAIL=ops@example.dz",
        "-v", f"{folder / 'Caddyfile'}:/etc/caddy/Caddyfile:ro", image,
        "caddy", "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile",
    ])  # fmt: skip
    check(True, "the server target's config is valid; a real certificate still needs a real domain")


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
        check(status["needsSetup"] is True, "first start asks for setup")
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
        check(Client().call("auth/status")["needsSetup"] is True, "the wipe left no owner")

        run(["./restore", dump, "--yes"], bundle)
        restored = Client()
        restored.call("auth/login", {"username": "patronne", "password": "un-long-mot-de-passe-1"})
        check(all_rows(restored, list(seed)) == before, "restore gives the same data")
        other = Client()
        other.call("auth/login", {"username": "comptable", "password": "un-autre-mot-de-passe-2"})
        check(True, "a user added after setup can log in again after the restore")

        offsite = work / "second-disk"
        settings = (bundle / ".env").read_text(encoding="utf-8")
        missing = subprocess.run(["./offsite"], cwd=bundle, check=False, capture_output=True)
        check(missing.returncode == 2, "./offsite refuses until a destination is set")
        (bundle / ".env").write_text(
            settings.replace("DAFTAR_OFFSITE=", f"DAFTAR_OFFSITE={offsite}"), encoding="utf-8"
        )
        run(["./offsite"], bundle)
        copied = [item.name for item in offsite.iterdir()]
        check(copied == [Path(dump).name], f"./offsite copies the dumps and nothing else: {copied}")
        stop(bundle)

        # The machine is lost: a new bundle has new secrets, and only the backup survives.
        fresh = work / "fresh"
        run([*daftar, "bundle", str(project), "-o", str(fresh), "--tag", args.tag])
        new_settings = (fresh / ".env").read_text(encoding="utf-8")
        check(new_settings != settings, "a new bundle has its own secrets")
        (fresh / ".env").write_text(
            new_settings.replace("DAFTAR_PORT=8080", f"DAFTAR_PORT={PORT}"), encoding="utf-8"
        )
        run(["./start"], fresh)
        run(["./restore", str(offsite / Path(dump).name), "--yes"], fresh)
        recovered = Client()
        recovered.call("auth/login", {"username": "patronne", "password": "un-long-mot-de-passe-1"})
        check(
            all_rows(recovered, list(seed)) == before,
            "a new install recovers the data and accounts from a backup",
        )
        stop(fresh)

        check_firm_box(work, project, daftar, args.tag, list(seed))
        check_server_config(work, project, daftar, args.tag)
        print("all checks passed")
    finally:
        for folder in (bundle, work / "fresh", work / "box"):
            if folder.exists():
                stop(folder)
        if args.keep:
            print(f"kept {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
