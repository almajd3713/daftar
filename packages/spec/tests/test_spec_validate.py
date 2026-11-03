import copy
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from daftar_spec import load_schema, validate_spec


SPEC_DIR = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((SPEC_DIR / "examples").glob("*.spec.json"))
CASES = json.loads((SPEC_DIR / "fixtures" / "invalid-cases.json").read_text(encoding="utf-8"))


def load_example(name: str) -> dict[str, Any]:
    data = json.loads((SPEC_DIR / "examples" / f"{name}.spec.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def change(spec: Any, at: list[Any], value: Any = None, remove: bool = False) -> None:
    node = spec
    for part in at[:-1]:
        node = node[part]
    if remove:
        del node[at[-1]]
    else:
        node[at[-1]] = value


def test_there_is_one_example_per_kind() -> None:
    assert {path.name.removesuffix(".spec.json") for path in EXAMPLES} == {
        "tutoring-register",
        "payments-ledger",
        "fee-calculator",
        "repair-tracker",
    }


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_is_valid(path: Path) -> None:
    assert validate_spec(json.loads(path.read_text(encoding="utf-8"))) == []


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_invalid_spec_reports_its_path(case: dict[str, Any]) -> None:
    spec = copy.deepcopy(load_example(case["base"]))
    change(spec, case["at"], case.get("set"), case.get("remove", False))
    if "alsoAt" in case:
        change(spec, case["alsoAt"], case["alsoSet"])
    assert sorted({error.path for error in validate_spec(spec)}) == case["expect"]


def test_schema_is_the_single_source() -> None:
    assert load_schema()["title"] == "DaftarSpec"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "daftar_spec", *args], capture_output=True, text=True, check=False
    )


def test_cli_exit_codes_follow_c5(tmp_path: Path) -> None:
    assert run_cli(str(EXAMPLES[0])).returncode == 0

    bad = load_example("fee-calculator")
    bad["app"]["currency"] = "EUR"
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(bad), encoding="utf-8")
    result = run_cli(str(invalid))
    assert result.returncode == 3
    assert "app.currency:" in result.stderr

    not_json = tmp_path / "broken.json"
    not_json.write_text("{ NaN", encoding="utf-8")
    assert run_cli(str(not_json)).returncode == 2
    assert run_cli(str(tmp_path / "missing.json")).returncode == 2


def test_nan_is_not_json(tmp_path: Path) -> None:
    path = tmp_path / "nan.json"
    path.write_text('{"a": NaN}', encoding="utf-8")
    assert run_cli(str(path)).returncode == 2


# JSON Schema can't see these. The examples are fixtures for later packages, so they must hold.
def keys(items: list[dict[str, Any]]) -> set[str]:
    found = [item["key"] for item in items]
    assert len(found) == len(set(found)), f"duplicate keys in {found}"
    return set(found)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_cross_references_resolve(path: Path) -> None:
    spec = json.loads(path.read_text(encoding="utf-8"))
    entity_keys = keys(spec["entities"])
    fields = {entity["key"]: keys(entity["fields"]) for entity in spec["entities"]}
    keys(spec["views"])
    keys(spec["forms"])
    keys(spec["dashboards"])
    keys(spec["roles"])
    keys(spec["calculators"])
    keys(spec["reminders"])
    workflows = {workflow["key"]: workflow for workflow in spec["workflows"]}

    for entity in spec["entities"]:
        own = fields[entity["key"]]
        assert entity["titleField"] in own
        assert set(entity.get("searchFields", [])) <= own
        if "period" in entity:
            assert entity["period"]["field"] in own
        if "field" in entity["naming"]:
            assert entity["naming"]["field"] in own
        for field in entity["fields"]:
            if field["type"] == "link":
                assert field["target"] in entity_keys
            if field["type"] == "child":
                assert field["via"] in fields[field["target"]]
            if field["type"] == "computed":
                assert set(field["computed"]["deps"]) <= own

    for view in spec["views"]:
        own = fields[view["entity"]]
        assert set(view.get("columns", view.get("cardFields"))) <= own
        assert {item["field"] for item in view.get("sort", [])} <= own
        assert {item["field"] for item in view.get("filters", [])} <= own
        assert set(view.get("totals", [])) <= own
        if view["type"] == "board":
            assert workflows[view["workflow"]]["entity"] == view["entity"]

    for form in spec["forms"]:
        for section in form["sections"]:
            assert set(section["fields"]) <= fields[form["entity"]]

    for dashboard in spec["dashboards"]:
        for widget in dashboard["widgets"]:
            own = fields[widget["entity"]]
            assert {widget[name] for name in ("field", "groupBy") if name in widget} <= own

    for role in spec["roles"]:
        assert {item["entity"] for item in role["permissions"]} <= entity_keys

    for workflow in spec["workflows"]:
        states = keys(workflow["states"])
        field = next(
            item
            for item in next(e for e in spec["entities"] if e["key"] == workflow["entity"])[
                "fields"
            ]
            if item["key"] == workflow["stateField"]
        )
        assert keys(field["choices"]) == states
        assert workflow["initialState"] in states
        keys(workflow["transitions"])
        for transition in workflow["transitions"]:
            assert set(transition["from"]) | {transition["to"]} <= states

    for reminder in spec["reminders"]:
        assert reminder["dateField"] in fields[reminder["entity"]]

    for mapping in spec["mapping"]:
        own = fields[mapping["entity"]]
        columns = {column["field"] for column in mapping["columns"]}
        assert columns <= own
        assert set(mapping["keyColumns"]) <= columns

    for calculator in spec["calculators"]:
        cells = {(cell["sheet"], cell["ref"]) for cell in calculator["cells"]}
        input_keys = keys(calculator["inputs"])
        output_keys = keys(calculator["outputs"])
        for port in calculator["inputs"] + calculator["outputs"]:
            assert (port["sheet"], port["cell"]) in cells
        for test_case in calculator["testCases"]:
            assert set(test_case["inputs"]) == input_keys
            assert set(test_case["outputs"]) == output_keys
