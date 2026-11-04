"""`daftar bundle`: the folder a client's server runs from (C-8, R-25).

Target-neutral until OQ-1: the proxy speaks plain HTTP and listens on this machine only, because a
public or LAN address needs the TLS setup that OQ-1 decides.
"""

from importlib.metadata import version
import json
from pathlib import Path
import secrets
import shutil
import stat
from typing import Any

from daftar_spec import format_errors, validate_spec


POSTGRES_IMAGE = (
    "postgres:16-alpine@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab"
)
CADDY_IMAGE = (
    "caddy:2-alpine@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5"
)
TEMPLATES = Path(__file__).parent / "bundle_files"
EXECUTABLE = ("start", "backup", "restore")
COPIED = ("backup", "restore", "start", "Caddyfile", "README.fr.md", "README.ar.md")


class BundleError(ValueError):
    pass


def _read_spec(project: Path) -> dict[str, Any]:
    path = project / "daftar.spec.json"
    if not path.exists():
        raise BundleError(f"{path} doesn't exist: run `daftar project generate` first")
    spec: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_spec(spec)
    if errors:
        raise BundleError(format_errors(errors))
    return spec


def _environment(spec: dict[str, Any], tag: str) -> str:
    locale = spec.get("locale", {})
    default = locale.get("default", "fr-DZ") if isinstance(locale, dict) else "fr-DZ"
    # Hex, so the password can sit inside the database URL as it is.
    return "\n".join(
        [
            f"DAFTAR_IMAGE_TAG={tag}",
            f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
            f"DAFTAR_SECRET={secrets.token_hex(32)}",
            f"DAFTAR_DEFAULT_LOCALE={default}",
            "DAFTAR_TZ=Africa/Algiers",
            "# Where the app listens. It stays on this machine until TLS is set up.",
            "DAFTAR_BIND=127.0.0.1",
            "DAFTAR_PORT=8080",
            "",
        ]
    )


def build_bundle(
    project: Path, output: Path, tag: str | None = None, images: Path | None = None
) -> dict[str, Any]:
    spec = _read_spec(project)
    if not spec["entities"]:
        raise BundleError("the spec has no entities: accept the findings to convert, then generate again")
    # Rebuilding over a bundle would replace its secrets and lock the client out of their data.
    if output.exists() and any(output.iterdir()):
        raise BundleError(f"{output} isn't empty; a bundle is never rebuilt in place")
    if images is not None and not images.is_file():
        raise BundleError(f"{images} doesn't exist")
    image_tag = tag or version("daftar-worker")

    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(project / "daftar.spec.json", output / "daftar.spec.json")
    seed = output / "seed"
    seed.mkdir()
    rows = 0
    for item in sorted((project / "seed").glob("*.jsonl")) if (project / "seed").is_dir() else []:
        shutil.copyfile(item, seed / item.name)
        rows += sum(1 for line in item.read_text(encoding="utf-8").splitlines() if line.strip())

    compose = (TEMPLATES / "compose.yaml").read_text(encoding="utf-8")
    compose = compose.replace("{{POSTGRES_IMAGE}}", POSTGRES_IMAGE).replace(
        "{{CADDY_IMAGE}}", CADDY_IMAGE
    )
    (output / "compose.yaml").write_text(compose, encoding="utf-8")
    for name in COPIED:
        shutil.copyfile(TEMPLATES / name, output / name)
    for name in EXECUTABLE:
        path = output / name
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

    environment = output / ".env"
    environment.touch(mode=0o600)
    environment.write_text(_environment(spec, image_tag), encoding="utf-8")
    if images is not None:
        shutil.copyfile(images, output / "images.tar")
    return {
        "output": str(output),
        "imageTag": image_tag,
        "seedRows": rows,
        "images": images is not None,
    }
