"""Read the OOXML package directly, for whatever openpyxl drops or never loads."""

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import posixpath
import re
from typing import Any
import zipfile

from defusedxml import ElementTree

from daftar_worker.errors import WorkerError
from daftar_worker.reader.colours import DEFAULT_THEME, resolve_parts
from daftar_worker.reader.limits import MAX_CELLS, MAX_UNCOMPRESSED_BYTES


REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
X14_NS = "microsoft.com/office/spreadsheetml/2009/9/main"
THEME_ORDER = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5",
               "accent6", "hlink", "folHlink"]  # fmt: skip


# The relationship types Excel writes for sheets that aren't worksheets or chart sheets.
SHEET_KINDS = {"xlmacrosheet": "macrosheet", "xlintlmacrosheet": "macrosheet"}


@dataclass
class RawSheet:
    name: str
    state: str
    kind: str  # worksheet, chartsheet, macrosheet or dialogsheet
    part: str


@dataclass
class RawPackage:
    application: str | None = None
    automatic_calc: bool = True
    sheets: list[RawSheet] = field(default_factory=list)
    palette: list[str] = field(default_factory=lambda: list(DEFAULT_THEME))
    unsupported: list[dict[str, str]] = field(default_factory=list)
    ext_validations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ext_conditional_formats: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    serial_60_cells: dict[str, set[str]] = field(default_factory=dict)
    non_empty_cells: int = 0


def local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _rels(archive: zipfile.ZipFile, part: str) -> dict[str, tuple[str, str]]:
    """Map relationship ids to (type suffix, resolved part name) for a package part."""
    path = PurePosixPath(part)
    rels_name = str(path.parent / "_rels" / f"{path.name}.rels")
    if rels_name not in archive.namelist():
        return {}
    out: dict[str, tuple[str, str]] = {}
    for rel in ElementTree.fromstring(archive.read(rels_name)):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            resolved = target
        elif target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join(str(path.parent), target))
        out[rel.get("Id", "")] = (rel.get("Type", "").rsplit("/", 1)[-1], resolved)
    return out


def _read_metadata(archive: zipfile.ZipFile, package: RawPackage) -> None:
    if "docProps/app.xml" in archive.namelist():
        for node in ElementTree.fromstring(archive.read("docProps/app.xml")):
            if local(node.tag) == "Application" and node.text:
                package.application = node.text.strip()


def _read_workbook(archive: zipfile.ZipFile, package: RawPackage) -> None:
    rels = _rels(archive, "xl/workbook.xml")
    root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    for node in root:
        name = local(node.tag)
        if name == "calcPr":
            # openpyxl and XlsxWriter also write "Microsoft Excel" as the application, but they
            # set fullCalcOnLoad. Excel clears that flag whenever it saves.
            mode = node.get("calcMode", "auto")
            forced = node.get("fullCalcOnLoad") in ("1", "true")
            package.automatic_calc = mode == "auto" and not forced
        elif name == "sheets":
            for sheet in node:
                kind, part = rels.get(sheet.get(f"{REL_NS}id", ""), ("worksheet", ""))
                package.sheets.append(
                    RawSheet(
                        name=sheet.get("name", ""),
                        state=sheet.get("state", "visible"),
                        kind=SHEET_KINDS.get(kind.lower(), kind.lower()),
                        part=part,
                    )
                )


def _read_theme(archive: zipfile.ZipFile, package: RawPackage) -> None:
    candidates = sorted(n for n in archive.namelist() if re.fullmatch(r"xl/theme/theme\d*\.xml", n))
    if not candidates:
        return
    colours: dict[str, str] = {}
    for node in ElementTree.fromstring(archive.read(candidates[0])).iter():
        if local(node.tag) == "clrScheme":
            for slot in node:
                for value in slot:
                    found = value.get("lastClr") or value.get("val")
                    if found:
                        colours[local(slot.tag)] = found.upper()
            break
    if all(slot in colours for slot in THEME_ORDER):
        package.palette = [colours[slot] for slot in THEME_ORDER]


def _colour(node: Any, palette: list[str]) -> str | None:
    def number(name: str) -> int | None:
        value = node.get(name)
        return int(value) if value is not None else None

    return resolve_parts(
        rgb=node.get("rgb"),
        theme=number("theme"),
        indexed=number("indexed"),
        tint=float(node.get("tint", 0)),
        palette=palette,
    )


def _ext_style(dxf: Any, palette: list[str]) -> dict[str, Any]:
    style: dict[str, Any] = {}
    for node in dxf.iter():
        name = local(node.tag)
        if name == "bgColor" and "fill" not in style:
            colour = _colour(node, palette)
            if colour:
                style["fill"] = colour
        elif name == "color" and "color" not in style:
            colour = _colour(node, palette)
            if colour:
                style["color"] = colour
        elif name == "b" and node.get("val", "1") not in ("0", "false"):
            style["bold"] = True
    return style


def _x14_validation(node: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"ranges": [], "type": node.get("type", "none")}
    if node.get("operator"):
        entry["operator"] = node.get("operator")
    entry["allowBlank"] = node.get("allowBlank") in ("1", "true")
    for child in node:
        name = local(child.tag)
        if name in ("formula1", "formula2"):
            text = "".join(part.text or "" for part in child.iter() if local(part.tag) == "f")
            entry[name] = text
        elif name == "sqref":
            entry["ranges"] = (child.text or "").split()
    return entry


def _x14_conditional_format(node: Any, palette: list[str]) -> list[dict[str, Any]]:
    ranges: list[str] = []
    rules: list[Any] = []
    for child in node:
        name = local(child.tag)
        if name == "sqref":
            ranges = (child.text or "").split()
        elif name == "cfRule":
            rules.append(child)
    out = []
    for rule in rules:
        entry: dict[str, Any] = {
            "ranges": ranges,
            "type": rule.get("type", ""),
            "formulas": [c.text or "" for c in rule if local(c.tag) == "f"],
            "priority": int(rule.get("priority", 0)),
        }
        if rule.get("operator"):
            entry["operator"] = rule.get("operator")
        for child in rule:
            if local(child.tag) == "dxf":
                style = _ext_style(child, palette)
                if style:
                    entry["style"] = style
        out.append(entry)
    return out


def _scan_worksheet(archive: zipfile.ZipFile, sheet: RawSheet, package: RawPackage) -> None:
    with archive.open(sheet.part) as stream:
        for _, node in ElementTree.iterparse(stream, events=("end",)):
            name = local(node.tag)
            namespace = node.tag if isinstance(node.tag, str) else ""
            if name == "c":
                _scan_cell(node, sheet, package)
                node.clear()
            elif name == "row":
                node.clear()
            elif name == "dataValidation" and X14_NS in namespace:
                package.ext_validations.setdefault(sheet.name, []).append(_x14_validation(node))
            elif name == "conditionalFormatting" and X14_NS in namespace:
                package.ext_conditional_formats.setdefault(sheet.name, []).extend(
                    _x14_conditional_format(node, package.palette)
                )


def _scan_cell(node: Any, sheet: RawSheet, package: RawPackage) -> None:
    filled = False
    for child in node:
        name = local(child.tag)
        if name in ("f", "is") or (name == "v" and child.text):
            filled = True
        if name == "v" and child.text and node.get("t", "n") == "n":
            try:
                if float(child.text) == 60:
                    package.serial_60_cells.setdefault(sheet.name, set()).add(node.get("r", ""))
            except ValueError:
                pass
    if filled:
        package.non_empty_cells += 1
        if package.non_empty_cells > MAX_CELLS:
            raise WorkerError("too_large", "more non-empty cells than the limit")


def _anchor_ref(anchor: Any) -> str | None:
    from openpyxl.utils import get_column_letter

    for node in anchor:
        if local(node.tag) == "from":
            values = {local(child.tag): child.text for child in node}
            try:
                return f"{get_column_letter(int(values['col'] or 0) + 1)}{int(values['row'] or 0) + 1}"
            except (KeyError, ValueError):
                return None
    return None


def _scan_drawing(archive: zipfile.ZipFile, part: str, sheet: str, package: RawPackage) -> None:
    if part not in archive.namelist():
        return
    for anchor in ElementTree.fromstring(archive.read(part)):
        if not local(anchor.tag).endswith("Anchor"):
            continue
        for node in anchor:
            name = local(node.tag)
            kind = {"pic": "image", "sp": "shape", "cxnSp": "shape", "grpSp": "shape"}.get(name)
            if name == "graphicFrame":
                is_chart = any(local(child.tag) == "chart" for child in node.iter())
                kind = "chart" if is_chart else "other"
            if kind:
                entry = {"kind": kind, "sheet": sheet}
                ref = _anchor_ref(anchor)
                if ref:
                    entry["ref"] = ref
                package.unsupported.append(entry)


def _scan_sheet_parts(archive: zipfile.ZipFile, sheet: RawSheet, package: RawPackage) -> None:
    if sheet.kind == "chartsheet" and not any(
        kind == "drawing" for kind, _ in _rels(archive, sheet.part).values()
    ):
        package.unsupported.append({"kind": "chart", "sheet": sheet.name})
    for kind, target in _rels(archive, sheet.part).values():
        if kind == "drawing":
            _scan_drawing(archive, target, sheet.name, package)
        elif kind == "pivotTable" and target in archive.namelist():
            entry = {"kind": "pivot", "sheet": sheet.name}
            for node in ElementTree.fromstring(archive.read(target)):
                if local(node.tag) == "location" and node.get("ref"):
                    entry["ref"] = node.get("ref", "")
            package.unsupported.append(entry)
        elif kind in ("oleObject", "ctrlProp", "queryTable", "slicer", "control"):
            package.unsupported.append({"kind": "other", "sheet": sheet.name})


def _scan_workbook_parts(archive: zipfile.ZipFile, package: RawPackage) -> None:
    names = archive.namelist()
    lowered = [name.lower() for name in names]
    if any(name.endswith("vbaproject.bin") for name in lowered):
        package.unsupported.append({"kind": "macro"})
    for name in names:
        if re.fullmatch(r"xl/externalLinks/externalLink\d+\.xml", name):
            package.unsupported.append({"kind": "externalLink"})
        elif name == "xl/connections.xml":
            package.unsupported.append({"kind": "other"})
    for sheet in package.sheets:
        if sheet.kind == "macrosheet":
            package.unsupported.append({"kind": "macro", "sheet": sheet.name})
        elif sheet.kind == "dialogsheet":
            package.unsupported.append({"kind": "other", "sheet": sheet.name})


PIVOT_RELATIONSHIP = re.compile(r"<Relationship\b[^>]*/pivotTable\"[^>]*/>")


def copy_without_pivot_links(path: str, target: str) -> bool:
    """Copy the package minus its sheet-to-pivot links. Returns False if it has no pivots.

    openpyxl parses every pivot on load, only to preserve it, and raises on any it dislikes. We
    never read pivots through it, so one odd pivot mustn't make a whole workbook unreadable.
    """
    with zipfile.ZipFile(path) as archive:
        if not any(name.startswith("xl/pivotTables/") for name in archive.namelist()):
            return False
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
            for name in archive.namelist():
                data = archive.read(name)
                if name.startswith("xl/worksheets/_rels/"):
                    data = PIVOT_RELATIONSHIP.sub("", data.decode("utf-8")).encode("utf-8")
                out.writestr(name, data)
    return True


def inspect_package(path: str) -> RawPackage:
    package = RawPackage()
    with zipfile.ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
            raise WorkerError("too_large", "uncompressed package is larger than the limit")
        _read_metadata(archive, package)
        _read_workbook(archive, package)
        _read_theme(archive, package)
        _scan_workbook_parts(archive, package)
        for sheet in package.sheets:
            if sheet.part not in archive.namelist():
                continue
            _scan_sheet_parts(archive, sheet, package)
            if sheet.kind == "worksheet":
                _scan_worksheet(archive, sheet, package)
    package.unsupported.sort(
        key=lambda item: (item["kind"], item.get("sheet", ""), item.get("ref", ""))
    )
    return package
