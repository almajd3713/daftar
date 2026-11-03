"""Facts about an original .xls or .ods that a conversion would lose."""

from dataclasses import dataclass
from pathlib import Path
import struct
import zipfile

from defusedxml import ElementTree
import olefile

from daftar_worker.reader.raw import local


BIFF_BOF = 0x0809
BIFF_CALCMODE = 0x000D
BIFF_FILEPASS = 0x002F


@dataclass
class LegacyFacts:
    application: str | None
    automatic_calc: bool
    has_macros: bool


@dataclass
class BiffFacts:
    encrypted: bool = False
    automatic_calc: bool = True
    # The BOF record's verLastXLSaved: 0 means Excel 97 or a library, 1 Excel 2000, 6 Excel 2010...
    last_saved_by_excel: int = 0


def scan_biff(stream: bytes) -> BiffFacts:
    """Walk the BIFF records of a workbook stream."""
    facts = BiffFacts()
    position = 0
    first_bof = True
    while position + 4 <= len(stream):
        record, length = struct.unpack_from("<HH", stream, position)
        position += 4
        if record == BIFF_BOF and first_bof:
            first_bof = False
            if length >= 14:
                facts.last_saved_by_excel = stream[position + 13] & 0x0F
        elif record == BIFF_FILEPASS:
            facts.encrypted = True
        elif record == BIFF_CALCMODE and length >= 2:
            # 0 manual, 1 automatic, -1 automatic except tables. Only plain automatic counts.
            mode = struct.unpack_from("<h", stream, position)[0]
            facts.automatic_calc = facts.automatic_calc and mode == 1
        position += length
    return facts


def is_encrypted_ooxml(path: Path) -> bool:
    """Excel stores a password-protected .xlsx as an OLE file, not a zip."""
    with olefile.OleFileIO(str(path)) as ole:
        return bool(ole.exists("EncryptedPackage") or ole.exists("EncryptionInfo"))


def inspect_xls(path: Path) -> tuple[bool, LegacyFacts]:
    """Returns (encrypted, facts). Raises if the file isn't a valid OLE workbook."""
    with olefile.OleFileIO(str(path)) as ole:
        name = "Workbook" if ole.exists("Workbook") else "Book"
        with ole.openstream(name) as stream:
            biff = scan_biff(stream.read())
        application = None
        if ole.exists("\x05SummaryInformation"):
            raw = ole.get_metadata().creating_application
            if isinstance(raw, bytes):
                application = raw.decode("latin-1").strip("\x00 ") or None
        if application is None and biff.last_saved_by_excel > 0:
            # Excel doesn't always write its name here, but it does stamp this field. Libraries
            # such as xlwt and POI leave it at 0, and an Excel 97 file stays "unknown": wrongly
            # calling a file Excel's would corrupt the parity metric, while missing one only
            # leaves it out, and the report lists what was left out.
            application = "Microsoft Excel"
        has_macros = bool(ole.exists("_VBA_PROJECT_CUR") or ole.exists("_VBA_PROJECT"))
    return biff.encrypted, LegacyFacts(application, biff.automatic_calc, has_macros)


def inspect_ods(path: Path) -> tuple[bool, LegacyFacts]:
    """Returns (encrypted, facts). Raises if the file isn't a valid zip."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        encrypted = False
        if "META-INF/manifest.xml" in names:
            for node in ElementTree.fromstring(archive.read("META-INF/manifest.xml")).iter():
                encrypted = encrypted or local(node.tag) == "encryption-data"
        application = None
        if "meta.xml" in names and not encrypted:
            for node in ElementTree.fromstring(archive.read("meta.xml")).iter():
                if local(node.tag) == "generator" and node.text:
                    application = node.text.strip()
        has_macros = any(name.startswith(("Basic/", "Scripts/")) for name in names)
    return encrypted, LegacyFacts(application, True, has_macros)
