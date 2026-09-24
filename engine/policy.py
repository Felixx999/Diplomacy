"""Ветви управления.

Восемнадцать политик в семи ветвях, отобранных по смыканию с внешним
контуром (Р-16). Каждая делает две вещи: двигает настроения групп,
которые за неё или против, и меняет макропоказатель страны — а тот
входит в совокупную мощь и в каналы распространения.

Асимметричная глубина: игрок крутит каждую политику отдельно, ИИ-страны
двигают их несколькими агрегированными рычагами в сторону, которую
диктует доктрина. Переменные общие, зернистость управления разная.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

from . import groups as _groups
from .state import DATA, World

MOOD_WEIGHT = 0.020    # насколько политика двигает настроение за квартал
AI_STEP = 0.020        # шаг, которым ИИ подтягивает политику к цели
BASE_ATTR: dict[tuple[str, str], float] = {}
SEED_LEVEL: dict[tuple[str, str], float] = {}


@dataclass
class Policy:
    id: str
    name_ru: str
    ministry: str
    default: float
    affects: str      # какой атрибут страны меняет, пусто — только настроения
    effect: float     # относительное изменение атрибута при сдвиге на 1.0
    note: str = ""
    name_en: str = ""


def _load() -> tuple[dict[str, Policy], dict[str, dict[str, float]]]:
    pol: dict[str, Policy] = {}
    with open(DATA / "policies.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pol[r["id"]] = Policy(r["id"], r["name_ru"], r["ministry"],
                                  float(r["default"]), r["affects"],
                                  float(r["effect"]), r.get("note", ""),
                                  r.get("name_en", ""))
    pos: dict[str, dict[str, float]] = {}
    with open(DATA / "policy_positions.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pos.setdefault(r["policy"], {})[r["group"]] = float(r["stance"])
    return pol, pos


POLICIES, POSITIONS = _load()
MINISTRY_IDS = sorted({p.ministry for p in POLICIES.values()})


def seed(world: World) -> None:
    """Стартовые уровни политик выводятся из того, что страна уже делает.

    Милитаризованная страна начинает с высоких военных расходов не
    потому, что так записано в таблице, а потому, что это видно из её
    бюджета. Свободы — из индекса режима.
    """
    # Опорные значения фиксированы, а не берутся как максимум по выборке:
    # иначе одна КНДР с её долей военных расходов сжимала всех остальных
    # к нулю, и США выглядели демилитаризованной страной.
    REF_MILEX = 0.055    # доля военных расходов в ВВП, соответствующая 1.0
    REF_TROOPS = 8.0     # военнослужащих на тысячу населения
    for c in world.countries.values():
        for pid, p in POLICIES.items():
            v = p.default
            if pid == "milex_level":
                v = min(0.95, (c.milex_bn / max(c.gdp_bn, 1.0)) / REF_MILEX)
            elif pid == "conscription":
                v = min(0.95, (c.troops_k / max(c.pop_mn, 0.1)) / REF_TROOPS)
            elif pid == "civil_liberties":
                v = min(0.95, max(0.05, c.vdem_liberal))
            elif pid == "surveillance":
                v = min(0.95, max(0.05, 1.0 - c.vdem_liberal))
            elif pid == "religion_state":
                v = min(0.90, max(0.05, 0.9 - c.vdem_liberal * 0.8))
            world.policies[(c.code, pid)] = round(v, 3)
            SEED_LEVEL[(c.code, pid)] = round(v, 3)
        for p in POLICIES.values():
            if p.affects:
                BASE_ATTR[(c.code, p.affects)] = getattr(c, p.affects)


def level(world: World, code: str, pid: str) -> float:
    return world.policies.get((code, pid), POLICIES[pid].default)


def set_level(world: World, code: str, pid: str, v: float,
              rng=None) -> None:
    """Установить рычаг. Между замыслом и результатом стоит министр.

    Компетентный исполнитель проводит решение почти как задумано,
    слабый — приблизительно. Без этого министры оставались украшением:
    их пригодность считалась, но ни на что не влияла.
    """
    from . import personnel
    target = max(0.0, min(1.0, v))
    owner = POLICIES[pid].ministry
    spread = personnel.execution_spread(world, code, owner)
    if spread and rng is not None:
        drift = rng.uniform(-spread, spread) * 0.35
        target = max(0.0, min(1.0, target + drift))
    world.policies[(code, pid)] = target


def grow_base(code: str, attr: str, factor: float) -> None:
    """Подрастить базу показателя вместе с ростом экономики.

    Без этого `apply_macro` каждый ход возвращал показатель к
    зафиксированной на старте базе и стирал рост, начисленный в
    `anchors`. ВВП не рос ни разу с тех пор, как появились ветви
    управления.
    """
    key = (code, attr)
    if key in BASE_ATTR:
        BASE_ATTR[key] *= factor


def apply_macro(world: World) -> None:
    """Перенести уровни политик в макропоказатели страны.

    Считается от базы, а не от текущего значения, иначе эффект
    накапливался бы каждый ход и уводил показатели в разнос. База при
    этом растёт вместе с экономикой — см. `grow_base`.
    """
    for c in world.countries.values():
        for p in POLICIES.values():
            if not p.affects:
                continue
            base = BASE_ATTR.get((c.code, p.affects))
            if base is None:
                continue
            delta = (level(world, c.code, p.id) - p.default) * p.effect
            v = base * (1.0 + delta)
            if p.affects == "vdem_liberal":
                v = max(0.02, min(0.98, v))
            setattr(c, p.affects, max(0.0, v))


def mood_pressure(world: World, code: str) -> dict[str, float]:
    """Сколько каждая группа выигрывает или теряет от нынешнего курса."""
    out: dict[str, float] = {}
    for pid, stances in POSITIONS.items():
        gap = level(world, code, pid) - POLICIES[pid].default
        for grp, st in stances.items():
            out[grp] = out.get(grp, 0.0) + st * gap
    return out


def ai_adjust(world: World, code: str, doc) -> list[tuple[str, float]]:
    """Ход ИИ по внутренней политике.

    Курс определяют собственные группы страны, а не веса внешней
    доктрины. Для каждой политики считается взвешенное по влиянию
    желание групп, и уровень ползёт в эту сторону мелким шагом, так что
    курс меняется годами, а не кварталами.

    Первая версия брала цель из доктрины, и Китай за десять лет поднял
    гражданские свободы с 0.08 до 0.52 — потому что у него низкий вес
    режимной выживаемости во внешней политике. Величины оказались
    разными по смыслу.
    """
    weights = {b.id: b.weight for b in _groups.blocs(world, code)}
    doctrine_pull = {
        "Оборона": 0.5 + 0.5 * doc.w_security + 0.3 * doc.revisionism,
        "Внешняя политика": 0.3 + 0.6 * doc.w_prestige,
    }
    moved = []
    for pid, p in POLICIES.items():
        want = sum(weights.get(g, 0.0) * st
                   for g, st in POSITIONS.get(pid, {}).items())
        engaged = sum(weights.get(g, 0.0) for g in POSITIONS.get(pid, {}))
        # Институты инерционны: цель отсчитывается от того, с чем страна
        # пришла, а давление групп сдвигает её на полях. Прежняя версия
        # тянула любой уровень к середине шкалы, и все страны без
        # исключения дрейфовали к авторитарности.
        anchor = SEED_LEVEL.get((code, pid), p.default)
        target = anchor + (want / engaged if engaged else 0.0) * 0.85
        if p.ministry in doctrine_pull:
            target = 0.65 * target + 0.35 * doctrine_pull[p.ministry]
        target = max(0.02, min(0.98, target))
        cur = level(world, code, pid)
        if abs(target - cur) < AI_STEP:
            continue
        step = AI_STEP if target > cur else -AI_STEP
        set_level(world, code, pid, cur + step)
        moved.append((pid, round(cur + step, 3)))
    return moved


def summary(world: World, code: str) -> list[tuple[str, str, float]]:
    return [(p.ministry, p.name_ru, level(world, code, p.id))
            for p in POLICIES.values()]
