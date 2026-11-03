from collections.abc import Iterator
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pytest
from workbook_builders import build_feature_workbook


@pytest.fixture
def feature_workbook(tmp_path: Path) -> Path:
    return build_feature_workbook(tmp_path / "toutes.xlsx")


@pytest.fixture
def clean_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point temporary files at an empty folder, so a test can assert nothing stays behind."""
    folder = tmp_path / "temp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    yield folder


def pytest_collection_modifyitems(config: Any, items: list[pytest.Item]) -> None:
    if shutil.which("soffice") or os.environ.get("DAFTAR_REQUIRE_LIBREOFFICE"):
        return  # With the variable set, a missing soffice fails these tests instead of skipping.
    skip = pytest.mark.skip(reason="LibreOffice is only in the worker image")
    for item in items:
        if "libreoffice" in item.keywords:
            item.add_marker(skip)
