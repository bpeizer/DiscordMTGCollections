"""Card name normalization so different spellings of the same card match."""
import re
import unicodedata

_space = re.compile(r"\s+")
_punct = re.compile(r"[^\w\s/]")


def normalize(name: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower().replace("’", "'")
    name = _punct.sub("", name)
    return _space.sub(" ", name).strip()


def front_face(name: str) -> str:
    """'Delver of Secrets // Insectile Aberration' -> 'Delver of Secrets'."""
    return name.split("//")[0].strip()
