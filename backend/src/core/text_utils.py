import re
import unicodedata


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s\-']", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
