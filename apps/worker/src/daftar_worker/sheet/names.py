"""Normalise retyped names: accents, Arabic spelling, Arabizi digits, titles and word order."""

import re
import unicodedata

from rapidfuzz import fuzz


ARABIC_LETTERS = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي", "ـ": None}
)
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# Digits inside a Latin word stand for Arabic sounds: "3li" is Ali, "7assan" is Hassan.
ARABIZI = {"2": "a", "3": "a", "5": "kh", "7": "h", "8": "gh", "9": "q"}
TITLES = {
    "m", "mr", "mme", "mlle", "dr", "pr", "me", "monsieur", "madame", "mademoiselle", "docteur", "sarl", "eurl", "spa", "ets",
    "السيد", "السيده", "الانسه", "الدكتور", "شركه", "مؤسسه", "موسسه",
}  # fmt: skip
PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
DIGIT_RUN = re.compile(r"[0-9]+")


def _strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(letter for letter in decomposed if not unicodedata.combining(letter))


def _fix_arabizi(word: str) -> str:
    """Only inside a word with letters: "client2" and "2026" keep their digits."""
    if not re.search(r"[a-z]", word) or not re.search(r"[0-9]", word):
        return word
    if re.fullmatch(r"[a-z]+[0-9]+", word):  # A trailing number is a number: "client2".
        return word
    return "".join(ARABIZI.get(letter, letter) for letter in word)


def tokens(text: str) -> list[str]:
    """The name's words after normalising, without titles."""
    clean = _strip_marks(text).casefold().translate(ARABIC_LETTERS).translate(ARABIC_DIGITS)
    clean = PUNCTUATION.sub(" ", clean)
    words = [_fix_arabizi(word) for word in clean.split()]
    kept = [word for word in words if word not in TITLES]
    return kept or words


def fingerprint(text: str) -> str:
    """Equal for names that differ only in case, accents, spelling variants of Arabic letters,
    titles, punctuation or word order."""
    return " ".join(sorted(tokens(text)))


def digits_in(text: str) -> list[str]:
    return DIGIT_RUN.findall(text)


def same_with_initial(left: list[str], right: list[str]) -> bool:
    """ "A Benali" and "Ahmed Benali": one name's initial stands for the other's first name."""
    if len(left) != len(right) or len(left) < 2:
        return False
    pairs = list(zip(sorted(left, key=len), sorted(right, key=len), strict=True))
    short_side = [(a, b) for a, b in pairs if len(a) == 1 or len(b) == 1]
    if len(short_side) != 1:
        return False
    a, b = short_side[0]
    rest = [(c, d) for c, d in pairs if (c, d) != (a, b)]
    return a[0] == b[0] and all(c == d for c, d in rest)


def spelling_similarity(first: str, second: str) -> float:
    """0 to 100, for two fingerprints. A typo scores high, and so does a name with words left out."""
    score = float(fuzz.token_sort_ratio(first, second))
    if len(first.split()) >= 2 and len(second.split()) >= 2:
        score = max(score, float(fuzz.token_set_ratio(first, second)))
    return score
