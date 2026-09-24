"""Скрытая информация.

Собственные границы страна знает точно: свой парламент виден изнутри.
Чужой порог принятия виден интервалом, ширина которого зависит от того,
сколько вложено в разведку и как давно.

Ошибка оценки хранится, а не разыгрывается заново при каждом обращении.
Дрожащий на экране интервал — это не туман войны, а мусор: игрок не
может строить на нём никаких планов.

Неопределённость симметрична. ИИ-страны тоже ошибаются в оценке чужих
порогов, и из этого возникает главное явление модуля — сделка
срывается, потому что предлагавший неверно оценил партнёра.
"""

from __future__ import annotations

import random

from .state import World

MAX_WIDTH = 34.0      # ширина интервала при полном неведении, пункты шкалы
INTEL_COST = 60.0     # дипкапитал за единицу осведомлённости при нуле
INTEL_DECAY = 0.9899   # сведения устаревают: за квартал теряется 3 процента
INTEL_CAP = 0.95      # полного знания не бывает
BIAS_SPAN = 0.45      # насколько сильно ошибка может смещать оценку


def seed_levels(world: World) -> None:
    """Стартовая осведомлённость выводится из связей, а не задаётся.

    Союзника и крупного торгового партнёра страна понимает лучше:
    посольство больше, обменов больше, чиновники знакомы лично.
    """
    rng = random.Random(20260101)
    for a in world.countries:
        for b in world.countries:
            if a == b:
                continue
            d = world.dyad(a, b)
            level = min(0.70, 0.10 + 0.35 * d.obligation()
                        + 1.2 * world.trade_dep(a, b))
            world.intel[(a, b)] = {
                "level": round(level, 3),
                "bias": rng.uniform(-1.0, 1.0) * (1.0 - level) * BIAS_SPAN,
                "updated": 0,
            }


def level(world: World, observer: str, subject: str) -> float:
    return world.intel.get((observer, subject), {}).get("level", 0.0)


def cost_to_gain(current: float, gain: float) -> float:
    """Сколько стоит поднять осведомлённость. Отдача убывающая."""
    return gain * INTEL_COST * (1.0 + 4.0 * current)


def invest(world: World, observer: str, subject: str,
           spend: float, rng: random.Random, turn: int = 0) -> dict:
    """Вложить дипломатический капитал в разведку по конкретной стране."""
    rec = world.intel.setdefault((observer, subject),
                                 {"level": 0.0, "bias": 0.0, "updated": 0})
    before = rec["level"]
    # Посол удешевляет работу разведки в своей столице
    edge = envoy_edge(world, observer, subject)
    gain = spend * (1.0 + edge) / (INTEL_COST * (1.0 + 4.0 * before))
    after = min(INTEL_CAP, before + gain)
    rec["level"] = round(after, 3)
    # свежие сведения не только сужают интервал, но и смещают его к правде
    rec["bias"] = rng.uniform(-1.0, 1.0) * (1.0 - after) * BIAS_SPAN
    rec["updated"] = turn
    world.countries[observer].diplomatic_capital -= spend
    return {"observer": observer, "subject": subject,
            "before": round(before, 3), "after": round(after, 3),
            "spent": round(spend, 1)}


def decay_all(world: World) -> None:
    """Сведения устаревают сами: люди уходят, обстоятельства меняются."""
    for rec in world.intel.values():
        rec["level"] *= INTEL_DECAY


def envoy_edge(world: World, observer: str, subject: str) -> float:
    """Прибавка от посла в этой столице.

    Посольство — это глаза и уши на месте: с хорошим послом чужой порог
    виден точнее, а разведка обходится дешевле. До этой правки
    пригодность посла считалась, но ни на что не влияла, то есть по
    мерке Р-28 послы были украшением.
    """
    from . import personnel
    return personnel.envoy_bonus(world, observer, subject)


def estimate(world: World, observer: str, subject: str,
             true_floor: float) -> tuple[float, float, float]:
    """Как наблюдатель видит чужой порог принятия.

    Возвращает нижнюю и верхнюю границы интервала и уровень
    осведомлённости. При полной осведомлённости интервал вырождается
    почти в точку, при нулевой занимает треть шкалы.
    """
    rec = world.intel.get((observer, subject), {"level": 0.0, "bias": 0.0})
    lv = max(0.0, min(INTEL_CAP, rec["level"] + envoy_edge(world, observer, subject)))
    width = (1.0 - lv) * MAX_WIDTH
    centre = true_floor + rec["bias"] * width
    return (max(0.0, centre - width / 2),
            min(100.0, centre + width / 2), lv)


def misjudged(world: World, observer: str, subject: str,
              offer: float, true_floor: float) -> str | None:
    """Почему предложение сорвалось, если сорвалось из-за незнания."""
    if offer >= true_floor:
        return None
    lo, hi, lv = estimate(world, observer, subject, true_floor)
    if offer >= lo:
        return (f"предложение {offer:.0f} выглядело достаточным: порог "
                f"оценивался в {lo:.0f}..{hi:.0f}, на деле {true_floor:.0f}")
    return f"предложение {offer:.0f} было заведомо ниже оценки {lo:.0f}"
