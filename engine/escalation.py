"""Эскалация.

`war_check` считал давление к конфликту правильно, но никуда его не
записывал: накал споров стоял на месте всю партию, и самый драматичный
источник событий был мёртв.

Здесь давление накапливается в накал, а накал на разных высотах даёт
разные последствия. Не переключатель «война да или нет», а лестница:
напряжение, кризис, развязка. Спуститься можно с любой ступени — через
соглашение по спорному вопросу или потому, что одна сторона отступила.

Развязка не бросок кубика. Исход решает соотношение сил с поправкой на
то, кто за кем стоит: союзник с обязательствами добавляет вес.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ai import doctrine_of, war_check
from .channels import Shock, apply
from .state import World

RISE = 0.03          # насколько давление поднимает накал за ход
COOL = 0.00667         # естественное остывание, если давления нет
PEAK = 0.85          # выше этого спор разрешается так или иначе
SETTLED = 48         # ходов покоя после развязки: свежий исход не переигрывают
MOBILISE = 0.55      # с этой ступени начинается мобилизация
TENSION = 0.35       # с этой ступени идут инциденты

STAGES = ((0.85, "развязка"), (0.55, "кризис"),
          (0.35, "напряжение"), (0.0, "спокойно"))


def baseline(d) -> float:
    """Ниже этого накал не опускается.

    Спорная территория не бывает совсем спокойной: пока обе стороны
    считают её своей, тлеет всегда. Без этого к концу партии все споры
    остывали в ноль и мир становился мёртвым.
    """
    return 0.10 + 0.25 * max(d.salience_claimant, d.salience_controller)


def stage(heat: float) -> str:
    for bar, name in STAGES:
        if heat >= bar:
            return name
    return "спокойно"


@dataclass
class Event:
    dispute: str
    name: str
    stage: str
    heat: float
    note: str
    resolved: str = ""


def _backing(world: World, side: str, against: str) -> float:
    """Кто за кем стоит: союзники с обязательствами добавляют вес."""
    extra = 0.0
    for third in world.others(side):
        if third == against:
            continue
        obl = world.dyad(side, third).obligation()
        if obl <= 0:
            continue
        # союзник помогает тем охотнее, чем хуже он относится к противнику
        hostility = max(0.0, -world.relation(third, against))
        extra += obl * world.countries[third].power() * (0.4 + hostility)
    return extra


def _resolve(world: World, d, turn: int) -> Event:
    """Развязка. Контроль меняется, только если перевес заметен."""
    cl, co = d.claimant, d.controller
    pc = world.countries[cl].power() + _backing(world, cl, co)
    cc = world.countries[co].power() + _backing(world, co, cl)
    edge = pc / max(pc + cc, 1e-9)

    if edge > 0.62:
        d.controller, d.claimant = cl, co
        d.recognition_share = round(min(0.95, d.recognition_share + 0.35), 3)
        d.heat = 0.45
        d.settled_turn = turn
        note = (f"контроль перешёл: перевес сил на стороне "
                f"{world.countries[cl].name_ru}")
        apply(world, [
            Shock(co, cl, -0.30, "развязка", "потеря контроля над спорной территорией"),
            Shock(co, cl, 0.35, "развязка", "проигравший видит прямую угрозу", "threat"),
        ])
        resolved = "смена контроля"
    else:
        d.heat = 0.22
        d.settled_turn = turn
        world.countries[cl].legitimacy = max(0.05,
                                             world.countries[cl].legitimacy - 0.08)
        note = (f"{world.countries[cl].name_ru} отступил: перевеса не хватило, "
                f"дома это припомнят")
        apply(world, [
            Shock(cl, co, -0.15, "развязка", "отступление после обострения"),
        ])
        resolved = "отступление"
    return Event(d.id, d.name_ru, stage(d.heat), round(d.heat, 3), note, resolved)


def tick(world: World, doctrines: dict, turn: int,
         trend: dict[str, float] | None = None) -> list[Event]:
    """Один ход лестницы для всех споров."""
    trend = trend or {}
    out: list[Event] = []

    for d in world.disputes.values():
        if d.claimant not in world.countries or d.controller not in world.countries:
            continue
        was = stage(d.heat)

        doc = doctrine_of(world, doctrines, d.claimant)
        a = war_check(world, doc, d.id, trend)
        # Свежая развязка не переигрывается: без этого Сенкаку менял
        # хозяина дважды за четыре года.
        since = turn - getattr(d, "settled_turn", -99)
        if since < SETTLED:
            d.heat = max(baseline(d), d.heat - COOL)
            continue

        push = a.pressure if a.verdict != "статус-кво" else 0.0
        d.heat = max(baseline(d), min(1.0, d.heat + push * RISE - COOL))

        now = stage(d.heat)

        # последствия ступени
        if d.heat >= MOBILISE:
            for side, other in ((d.claimant, d.controller),
                                (d.controller, d.claimant)):
                c = world.countries[side]
                c.milex_bn *= 1.004                    # мобилизация
                c.diplomatic_capital -= 1.0            # внимание уходит туда
            world.dyad(d.claimant, d.controller).add_threat(d.controller, 0.035)
            world.dyad(d.claimant, d.controller).add_threat(d.claimant, 0.035)
        elif d.heat >= TENSION:
            world.dyad(d.claimant, d.controller).add_threat(d.controller, 0.012)

        if d.heat >= PEAK:
            out.append(_resolve(world, d, turn))
            continue

        if now != was:
            note = {"напряжение": "стороны обмениваются угрозами",
                    "кризис": "объявлена мобилизация, дипломатия отходит на второй план",
                    "спокойно": "напряжение спало"}.get(now, "")
            out.append(Event(d.id, d.name_ru, now, round(d.heat, 3), note))
    return out


def hottest(world: World, code: str | None = None) -> list:
    rows = [d for d in world.disputes.values()
            if code is None or code in (d.controller, d.claimant)]
    rows.sort(key=lambda d: -d.heat)
    return rows
