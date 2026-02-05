# utils.py
import logging
import re

def setup_logger():
    logger = logging.getLogger("bcdbot")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger

logger = setup_logger()

# Простой, но эффективный чистильщик HTML + лишних пробелов
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

def safe_strip(text: str) -> str:
    """
    Очищает текст письма:
    - убирает HTML-теги (грубо, но эффективно),
    - схлопывает все виды пробелов в один,
    - обрезает переносы.
    """
    if not text:
        return ""
    t = str(text)
    # убираем теги
    t = _TAG_RE.sub(" ", t)
    # заменяем CR/LF на пробел
    t = t.replace("\r", " ").replace("\n", " ")
    # схлопываем множественные пробелы
    t = _WHITESPACE_RE.sub(" ", t)
    return t.strip()
