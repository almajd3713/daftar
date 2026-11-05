"""The Studio's API, as `docs/studio-api.md` describes it."""

from collections.abc import Iterator
from pathlib import Path
import sys
import time
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest
import workbook_builders as builders

from daftar_worker.project.files import project_reanalyze
from daftar_worker.studio.app import create_studio_app
from daftar_worker.studio.preview import Previews


PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
BINARY = {"content-type": "application/octet-stream"}


@pytest.fixture(name="client")
def fixture_client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_studio_app(tmp_path / "projects", "operateur", PORT), base_url=BASE) as client:
        yield client


@pytest.fixture(name="tutoring")
def fixture_tutoring(tmp_path: Path) -> bytes:
    path = tmp_path / "tutoring.xlsx"
    builders.tutoring_workbook(path)
    return path.read_bytes()


def finished(client: TestClient, job: str) -> dict[str, Any]:
    for _ in range(600):
        body: dict[str, Any] = client.get(f"/api/jobs/{job}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("the job didn't finish")


def uploaded(client: TestClient, data: bytes, file_name: str = "cours.xlsx") -> str:
    response = client.post(f"/api/projects?fileName={file_name}&name=Cours", content=data, headers=BINARY)
    assert response.status_code == 202
    body = response.json()
    assert finished(client, body["jobId"])["status"] == "done"
    project: str = body["id"]
    return project


def analysis_of(client: TestClient, project: str) -> dict[str, Any]:
    result: dict[str, Any] = client.get(f"/api/projects/{project}/analysis").json()
    return result


def test_upload_review_and_generate(client: TestClient, tutoring: bytes) -> None:
    project = uploaded(client, tutoring)
    listed = client.get("/api/projects").json()
    assert [item["id"] for item in listed] == [project]
    assert listed[0]["name"] == "Cours"
    assert listed[0]["fileName"] == "cours.xlsx"
    assert listed[0]["counts"]["accepted"] == 0
    findings = analysis_of(client, project)["findings"]
    assert listed[0]["counts"]["pending"] == len(findings)

    accepted = client.post(f"/api/projects/{project}/decisions/accept-high", json={}).json()
    assert accepted["acceptedHigh"] == accepted["accepted"] > 0
    for finding in findings:
        if finding["decision"]["status"] == "pending" and finding["kind"] != "unsupported":
            response = client.put(f"/api/projects/{project}/findings/{finding['id']}/decision", json={"status": "accepted"})
            assert response.status_code == 200
            assert response.json()["decision"]["by"] == "operateur"

    job = client.post(f"/api/projects/{project}/generate", json={})
    assert job.status_code == 202
    report = finished(client, job.json()["jobId"])
    assert report["status"] == "done"
    for name in ("entities", "rows", "badValues", "parityFailures", "seriesFormulas", "questions"):
        assert name in report["result"]
    assert isinstance(report["result"]["badValues"], list)
    assert report["result"]["entities"] > 0


def test_nothing_is_accepted_by_an_upload(client: TestClient, tutoring: bytes) -> None:
    project = uploaded(client, tutoring)
    assert {item["decision"]["status"] for item in analysis_of(client, project)["findings"]} == {"pending"}


def test_a_decision_can_go_back_to_pending(client: TestClient, tutoring: bytes) -> None:
    project = uploaded(client, tutoring)
    finding = analysis_of(client, project)["findings"][0]
    url = f"/api/projects/{project}/findings/{finding['id']}/decision"
    assert client.put(url, json={"status": "rejected"}).json()["decision"]["status"] == "rejected"
    assert client.put(url, json={"status": "pending"}).json()["decision"] == {"status": "pending"}
    assert client.put(url, json={"status": "maybe"}).status_code == 400


def test_an_edit_must_fit_its_kind(client: TestClient, tutoring: bytes) -> None:
    project = uploaded(client, tutoring)
    finding = next(item for item in analysis_of(client, project)["findings"] if item["kind"] == "fieldType")
    url = f"/api/projects/{project}/findings/{finding['id']}/decision"
    assert client.put(url, json={"status": "edited"}).status_code == 400
    assert client.put(url, json={"status": "edited", "value": {"type": "nonsense"}}).status_code == 400
    assert client.put(url, json={"status": "edited", "value": {"nonsense": 1}}).status_code == 400
    good = client.put(url, json={"status": "edited", "value": {"type": "text"}})
    assert good.status_code == 200
    assert good.json()["decision"]["value"] == {"type": "text"}


def test_a_bad_file_leaves_nothing_behind(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/projects?fileName=x.xlsx", content=b"not a workbook", headers=BINARY)
    assert response.status_code == 202
    body = response.json()
    job = finished(client, body["jobId"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "unreadable"
    assert job["error"]["message"]["ar"]
    assert client.get("/api/projects").json() == []
    assert client.get(f"/api/projects/{body['id']}/analysis").status_code == 404
    assert [item.name for item in (tmp_path / "projects").iterdir()] == []
    assert client.post("/api/projects?fileName=x.xlsx", content=b"", headers=BINARY).status_code == 422


def test_snapshot_has_no_cells_and_a_sheet_comes_by_range(client: TestClient, tutoring: bytes) -> None:
    project = uploaded(client, tutoring)
    snapshot = client.get(f"/api/projects/{project}/snapshot").json()
    assert snapshot["source"]["fileName"] == "cours.xlsx"
    assert "cells" not in snapshot["sheets"][0]
    assert snapshot["sheets"][0]["cellCount"] > 0
    part = client.get(f"/api/projects/{project}/sheets/0?range=A1:B2").json()
    assert part["cells"]
    assert {cell["ref"] for cell in part["cells"]} <= {"A1", "B1", "A2", "B2"}
    assert client.get(f"/api/projects/{project}/sheets/99?range=A1:B2").status_code == 404
    assert client.get(f"/api/projects/{project}/sheets/0?range=nonsense!!").status_code == 400
    assert client.get(f"/api/projects/{project}/sheets/0?range=A1:ZZ9999").status_code == 400
    assert client.get(f"/api/projects/{project}/sheets/0").status_code == 422


def test_a_rerun_keeps_decisions_and_shows_conflicts(client: TestClient, tmp_path: Path) -> None:
    def book(rows: int, extra: bool = False) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        sheet.append(["Nom", "Ville", *(["Âge"] if extra else [])])
        for row in range(rows):
            sheet.append([f"Nom {row}", "Oran", *([20] if extra else [])])
        target = tmp_path / "b.xlsx"
        workbook.save(target)
        return target.read_bytes()

    project = uploaded(client, book(6))
    findings = analysis_of(client, project)["findings"]
    table = next(item for item in findings if item["kind"] == "table")
    client.put(f"/api/projects/{project}/findings/{table['id']}/decision", json={"status": "accepted"})

    same = finished(client, client.post(f"/api/projects/{project}/reanalyze", json={}).json()["jobId"])
    assert same["result"]["applied"] == 1
    assert client.get(f"/api/projects/{project}/conflicts").json() == []

    updated = client.post(f"/api/projects/{project}/reanalyze?fileName=b2.xlsx", content=book(8), headers=BINARY)
    assert finished(client, updated.json()["jobId"])["status"] == "done"
    assert client.get("/api/projects").json()[0]["fileName"] == "b2.xlsx"
    statuses = {item["kind"]: item["decision"]["status"] for item in analysis_of(client, project)["findings"] if item["kind"] == "table"}
    assert statuses == {"table": "accepted"}

    # An unreadable new file changes nothing.
    bad = client.post(f"/api/projects/{project}/reanalyze?fileName=b3.xlsx", content=b"nope", headers=BINARY)
    assert finished(client, bad.json()["jobId"])["status"] == "failed"
    assert client.get(f"/api/projects/{project}/snapshot").json()["source"]["fileName"] == "b2.xlsx"
    assert client.post(f"/api/projects/{project}/reanalyze", content=b"x", headers=BINARY).status_code == 422


def test_a_decision_on_a_finding_a_rerun_removed_says_so(client: TestClient, tmp_path: Path) -> None:
    project = uploaded(client, _months(tmp_path))
    findings = analysis_of(client, project)["findings"]
    gone = next(item for item in findings if item["kind"] == "periodUnion")
    client.put(f"/api/projects/{project}/findings/{gone['id']}/decision", json={"status": "accepted"})
    single = Workbook()
    sheet = single.active
    assert sheet is not None
    sheet.append(["Nom", "Ville"])
    sheet.append(["Ali", "Oran"])
    sheet.append(["Sara", "Blida"])
    target = tmp_path / "one.xlsx"
    single.save(target)
    job = client.post(f"/api/projects/{project}/reanalyze?fileName=one.xlsx", content=target.read_bytes(), headers=BINARY)
    finished(client, job.json()["jobId"])
    conflicts = client.get(f"/api/projects/{project}/conflicts").json()
    assert any(item["reason"] == "gone" and item["finding"]["id"] == gone["id"] for item in conflicts)
    refused = client.put(f"/api/projects/{project}/findings/{gone['id']}/decision", json={"status": "rejected"})
    assert refused.status_code == 409
    assert refused.json()["reason"]["ar"]
    assert client.put(f"/api/projects/{project}/findings/nope/decision", json={"status": "rejected"}).status_code == 404


def _months(tmp_path: Path, year: bool = True) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name in ("Janvier", "Février", "Mars"):
        sheet = book.create_sheet(f"{name} 2026" if year else name)
        sheet.append(["Facture", "Client", "Montant"])
        for row in range(1, 5):
            sheet.append([f"{name}-{row}", f"Client {row}", row * 100])
    target = tmp_path / "m.xlsx"
    book.save(target)
    return target.read_bytes()


def test_answers_survive_a_rerun_and_reach_the_app(client: TestClient, tmp_path: Path) -> None:
    project = uploaded(client, _months(tmp_path, year=False))
    for finding in analysis_of(client, project)["findings"]:
        if finding["kind"] != "unsupported":
            client.put(f"/api/projects/{project}/findings/{finding['id']}/decision", json={"status": "accepted"})
    first = finished(client, client.post(f"/api/projects/{project}/generate", json={}).json()["jobId"])["result"]
    asked = [item["sheet"] for item in first["questions"] if item["kind"] == "periodYear"]
    assert sorted(asked) == ["Février", "Janvier", "Mars"]
    assert first["rows"] == {}
    assert client.post(f"/api/projects/{project}/answers", json={"kind": "periodYear", "sheet": "Mars", "year": 1}).status_code == 400
    assert client.post(f"/api/projects/{project}/answers", json={"kind": "odd"}).status_code == 400
    for sheet in asked[:2]:
        left = client.post(f"/api/projects/{project}/answers", json={"kind": "periodYear", "sheet": sheet, "year": 2026}).json()["questions"]
    assert [item["sheet"] for item in left if item["kind"] == "periodYear"] == asked[2:]
    client.post(f"/api/projects/{project}/answers", json={"kind": "periodYear", "sheet": asked[2], "year": 2026})
    finished(client, client.post(f"/api/projects/{project}/reanalyze", json={}).json()["jobId"])
    second = finished(client, client.post(f"/api/projects/{project}/generate", json={}).json()["jobId"])["result"]
    assert not [item for item in second["questions"] if item["kind"] == "periodYear"]
    assert second["rows"]["suivi_par_periode"] == 12


def test_nothing_is_changed_while_a_job_runs(client: TestClient, tutoring: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    project = uploaded(client, tutoring)
    finding = analysis_of(client, project)["findings"][0]
    gate = {"open": False}
    real = project_reanalyze

    def slow(*args: Any, **kwargs: Any) -> dict[str, Any]:
        while not gate["open"]:
            time.sleep(0.01)
        return real(*args, **kwargs)

    monkeypatch.setattr("daftar_worker.studio.app.project_reanalyze", slow)
    job = client.post(f"/api/projects/{project}/reanalyze", json={}).json()["jobId"]
    refused = client.put(f"/api/projects/{project}/findings/{finding['id']}/decision", json={"status": "accepted"})
    assert refused.status_code == 409
    assert refused.json()["reason"]["fr"]
    assert client.post(f"/api/projects/{project}/decisions/accept-high", json={}).status_code == 409
    assert client.post(f"/api/projects/{project}/generate", json={}).status_code == 409
    assert client.post(f"/api/projects/{project}/reanalyze", json={}).status_code == 409
    assert client.get(f"/api/projects/{project}/analysis").status_code == 200
    gate["open"] = True
    assert finished(client, job)["status"] == "done"
    assert client.put(f"/api/projects/{project}/findings/{finding['id']}/decision", json={"status": "accepted"}).status_code == 200


def test_other_websites_are_kept_out(client: TestClient, tutoring: bytes) -> None:
    assert client.get("/api/projects", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/projects", headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/projects", headers={"origin": BASE}).status_code == 200
    project = uploaded(client, tutoring)
    finding = analysis_of(client, project)["findings"][0]
    url = f"/api/projects/{project}/findings/{finding['id']}/decision"
    # What a plain form on another site can send.
    for kind in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
        assert client.put(url, content='{"status":"accepted"}', headers={"content-type": kind}).status_code == 415
        assert client.post("/api/projects?fileName=x.xlsx", content=tutoring, headers={"content-type": kind}).status_code == 415
        assert client.post(f"/api/projects/{project}/decisions/accept-high", content="{}", headers={"content-type": kind}).status_code == 415
    assert client.post(f"/api/projects/{project}/decisions/accept-high").status_code == 415
    assert "access-control-allow-origin" not in client.get("/api/projects", headers={"origin": BASE}).headers


def test_project_ids_are_never_paths(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "project.json").write_text("{}", encoding="utf-8")
    for project in ("..%2Fsecret", "secret", "%2E%2E"):
        assert client.get(f"/api/projects/{project}/analysis").status_code == 404


def test_a_file_name_is_never_a_path(client: TestClient, tutoring: bytes, tmp_path: Path) -> None:
    response = client.post("/api/projects", params={"fileName": "..\\..\\evil.xlsx"}, content=tutoring, headers=BINARY)
    finished(client, response.json()["jobId"])
    assert client.get("/api/projects").json()[0]["fileName"] == "evil.xlsx"
    assert not (tmp_path / "evil.xlsx").exists()


def test_unknown_things_are_404(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/projects/0123456789abcdef0123456789abcdef/snapshot").status_code == 404


FAKE_RUNTIME = """
import json, os, sys
assert os.environ["DAFTAR_PREVIEW_DATABASE"].startswith("daftar_preview_")
assert os.path.exists(os.environ["DAFTAR_SPEC_PATH"])
assert "SECRET_OF_THE_STUDIO" not in os.environ
print(json.dumps({"port": 45678, "cookie": "daftar_session=abc"}), flush=True)
sys.stdin.read()
"""


@pytest.fixture(name="previews")
def fixture_previews(tmp_path: Path) -> Iterator[Previews]:
    script = tmp_path / "fake_runtime.py"
    script.write_text(FAKE_RUNTIME, encoding="utf-8")
    previews = Previews([sys.executable, str(script)], "postgres://x")
    yield previews
    previews.stop_all()


@pytest.fixture(name="with_preview")
def fixture_with_preview(tmp_path: Path, previews: Previews) -> Iterator[TestClient]:
    app = create_studio_app(tmp_path / "projects", "operateur", PORT, previews)
    with TestClient(app, base_url=BASE, follow_redirects=False) as client:
        yield client


def _generated(client: TestClient, tmp_path: Path) -> str:
    project = uploaded(client, _months(tmp_path))
    client.post(f"/api/projects/{project}/decisions/accept-high", json={})
    assert finished(client, client.post(f"/api/projects/{project}/generate", json={}).json()["jobId"])["status"] == "done"
    return project


def test_a_preview_opens_signed_in_and_stops(with_preview: TestClient, previews: Previews, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_OF_THE_STUDIO", "x")
    project = _generated(with_preview, tmp_path)
    assert with_preview.get(f"/api/projects/{project}/preview/open").status_code == 404
    job = finished(with_preview, with_preview.post(f"/api/projects/{project}/preview", json={}).json()["jobId"])
    assert job["status"] == "done"
    assert "abc" not in str(job)  # The session never reaches the page's scripts.
    opened = with_preview.get(job["result"]["url"])
    assert opened.status_code == 303
    assert opened.headers["location"] == "http://127.0.0.1:45678/"
    assert "daftar_session=abc" in opened.headers["set-cookie"]
    assert "httponly" in opened.headers["set-cookie"].lower()
    running = previews.running(project)
    assert running is not None
    process, folder = running.process, Path(running.folder.name)
    assert with_preview.delete(f"/api/projects/{project}/preview").status_code == 204
    assert process.poll() is not None
    assert not folder.exists()
    assert with_preview.get(job["result"]["url"]).status_code == 404


def test_starting_again_replaces_the_old_preview(with_preview: TestClient, previews: Previews, tmp_path: Path) -> None:
    project = _generated(with_preview, tmp_path)
    finished(with_preview, with_preview.post(f"/api/projects/{project}/preview", json={}).json()["jobId"])
    first = previews.running(project)
    assert first is not None
    finished(with_preview, with_preview.post(f"/api/projects/{project}/preview", json={}).json()["jobId"])
    assert first.process.poll() is not None
    assert previews.running(project) is not first


def test_a_preview_needs_generating_first_and_a_database(with_preview: TestClient, client: TestClient, tutoring: bytes) -> None:
    project = uploaded(with_preview, tutoring)
    refused = with_preview.post(f"/api/projects/{project}/preview", json={})
    assert refused.status_code == 409
    assert refused.json()["reason"]["ar"]
    other = uploaded(client, tutoring)
    assert client.post(f"/api/projects/{other}/preview", json={}).status_code == 503


def test_a_preview_that_doesnt_start_is_a_failed_job(tmp_path: Path) -> None:
    script = tmp_path / "broken.py"
    script.write_text("import sys; sys.exit(1)", encoding="utf-8")
    previews = Previews([sys.executable, str(script)], "postgres://x")
    with TestClient(create_studio_app(tmp_path / "projects", "operateur", PORT, previews), base_url=BASE) as client:
        project = _generated(client, tmp_path)
        job = finished(client, client.post(f"/api/projects/{project}/preview", json={}).json()["jobId"])
        assert job["status"] == "failed"
        assert job["error"]["message"]["fr"]
        assert previews.running(project) is None


def test_closing_the_studio_stops_previews(tmp_path: Path) -> None:
    script = tmp_path / "fake_runtime.py"
    script.write_text(FAKE_RUNTIME, encoding="utf-8")
    previews = Previews([sys.executable, str(script)], "postgres://x")
    with TestClient(create_studio_app(tmp_path / "projects", "operateur", PORT, previews), base_url=BASE) as client:
        project = _generated(client, tmp_path)
        finished(client, client.post(f"/api/projects/{project}/preview", json={}).json()["jobId"])
        running = previews.running(project)
        assert running is not None
    assert running.process.poll() is not None
