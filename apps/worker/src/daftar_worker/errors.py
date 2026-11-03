"""C-4 error codes, with messages written for a shop owner."""

from typing import Literal


ErrorCode = Literal["unreadable", "protected", "too_large", "unsupported_format", "invalid_spec"]

MESSAGES: dict[ErrorCode, dict[str, str]] = {
    "unreadable": {
        "fr": "Impossible de lire ce fichier. Il est peut-être endommagé.",
        "ar": "تعذرت قراءة هذا الملف. ربما يكون تالفا.",
    },
    "protected": {
        "fr": "Ce fichier est protégé par un mot de passe. Retirez le mot de passe puis réessayez.",
        "ar": "هذا الملف محمي بكلمة مرور. أزل كلمة المرور ثم أعد المحاولة.",
    },
    "too_large": {
        "fr": "Ce fichier est trop volumineux. La limite est de 25 Mo et d'un million de cellules.",
        "ar": "هذا الملف كبير جدا. الحد الأقصى هو 25 ميغابايت ومليون خلية.",
    },
    "unsupported_format": {
        "fr": "Ce format n'est pas pris en charge. Utilisez un fichier .xlsx, .xlsm, .xls, .ods ou .csv.",
        "ar": "هذه الصيغة غير مدعومة. استعمل ملفا بصيغة ‎.xlsx أو ‎.xlsm أو ‎.xls أو ‎.ods أو ‎.csv.",
    },
    "invalid_spec": {
        "fr": "La description de l'application n'est pas valide.",
        "ar": "وصف التطبيق غير صالح.",
    },
}


class WorkerError(Exception):
    """A failure the caller can show to the user. `detail` is for logs and never holds cell data."""

    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code: ErrorCode = code
        self.detail = detail

    def to_json(self) -> dict[str, object]:
        return {"code": self.code, "message": MESSAGES[self.code]}
