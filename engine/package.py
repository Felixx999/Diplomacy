"""Пакетные сделки.

До сих пор сделка была односторонней: донор уступал и не получал
ничего. На вопрос «зачем уступать» модель не отвечала, а ИИ выбирал
самый лёгкий вопрос вместо нужного.

Пакет — набор встречных уступок. Он решает две задачи сразу.

Первая: неделимый вопрос получает решение. Суверенитет режется только
на ноль и сто, поэтому в одиночку он почти всегда без исхода. Но за
уступку по неделимому можно доплатить делимым — и пакет проходит там,
где ни один из вопросов по отдельности не прошёл бы.

Вторая: ратификация считается по пакету целиком. Болезненная уступка,
которая сама по себе не прошла бы, проходит, если рядом лежит выигрыш,
радующий тех же самых людей.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import groups
from .deal import TYPES, Issue, acceptance_with_aspiration, ratification_ceiling
from .state import World

GAIN_DISCOUNT = 0.65   # выигрыш ощущается слабее потери такого же размера
BALANCE_NEED = 0.55    # какую долю отданного надо вернуть, чтобы сделка имела смысл


@dataclass
class Leg:
    """Одна нога пакета: кто по какому вопросу и сколько уступает."""
    type_id: str
    giver: str
    level: float

    def name(self) -> str:
        return TYPES[self.type_id].name_ru


@dataclass
class Package:
    a: str
    b: str
    legs: list[Leg] = field(default_factory=list)

    def give(self, side: str) -> list[Leg]:
        return [l for l in self.legs if l.giver == side]

    def get(self, side: str) -> list[Leg]:
        return [l for l in self.legs if l.giver != side]

    def label(self, world: World) -> str:
        parts = [f"{world.countries[l.giver].name_ru}: "
                 f"{l.name().lower()} на {l.level:.0f}" for l in self.legs]
        return " ⇄ ".join(parts)


# --- ратификация пакета --------------------------------------------------

@dataclass
class Verdict:
    passes: bool
    pivotal: str | None
    detail: list[tuple[str, float, bool]]   # группа, чистое чувство, за или против

    def why(self) -> str:
        if self.passes:
            return "пакет проходит: выигрыш перевешивает уступки"
        return (f"пакет не проходит: {self.pivotal} против"
                if self.pivotal else "пакет не проходит")


def ratify_package(world: World, code: str, pkg: Package) -> Verdict:
    """Пройдёт ли пакет дома. Группы смотрят на него целиком.

    Позиции в таблице записаны с точки зрения уступающего. Полученная
    уступка переживается зеркально и слабее: потеря весит больше
    выигрыша того же размера.
    """
    c = world.countries[code]
    autocracy = 1.0 - c.vdem_liberal
    bs = groups.blocs(world, code)
    thr = groups.THRESHOLD.get(c.regime, 0.45)

    net: dict[str, float] = {}
    for b in bs:
        total = 0.0
        for leg in pkg.legs:
            stance = groups.POSITIONS.get(leg.type_id, {}).get(b.id, 0.0)
            if not stance:
                continue
            share = leg.level / 100.0
            total += (stance * share if leg.giver == code
                      else -stance * share * GAIN_DISCOUNT)
        net[b.id] = total

    engaged = sum(b.weight for b in bs if abs(net[b.id]) > 1e-6)
    if engaged < 1e-6:
        return Verdict(True, None, [])

    support, detail, pivotal = 1.0, [], None
    for b in sorted(bs, key=lambda x: net[x.id]):
        if abs(net[b.id]) < 1e-6:
            continue
        stays = b.goodwill(autocracy) + net[b.id] > 0
        detail.append((b.name_ru, round(net[b.id], 3), stays))
        if not stays:
            support -= b.weight / engaged
            if support < thr and pivotal is None:
                pivotal = b.name_ru
    return Verdict(pivotal is None, pivotal, detail)


# --- ценность для сторон -------------------------------------------------

def value_for(world: World, code: str, pkg: Package) -> float:
    """Насколько пакет выгоден стороне. Ноль — ровно баланс."""
    gain = sum(l.level * TYPES[l.type_id].ratify_difficulty for l in pkg.get(code))
    cost = sum(l.level * TYPES[l.type_id].ratify_difficulty for l in pkg.give(code))
    return round(gain - cost * BALANCE_NEED, 1)


def workable(world: World, pkg: Package) -> tuple[bool, str]:
    """Пройдёт ли пакет оба уровня с обеих сторон."""
    for side in (pkg.a, pkg.b):
        if value_for(world, side, pkg) < 0:
            return False, f"{world.countries[side].name_ru} остаётся в убытке"
        v = ratify_package(world, side, pkg)
        if not v.passes:
            return False, f"{world.countries[side].name_ru}: {v.why()}"
    return True, "пакет проходит с обеих сторон"


# --- сборка пакета -------------------------------------------------------

def sweeten(world: World, giver: str, receiver: str, hard_type: str,
            hard_level: float, candidates: list[str] | None = None,
            steps: int = 6) -> Package | None:
    """Подобрать доплату к трудной уступке.

    Берём неделимый или болезненный вопрос, по которому в одиночку
    решения нет, и ищем встречную уступку получателя, которая делает
    пакет проходимым для обеих сторон.
    """
    from .deal import live
    base = Leg(hard_type, giver, hard_level)
    pool = candidates or [t for t in TYPES
                          if t != hard_type and live(world, receiver, giver, t)
                          and TYPES[t].divisibility >= 0.5]
    # Ищем самую дешёвую доплату, а не первую подошедшую: уровень
    # перебирается снаружи, тип внутри. Иначе ответ зависел от порядка
    # строк в таблице и всегда выходил одинаковым.
    from .deal import stake
    pool = sorted(pool, key=lambda t: -stake(world, receiver, giver, t))
    for i in range(1, steps + 1):
        lvl = round(100.0 * i / steps)
        for tid in pool:
            pkg = Package(giver, receiver, [base, Leg(tid, receiver, lvl)])
            ok, _ = workable(world, pkg)
            if ok:
                return pkg
    return None


def solo_fails(world: World, giver: str, receiver: str, type_id: str,
               level: float) -> bool:
    """Правда ли, что в одиночку этот вопрос не решается."""
    from .deal import feasible
    issue = Issue("x", TYPES[type_id].name_ru, giver, receiver, type_id=type_id)
    ceil_ = ratification_ceiling(world, issue)
    floor_ = acceptance_with_aspiration(world, issue, ceil_)
    pts = feasible(issue, ceil_, floor_)
    return not pts or level > ceil_.hi
