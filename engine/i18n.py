"""Два языка.

Русский — исходный, английский — перевод. Правило простое: всё, что
видит игрок, проходит через `t()`; всё, что видит разработчик —
комментарии, имена полей, ключи — остаётся как есть и не переводится.

Названия сущностей живут в таблицах данных парами столбцов `name_ru` и
`name_en`. Порождаемые движком фразы живут здесь, в `data/strings.csv`,
с подстановкой параметров: собирать предложение из кусков нельзя, потому
что порядок слов в двух языках разный.

Если перевода нет, показывается русский оригинал. Пустой экран хуже
непереведённой строки.
"""

from __future__ import annotations

import csv
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
LANGS = ("ru", "en")
DEFAULT = "ru"

_TABLE: dict[str, dict[str, str]] | None = None


def _load() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    path = DATA / "strings.csv"
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["key"]] = {"ru": r.get("ru", ""), "en": r.get("en", "")}
    return out


def table() -> dict[str, dict[str, str]]:
    global _TABLE
    if _TABLE is None:
        _TABLE = _load()
    return _TABLE


def reload() -> None:
    global _TABLE
    _TABLE = None


def norm(lang: str | None) -> str:
    lang = (lang or DEFAULT).lower()[:2]
    return lang if lang in LANGS else DEFAULT


def t(key: str, lang: str = DEFAULT, **params) -> str:
    """Фраза по ключу с подстановкой. Нет перевода — берём русский."""
    lang = norm(lang)
    row = table().get(key)
    if row is None:
        return key
    text = row.get(lang) or row.get("ru") or key
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def pick(row: dict, field: str, lang: str = DEFAULT) -> str:
    """Значение из строки таблицы на нужном языке.

    Ищет `field_en`, если не нашло — `field_ru`, если и его нет — `field`.
    Так одна и та же функция работает и с переведёнными таблицами, и с
    ещё не переведёнными.
    """
    lang = norm(lang)
    if lang != "ru":
        v = (row.get(f"{field}_{lang}") or "").strip()
        if v:
            return v
    return (row.get(f"{field}_ru") or row.get(field) or "").strip()


def missing() -> list[str]:
    """Ключи без английского перевода. Печатается ревизией."""
    return sorted(k for k, v in table().items() if not (v.get("en") or "").strip())
