"""Экономика страны: отрасли, торговля, курс.

Всё, что здесь показывается игроку, считается из уже существующего
состояния, а не рисуется. Экспорт выводится из размера экономики,
открытости и зависимости партнёров; структура товаров — из отраслевых
долей; курс валюты — из торгового баланса, роста и доверия к стране.

Нарисованные показатели рассыпаются на первом же вопросе «откуда это
число». Выведенные — нет.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

from . import policy
from .state import DATA, World

SECTORS = ("agriculture", "industry", "energy", "services", "technology")
SECTOR_RU = {
    "agriculture": "сельское хозяйство",
    "industry": "промышленность",
    "energy": "энергоносители",
    "services": "услуги",
    "technology": "технологии",
}
# Насколько отрасль вообще торгуется через границу. Услуги в основном нет.
TRADABLE = {"agriculture": 0.75, "industry": 0.95, "energy": 0.90,
            "services": 0.20, "technology": 0.85}

BASE_OPENNESS = 0.42     # доля ВВП во внешней торговле при нейтральных тарифах
CURRENCY_BASE = 100.0


def load_sectors() -> dict[str, dict[str, float]]:
    out = {}
    with open(DATA / "sectors.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["code"]] = {s: float(r[s]) for s in SECTORS}
    return out


MIX = load_sectors()


@dataclass
class Trade:
    exports: float             # млрд долларов в год
    imports: float
    balance: float
    partners_out: list[tuple[str, float]]   # куда идёт экспорт
    partners_in: list[tuple[str, float]]
    basket: list[tuple[str, float]]         # структура экспорта по отраслям


def openness(world: World, code: str) -> float:
    """Открытость экономики. Тарифная защита её прямо снижает."""
    tar = policy.level(world, code, "tariffs") if hasattr(policy, "level") else 0.5
    return BASE_OPENNESS * (1.35 - 0.7 * (tar / 100.0))


def basket(world: World, code: str) -> list[tuple[str, float]]:
    """Структура экспорта: что страна на самом деле продаёт.

    Не то же самое, что структура экономики: услуги занимают половину
    ВВП, но почти не пересекают границу, поэтому в корзине экспорта их
    доля мала, а сырья и промышленности — велика.
    """
    mix = MIX.get(code, {s: 0.2 for s in SECTORS})
    raw = {s: mix[s] * TRADABLE[s] for s in SECTORS}
    total = sum(raw.values()) or 1.0
    rows = [(SECTOR_RU[s], round(v / total, 3)) for s, v in raw.items()]
    rows.sort(key=lambda x: -x[1])
    return rows



def trade(world: World, code: str) -> Trade:
    """Потоки экспорта и импорта с разбивкой по партнёрам."""
    c = world.countries[code]
    op = openness(world, code)
    gross = c.gdp_bn * op

    # Зависимость — это доля, а покупает партнёр пропорционально своему
    # размеру. Без веса по ВВП главным покупателем России выходила
    # Украина, а Саудовской Аравии — Иран: страны с высокой
    # зависимостью и крошечной экономикой.
    out_rows, in_rows = [], []
    for other in world.others(code):
        size = world.countries[other].gdp_bn
        their_dep = world.trade_dep(other, code)
        our_dep = world.trade_dep(code, other)
        if their_dep > 0.005:
            out_rows.append((other, their_dep * size))
        if our_dep > 0.005:
            in_rows.append((other, our_dep * size))
    ws_out = sum(w for _, w in out_rows) or 1.0
    ws_in = sum(w for _, w in in_rows) or 1.0

    # Разделение оборота на вывоз и ввоз ограничено: страна не может
    # вывозить в девять раз больше, чем ввозит. Перекос отражает
    # соотношение спроса на нас и нашего спроса, но сжат в разумные
    # рамки.
    tilt = (ws_out - ws_in) / (ws_out + ws_in)
    share = 0.5 + 0.14 * max(-1.0, min(1.0, tilt))
    exports = gross * share
    imports = gross - exports

    out_rows = sorted(((o, round(exports * w / ws_out, 1)) for o, w in out_rows),
                      key=lambda x: -x[1])[:6]
    in_rows = sorted(((o, round(imports * w / ws_in, 1)) for o, w in in_rows),
                     key=lambda x: -x[1])[:6]
    return Trade(round(exports, 1), round(imports, 1),
                 round(exports - imports, 1), out_rows, in_rows,
                 basket(world, code))


def currency(world: World, code: str) -> float:
    """Индекс курса, сто на старте.

    Держится на трёх вещах: сальдо внешней торговли, отрыв роста от
    среднего и доверие к стране — легитимность режима минус ощущаемая
    соседями угроза. Ни одна из них не выдумана, все уже есть в модели.
    """
    c = world.countries[code]
    t = trade(world, code)
    bal = t.balance / max(c.gdp_bn, 1.0)

    growth = getattr(c, "_growth", 0.0)
    avg = sum(getattr(x, "_growth", 0.0) for x in world.countries.values())
    avg /= max(len(world.countries), 1)

    threat_out = sum(world.threat(o, code) for o in world.others(code))
    threat_out /= max(len(world.countries) - 1, 1)
    confidence = c.legitimacy - 0.5 * threat_out

    idx = CURRENCY_BASE * (1.0 + 1.8 * bal + 6.0 * (growth - avg)
                           + 0.25 * confidence)
    return round(max(15.0, idx), 1)


def profile(world: World, code: str) -> dict:
    """Всё, что показывается на экономической панели, одним вызовом."""
    c = world.countries[code]
    t = trade(world, code)
    return {
        "code": code, "name": c.name_ru,
        "gdp": round(c.gdp_bn),
        "gdp_per_capita": round(c.gdp_bn * 1000 / max(c.pop_mn, 0.1)),
        "currency": currency(world, code),
        "exports": t.exports, "imports": t.imports, "balance": t.balance,
        "openness": round(openness(world, code), 3),
        "basket": t.basket,
        "dominant": t.basket[0][0],
        "to": [(world.countries[o].name_ru, v) for o, v in t.partners_out],
        "from": [(world.countries[o].name_ru, v) for o, v in t.partners_in],
        "sectors": [(SECTOR_RU[s], MIX.get(code, {}).get(s, 0.0))
                    for s in SECTORS],
    }
