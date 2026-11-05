"""R-12 and R-15: decisions on findings, and carrying them over when an analysis is rerun.

A finding's id hashes its evidence, so a workbook with one more row gets new ids. A decision then
follows a looser key: same kind, sheet and column or table start. If even that fails, or what the
finding proposes has changed, it comes back as a conflict for a person. Nothing is carried silently.
"""

from datetime import datetime, timezone
import re
from typing import Any


RANGE_START = re.compile(r"^([A-Z]+)([0-9]+)")
# Fields whose change means the person decided on something else.
MEANINGFUL = {
    "sheetKind": ("outcome",),
    "fieldType": ("type",),
    "relation": ("from", "to"),
    "computedField": ("excel",),
    "statusColours": ("choices",),
    "groupColumn": ("groups",),
}


def match_key(finding: dict[str, Any]) -> str:
    """A key that survives more rows. It's looser than the id, so only used when the id has gone."""
    kind, sheet, proposal = finding["kind"], finding.get("sheet"), finding.get("proposal") or {}
    if kind == "relation":
        return f"relation|{proposal['from']['sheet']}|{proposal['from']['column']}"
    if kind == "periodUnion":
        return f"periodUnion|{sheet}"
    if kind == "entityMerge":
        columns = sorted(f"{item['sheet']}!{item['column']}" for item in proposal.get("columns", []))
        return f"entityMerge|{'|'.join(columns)}"
    if "column" in proposal:
        return f"{kind}|{sheet}|{proposal['column']}"
    evidence = finding.get("evidence") or []
    match = RANGE_START.match(evidence[0]) if evidence else None
    start = f"{match.group(1)}{match.group(2)}" if match and kind in ("table", "header", "totalRow", "groupColumn") else ""
    if kind == "totalRow":
        start = match.group(1) if match else ""
    return f"{kind}|{sheet}|{start}"


def decide(finding: dict[str, Any], status: str, by: str, value: Any = None, at: str | None = None) -> None:
    if status not in ("accepted", "edited", "rejected", "pending"):
        raise ValueError(f"unknown decision {status}")
    decision: dict[str, Any] = {"status": status}
    if status != "pending":
        decision.update(by=by, at=at or datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if value is not None:
        decision["value"] = value
    finding["decision"] = decision


def accept_high_confidence(analysis: dict[str, Any], by: str) -> int:
    """R-12's bulk accept: an explicit act by a person, for what starts pre-selected."""
    count = 0
    for finding in analysis["findings"]:
        if finding["decision"]["status"] == "pending" and finding["confidence"]["level"] == "high":
            decide(finding, "accepted", by)
            count += 1
    return count


def _changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    fields = MEANINGFUL.get(old["kind"], ())
    return any((old.get("proposal") or {}).get(name) != (new.get("proposal") or {}).get(name) for name in fields)


def reapply(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Apply `old`'s decisions to `new`, in place. Returns what carried over and what didn't."""
    by_id = {finding["id"]: finding for finding in new["findings"]}
    by_key: dict[str, list[dict[str, Any]]] = {}
    for finding in new["findings"]:
        by_key.setdefault(match_key(finding), []).append(finding)
    applied = 0
    moved = 0
    conflicts: list[dict[str, Any]] = []
    for finding in old["findings"]:
        decision = finding["decision"]
        if decision["status"] == "pending":
            continue
        target = by_id.get(finding["id"])
        how = "id"
        if target is None:
            candidates = by_key.get(match_key(finding), [])
            target = candidates[0] if len(candidates) == 1 else None
            how = "key"
        if target is None:
            conflicts.append({"reason": "gone", "finding": finding})
        elif _changed(finding, target):
            conflicts.append({"reason": "changed", "finding": finding, "now": target["id"]})
        else:
            target["decision"] = dict(decision)
            applied += how == "id"
            moved += how == "key"
    return {"applied": applied, "moved": moved, "conflicts": conflicts}
