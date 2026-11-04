"""Convert .xls and .ods to .xlsx with headless LibreOffice, for their structure.

Don't trust the formula results in the output: LibreOffice recalculates these formats on load, so
`stored.py` restores the original's. Never force a recalculation here, and never use this path for
.xlsx. The stored results are the reference for the formula parity metric.
"""

import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import zipfile

from daftar_worker.errors import WorkerError
from daftar_worker.reader.limits import CONVERT_TIMEOUT_SECONDS


# 1 means "never recalculate" on load. It's the default, and it binds .xlsx only. Macros stay off.
PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
 xmlns:xs="http://www.w3.org/2001/XMLSchema"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>1</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>1</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
</oor:items>
"""  # noqa: E501


# Control characters XML 1.0 forbids, raw or as numeric references. Old .xls text can hold them.
RAW_CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
REFERENCE = re.compile(rb"&#(x[0-9a-fA-F]+|[0-9]+);")
# LibreOffice also leaves a bare "&" in some drawing names, as in "Sales & Use".
BARE_AMPERSAND = re.compile(rb"&(?!(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);)")


def _drop_illegal_reference(match: re.Match[bytes]) -> bytes:
    text = match.group(1).decode()
    code = int(text[1:], 16) if text.startswith("x") else int(text)
    legal = code in (0x9, 0xA, 0xD) or 0x20 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD or code >= 0x10000
    return match.group(0) if legal else b""


def remove_illegal_xml(path: Path) -> None:
    """Repair a converted file in place: LibreOffice's XML isn't always well-formed."""
    temporary = path.with_suffix(".clean")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            data = source.read(name)
            if name.endswith((".xml", ".rels")):
                data = REFERENCE.sub(_drop_illegal_reference, RAW_CONTROL.sub(b"", data))
                data = BARE_AMPERSAND.sub(b"&amp;", data)
            target.writestr(name, data)
    temporary.replace(path)


def soffice_path() -> str | None:
    return shutil.which("soffice")


def convert_to_xlsx(source: Path, work_dir: Path) -> Path:
    """Convert `source` into `work_dir`. The caller owns the directory and its cleanup."""
    soffice = soffice_path()
    if soffice is None:
        raise WorkerError("unreadable", "LibreOffice isn't installed here; it's in the worker image")
    profile = work_dir / "profile"
    (profile / "user").mkdir(parents=True)
    (profile / "user" / "registrymodifications.xcu").write_text(PROFILE, encoding="utf-8")
    out_dir = work_dir / "converted"
    out_dir.mkdir()
    process = subprocess.Popen(
        [
            soffice,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--norestore",
            "--nologo",
            "--nolockcheck",
            "--convert-to",
            "xlsx:Calc MS Excel 2007 XML",
            "--outdir",
            str(out_dir),
            str(source),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # soffice is a wrapper: a timeout must kill its children too.
    )
    try:
        process.wait(timeout=CONVERT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise WorkerError("unreadable", "LibreOffice timed out") from error
    converted = out_dir / f"{source.stem}.xlsx"
    if not converted.exists():
        raise WorkerError("unreadable", f"LibreOffice produced no file, exit {process.returncode}")
    remove_illegal_xml(converted)
    return converted
