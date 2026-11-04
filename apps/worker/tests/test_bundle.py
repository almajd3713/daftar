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


def test_it_listens_on_this_machine_until_tls_is_decided(project: Path, tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_bundle(project, output, "1")
    assert "DAFTAR_BIND=127.0.0.1" in (output / ".env").read_text(encoding="utf-8")


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
