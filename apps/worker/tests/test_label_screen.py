"""WP-4's labelling screen: it must never damage a label, and never serve anyone but this machine."""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest
import workbook_builders as builders

from daftar_worker.evaluation.label_screen import create_label_app
from daftar_worker.evaluation.labels import EvalError, check_against_workbook, read_manifest
from daftar_worker.evaluation.run import _series_of, run_evaluation, workbook_path, write_drafts
from daftar_worker.reader import read_file


PORT = 8790
HEADERS = {"X-Daftar-Label": "1"}
JANVIER = "Janvier 2026"


def _manifest(root: Path, rows: list[tuple[str, str]]) -> Path:
    path = root / "manifest.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "source", "licence", "language", "stratum", "split", "consent", "sha256"])
        for workbook_id, split in rows:
            digest = hashlib.sha256((root / "workbooks" / f"{workbook_id}.xlsx").read_bytes()).hexdigest()
            writer.writerow([workbook_id, "test", "test", "fr", "ledger", split, "invented", digest])
    return path


@pytest.fixture(name="root")
def fixture_root(tmp_path: Path) -> Path:
    (tmp_path / "workbooks").mkdir()
    builders.tutoring_workbook(tmp_path / "workbooks" / "centre.xlsx")
    builders.tutoring_workbook(tmp_path / "workbooks" / "held.xlsx")
    # The same bytes can't be in both splits, so the held-back one gets a byte of its own.
    held = tmp_path / "workbooks" / "held.xlsx"
    builders.patch_zip(held, edit={"docProps/core.xml": lambda xml: xml + " "})
    _manifest(tmp_path, [("centre", "dev"), ("held", "test")])
    return tmp_path


@pytest.fixture(name="client")
def fixture_client(root: Path) -> TestClient:
    app = create_label_app(root / "labels", root / "manifest.csv", "Amina", PORT)
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}", headers=HEADERS)


def editable(data: dict[str, Any], **changes: Any) -> dict[str, Any]:
    label = data["label"]
    return {"status": "draft", "workbook": label.get("workbook"), "sheets": label["sheets"], "relations": label["relations"], **changes}


def stored(root: Path, workbook_id: str = "centre") -> dict[str, Any]:
    result: dict[str, Any] = json.loads((root / "labels" / f"{workbook_id}.json").read_text(encoding="utf-8"))
    return result


def valid_sheets(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Every sheet converted or set aside, so that a review can pass."""
    sheets: list[dict[str, Any]] = data["label"]["sheets"]
    for sheet in sheets:
        if not sheet["tables"] and sheet["kind"] != "formulaModel":
            sheet["kind"] = "notConverted"
            sheet["reason"] = "outOfScope"
        sheet.pop("periodGroup", None)
    return sheets


def test_the_list_shows_every_workbook_and_who_is_labelling(client: TestClient) -> None:
    data = client.get("/api/workbooks").json()
    assert data["who"] == "Amina"
    assert [(item["id"], item["split"], item["status"]) for item in data["workbooks"]] == [("centre", "dev", "new"), ("held", "test", "new")]


def test_opening_starts_a_draft_with_header_names_and_the_analysers_guesses(client: TestClient, root: Path) -> None:
    data = client.get("/api/workbooks/centre").json()
    assert data["label"]["status"] == "draft"
    january = next(sheet for sheet in data["label"]["sheets"] if sheet["name"] == JANVIER)
    assert january["tables"]
    names = [field["name"] for field in january["tables"][0]["fields"]]
    assert "Matricule" in names
    assert (root / "labels" / "centre.json").exists()
    assert client.get("/api/workbooks").json()["workbooks"][0]["status"] == "draft"


def test_a_draft_groups_the_tabs_the_analyser_sees_as_a_series(client: TestClient) -> None:
    sheets = client.get("/api/workbooks/centre").json()["label"]["sheets"]
    groups = {sheet["name"]: sheet.get("periodGroup") for sheet in sheets}
    assert groups[JANVIER] == groups["Février 2026"] == groups["Mars 2026"] is not None
    assert groups["Élèves"] is None


def test_a_test_workbook_starts_blank_so_guesses_cant_steer_the_published_number(client: TestClient, root: Path) -> None:
    data = client.get("/api/workbooks/held").json()
    assert all(sheet["tables"] == [] and sheet["kind"] == "notConverted" for sheet in data["label"]["sheets"])
    assert data["label"]["relations"] == []
    assert stored(root, "held")["formulas"]


def test_the_prelabel_command_refuses_guesses_for_the_test_split(root: Path, tmp_path: Path) -> None:
    with pytest.raises(EvalError, match="start blank"):
        write_drafts(root / "labels", root / "manifest.csv", "test", tmp_path, tmp_path / "out")


def test_opening_again_keeps_what_was_there(client: TestClient, root: Path) -> None:
    data = client.get("/api/workbooks/centre").json()
    data["label"]["workbook"]["notes"] = "à vérifier"
    assert client.put("/api/workbooks/centre/label", json=editable(data)).json()["saved"]
    assert client.get("/api/workbooks/centre").json()["label"]["workbook"]["notes"] == "à vérifier"


def test_formula_results_arent_sent_and_cant_be_changed(client: TestClient, root: Path) -> None:
    data = client.get("/api/workbooks/centre").json()
    assert "formulas" not in data["label"]
    assert data["label"]["formulaCount"] == len(stored(root)["formulas"]) > 0
    before = stored(root)
    body = editable(data, formulas=[], id="other", workbookSha256="0" * 64, resultsFrom="none", labelVersion=9)
    assert client.put("/api/workbooks/centre/label", json=body).json()["saved"]
    after = stored(root)
    for key in ("formulas", "id", "workbookSha256", "resultsFrom", "labelVersion"):
        assert after[key] == before[key]


def test_a_label_that_breaks_the_format_isnt_written(client: TestClient, root: Path) -> None:
    data = client.get("/api/workbooks/centre").json()
    before = stored(root)
    data["label"]["sheets"][0]["kind"] = "nonsense"
    response = client.put("/api/workbooks/centre/label", json=editable(data))
    assert response.status_code == 422
    assert response.json()["saved"] is False
    assert stored(root) == before


def test_a_review_with_problems_stays_a_draft_and_lists_them(client: TestClient, root: Path) -> None:
    data = client.get("/api/workbooks/centre").json()
    data["label"]["sheets"][0]["kind"] = "register"
    data["label"]["sheets"][0]["reason"] = "form"
    data["label"]["sheets"][0]["tables"] = []
    answer = client.put("/api/workbooks/centre/label", json=editable(data, status="reviewed")).json()
    assert answer["status"] == "draft"
    assert any("needs a table" in text for text in answer["problems"])
    assert stored(root)["status"] == "draft"
    assert "labelledBy" not in stored(root)


def test_a_clean_review_records_who_and_counts_towards_the_score(client: TestClient, root: Path) -> None:
    data = client.get("/api/workbooks/centre").json()
    data["label"]["sheets"] = valid_sheets(data)
    answer = client.put("/api/workbooks/centre/label", json=editable(data, status="reviewed")).json()
    assert answer["status"] == "reviewed", answer
    assert answer["problems"] == []
    assert stored(root)["labelledBy"] == ["Amina"]
    # A second review by the same person doesn't count them twice.
    client.put("/api/workbooks/centre/label", json=editable(data, status="reviewed"))
    assert stored(root)["labelledBy"] == ["Amina"]
    manifest = root / "manifest.csv"
    rows = [row for row in read_manifest(manifest) if row.split == "dev"]
    assert len(rows) == 1
    report = run_evaluation(root / "labels", manifest, "dev", root / "no-analyses")
    assert report["workbooks"] == 1


def test_saving_a_draft_after_a_review_takes_the_review_back(client: TestClient, root: Path) -> None:
    data = client.get("/api/workbooks/centre").json()
    data["label"]["sheets"] = valid_sheets(data)
    client.put("/api/workbooks/centre/label", json=editable(data, status="reviewed"))
    assert client.put("/api/workbooks/centre/label", json=editable(data, status="draft")).json()["status"] == "draft"
    assert stored(root)["status"] == "draft"


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8790", "127.0.0.1:9999", "0.0.0.0:8790"])
def test_only_this_machines_address_is_served(root: Path, host: str) -> None:
    app = create_label_app(root / "labels", root / "manifest.csv", "Amina", PORT)
    client = TestClient(app, base_url=f"http://{host}", headers=HEADERS)
    assert client.get("/api/workbooks").status_code == 403
    assert client.get("/").status_code == 403
    assert client.get("/api/workbooks/centre/file").status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1:8790", "localhost:8790"])
def test_both_names_of_this_machine_work(root: Path, host: str) -> None:
    app = create_label_app(root / "labels", root / "manifest.csv", "Amina", PORT)
    assert TestClient(app, base_url=f"http://{host}").get("/api/workbooks").status_code == 200


def test_a_write_from_another_site_is_refused(root: Path, client: TestClient) -> None:
    data = client.get("/api/workbooks/centre").json()
    before = stored(root)
    plain = TestClient(client.app, base_url=f"http://127.0.0.1:{PORT}")
    assert plain.put("/api/workbooks/centre/label", json=editable(data, status="draft")).status_code == 403
    assert plain.post("/api/workbooks/centre/time", json={"seconds": 15}).status_code == 403
    assert stored(root) == before


@pytest.mark.parametrize("workbook_id", ["nope", "..", "..%2F..%2Fsecret", "centre.json"])
def test_only_listed_workbooks_can_be_reached(client: TestClient, workbook_id: str) -> None:
    assert client.get(f"/api/workbooks/{workbook_id}").status_code in (404, 405)
    assert client.get(f"/api/workbooks/{workbook_id}/file").status_code in (404, 405)


def test_a_changed_file_is_refused(root: Path) -> None:
    builders.patch_zip(root / "workbooks" / "centre.xlsx", edit={"docProps/core.xml": lambda xml: xml + "  "})
    app = create_label_app(root / "labels", root / "manifest.csv", "Amina", PORT)
    response = TestClient(app, base_url=f"http://127.0.0.1:{PORT}").get("/api/workbooks/centre")
    assert response.status_code == 422
    assert "sha256" in response.json()["detail"]


def test_time_adds_up_per_person_and_stays_private(client: TestClient, root: Path) -> None:
    for _ in range(3):
        assert client.post("/api/workbooks/centre/time", json={"seconds": 15}).status_code == 200
    assert client.get("/api/workbooks").json()["workbooks"][0]["seconds"] == {"Amina": 45}
    assert (root / "private" / "label-times.json").exists()


@pytest.mark.parametrize("seconds", [0, -5, 61, "15", True, None])
def test_time_only_takes_a_sensible_beat(client: TestClient, seconds: Any) -> None:
    assert client.post("/api/workbooks/centre/time", json={"seconds": seconds}).status_code == 422


def test_the_original_can_be_opened(client: TestClient, root: Path) -> None:
    response = client.get("/api/workbooks/centre/file")
    assert response.status_code == 200
    assert response.content == (root / "workbooks" / "centre.xlsx").read_bytes()


def test_the_page_never_turns_a_cell_into_markup_and_says_so_to_the_browser(client: TestClient) -> None:
    response = client.get("/")
    assert "innerHTML" not in response.text
    assert "insertAdjacentHTML" not in response.text
    assert "document.write" not in response.text
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "http://" not in response.text and "https://" not in response.text


def _label(*sheets: dict[str, Any], relations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"sheets": list(sheets), "relations": relations or []}


def _sheet(name: str = "A", kind: str = "register", tables: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    return {"name": name, "kind": kind, "regions": [], "tables": tables or [], **extra}


def _table(range_: str = "A1:B5", headers: list[int] | None = None, columns: str = "AB", **extra: Any) -> dict[str, Any]:
    return {"range": range_, "headerRows": [1] if headers is None else headers, "fields": [{"column": c, "name": c, "type": "text"} for c in columns], **extra}


def _snapshot(*names: str) -> dict[str, Any]:
    return {"sheets": [{"name": name} for name in names or ("A",)]}


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (_label(_sheet(tables=[_table(headers=[9])])), "header row 9 is outside"),
        (_label(_sheet(tables=[_table(totalRows=[9])])), "total row 9 is outside"),
        (_label(_sheet(tables=[_table(totalRows=[1])])), "both a header and a total"),
        (_label(_sheet(tables=[_table(columns="AC")])), "field C is outside"),
        (_label(_sheet(tables=[_table(columns="AA")])), "column A has two fields"),
        (_label(_sheet(tables=[_table(columns="")])), "no fields"),
        (_label(_sheet(tables=[_table(), _table("B3:C9", columns="BC")])), "overlap"),
        (_label(_sheet(kind="notConverted", reason="form", tables=[_table()])), "can't have tables"),
        (_label(_sheet()), "needs a table"),
        (_label(_sheet("B", tables=[_table()])), "not labelled"),
        (_label(_sheet(tables=[_table()], periodGroup="Mois")), "needs at least two tabs"),
        (_label(_sheet(tables=[_table()]), relations=[{"from": {"sheet": "A", "column": "A"}, "to": {"sheet": "Z", "column": "A"}}]), "no sheet Z"),
        (_label(_sheet(tables=[_table()]), relations=[{"from": {"sheet": "A", "column": "A"}, "to": {"sheet": "A", "column": "A"}}]), "itself"),
    ],
)
def test_mistakes_only_the_workbook_can_show(label: dict[str, Any], expected: str) -> None:
    problems, _ = check_against_workbook(label, _snapshot())
    assert any(expected in text for text in problems), problems


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (_label(_sheet(tables=[_table(columns="A")])), "some columns"),
        (_label(_sheet(tables=[_table(headers=[])])), "no header row"),
        (_label(_sheet(tables=[_table()]), relations=[{"from": {"sheet": "A", "column": "A"}, "to": {"sheet": "A", "column": "Z"}}]), "isn't in a table"),
    ],
)
def test_things_worth_a_second_look_dont_block(label: dict[str, Any], expected: str) -> None:
    problems, warnings = check_against_workbook(label, _snapshot())
    assert problems == []
    assert any(expected in text for text in warnings), warnings


def test_series_join_up_however_the_pairs_arrive() -> None:
    assert _series_of({("B", "C"), ("A", "B"), ("X", "Y")}) == {"A": "A", "B": "A", "C": "A", "X": "X", "Y": "X"}
    assert _series_of({("A", "B"), ("C", "D"), ("B", "C")}) == {"A": "A", "B": "A", "C": "A", "D": "A"}


def test_a_correct_label_has_nothing_to_say() -> None:
    label = _label(_sheet(tables=[_table()]), _sheet("B", "formulaModel"), _sheet("C", "notConverted", reason="empty"))
    assert check_against_workbook(label, _snapshot("A", "B", "C")) == ([], [])


def test_the_real_batch_is_listed_and_every_file_matches() -> None:
    root = Path(__file__).resolve().parents[3] / "eval"
    if not (root / "workbooks").exists():
        pytest.skip("the worker image doesn't carry the evaluation set")
    rows = read_manifest(root / "manifest.csv")
    assert rows
    for row in rows:
        path = workbook_path(root / "manifest.csv", row)
        if path is None:
            # Private workbooks exist only on the labeller's machine. Published ones must be here.
            assert row.id.startswith("sb_"), row.id
            continue
        assert read_file(path)["source"]["sha256"] == row.sha256
