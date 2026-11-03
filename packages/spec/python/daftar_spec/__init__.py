"""Validate Daftar app specs against packages/spec/schema/daftar.spec.schema.json."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator
from jsonschema.validators import extend


__all__ = ["SpecError", "format_errors", "load_schema", "load_spec_file", "validate_spec"]

SCHEMA_NAME = "daftar.spec.schema.json"
_DEFAULTS = Draft202012Validator.VALIDATORS


@dataclass(frozen=True, order=True)
class SpecError:
    """One problem in a spec. `path` reads like `entities[0].fields[2].key`."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def _schema_path() -> Path:
    here = Path(__file__).resolve().parent
    installed = here / "schema" / SCHEMA_NAME
    return installed if installed.exists() else here.parents[1] / "schema" / SCHEMA_NAME


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_schema_path().read_text(encoding="utf-8")))


def _strict_search(pattern: str, value: str) -> bool:
    # Python's `$` also matches before a trailing newline; JavaScript's doesn't. Without this,
    # "abc\n" would pass as a key here and could reach a database identifier.
    if pattern.endswith("$") and not pattern.endswith(r"\$"):
        pattern = pattern[:-1] + r"\Z"
    return re.search(pattern, value) is not None


def _pattern(
    validator: Validator, pattern: str, instance: Any, schema: Mapping[str, Any]
) -> Iterator[ValidationError]:
    if isinstance(instance, str) and not _strict_search(pattern, instance):
        yield ValidationError(f"must match pattern {pattern}")


def _required(
    validator: Validator, required: list[str], instance: Any, schema: Mapping[str, Any]
) -> Iterator[ValidationError]:
    if isinstance(instance, dict):
        for name in required:
            if name not in instance:
                yield ValidationError("required property is missing", path=[name])


def _additional_properties(
    validator: Validator, additional: Any, instance: Any, schema: Mapping[str, Any]
) -> Iterator[ValidationError]:
    if additional is not False:
        yield from _DEFAULTS["additionalProperties"](validator, additional, instance, schema)
        return
    if isinstance(instance, dict):
        known = schema.get("properties", {})
        patterns = schema.get("patternProperties", {})
        for name in instance:
            if name not in known and not any(_strict_search(p, name) for p in patterns):
                yield ValidationError("unknown property", path=[name])


def _branch_values(branch: Mapping[str, Any], tag: str) -> list[Any]:
    target = branch
    if "$ref" in branch:
        node: Any = load_schema()
        for part in branch["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        target = node
    tag_schema = target["properties"][tag]
    return [tag_schema["const"]] if "const" in tag_schema else list(tag_schema["enum"])


def _one_of(
    validator: Any, branches: list[Any], instance: Any, schema: Mapping[str, Any]
) -> Iterator[ValidationError]:
    discriminator = schema.get("discriminator")
    if discriminator is None:
        yield from _DEFAULTS["oneOf"](validator, branches, instance, schema)
        return
    if not isinstance(instance, dict):
        return  # The sibling `type: object` reports this.
    tag = discriminator["propertyName"]
    if tag not in instance:
        yield ValidationError("required property is missing", path=[tag])
        return
    allowed: list[Any] = []
    for branch in branches:
        values = _branch_values(branch, tag)
        if instance[tag] in values:
            yield from validator.descend(instance, branch)
            return
        allowed.extend(values)
    yield ValidationError(f"must be one of {', '.join(map(str, allowed))}", path=[tag])


_SpecValidator = extend(  # type: ignore[no-untyped-call]
    Draft202012Validator,
    {
        "additionalProperties": _additional_properties,
        "oneOf": _one_of,
        "pattern": _pattern,
        "required": _required,
    },
)


def _format_path(parts: Any) -> str:
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out or "(root)"


def validate_spec(spec: Any) -> list[SpecError]:
    """Return every schema violation, sorted by path. An empty list means the spec is valid."""
    errors = _SpecValidator(load_schema()).iter_errors(spec)
    return sorted({SpecError(_format_path(e.absolute_path), e.message) for e in errors})


def format_errors(errors: list[SpecError]) -> str:
    return "\n".join(str(error) for error in errors)


def _refuse_constant(name: str) -> None:
    raise ValueError(f"{name} is not valid JSON")


def load_spec_file(path: str | Path) -> Any:
    """Read a spec file as strict JSON. Raises OSError or ValueError if it can't be read."""
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text, parse_constant=_refuse_constant)
