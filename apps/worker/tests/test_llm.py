from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import threading
from typing import Any

from jsonschema import Draft202012Validator
import pytest
import xlsxwriter

from daftar_worker import analyser
from daftar_worker.analyser import analyze, analyze_snapshot
from daftar_worker.cli import main
from daftar_worker.llm.client import LlmClient, LlmSettings, settings_from_env
from daftar_worker.llm.glossary import gloss
from daftar_worker.llm.tasks import apply_model, keeps_facts, keeps_language
from daftar_worker.reader import read_file


SCHEMA = json.loads(Path(analyser.__file__).with_name("analysis.schema.json").read_text(encoding="utf-8"))
Script = Callable[[dict[str, Any]], Any]


class FakeModel:
    """An OpenAI-compatible server whose answers come from a test's script."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.script: Script = lambda _: {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                if self.path.endswith("/api/show"):
                    self._send({"details": {"quantization_level": "Q4_K_M"}})
                    return
                outer.requests.append(body)
                answer = outer.script(body)
                content = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
                self._send({"choices": [{"message": {"content": content}}]})

            def _send(self, data: dict[str, Any]) -> None:
                encoded = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_: Any) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def settings(self) -> LlmSettings:
        return LlmSettings(f"http://127.0.0.1:{self.server.server_port}/v1", "fake-model")

    def tasks(self) -> list[str]:
        return [request["response_format"]["json_schema"]["name"] for request in self.requests]


@pytest.fixture
def model() -> Iterator[FakeModel]:
    fake = FakeModel()
    yield fake
    fake.server.shutdown()


def workbook(path: Path) -> Path:
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Clients")
    sheet.write_row("A1", ["Nom", "Tel"], book.add_format({"bold": True}))
    for row, values in enumerate([("Sara", "0550123456"), ("Omar", "0661234567"), ("Lina", "0771234567")], start=2):
        sheet.write_row(f"A{row}", values)
    book.close()
    return path


def naming_answer(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_fr": "Clients",
        "entity_ar": "الزبائن",
        "fields": [{"column": "A", "fr": "Nom", "ar": "الاسم"}, {"column": "B", "fr": "Téléphone", "ar": "الهاتف"}],
    }


def by_kind(analysis: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [item for item in analysis["findings"] if item["kind"] == kind]


# --- Names --------------------------------------------------------------------------------------


def test_model_names_entities_and_fields_in_both_languages(model: FakeModel, tmp_path: Path) -> None:
    model.script = naming_answer
    analysis = analyze(read_file(workbook(tmp_path / "w.xlsx")), model.settings)
    assert by_kind(analysis, "table")[0]["proposal"]["entityLabel"] == {"fr": "Clients", "ar": "الزبائن"}
    labels = {item["proposal"]["column"]: item["proposal"]["label"] for item in by_kind(analysis, "fieldType")}
    assert labels["B"] == {"fr": "Téléphone", "ar": "الهاتف"}
    assert analysis["engine"]["model"] == "fake-model"
    assert analysis["engine"]["quant"] == "Q4_K_M"
    assert [error.message for error in Draft202012Validator(SCHEMA).iter_errors(analysis)] == []


@pytest.mark.parametrize(
    "answer",
    [
        "this is not JSON",
        {"entity_fr": "Clients"},  # Missing fields.
        {"entity_fr": "Clients", "entity_ar": "Clients", "fields": []},  # "Arabic" with no Arabic.
        {"entity_fr": "الزبائن", "entity_ar": "الزبائن", "fields": []},  # "French" in Arabic.
        {"entity_fr": "", "entity_ar": "الزبائن", "fields": []},
        {"entity_fr": "Clients", "entity_ar": "الزبائن", "fields": [{"column": "Z", "fr": "a", "ar": "ب"}]},  # No such column.
    ],
    ids=["not-json", "missing", "no-arabic", "no-french", "empty", "wrong-column"],
)
def test_a_bad_answer_is_retried_once_and_then_the_rules_stand(model: FakeModel, tmp_path: Path, answer: Any) -> None:
    model.script = lambda _: answer
    analysis = analyze(read_file(workbook(tmp_path / "w.xlsx")), model.settings)
    assert model.tasks().count("name_table") == 2
    assert "entityLabel" not in by_kind(analysis, "table")[0]["proposal"]
    assert all("label" not in item["proposal"] for item in by_kind(analysis, "fieldType"))
    assert [error.message for error in Draft202012Validator(SCHEMA).iter_errors(analysis)] == []


def test_a_retry_can_succeed(model: FakeModel, tmp_path: Path) -> None:
    answers = iter(["garbage"])

    def script(body: dict[str, Any]) -> Any:
        return next(answers, naming_answer(body))

    model.script = script
    analysis = analyze(read_file(workbook(tmp_path / "w.xlsx")), model.settings)
    assert "entityLabel" in by_kind(analysis, "table")[0]["proposal"]


def test_each_request_turns_thinking_off_and_describes_the_shape(model: FakeModel, tmp_path: Path) -> None:
    model.script = naming_answer
    analyze(read_file(workbook(tmp_path / "w.xlsx")), model.settings)
    request = model.requests[0]
    assert request["think"] is False
    assert request["chat_template_kwargs"] == {"enable_thinking": False}
    assert request["temperature"] == 0.0
    assert '"entity_fr"' in request["messages"][1]["content"]  # Servers ignore some schema features.
    schema = json.dumps(request["response_format"]["json_schema"]["schema"])
    assert "$ref" not in schema and "prefixItems" not in schema


@pytest.mark.parametrize("name", ["Ligne", "Lignes client", "Row", "Données", "سطر", "بيانات"])
def test_a_name_that_says_nothing_is_refused(model: FakeModel, tmp_path: Path, name: str) -> None:
    arabic = bool(re.search(r"[\u0600-\u06ff]", name))
    model.script = lambda _: {
        "entity_fr": "Clients" if arabic else name,
        "entity_ar": name if arabic else "الزبائن",
        "fields": [],
    }
    analysis = analyze(read_file(workbook(tmp_path / "w.xlsx")), model.settings)
    assert "entityLabel" not in by_kind(analysis, "table")[0]["proposal"]


def _monthly(path: Path) -> Path:
    book = xlsxwriter.Workbook(str(path))
    for tab in ("Janvier 2026", "Février 2026", "Mars 2026"):
        sheet = book.add_worksheet(tab)
        sheet.write("A1", f"Paiements {tab}")
        sheet.write_row("A2", ["Nom", "Montant"], book.add_format({"bold": True}))
        for row in range(3, 8):
            sheet.write_row(f"A{row}", [f"Client {row}", row * 1.5])
    book.close()
    return path


def test_tabs_of_a_series_share_one_name_and_one_question(model: FakeModel, tmp_path: Path) -> None:
    model.script = lambda _: {
        "entity_fr": "Paiements",
        "entity_ar": "المدفوعات",
        "fields": [{"column": "B", "fr": "Montant", "ar": "المبلغ"}],
    }
    analysis = analyze(read_file(_monthly(tmp_path / "m.xlsx")), model.settings)
    assert model.tasks().count("name_table") == 1
    assert {str(item["proposal"]["entityLabel"]) for item in by_kind(analysis, "table")} == {str({"fr": "Paiements", "ar": "المدفوعات"})}
    amounts = [item for item in by_kind(analysis, "fieldType") if item["proposal"]["column"] == "B"]
    assert len(amounts) == 3 and all(item["proposal"]["label"]["ar"] == "المبلغ" for item in amounts)


def test_the_sheet_title_reaches_the_prompt(model: FakeModel, tmp_path: Path) -> None:
    model.script = lambda _: "skip"
    analyze(read_file(_monthly(tmp_path / "m.xlsx")), model.settings)
    naming = next(item for item in model.requests if item["response_format"]["json_schema"]["name"] == "name_table")
    assert "Paiements Janvier 2026" in naming["messages"][1]["content"]


def test_a_title_above_a_blank_row_reaches_the_prompt(model: FakeModel, tmp_path: Path) -> None:
    path = tmp_path / "t.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Janvier")
    sheet.merge_range("A1:B1", "Paiements de janvier")
    sheet.write_row("A3", ["Nom", "Montant"], book.add_format({"bold": True}))
    sheet.write_row("A4", ["Sara", 1.5])
    sheet.write_row("A5", ["Omar", 2.5])
    book.close()
    model.script = lambda _: "skip"
    analyze(read_file(path), model.settings)
    naming = next(item for item in model.requests if item["response_format"]["json_schema"]["name"] == "name_table")
    assert "Paiements de janvier" in naming["messages"][1]["content"]


def test_prompts_hold_samples_not_whole_sheets(model: FakeModel, tmp_path: Path) -> None:
    path = tmp_path / "big.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Grand")
    sheet.write_row("A1", ["Nom", "Montant"], book.add_format({"bold": True}))
    for row in range(2, 502):
        sheet.write_row(f"A{row}", [f"Client numéro {row}", row * 1.5])
    book.close()
    model.script = lambda _: {"entity_fr": "Clients", "entity_ar": "زبائن", "fields": []}
    analyze(read_file(path), model.settings)
    assert len(model.requests[0]["messages"][1]["content"]) < 1000
    assert all("Client numéro 400" not in item["messages"][1]["content"] for item in model.requests)


# --- Rules only ---------------------------------------------------------------------------------


def test_no_settings_means_rules_only(tmp_path: Path) -> None:
    snapshot = read_file(workbook(tmp_path / "w.xlsx"))
    assert analyze(snapshot) == analyze_snapshot(snapshot)


@pytest.mark.parametrize(
    ("env", "configured"),
    [
        ({}, False),
        ({"DAFTAR_LLM_BASE_URL": "", "DAFTAR_LLM_MODEL": "x"}, False),
        ({"DAFTAR_LLM_BASE_URL": "http://h/v1"}, False),
        ({"DAFTAR_LLM_BASE_URL": "http://h/v1/", "DAFTAR_LLM_MODEL": "x"}, True),
    ],
)
def test_settings_follow_c10(env: dict[str, str], configured: bool) -> None:
    settings = settings_from_env(env)
    assert (settings is not None) is configured
    if settings:
        assert settings.base_url == "http://h/v1"


def test_an_unreachable_model_leaves_a_valid_rules_only_analysis(tmp_path: Path) -> None:
    snapshot = read_file(workbook(tmp_path / "w.xlsx"))
    analysis = analyze(snapshot, LlmSettings("http://127.0.0.1:9/v1", "gone"))
    assert analysis["engine"] == {"rulesVersion": analyser.RULES_VERSION}
    assert analysis == analyze_snapshot(snapshot)


def test_cli_no_llm_ignores_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: FakeModel) -> None:
    monkeypatch.setenv("DAFTAR_LLM_BASE_URL", model.settings.base_url)
    monkeypatch.setenv("DAFTAR_LLM_MODEL", "fake-model")
    monkeypatch.setenv("HOME", str(tmp_path))
    output = tmp_path / "a.json"
    assert main(["analyze", str(workbook(tmp_path / "w.xlsx")), "--no-llm", "-o", str(output)]) == 0
    assert model.requests == []
    assert "model" not in json.loads(output.read_text(encoding="utf-8"))["engine"]


def test_cli_uses_the_environment_when_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: FakeModel) -> None:
    monkeypatch.setenv("DAFTAR_LLM_BASE_URL", model.settings.base_url)
    monkeypatch.setenv("DAFTAR_LLM_MODEL", "fake-model")
    monkeypatch.setenv("HOME", str(tmp_path))
    model.script = naming_answer
    output = tmp_path / "a.json"
    assert main(["analyze", str(workbook(tmp_path / "w.xlsx")), "-o", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["engine"]["model"] == "fake-model"


# --- Determinism, cache and votes ---------------------------------------------------------------


def test_cache_means_the_same_analysis_with_no_new_calls(model: FakeModel, tmp_path: Path) -> None:
    settings = LlmSettings(model.settings.base_url, "fake-model", cache_dir=tmp_path / "cache")
    model.script = naming_answer
    snapshot = read_file(workbook(tmp_path / "w.xlsx"))
    first = json.dumps(analyze(snapshot, settings), ensure_ascii=False)
    calls = len(model.requests)
    assert calls > 0
    model.script = lambda _: "the server changed its mind"
    assert json.dumps(analyze(snapshot, settings), ensure_ascii=False) == first
    assert len(model.requests) == calls


def test_refused_answers_are_cached_so_a_rerun_doesnt_ask_again(model: FakeModel, tmp_path: Path) -> None:
    settings = LlmSettings(model.settings.base_url, "fake-model", cache_dir=tmp_path / "cache")
    model.script = lambda _: "garbage"
    snapshot = read_file(workbook(tmp_path / "w.xlsx"))
    first = analyze(snapshot, settings)
    calls = len(model.requests)
    assert calls == 2  # One retry.
    model.script = naming_answer
    assert analyze(snapshot, settings) == first
    assert len(model.requests) == calls


def test_an_unreachable_server_isnt_cached_as_a_refusal(tmp_path: Path) -> None:
    settings = LlmSettings("http://127.0.0.1:9/v1", "gone", cache_dir=tmp_path / "cache")
    analyze(read_file(workbook(tmp_path / "w.xlsx")), settings)
    assert not (tmp_path / "cache").exists()


def test_cache_key_separates_model_and_prompt_version(model: FakeModel, tmp_path: Path) -> None:
    one = LlmClient(LlmSettings(model.settings.base_url, "a"), "1")
    other = LlmClient(LlmSettings(model.settings.base_url, "b"), "1")
    later = LlmClient(LlmSettings(model.settings.base_url, "a"), "2")
    assert one._key(["x"]) != other._key(["x"])
    assert one._key(["x"]) != later._key(["x"])
    assert one._key(["x"]) == LlmClient(LlmSettings(model.settings.base_url, "a"), "1")._key(["x"])


def _client(model: FakeModel) -> LlmClient:
    return LlmClient(model.settings, "1")


def test_votes_use_fixed_seeds_and_stop_at_three_if_unanimous(model: FakeModel) -> None:
    model.script = lambda _: {"answer": "b"}
    vote = _client(model).vote("t", "s", "p", ["a", "b"])
    assert vote is not None
    assert (vote.answer, vote.agreement, vote.votes) == ("b", 1.0, 3)
    assert [request["seed"] for request in model.requests] == [11, 23, 37]
    assert all(request["temperature"] == 0.7 for request in model.requests)


def test_a_split_goes_to_five_votes(model: FakeModel) -> None:
    answers = iter(["a", "b", "a", "a", "b"])
    model.script = lambda _: {"answer": next(answers)}
    vote = _client(model).vote("t", "s", "p", ["a", "b"])
    assert vote is not None
    assert (vote.answer, vote.agreement, vote.votes) == ("a", 0.6, 5)


def test_an_answer_outside_the_options_doesnt_count(model: FakeModel) -> None:
    model.script = lambda _: {"answer": "c"}
    assert _client(model).vote("t", "s", "p", ["a", "b"]) is None


# --- Ties ---------------------------------------------------------------------------------------


def tied_sheet(path: Path) -> Path:
    """Money beside a status column, with no date, scores close: register or tracker."""
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Suivi")
    bold = book.add_format({"bold": True})
    sheet.write_row("A1", ["Élément", "Montant", "Statut"], bold)
    for row in range(2, 14):
        sheet.write_row(f"A{row}", [f"Élément {row}", row * 1.5, ["Ouvert", "Fermé"][row % 2]])
    book.close()
    return path


def _kind(analysis: dict[str, Any]) -> dict[str, Any]:
    return by_kind(analysis, "sheetKind")[0]


def _vote_or_name(answer: str) -> Script:
    def script(body: dict[str, Any]) -> Any:
        if body["response_format"]["json_schema"]["name"] == "sheet_kind":
            return {"answer": answer}
        return "skip"

    return script


def test_a_close_call_on_sheet_kind_goes_to_a_vote(model: FakeModel, tmp_path: Path) -> None:
    snapshot = read_file(tied_sheet(tmp_path / "t.xlsx"))
    rules = _kind(analyze_snapshot(snapshot))
    assert rules["proposal"]["outcome"] == "register"
    assert any(option["outcome"] == "tracker" for option in rules["alternatives"])
    model.script = _vote_or_name("tracker")
    analysis = analyze(snapshot, model.settings)
    assert _kind(analysis)["proposal"]["outcome"] == "tracker"
    assert analysis["sheets"][0]["outcome"] == "tracker"
    assert _kind(analysis)["confidence"] == {"level": "high", "score": 0.9, "source": "votes"}


def test_an_unsettled_tie_keeps_the_rules_and_needs_review(model: FakeModel, tmp_path: Path) -> None:
    snapshot = read_file(tied_sheet(tmp_path / "t.xlsx"))
    model.script = lambda _: "garbage"
    finding = _kind(analyze(snapshot, model.settings))
    assert finding["proposal"]["outcome"] == "register"
    assert finding["proposal"]["needsReview"] is True
    assert finding["confidence"]["source"] == "rules"


def test_a_clear_sheet_kind_never_reaches_the_model(model: FakeModel, tmp_path: Path) -> None:
    model.script = naming_answer
    analyze(read_file(workbook(tmp_path / "w.xlsx")), model.settings)
    assert "sheet_kind" not in model.tasks()


def test_low_confidence_header_is_checked_and_a_no_needs_review(model: FakeModel, tmp_path: Path) -> None:
    path = tmp_path / "h.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("H")
    for row in range(1, 9):
        sheet.write_row(f"A{row}", [f"Nom {row}", f"Rue {row}"])
    book.close()
    snapshot = read_file(path)

    def answer(word: str) -> Script:
        return lambda body: {"answer": word} if body["response_format"]["json_schema"]["name"] == "header_check" else "skip"

    model.script = answer("no")
    assert by_kind(analyze(snapshot, model.settings), "header")[0]["proposal"]["needsReview"] is True
    model.script = answer("yes")
    finding = by_kind(analyze(snapshot, model.settings), "header")[0]
    assert "needsReview" not in finding["proposal"]
    assert finding["confidence"]["source"] == "votes"


def test_borderline_spellings_can_be_dropped_but_nothing_merges(model: FakeModel, tmp_path: Path) -> None:
    path = tmp_path / "n.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("N")
    sheet.write_row("A1", ["N°", "Parent"], book.add_format({"bold": True}))
    names = ["A. Benali", "Ahmed Benali", "BENALI Ahmed", "Mme Saidi", "SAIDI", "Hamdi"]
    for row, name in enumerate(names, start=2):
        sheet.write_row(f"A{row}", [row, name])
    book.close()
    snapshot = read_file(path)
    before = by_kind(analyze_snapshot(snapshot), "entityMerge")[0]["proposal"]["clusters"]
    assert any(cluster["match"] == "possible" for cluster in before)

    def script(body: dict[str, Any]) -> Any:
        return {"answer": "different"} if body["response_format"]["json_schema"]["name"] == "same_name" else "skip"

    model.script = script
    finding = by_kind(analyze(snapshot, model.settings), "entityMerge")[0]
    assert [cluster["match"] for cluster in finding["proposal"]["clusters"]] == [
        cluster["match"] for cluster in before if cluster["match"] != "possible"
    ]
    assert finding["decision"] == {"status": "pending"}


# --- Wording ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("original", "reworded", "kept"),
    [
        ("« Parent » : 12 valeurs dans A1:B3.", "Dans A1:B3, « Parent » a 12 valeurs.", True),
        ("« Parent » : 12 valeurs.", "« Parent » : 13 valeurs.", False),  # A changed number.
        ("« Parent » : 12 valeurs.", "« Parent » : 12 valeurs, sur 40 lignes.", False),  # A new number.
        ("« Parent » : 12 valeurs.", "12 valeurs.", False),  # A lost name.
        ("Cellules A1:B3.", "Cellules A1:B4.", False),  # A changed cell.
        ("Cellules A1:B3.", "Quelques cellules.", False),  # A lost cell.
        ("«الزبائن»: 12 قيمة.", "12 قيمة في «الزبائن».", True),
    ],
)
def test_rewording_keeps_every_fact(original: str, reworded: str, kept: bool) -> None:
    assert keeps_facts(original, reworded) is kept


def reworded_analysis(model: FakeModel, tmp_path: Path, rewrite: Callable[[str], str]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = tmp_path / "e.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("E")
    sheet.write_row("A1", ["N°", "Parent"], book.add_format({"bold": True}))
    for row, name in enumerate(["M. Benali", "BENALI", "Saidi", "Hamdi", "Kaci"], start=2):
        sheet.write_row(f"A{row}", [row, name])
    book.close()
    snapshot = read_file(path)

    def script(body: dict[str, Any]) -> Any:
        if body["response_format"]["json_schema"]["name"] == "reword":
            return {"text": rewrite(body["messages"][1]["content"])}
        return "skip"

    model.script = script
    settings = LlmSettings(model.settings.base_url, "fake-model", reword=True)
    return by_kind(analyze_snapshot(snapshot), "entityMerge")[0], by_kind(analyze(snapshot, settings), "entityMerge")[0]


def test_a_faithful_rewording_replaces_the_template(model: FakeModel, tmp_path: Path) -> None:
    _, after = reworded_analysis(model, tmp_path, lambda text: "Bonjour : " + text)
    assert after["explanation"]["fr"].startswith("Bonjour : ")


def test_rewording_is_off_unless_asked_for(model: FakeModel, tmp_path: Path) -> None:
    model.script = naming_answer
    analyze(read_file(workbook(tmp_path / "w.xlsx")), model.settings)
    assert "reword" not in model.tasks()
    assert settings_from_env({"DAFTAR_LLM_BASE_URL": "http://h", "DAFTAR_LLM_MODEL": "x"}).reword is False  # type: ignore[union-attr]
    assert settings_from_env({"DAFTAR_LLM_BASE_URL": "http://h", "DAFTAR_LLM_MODEL": "x", "DAFTAR_LLM_REWORD": "1"}).reword is True  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("original", "reworded", "kept"),
    [
        ("«Parent» يتكرر: 12 قيمة.", "«Parent» appears: 12 values.", False),  # Seen in a real run.
        ("«Parent» يتكرر: 12 قيمة.", "«Parent» موجود: 12 قيمة.", True),
        ("« Parent » revient : 12 valeurs.", "« Parent » est là : 12 valeurs.", True),
        ("« الزبائن » revient : 12 valeurs.", "« الزبائن » est là : 12 valeurs.", True),  # An Arabic name in French.
        ("« Parent » revient : 12 valeurs.", "«Parent» موجود: 12 قيمة.", False),
    ],
)
def test_rewording_keeps_the_language(original: str, reworded: str, kept: bool) -> None:
    assert keeps_language(original, reworded) is kept


def test_a_rewording_that_adds_a_fact_is_refused(model: FakeModel, tmp_path: Path) -> None:
    before, after = reworded_analysis(model, tmp_path, lambda text: text + " Il y a 999 doublons.")
    assert after["explanation"] == before["explanation"]


# --- Glossary -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("khlas", "khlas (paiement)"),
        ("Drahem khlas", "Drahem khlas (argent, paiement)"),
        ("خلاص", "خلاص (paiement)"),
        ("Montant", "Montant"),
        ("tel zboun", "tel zboun (téléphone, client)"),
    ],
)
def test_darja_is_glossed_before_the_model_sees_it(label: str, expected: str) -> None:
    assert gloss(label) == expected


def test_a_darja_title_reaches_the_prompt_with_its_meaning(model: FakeModel, tmp_path: Path) -> None:
    path = tmp_path / "d.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Kridi")
    sheet.write_row("A1", ["Zboun", "Khlas"], book.add_format({"bold": True}))
    sheet.write_row("A2", ["Sara", 1.5])
    sheet.write_row("A3", ["Omar", 2.5])
    book.close()
    model.script = lambda _: {"entity_fr": "Crédits", "entity_ar": "ديون", "fields": []}
    analyze(read_file(path), model.settings)
    prompt = model.requests[0]["messages"][1]["content"]
    assert "Zboun (client)" in prompt and "Khlas (paiement)" in prompt and "Kridi (crédit)" in prompt


def test_apply_model_keeps_finding_ids(model: FakeModel, tmp_path: Path) -> None:
    snapshot = read_file(workbook(tmp_path / "w.xlsx"))
    before = [item["id"] for item in analyze_snapshot(snapshot)["findings"]]
    model.script = naming_answer
    after = apply_model(analyze_snapshot(snapshot), snapshot, model.settings)
    assert [item["id"] for item in after["findings"]] == before
