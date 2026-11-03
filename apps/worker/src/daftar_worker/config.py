"""C-10 config keys the worker reads."""

from collections.abc import Mapping
from dataclasses import dataclass
import os


LOCALES = ("fr-DZ", "ar-DZ")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    default_locale: str
    timezone: str
    llm_base_url: str | None
    llm_model: str | None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env
    locale = source.get("DAFTAR_DEFAULT_LOCALE") or "fr-DZ"
    if locale not in LOCALES:
        raise ConfigError(f"DAFTAR_DEFAULT_LOCALE must be one of {LOCALES}, got {locale!r}")
    return Settings(
        default_locale=locale,
        timezone=source.get("DAFTAR_TZ") or "Africa/Algiers",
        llm_base_url=source.get("DAFTAR_LLM_BASE_URL") or None,
        llm_model=source.get("DAFTAR_LLM_MODEL") or None,
    )
