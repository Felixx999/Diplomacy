"""Пул портретов по образцу Hearts of Iron IV.

Там это устроено так: обобщённые лица лежат пулами и назначаются по
региону, отдельно мужские и женские. В базовой игре таких портретов 64,
крупные наборы сообщества доходят до нескольких сотен, разложенных по
регионам и полу.

Здесь то же самое. Файлы кладутся в `web/faces/<регион>/<пол>/`, и
система подхватывает их сама: манифест не нужен, достаточно положить
изображения. Пока пул пуст, рисуется послойная фигура — она же остаётся
запасным вариантом навсегда.

Назначение устойчиво: один человек всегда получает одно и то же лицо,
потому что индекс берётся из его имени, а не из случайного числа.

Важно: лица должны быть обезличенными и вымышленными. Пул обобщённых
портретов под вымышленными именами — обычная практика жанра. Портрет,
подписанный как конкретное реальное должностное лицо, — нет.
"""

from __future__ import annotations

from pathlib import Path

FACE_DIR = Path(__file__).resolve().parent.parent / "web" / "faces"
CLIP_DIR = Path(__file__).resolve().parent.parent / "web" / "clips"
EXT = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".svg")

# Регион берётся тот же, что у палитр в portrait.py, чтобы лицо и
# оформление не расходились.
from .portrait import REGION, _seed  # noqa: E402

# Сколько лиц нужно на регион, чтобы повторы не бросались в глаза.
# Считано от худшего случая: 24 человека в резерве, из них примерно
# 38 процентов женщин.
TARGET = {"m": 16, "f": 10}

_INDEX: dict[tuple[str, str], list[str]] | None = None


def _scan() -> dict[tuple[str, str], list[str]]:
    out: dict[tuple[str, str], list[str]] = {}
    if not FACE_DIR.exists():
        return out
    for region_dir in sorted(FACE_DIR.iterdir()):
        if not region_dir.is_dir():
            continue
        for sex in ("m", "f"):
            d = region_dir / sex
            if not d.is_dir():
                continue
            files = sorted(f.name for f in d.iterdir()
                           if f.suffix.lower() in EXT)
            if files:
                out[(region_dir.name, sex)] = files
    return out


def reload() -> None:
    global _INDEX
    _INDEX = _scan()


def index() -> dict[tuple[str, str], list[str]]:
    if _INDEX is None:
        reload()
    return _INDEX or {}


def face_url(name: str, country: str, female: bool) -> str | None:
    """Устойчивый выбор лица из пула. None — пула нет, рисуем фигуру."""
    region = REGION.get(country, "west")
    sex = "f" if female else "m"
    pool = index().get((region, sex)) or index().get(("west", sex))
    if not pool:
        return None
    return f"/faces/{region}/{sex}/{pool[_seed(name) % len(pool)]}"


def coverage() -> list[dict]:
    """Чего не хватает в пуле. Печатается инструментом ревизии."""
    have = index()
    rows = []
    for region in sorted(set(REGION.values())):
        for sex, need in TARGET.items():
            n = len(have.get((region, sex), []))
            rows.append({"region": region, "sex": sex, "have": n,
                         "need": need, "short": max(0, need - n)})
    return rows


# --- короткие ролики -----------------------------------------------------

# Ролик подставляется по виду сцены. Их нужно немного: одни и те же
# кадры переиспользуются в сотнях событий, как в спортивных симуляторах.
CLIPS = {
    "speech": "выступление главы государства",
    "talks": "приезд делегации на переговоры",
    "oath": "присяга при вступлении в должность",
    "signing": "подписание соглашения",
    "crisis": "экстренное совещание",
}

CLIP_FOR_THEME = {
    "кризис": "crisis", "переговоры": "talks",
    "соглашение": "signing", "правительство": "oath",
    "внутренняя политика": "speech",
}


def clip_url(theme: str) -> str | None:
    """Ролик по названию темы сцены."""
    kind = CLIP_FOR_THEME.get(theme)
    if not kind or not CLIP_DIR.exists():
        return None
    return clip_url_by_kind(kind)


def clip_coverage() -> list[dict]:
    return [{"kind": k, "what": v, "have": clip_url_by_kind(k) is not None}
            for k, v in CLIPS.items()]


def clip_url_by_kind(kind: str) -> str | None:
    """Настоящее видео вытесняет заглушку: сначала ищем mp4, потом svg."""
    if not CLIP_DIR.exists():
        return None
    for ext in (".mp4", ".webm", ".svg"):
        if (CLIP_DIR / f"{kind}{ext}").exists():
            return f"/clips/{kind}{ext}"
    return None
