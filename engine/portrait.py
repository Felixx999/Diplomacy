"""Графика послойной сборкой.

Пятнадцать министерств на тридцать две страны — это сотни лиц, если
рисовать каждое. Здесь фигура собирается из слоёв: силуэт, одежда,
деталь-признак архетипа, региональная гамма. Около тридцати элементов
дают несколько сотен различимых людей.

Узнаваемость идёт через силуэт и деталь, а не через лицо. Это же
снимает вопрос реальных людей: в условной фигуре никто не увидит
конкретного политика.

Страны обозначаются знаками, а не снимками: флаг простым вектором и
полоса ландшафта одной линией.
"""

from __future__ import annotations

from pathlib import Path

# Региональные гаммы: пара цветов на фигуру
TONES_HEX = ("#F2D6C0", "#E3BC9A", "#C99A6E",
             "#A87545", "#7E5230", "#553521")

PALETTES = {
    "west": ("#2E6E8E", "#C9D6DA"),
    "east": ("#8E3F2E", "#E0CFC6"),
    "south": ("#B07D2B", "#E6DAC2"),
    "gulf": ("#3F7A5E", "#CFE0D5"),
    "north": ("#4A5568", "#D2D7DE"),
    "isles": ("#6B4E8E", "#D8D0E4"),
}
REGION = {
    "USA": "west", "GBR": "isles", "FRA": "west", "DEU": "west",
    "POL": "west", "UKR": "north", "RUS": "north", "KAZ": "north",
    "CHN": "east", "JPN": "east", "KOR": "east", "PRK": "east",
    "TWN": "east", "VNM": "east", "IDN": "east", "PHL": "east",
    "IND": "south", "PAK": "south", "BRA": "south", "MAR": "south",
    "EGY": "south", "SAH": "south", "IRN": "gulf", "SAU": "gulf",
    "ISR": "gulf", "TUR": "gulf", "SYR": "gulf", "PSE": "gulf",
    "CYP": "isles", "SRB": "isles", "XKX": "isles", "AUS": "isles",
}

# Деталь-признак: по ней узнают должность, а не по лицу
MARKS = {
    "technocrat": '<rect x="26" y="41" width="12" height="4" rx="1"/>'
                  '<rect x="46" y="41" width="12" height="4" rx="1"/>'
                  '<rect x="38" y="42" width="8" height="2"/>',
    "hawk": '<path d="M22 62h12l3 8H19z"/><path d="M50 62h12l3 8H47z"/>',
    "trader": '<rect x="48" y="70" width="20" height="14" rx="2"/>'
              '<rect x="53" y="67" width="10" height="4" rx="1"/>',
    "diplomat": '<path d="M34 66l8 12 8-12" fill="none" stroke-width="3"/>',
    "spymaster": '<rect x="20" y="38" width="44" height="7" rx="3"/>',
    "ideologue": '<circle cx="42" cy="72" r="6" fill="none" stroke-width="2.5"/>',
    "energy_boss": '<path d="M40 64l-6 12h8l-3 10 10-14h-8z"/>',
    "populist": '<path d="M18 74q24 -12 48 0" fill="none" stroke-width="3"/>',
}

TERRAIN = {
    "mountain": "M0 26 L18 8 L30 20 L46 4 L62 22 L80 10 L100 26 Z",
    "plain": "M0 26 Q25 18 50 22 T100 20 L100 26 Z",
    "coast": "M0 26 Q20 14 40 20 Q60 26 80 16 L100 22 L100 26 Z",
    "desert": "M0 26 Q15 20 28 24 Q45 14 62 24 Q80 18 100 24 L100 26 Z",
    "island": "M12 26 Q22 12 34 26 Z M56 26 Q70 10 86 26 Z",
    "steppe": "M0 24 L100 21 L100 26 L0 26 Z",
    "delta": "M0 26 Q18 22 30 26 Q44 18 58 26 Q74 20 100 26 Z",
    "forest": "M6 26l6-12 6 12z M26 26l7-14 7 14z M50 26l6-12 6 12z"
              " M72 26l7-13 7 13z",
}
LAND = {
    "USA": "plain", "CHN": "mountain", "RUS": "forest", "IND": "delta",
    "DEU": "plain", "FRA": "plain", "GBR": "island", "TUR": "mountain",
    "IRN": "desert", "ISR": "desert", "JPN": "island", "SAU": "desert",
    "TWN": "island", "UKR": "steppe", "PAK": "mountain", "KOR": "mountain",
    "PRK": "mountain", "POL": "plain", "EGY": "delta", "IDN": "island",
    "BRA": "forest", "PHL": "island", "VNM": "coast", "SYR": "desert",
    "PSE": "coast", "SRB": "mountain", "XKX": "mountain", "CYP": "island",
    "MAR": "desert", "SAH": "desert", "AUS": "plain", "KAZ": "steppe",
}


def _seed(text: str) -> int:
    n = 0
    for ch in text:
        n = (n * 131 + ord(ch)) & 0xFFFFFF
    return n


# Причёски и головные уборы. Рисуются поверх головы, поэтому голова
# остаётся без черт лица — фигура узнаётся по силуэту и детали.
HAIRS = {
    "short": "M26 30 Q26 15 42 15 Q58 15 58 30 Q58 22 42 22 Q26 22 26 30 Z",
    "crop": "M27 28 Q30 17 42 17 Q54 17 57 28 Q50 21 42 21 Q34 21 27 28 Z",
    "long": "M25 32 Q25 14 42 14 Q59 14 59 32 L59 50 Q54 40 54 30 "
            "Q42 24 30 30 Q30 40 25 50 Z",
    "bun": "M26 30 Q26 15 42 15 Q58 15 58 30 Q58 22 42 22 Q26 22 26 30 Z"
           "M42 8 m-6 0 a6 6 0 1 0 12 0 a6 6 0 1 0 -12 0",
    "cover": "M24 34 Q24 12 42 12 Q60 12 60 34 Q60 42 56 46 L28 46 Q24 42 24 34 Z",
    "bald": "",
}
HAIR_COLORS = ("#1F1B17", "#2E2620", "#4A3728", "#6B5A44", "#8C8378", "#B9B3AA")


def portrait(name: str, archetype: str, country: str, size: int = 84,
             look=None, state: float | None = None) -> str:
    """Фигура, собранная из слоёв.

    Слои: фон региона, плечи, голова с тоном кожи, причёска или убор,
    воротник, деталь-признак архетипа. Одно имя всегда даёт одну и ту же
    фигуру.

    Лица нет намеренно. Внешность передаётся тоном кожи, причёской и
    силуэтом: так в министре нельзя узнать конкретного политика, и не
    возникает соблазна изображать этничность чертами лица, что в
    условной графике неизбежно скатывается в карикатуру.
    """
    ink, tint = PALETTES.get(REGION.get(country, "west"), PALETTES["west"])
    h = _seed(f"{name}|{archetype}")
    female = bool(getattr(look, "female", h % 3 == 0))
    tone_i = getattr(look, "tone", h % 6)
    hair_key = getattr(look, "hair", "short")
    skin = TONES_HEX[max(0, min(len(TONES_HEX) - 1, tone_i))]
    hair_col = HAIR_COLORS[(h >> 5) % len(HAIR_COLORS)]
    collar = (h >> 3) % 3
    mark = MARKS.get(archetype, "")

    shoulders = ("M10 84 Q42 58 74 84 Z" if not female
                 else "M14 84 Q42 60 70 84 Z")
    collars = ("<path d='M34 62 L42 76 L50 62' fill='none' stroke-width='3'/>",
               "<path d='M32 64 h20 v6 h-20 z'/>",
               "<path d='M36 62 L42 70 L48 62' fill='none' stroke-width='2'/>")
    hair = HAIRS.get(hair_key, HAIRS["short"])

    hair_layer = f'<path d="{hair}" fill="{hair_col}"/>' if hair else ""

    # Портрет меняется вместе с человеком — приём из Crusader Kings III,
    # где изображение отражает возраст, образ жизни и положение дел.
    # У нас проще: положение министра или страны. В опале фон гаснет и
    # появляется тень, на подъёме фон светлеет.
    overlay = ""
    if state is not None:
        st = max(0.0, min(1.0, state))
        if st < 0.4:
            overlay = (f'<rect width="84" height="84" rx="4" '
                       f'fill="#1F2A2E" opacity="{0.34 - st * 0.5:.2f}"/>')
        elif st > 0.75:
            overlay = ('<rect width="84" height="84" rx="4" '
                       'fill="#FFFFFF" opacity="0.10"/>')
    return (
        f'<svg viewBox="0 0 84 84" width="{size}" height="{size}" '
        f'role="img" aria-label="условный портрет">'
        f'<rect width="84" height="84" rx="4" fill="{tint}"/>'
        f'<g fill="{ink}" stroke="{ink}" stroke-linejoin="round">'
        f'<path d="{shoulders}"/></g>'
        f'<ellipse cx="42" cy="36" rx="15" ry="18" fill="{skin}"/>'
        f'{hair_layer}'
        f'<g fill="{ink}" stroke="{ink}" stroke-linejoin="round">'
        f'{collars[collar]}{mark}</g>{overlay}</svg>'
    )


FLAG_DIR = Path(__file__).resolve().parent.parent / "web" / "flags"


def has_flag(code: str) -> bool:
    return (FLAG_DIR / f"{code}.svg").exists()


def flag_url(code: str) -> str | None:
    """Путь к настоящему флагу, если он есть в наборе.

    Флаги — общественное достояние и в этом жанре стандартны. Набор
    взят из flag-icons под лицензией MIT, лицензия лежит рядом с
    файлами.

    Для спорных образований — Тайваня, Косова, Палестины, Западной
    Сахары — само наличие флага является высказыванием. У нас признание
    отдельная переменная (Р-07), поэтому флаг показывается всем, а долю
    признающих интерфейс называет рядом.
    """
    return f"/flags/{code}.svg" if has_flag(code) else None


def flag(code: str, w: int = 30, h: int = 20) -> str:
    """Запасной знак, если настоящего флага в наборе нет.

    Три полосы из региональной гаммы: не государственный символ, а
    метка, чтобы строка не осталась пустой.
    """
    ink, tint = PALETTES.get(REGION.get(code, "west"), PALETTES["west"])
    h1 = _seed(code)
    vertical = h1 % 2 == 0
    third = (h / 3) if not vertical else (w / 3)
    bars = []
    for i, col in enumerate((ink, tint, ink)):
        if vertical:
            bars.append(f'<rect x="{i * third}" y="0" width="{third}" '
                        f'height="{h}" fill="{col}"/>')
        else:
            bars.append(f'<rect x="0" y="{i * third}" width="{w}" '
                        f'height="{third}" fill="{col}"/>')
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="условный флаг">{"".join(bars)}'
            f'<rect width="{w}" height="{h}" fill="none" '
            f'stroke="rgba(31,42,46,.35)"/></svg>')


def terrain(code: str, w: int = 200, h: int = 26) -> str:
    """Полоса ландшафта одной линией: восемь типов на тридцать две страны."""
    ink, _ = PALETTES.get(REGION.get(code, "west"), PALETTES["west"])
    path = TERRAIN.get(LAND.get(code, "plain"), TERRAIN["plain"])
    return (f'<svg viewBox="0 0 100 26" width="{w}" height="{h}" '
            f'preserveAspectRatio="none" role="img" '
            f'aria-label="условный ландшафт"><path d="{path}" '
            f'fill="{ink}" opacity="0.5"/></svg>')


# --- иконки и эмблемы ----------------------------------------------------

ICON_DIR = Path(__file__).resolve().parent.parent / "web" / "icons"
_ICONS: dict[tuple[str, str], str] = {}


def _load_icons() -> None:
    import csv
    from .state import DATA
    if _ICONS:
        return
    with open(DATA / "icons.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            _ICONS[(r["kind"], r["id"])] = r["icon"]


def icon(kind: str, key: str) -> str | None:
    """Путь к иконке для сущности игры.

    Набор из Tabler Icons под лицензией MIT: пятнадцать министерств,
    четыре направления, двенадцать типов вопросов, десять групп и восемь
    шкал получают свой знак. Все в одном весе линии.
    """
    _load_icons()
    name = _ICONS.get((kind, key))
    if not name:
        return None
    return f"/icons/{name}.svg" if (ICON_DIR / f"{name}.svg").exists() else None


# Оригинальные эмблемы блоков. Гербы государств и знаки НАТО, ООН, ЕС
# намеренно не используются: государственные гербы во многих странах
# ограничены отдельными законами об официальных символах, а эмблемы
# международных организаций — охраняемые знаки. Здесь геометрические
# фигуры, узнаваемые по форме и не копирующие чужое.
BLOC_SHAPES = {
    "defense": "M20 4 L34 12 V24 Q34 34 20 38 Q6 34 6 24 V12 Z",
    "entente": "M20 6 L33 20 L20 34 L7 20 Z",
    "nonaggression": "M8 14 H32 V26 H8 Z",
    "none": "M20 20 m-11 0 a11 11 0 1 0 22 0 a11 11 0 1 0 -22 0",
}


def bloc_emblem(patron: str, kind: str = "defense", size: int = 40) -> str:
    """Знак блока: форма по типу обязательств, гамма по региону патрона."""
    ink, tint = PALETTES.get(REGION.get(patron, "west"), PALETTES["west"])
    path = BLOC_SHAPES.get(kind, BLOC_SHAPES["none"])
    h = _seed(patron)
    rays = "".join(
        f'<circle cx="{20 + 9 * __import__("math").cos(i * 1.2566):.1f}" '
        f'cy="{20 + 9 * __import__("math").sin(i * 1.2566):.1f}" r="1.6"/>'
        for i in range(3 + h % 4))
    return (f'<svg viewBox="0 0 40 40" width="{size}" height="{size}" '
            f'role="img" aria-label="знак блока">'
            f'<path d="{path}" fill="{tint}" stroke="{ink}" stroke-width="2" '
            f'stroke-linejoin="round"/><g fill="{ink}">{rays}</g></svg>')
