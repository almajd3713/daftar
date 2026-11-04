"""The expression cases that keep the Python and TypeScript evaluators in step.

`packages/spec/fixtures/expression-cases.json` comes from test_formulas.py's table. Run this file with
DAFTAR_WRITE_CASES=1 after changing that table.
"""

import json
import os
from pathlib import Path
from typing import Any

from test_formulas import CASES, CLOCK, EVAL_RECORD, RECORD_ROW, TYPES

from daftar_worker.formulas.evaluate import Evaluator, ExcelError
from daftar_worker.formulas.translate import translate


FIXTURE = Path(__file__).resolve().parents[3] / "packages" / "spec" / "fixtures" / "expression-cases.json"


def build() -> dict[str, Any]:
    now = CLOCK.replace(tzinfo=None)
    cases = []
    for formula, _ in CASES:
        expr = translate(formula, "S", RECORD_ROW, TYPES).expr
        assert expr is not None
        result = Evaluator(EVAL_RECORD, now=now).run(expr)
        expected = {"error": result.code} if isinstance(result, ExcelError) else {"value": result}
        cases.append({"formula": formula, "expr": expr, **expected})
    return {"record": EVAL_RECORD, "now": now.isoformat() + "Z", "cases": cases}


def test_fixture_is_current() -> None:
    data = json.dumps(build(), ensure_ascii=False, indent=1) + "\n"
    if os.environ.get("DAFTAR_WRITE_CASES"):
        FIXTURE.write_text(data, encoding="utf-8")
    assert FIXTURE.read_text(encoding="utf-8") == data
