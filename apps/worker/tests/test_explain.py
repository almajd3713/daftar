"""R-10 and R-13: explanations read properly at any count, and in either direction."""

import pytest

from daftar_worker.analyser import explain


FSI, PDI = "\u2068", "\u2069"


@pytest.mark.parametrize(
    ("count", "object_form", "expected"),
    [
        (1, False, "صف واحد"),
        (2, False, "صفان"),
        (2, True, "صفين"),
        (3, False, "3 صفوف"),
        (10, False, "10 صفوف"),
        (11, False, "11 صفا"),
        (99, False, "99 صفا"),
        (100, False, "100 صف"),
        (102, False, "102 صف"),
        (103, False, "103 صفوف"),
        (111, False, "111 صفا"),
        (1000, False, "1000 صف"),
    ],
)
def test_arabic_counts(count: int, object_form: bool, expected: str) -> None:
    assert explain._ar(count, "row", object_form) == expected


def test_a_table_reads_properly_at_small_counts() -> None:
    one = explain.table("S", "A1:A2", 1, 1)
    assert "1 ligne et 1 colonne." in one["fr"]
    assert "صف واحد وعمود واحد." in one["ar"]
    two = explain.table("S", "A1:B3", 2, 2)
    assert "2 lignes et 2 colonnes." in two["fr"]
    assert "صفان وعمودان." in two["ar"]
    many = explain.table("S", "A1:L21", 20, 12)
    assert "20 صفا و12 عمودا." in many["ar"]


def test_arabic_verbs_agree_with_two_sheets() -> None:
    assert "تشتركان في 3 أعمدة" in explain.period_union(["S", "T"], "month", 3, 0, False)["ar"]
    assert "تشترك في 3 أعمدة" in explain.period_union(["S", "T", "U"], "month", 3, 0, False)["ar"]


def test_french_verbs_agree_with_the_count() -> None:
    assert "1 cellule ne suit pas" in explain.inconsistent_formula("Prix", "C", ["C2"], 1)["fr"]
    assert "2 cellules ne suivent pas" in explain.inconsistent_formula("Prix", "C", ["C2", "C3"], 2)["fr"]
    assert "ligne " in explain.header("S", [1], 3)["fr"] and "lignes " in explain.header("S", [1, 2], 3)["fr"]


@pytest.mark.parametrize(
    "explanation",
    [
        explain.sheet_kind("S", "register", None, {"tables": 1, "cells": 1}),
        explain.sheet_kind("S", "notConverted", "empty", {"cells": 0}),
        explain.table("S", "A1:B3", 2, 2),
        explain.group_column("S", ["Un", "Deux"]),
        explain.group_column("S", ["Un"]),
        explain.header("S", [1, 2], 1),
        explain.total_row("S", 9, "formula", 1),
        explain.field_type("Prix", "C", "money", "moneyHeader", 1, 2),
        explain.choice_list("Etat", "C", [{"value": "a"}], "validationList"),
        explain.choice_list("Etat", "C", [{"value": "a"}, {"value": "b"}], "fewValues"),
        explain.computed_field("Total", "C", "=A2*B2", 1, 2, True, []),
        explain.computed_field("Total", "C", "=A2*B2", 2, 2, False, ["LET"]),
        explain.inconsistent_formula("Prix", "C", ["C2"], 1),
        explain.relation_from_lookup("S", "A", "T", "B"),
        explain.relation_from_aggregate("S", "A", "T", "B"),
        explain.relation_from_validation("S", "A", "T", "B"),
        explain.relation_from_inclusion("S", "A", "T", "B", 0.9),
        explain.calculator("S", ["a", "b"], ["c"]),
        explain.entity_merge("Client", ["S", "T"], 2, []),
        explain.entity_merge("Client", ["S", "T"], 2, [{"variants": [{"value": "a"}, {"value": "b"}]}]),
        explain.period_union(["S", "T"], "month", 3),
        explain.period_union(["S", "T"], "month", 3, 1, False),
        explain.status_colours("Etat", [{"value": None}, {"value": None}], "fill"),
        explain.status_colours("Etat", [{"value": "a"}, {"value": "b"}], "fill"),
        explain.unsupported("chart", "S", "A1", 2),
    ],
)
def test_nothing_is_left_to_guess_and_every_fact_is_isolated(explanation: dict[str, str]) -> None:
    for text in explanation.values():
        assert "(s)" not in text and "(x)" not in text
        assert FSI in text
        assert text.count(FSI) == text.count(PDI)


def test_a_cell_cant_break_out_of_its_isolate() -> None:
    text = explain.table("S\u2069\u202e", "A1:B2", 2, 2)["fr"]
    assert "\u202e" not in text
    assert f"{FSI}S{PDI}" in text


def test_a_rewording_gets_its_isolates_back() -> None:
    template = explain.table("Ventes 12", "A1:B2", 2, 2)["fr"]
    plain = explain.plain(template)
    assert FSI not in plain
    reworded = "Ici, « Ventes 12 » : voyez A1:B2, et non A1:B20."
    assert explain.isolate_again(template, reworded) == f"Ici, « {FSI}Ventes 12{PDI} » : voyez {FSI}A1:B2{PDI}, et non A1:B20."
