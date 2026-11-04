"""C-8: the folder a client runs from. Starting it for real is deploy/e2e.py."""

import json
from pathlib import Path
import re
import subprocess
import sys

import pytest
import workbook_builders as builders

from daftar_worker.cli import main
from daftar_worker.project.bundle import BundleError, build_bundle
from daftar_worker.project.files import project_decide, project_generate, project_init


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "project"
    project_init(builders.tutoring_workbook(tmp_path / "centre.xlsx"), folder)
    analysis = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    project_decide(folder, [item["id"] for item in analysis["findings"]], [], False, "test")
    project_generate(folder)
    return folder


def test_a_bundle_has_everything_c8_lists(project: Path, tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    result = build_bundle(project, output, "1.2.3")
    names = {item.name for item in output.iterdir()}
    assert {
        "compose.yaml",
        ".env",
        "daftar.spec.json",
        "seed",
        "backup",
        "restore",
        "README.fr.md",
        "README.ar.md",
    } <= names
    assert result["seedRows"] > 0
    assert sum(1 for _ in (output / "seed").glob("*.jsonl")) > 0


def test_secrets_are_generated_private_and_different_each_time(
    project: Path, tmp_path: Path
) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    build_bundle(project, first, "1")
    build_bundle(project, second, "1")
    assert (first / ".env").stat().st_mode & 0o077 == 0
    values = [
        dict(
            line.split("=", 1)
            for line in (item / ".env").read_text().splitlines()
            if "=" in line and line[0] != "#"
        )
        for item in (first, second)
    ]
    for key in ("POSTGRES_PASSWORD", "DAFTAR_SECRET"):
        assert len(values[0][key]) >= 48
        assert values[0][key] != values[1][key]


def test_compose_has_no_credentials_or_floating_images(project: Path, tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_bundle(project, output, "1.2.3")
    text = (output / "compose.yaml").read_text(encoding="utf-8")
    services = text[text.index("services:") : text.index("\nvolumes:\n")]
    assert set(re.findall(r"^  (\w+):$", services, re.MULTILINE)) == {
        "proxy",
        "runtime",
        "worker",
        "postgres",
        "backup",
    }
    assert "{{" not in text
    images = re.findall(r"^    image: (\S+)$", services, re.MULTILINE)
    assert len(images) == 5
    assert all("@sha256:" in image or "${DAFTAR_IMAGE_TAG" in image for image in images)
    assert services.count("ports:") == 1
    assert services.index("ports:") < services.index("  runtime:")
    secrets = re.findall(r"^\s+\w*(?:PASSWORD|SECRET):\s*(\S+)$", text, re.MULTILINE)
    assert secrets and all(value.startswith("${") for value in secrets)


def test_the_default_listens_on_this_machine_over_plain_http(project: Path, tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_bundle(project, output, "1")
    assert '"127.0.0.1:${DAFTAR_PORT:-8080}:80"' in (output / "compose.yaml").read_text(
        encoding="utf-8"
    )
    assert "auto_https off" in (output / "Caddyfile").read_text(encoding="utf-8")
    assert not (output / "export-ca").exists()


def test_a_bundle_is_never_rebuilt_over_its_secrets(project: Path, tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_bundle(project, output, "1")
    before = (output / ".env").read_text(encoding="utf-8")
    with pytest.raises(BundleError, match="never rebuilt"):
        build_bundle(project, output, "2")
    assert (output / ".env").read_text(encoding="utf-8") == before


def test_it_refuses_a_project_with_nothing_to_run(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    project_init(builders.tutoring_workbook(tmp_path / "centre.xlsx"), folder)
    with pytest.raises(BundleError, match="generate"):
        build_bundle(folder, tmp_path / "bundle")
    project_generate(folder)
    with pytest.raises(BundleError, match="no entities"):
        build_bundle(folder, tmp_path / "bundle")


def test_the_command(project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bundle", str(project), "-o", str(tmp_path / "bundle"), "--tag", "9"]) == 0
    assert json.loads(capsys.readouterr().out)["imageTag"] == "9"
    assert main(["bundle", str(project), "-o", str(tmp_path / "bundle")]) == 3


def test_the_client_worker_loads_no_analyser_or_model_code() -> None:
    script = (
        "import sys, daftar_worker.client_app\n"
        "banned = ('analyser', 'llm', 'project', 'evaluation', 'app', 'cli', 'census')\n"
        "bad = [m for m in sys.modules if m.split('.')[:2][0] == 'daftar_worker'"
        " and m.split('.')[1:2] and m.split('.')[1] in banned]\n"
        "print(bad)\n"
        "sys.exit(1 if bad else 0)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_box_at_the_firm_has_a_private_ca_and_its_export(project: Path, tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    assert build_bundle(project, output, "1", target="lan", host="192.168.1.20")["target"] == "lan"
    assert "tls internal" in (output / "Caddyfile").read_text(encoding="utf-8")
    assert "DAFTAR_HOST=192.168.1.20" in (output / ".env").read_text(encoding="utf-8")
    assert (output / "export-ca").stat().st_mode & 0o100
    for language in ("fr", "ar"):
        text = (output / f"README.{language}.md").read_text(encoding="utf-8")
        assert "192.168.1.20" in text and "export-ca" in text
        assert "{{" not in text


def test_a_server_gets_a_public_certificate_and_says_who_can_reach_the_data(
    project: Path, tmp_path: Path
) -> None:
    output = tmp_path / "bundle"
    build_bundle(project, output, "1", target="vps", host="app.example.dz", email="ops@example.dz")
    caddy = (output / "Caddyfile").read_text(encoding="utf-8")
    assert "tls internal" not in caddy and "auto_https off" not in caddy
    assert "DAFTAR_ACME_EMAIL=ops@example.dz" in (output / ".env").read_text(encoding="utf-8")
    assert not (output / "export-ca").exists()
    assert "registre" in (output / "README.fr.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("target", "host", "email", "message"),
    [
        ("lan", None, None, "needs --host"),
        ("vps", None, "a@b.dz", "needs --host"),
        ("vps", "192.168.1.20", "a@b.dz", "isn't a domain"),
        ("vps", "app.example.dz", None, "needs --email"),
        ("lan", "bad host\nDAFTAR_SECRET=x", None, "isn't an address"),
        ("local", "app.example.dz", None, "takes no --host"),
        ("mars", None, None, "unknown target"),
    ],
)
def test_it_refuses_a_target_it_cant_set_up(
    project: Path, tmp_path: Path, target: str, host: str | None, email: str | None, message: str
) -> None:
    with pytest.raises(BundleError, match=message):
        build_bundle(project, tmp_path / "bundle", "1", target=target, host=host, email=email)
    assert not (tmp_path / "bundle").exists()
