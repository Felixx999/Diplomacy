"""Совокупная мощь.

Устроена как индекс COW: доля страны по каждому компоненту берётся от
мирового итога, индекс — среднее этих долей. Компонентов пять вместо
шести, потому что численность вооружённых сил у нас в данных
отсутствует, а городское население заменено потреблением энергии.

Ключевое отличие от прежней формулы: она считалась только по ВВП и
военным расходам, из-за чего расходы весили треть вместо шестой части и
США обгоняли Китай — в реальном индексе наоборот. Промышленные
компоненты возвращают правильное соотношение.

Покрытие вынесено в `data/capability.csv`: наши тридцать две страны это
не весь мир, и доля, которую они покрывают по каждому компоненту,
задаётся отдельно. Побочное следствие приятное — сумма индекса по всем
странам равна среднему покрытию по построению, то есть шкала не может
уехать сама по себе.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

from .state import DATA, World

# Промышленный выпуск и энергопотребление растут медленнее ВВП:
# развитая экономика прибавляет в услугах, а не в тоннах стали.
INDUSTRY_ELASTICITY = 0.55
ENERGY_ELASTICITY = 0.70


@dataclass
class Component:
    name: str
    column: str
    coverage: float
    note: str


def load_components() -> list[Component]:
    out = []
    with open(DATA / "capability.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(Component(r["component"], r["column"],
                                 float(r["coverage"]), r["note"]))
    return out


COMPONENTS = load_components()

RU_NAMES = {"gdp": "экономика", "population": "население",
            "military": "оборона", "energy": "энергия",
            "industry": "промышленность", "personnel": "армия"}


def shares(world: World, comp: Component) -> dict[str, float]:
    """Доли стран по одному компоненту, приведённые к мировому итогу."""
    raw = {c.code: max(0.0, getattr(c, comp.column, 0.0))
           for c in world.countries.values()}
    total = sum(raw.values()) or 1.0
    return {code: v / total * comp.coverage for code, v in raw.items()}


def recompute(world: World) -> None:
    """Пересчитать мощь всех стран. Единственное место, где она меняется."""
    acc: dict[str, float] = {c: 0.0 for c in world.countries}
    for comp in COMPONENTS:
        for code, v in shares(world, comp).items():
            acc[code] += v
    n = len(COMPONENTS)
    for code, total in acc.items():
        world.countries[code].cinc = round(total / n, 5)


def breakdown(world: World, code: str) -> list[tuple[str, float]]:
    """Из чего сложилась мощь конкретной страны. Для трассировки причин."""
    rows = []
    for comp in COMPONENTS:
        rows.append((RU_NAMES.get(comp.name, comp.name),
                     round(shares(world, comp)[code], 4)))
    return rows


def scale_total(world: World) -> float:
    """Сумма индекса по всем странам. По построению равна среднему покрытию."""
    return sum(c.cinc for c in world.countries.values())
