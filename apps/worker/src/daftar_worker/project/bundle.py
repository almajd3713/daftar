"""`daftar bundle`: the folder a client's server runs from (C-8, R-25).

Three targets (OQ-1), differing only in the proxy and its ports. `lan` is a box at the firm, with a
private CA. `vps` is a server with a domain. `local` is plain HTTP on this machine, for a preview.
"""

from importlib.metadata import version
import json
from pathlib import Path
import re
import secrets
import shutil
import stat
from typing import Any

from daftar_spec import format_errors, validate_spec


POSTGRES_IMAGE = (
    "postgres:16-alpine@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab"
)
CADDY_IMAGE = (
    "caddy:2-alpine@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5"
)
TEMPLATES = Path(__file__).parent / "bundle_files"
SCRIPTS = ("start", "backup", "restore", "offsite")
TARGETS = ("local", "lan", "vps")
DOMAIN = re.compile(
    r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)
LAN_NAME = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOCAL_PORTS = '      - "127.0.0.1:${DAFTAR_PORT:-8080}:80"'
PUBLIC_PORTS = '      - "${DAFTAR_HTTP_PORT:-80}:80"\n      - "${DAFTAR_HTTPS_PORT:-443}:443"'
ACCESS = {
    (
        "local",
        "fr",
    ): "Ouvrez ensuite <http://127.0.0.1:8080>. **L'application n'est accessible que depuis cette machine** : c'est un aperçu, sans connexion sécurisée.",
    (
        "local",
        "ar",
    ): 'افتح بعد ذلك <span dir="ltr">`http://127.0.0.1:8080`</span>. **لا يمكن الوصول إلى التطبيق إلا من هذا الجهاز**: هذه معاينة دون اتصال آمن.',
    (
        "lan",
        "fr",
    ): "Ouvrez ensuite <https://{host}> depuis un appareil du réseau de l'entreprise.\n\nChaque téléphone et chaque PC doit d'abord installer une fois le certificat de l'entreprise. `./export-ca` crée le fichier `daftar-root-ca.crt` : envoyez-le sur l'appareil et installez-le comme certificat de confiance. Sans cela, le navigateur affiche un avertissement. Ce certificat donne à cette machine la confiance de l'appareil : installez-le uniquement sur les appareils de l'entreprise, et protégez l'accès à cette machine.\n\nL'application fonctionne sans internet, à l'intérieur de l'entreprise. Donnez à cette machine une adresse fixe sur le réseau.",
    (
        "lan",
        "ar",
    ): 'افتح بعد ذلك <span dir="ltr">`https://{host}`</span> من جهاز موصول بشبكة المؤسسة.\n\nيجب أن يثبّت كل هاتف وكل حاسوب شهادة المؤسسة مرة واحدة أولا. ينشئ الأمر <span dir="ltr">`./export-ca`</span> الملف <span dir="ltr">`daftar-root-ca.crt`</span>: أرسله إلى الجهاز وثبّته كشهادة موثوقة. دون ذلك يعرض المتصفح تحذيرا. تمنح هذه الشهادة هذا الجهاز ثقة الهاتف أو الحاسوب: ثبّتها على أجهزة المؤسسة فقط، واحمِ الوصول إلى هذا الجهاز.\n\nيعمل التطبيق دون إنترنت داخل المؤسسة. أعطِ هذا الجهاز عنوانا ثابتا على الشبكة.',
    (
        "vps",
        "fr",
    ): "Le nom de domaine `{host}` doit d'abord pointer vers ce serveur, et les ports 80 et 443 doivent être ouverts. Ouvrez ensuite <https://{host}> : le certificat est obtenu et renouvelé automatiquement.\n\nL'application a besoin d'internet. L'hébergeur a accès à la machine qui contient vos données : mentionnez-le dans votre registre des traitements.",
    (
        "vps",
        "ar",
    ): 'يجب أولا أن يشير النطاق <span dir="ltr">`{host}`</span> إلى هذا الخادم، وأن يكون المنفذان 80 و443 مفتوحين. افتح بعد ذلك <span dir="ltr">`https://{host}`</span>: يُحصل على الشهادة وتُجدَّد تلقائيا.\n\nيحتاج التطبيق إلى الإنترنت. لمزوّد الاستضافة وصول إلى الجهاز الذي يحتوي بياناتك: اذكر ذلك في سجل المعالجة.',
}
OFFSITE = {
    ("lan", "fr"): "Branchez un second disque et copiez-y les sauvegardes.",
    ("lan", "ar"): "صِل قرصا ثانيا وانسخ إليه النسخ الاحتياطية.",
    (
        "vps",
        "fr",
    ): "Copiez les sauvegardes sur un autre serveur, chez un autre hébergeur si possible.",
    ("vps", "ar"): "انسخ النسخ الاحتياطية إلى خادم آخر، لدى مزوّد آخر إن أمكن.",
    ("local", "fr"): "Copiez-les ailleurs.",
    ("local", "ar"): "انسخها إلى مكان آخر.",
}


class BundleError(ValueError):
    pass


def _read_spec(project: Path) -> dict[str, Any]:
    path = project / "daftar.spec.json"
    if not path.exists():
        raise BundleError(f"{path} doesn't exist: run `daftar project generate` first")
    spec: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_spec(spec)
    if errors:
        raise BundleError(format_errors(errors))
    return spec


def _check_target(target: str, host: str | None, email: str | None) -> None:
    if target not in TARGETS:
        raise BundleError(f"unknown target {target}: use {', '.join(TARGETS)}")
    if target == "local":
        if host or email:
            raise BundleError(
                "the local target listens on this machine: it takes no --host or --email"
            )
        return
    if not host:
        raise BundleError(f"the {target} target needs --host")
    if target == "lan" and not LAN_NAME.fullmatch(host):
        raise BundleError(f"{host} isn't an address or a machine name")
    if target == "vps":
        if not DOMAIN.fullmatch(host):
            raise BundleError(f"{host} isn't a domain: a public certificate needs one")
        if not email or not EMAIL.fullmatch(email):
            raise BundleError(
                "the vps target needs --email: the certificate authority writes there about renewals"
            )


def _environment(
    spec: dict[str, Any], tag: str, target: str, host: str | None, email: str | None
) -> str:
    locale = spec.get("locale", {})
    default = locale.get("default", "fr-DZ") if isinstance(locale, dict) else "fr-DZ"
    # Hex, so the password can sit inside the database URL as it is.
    return "\n".join(
        [
            f"DAFTAR_IMAGE_TAG={tag}",
            f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
            f"DAFTAR_SECRET={secrets.token_hex(32)}",
            f"DAFTAR_DEFAULT_LOCALE={default}",
            "DAFTAR_TZ=Africa/Algiers",
            *(
                ["DAFTAR_PORT=8080"]
                if target == "local"
                else [f"DAFTAR_HOST={host}", "DAFTAR_HTTP_PORT=80", "DAFTAR_HTTPS_PORT=443"]
            ),
            *([f"DAFTAR_ACME_EMAIL={email}"] if email else []),
            "# Where ./offsite copies backups: a folder on a second disk, or user@server:path.",
            "DAFTAR_OFFSITE=",
            "",
        ]
    )


def _fill_readme(text: str, target: str, language: str, host: str | None) -> str:
    access = ACCESS[(target, language)].replace("{host}", host or "")
    return text.replace("{{ACCESS}}", access).replace("{{OFFSITE}}", OFFSITE[(target, language)])


def build_bundle(
    project: Path,
    output: Path,
    tag: str | None = None,
    images: Path | None = None,
    target: str = "local",
    host: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    _check_target(target, host, email)
    spec = _read_spec(project)
    if not spec["entities"]:
        raise BundleError(
            "the spec has no entities: accept the findings to convert, then generate again"
        )
    # Rebuilding over a bundle would replace its secrets and lock the client out of their data.
    if output.exists() and any(output.iterdir()):
        raise BundleError(f"{output} isn't empty; a bundle is never rebuilt in place")
    if images is not None and not images.is_file():
        raise BundleError(f"{images} doesn't exist")
    image_tag = tag or version("daftar-worker")

    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(project / "daftar.spec.json", output / "daftar.spec.json")
    seed = output / "seed"
    seed.mkdir()
    rows = 0
    for item in sorted((project / "seed").glob("*.jsonl")) if (project / "seed").is_dir() else []:
        shutil.copyfile(item, seed / item.name)
        rows += sum(1 for line in item.read_text(encoding="utf-8").splitlines() if line.strip())

    compose = (TEMPLATES / "compose.yaml").read_text(encoding="utf-8")
    compose = (
        compose.replace("{{POSTGRES_IMAGE}}", POSTGRES_IMAGE)
        .replace("{{CADDY_IMAGE}}", CADDY_IMAGE)
        .replace("{{PORTS}}", LOCAL_PORTS if target == "local" else PUBLIC_PORTS)
    )
    (output / "compose.yaml").write_text(compose, encoding="utf-8")
    shutil.copyfile(TEMPLATES / f"Caddyfile.{target}", output / "Caddyfile")
    for language in ("fr", "ar"):
        text = (TEMPLATES / f"README.{language}.md").read_text(encoding="utf-8")
        (output / f"README.{language}.md").write_text(
            _fill_readme(text, target, language, host), encoding="utf-8"
        )
    scripts = (*SCRIPTS, "export-ca") if target == "lan" else SCRIPTS
    for name in scripts:
        shutil.copyfile(TEMPLATES / name, output / name)
        path = output / name
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

    environment = output / ".env"
    environment.touch(mode=0o600)
    environment.write_text(_environment(spec, image_tag, target, host, email), encoding="utf-8")
    if images is not None:
        shutil.copyfile(images, output / "images.tar")
    return {
        "output": str(output),
        "target": target,
        "imageTag": image_tag,
        "seedRows": rows,
        "images": images is not None,
    }
