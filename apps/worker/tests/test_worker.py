from fastapi.testclient import TestClient
import pytest

from daftar_worker.app import app
from daftar_worker.config import ConfigError, load_settings


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_defaults_and_empty_llm_url_means_rules_only() -> None:
    settings = load_settings({"DAFTAR_LLM_BASE_URL": ""})
    assert settings.default_locale == "fr-DZ"
    assert settings.timezone == "Africa/Algiers"
    assert settings.llm_base_url is None


def test_plain_ar_locale_is_refused() -> None:
    with pytest.raises(ConfigError):
        load_settings({"DAFTAR_DEFAULT_LOCALE": "ar"})
