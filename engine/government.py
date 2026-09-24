"""Правительство.

Две разные вещи, которые легко перепутать.

Кабинет — пятнадцать министерств. Каждое владеет своим набором рычагов
и своим министром. Министр не решает, что делать: решает игрок. Министр
определяет, насколько точно решение воплотится.

Направления внешней политики — четыре, и это не министерства, а
распределение усилий. Сумма всегда сто: нельзя быть сильным везде.
Направление задаёт, какие внешние действия вообще доступны. Не вложился
в гуманитарное — не сможешь работать через гранты и обмены, сколько бы
влияния ни накопил.

Пока список министерств один для всех стран, американского образца.
Национальные наборы появятся позже — структура к этому готова, менять
придётся только таблицу.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field

from . import personnel, policy
from .state import DATA, World

DIRECTION_POOL = 100.0     # усилия распределяются, а не добавляются
MIN_FOR_ACTION = 15.0      # ниже этого направление не работает вовсе


@dataclass
class Ministry:
    id: str
    name_ru: str
    short: str
    archetype: str
    note: str
    policies: list[str] = field(default_factory=list)
    name_en: str = ""
    short_en: str = ""


@dataclass
class Direction:
    id: str
    name_ru: str
    ministry: str
    unlocks: list[str]
    note: str
    name_en: str = ""


def _read_sets() -> tuple[dict[str, str], dict[str, dict[str, Ministry]]]:
    """Национальные наборы министерств.

    У кого набора нет — американский по умолчанию. Структура была
    рассчитана на это с самого начала: меняется только таблица.
    """
    which, sets = {}, {}
    try:
        with open(DATA / "country_ministries.csv", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                which[r["code"]] = r["set"]
        with open(DATA / "ministry_sets.csv", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                sets.setdefault(r["set"], {})[r["id"]] = Ministry(
                    id=r["id"], name_ru=r["name_ru"], short=r["short"],
                    archetype=r["archetype"], note=r["note"] or "",
                    name_en=r.get("name_en", ""),
                    short_en=r.get("short_en", ""))
    except FileNotFoundError:
        pass
    return which, sets


def _load() -> tuple[dict[str, Ministry], dict[str, Direction]]:
    mins: dict[str, Ministry] = {}
    with open(DATA / "ministries.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            mins[r["id"]] = Ministry(id=r["id"], name_ru=r["name_ru"],
                                     short=r["short"], archetype=r["archetype"],
                                     note=r["note"],
                                     name_en=r.get("name_en", ""),
                                     short_en=r.get("short_en", ""))
    for p in policy.POLICIES.values():
        owner = getattr(p, "ministry", None) or getattr(p, "branch", None)
        if owner in mins:
            mins[owner].policies.append(p.id)

    dirs: dict[str, Direction] = {}
    with open(DATA / "directions.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            dirs[r["id"]] = Direction(r["id"], r["name_ru"], r["ministry"],
                                      r["unlocks"].split(";"), r["note"],
                                      r.get("name_en", ""))
    return mins, dirs


MINISTRIES, DIRECTIONS = _load()
SET_OF, SETS = _read_sets()


def ministries_of(code: str) -> dict[str, Ministry]:
    """Кабинет конкретной страны."""
    key = SET_OF.get(code)
    return SETS.get(key, MINISTRIES) if key else MINISTRIES
UNLOCKED_BY = {act: d.id for d in DIRECTIONS.values() for act in d.unlocks}


# --- кабинет -------------------------------------------------------------

def cabinet(world: World, code: str, lang: str = "ru") -> list[dict]:
    """Состав правительства: кто где сидит и насколько подходит."""
    rows = []
    for m in ministries_of(code).values():
        held = world.ministers.get((code, m.id))
        pick = (lambda ru, en: en if (lang == "en" and en) else ru)
        rows.append({
            "id": m.id, "name": pick(m.name_ru, m.name_en),
            "short": pick(m.short, m.short_en), "note": m.note,
            "minister": held[0].title_in(lang) if held else None,
            "fit": held[1] if held else None,
            "spread": personnel.execution_spread(world, code, m.id),
            "levers": [(pid, policy.POLICIES[pid].name_ru,
                        policy.level(world, code, pid))
                       for pid in m.policies],
        })
    return rows


def vacancies(world: World, code: str) -> list[str]:
    return [m.id for m in ministries_of(code).values()
            if (code, m.id) not in world.ministers]


def shortlist(world: World, code: str, ministry: str, n: int = 3) -> list[dict]:
    """Кого стоит поставить на это министерство."""
    m = ministries_of(code).get(ministry) or MINISTRIES[ministry]
    out = []
    for p in personnel.pool(world, code):
        fit, why = personnel.minister_fit(world, p, ministry)
        if p.archetype.id == m.archetype:
            fit, why = min(0.95, fit + 0.15), "профильный человек на профильном месте"
        out.append({"who": p.title, "person": p, "fit": round(fit, 2), "why": why})
    out.sort(key=lambda x: -x["fit"])
    return out[:n]


# --- направления внешней политики ----------------------------------------

def effort(world: World, code: str) -> dict[str, float]:
    """Текущее распределение усилий. По умолчанию поровну."""
    cur = {d: world.directions.get((code, d)) for d in DIRECTIONS}
    if any(v is None for v in cur.values()):
        share = DIRECTION_POOL / len(DIRECTIONS)
        cur = {d: share for d in DIRECTIONS}
        for d, v in cur.items():
            world.directions[(code, d)] = v
    return cur


def set_effort(world: World, code: str, weights: dict[str, float]) -> dict:
    """Перераспределить усилия. Сумма приводится к ста автоматически."""
    total = sum(max(0.0, v) for v in weights.values()) or 1.0
    out = {}
    for d in DIRECTIONS:
        v = max(0.0, weights.get(d, 0.0)) / total * DIRECTION_POOL
        world.directions[(code, d)] = round(v, 1)
        out[d] = round(v, 1)
    world.countries[code].political_capital -= 8.0
    return out


def can_do(world: World, code: str, action: str) -> tuple[bool, str]:
    """Доступно ли внешнее действие. Доступность отдельна от цены."""
    d_id = UNLOCKED_BY.get(action)
    if d_id is None:
        return True, ""
    d = DIRECTIONS[d_id]
    level = effort(world, code).get(d_id, 0.0)
    if level < MIN_FOR_ACTION:
        return False, (f"{d.name_ru.lower()} ветвь свёрнута — "
                       f"этим никто не занимается")
    held = world.ministers.get((code, d.ministry))
    if held is None:
        return False, f"{MINISTRIES[d.ministry].name_ru} без руководителя"
    return True, ""


def foreign_panel(world: World, code: str) -> list[dict]:
    """Панель внешней политики: направления, их вес и что они открывают."""
    eff = effort(world, code)
    rows = []
    for d in DIRECTIONS.values():
        ok, why = can_do(world, code, d.unlocks[0])
        rows.append({
            "id": d.id, "name": d.name_ru, "note": d.note,
            "effort": eff[d.id],
            "ministry": (ministries_of(code).get(d.ministry)
                         or MINISTRIES[d.ministry]).name_ru,
            "works": ok, "blocked": why,
            "unlocks": d.unlocks,
        })
    return rows
