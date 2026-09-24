"""Стартовое положение.

Игрок приходит не на пустое место. У него уже есть правительство,
послы в главных столицах, действующие соглашения и накопленные обиды —
всё это досталось от предшественника.

Без этого партия начинается с пустого кабинета, пустой повестки и
пустых досье, и первое, что видит человек, — экран, на котором ничего
нет. Механически это верно, показательно это провал.

Три министерства оставлены вакантными намеренно. Новый глава
государства редко наследует полностью укомплектованный кабинет, и у
игрока сразу есть осмысленное первое действие.
"""

from __future__ import annotations

import random

from . import execution, groups, intel, personnel as hr, policy
from .state import World

VACANT = ("homeland", "veterans", "education")   # что предшественник не закрыл
ENVOY_POSTS = 6                                  # в скольких столицах есть посол
LEGACY_DEALS = 3                                 # соглашений в работе на старте


def _rng(world: World, tag: str) -> random.Random:
    return random.Random(f"{tag}:{world.year}")


def seed_cabinet(world: World, code: str) -> list[dict]:
    """Правительство, доставшееся по наследству.

    Назначения бесплатны: игрок за них не платил. Но и подобраны они не
    им, поэтому среди министров попадаются неподходящие — это нормально
    и даёт повод для первых перестановок.
    """
    from .government import ministries_of
    out = []
    pool = hr.pool(world, code)
    used: set[str] = set()
    for mid in ministries_of(code):
        if mid in VACANT:
            continue
        ranked = sorted(
            ((hr.minister_fit(world, p, mid)[0], p) for p in pool
             if p.name not in used), key=lambda x: -x[0])
        if not ranked:
            break
        fit, person = ranked[0]
        used.add(person.name)
        world.ministers[(code, mid)] = (person, fit)
        out.append({"ministry": mid, "who": person.title, "fit": round(fit, 2)})
    return out


def seed_envoys(world: World, code: str, n: int = ENVOY_POSTS) -> list[dict]:
    """Послы в столицах, которые важнее всего по весу и связям."""
    targets = sorted(world.others(code),
                     key=lambda c: -(world.countries[c].power()
                                     + world.trade_dep(code, c)))[:n]
    # Посол сидит в одной столице, а не в двух сразу: занятые люди
    # исключаются, в том числе уже назначенные министрами.
    out = []
    busy = {p.name for p, _ in world.ministers.values()}
    for t in targets:
        ranked = sorted(((hr.ambassador_fit(world, p, t)[0], p)
                         for p in hr.pool(world, code) if p.name not in busy),
                        key=lambda x: -x[0])
        if not ranked:
            break
        fit, person = ranked[0]
        busy.add(person.name)
        world.ambassadors[(code, t)] = (person, fit)
        out.append({"to": t, "who": person.title, "fit": round(fit, 2)})
    return out


def seed_deals(world: World, code: str, turn: int) -> list[dict]:
    """Соглашения, подписанные до прихода игрока и ещё не исполненные."""
    from .deal import TYPES, live
    rng = _rng(world, "deals")
    out = []
    partners = sorted(world.others(code),
                      key=lambda c: -world.trade_dep(code, c))[:8]
    for other in partners:
        if len(out) >= LEGACY_DEALS:
            break
        kinds = [t for t in TYPES if live(world, code, other, t)
                 and TYPES[t].horizon_q >= 3]
        if not kinds:
            continue
        tid = kinds[rng.randrange(len(kinds))]
        d = execution.sign(world, code, other, tid, rng.uniform(35, 65), turn)
        d.delivered = round(rng.uniform(0.2, 0.6), 2)   # часть уже поставлена
        out.append({"deal": d.label(world), "progress": d.delivered})
    return out


def seed_moods(world: World, code: str) -> None:
    """Настроения групп не одинаковы: у предшественника были свои друзья."""
    rng = _rng(world, "moods")
    sat = policy.mood_pressure(world, code) if hasattr(policy, "mood_pressure") else {}
    for b in groups.blocs(world, code):
        base = 0.55 + 0.25 * sat.get(b.id, 0.0) + rng.uniform(-0.12, 0.12)
        groups.set_mood(world, code, b.id, base)


def seed_intel(world: World, code: str) -> None:
    """Посол в столице означает, что мы знаем эту страну лучше."""
    for (a, t), rec in list(world.intel.items()):
        if a != code:
            continue
        if (code, t) in world.ambassadors:
            rec["level"] = min(0.85, rec["level"] + 0.20)


def setup(world: World, code: str, turn: int = 0) -> dict:
    """Полное стартовое положение для страны игрока."""
    report = {
        "cabinet": seed_cabinet(world, code),
        "envoys": seed_envoys(world, code),
        "deals": seed_deals(world, code, turn),
        "vacant": list(VACANT),
    }
    seed_moods(world, code)
    seed_intel(world, code)
    return report
