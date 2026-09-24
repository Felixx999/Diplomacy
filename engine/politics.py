"""Выборы, смена власти и инерция курса.

Партия здесь — не строка в таблице избирателей, а коалиция групп
интересов. Её поддержка складывается из веса входящих групп и их
настроения, поэтому выборы автоматически отражают всё, что происходило
в стране: экономику, проведённые уступки, изменения курса.

Смена власти двигает доктрину не мгновенно. Договоры, аппарат и взятые
обязательства держат прежний курс годами — это та самая инерция, о
которой шла речь в Р-17.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

from . import groups as _groups
from .state import DATA, World

TERM = {"democracy": 48, "hybrid": 60}   # месяцев между выборами
DOCTRINE_INERTIA = 0.06                   # скорость поворота курса за квартал
COUP_BASE = 0.006                         # квартальный риск смены в автократии


@dataclass
class Party:
    id: str
    name_ru: str
    base_groups: list[str]
    shifts: dict[str, float]
    d_horizon: int


def _load() -> dict[str, Party]:
    out = {}
    with open(DATA / "parties.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["id"]] = Party(
                r["id"], r["name_ru"], r["base_groups"].split(";"),
                {k[2:]: float(v) for k, v in r.items()
                 if k.startswith("d_") and k != "d_horizon"},
                int(r["d_horizon"]))
    return out


PARTIES = _load()
DOCTRINE_SEED: dict[str, dict[str, float]] = {}


def support(world: World, code: str) -> list[tuple[str, float]]:
    """Поддержка партий: вес входящих групп, умноженный на их настроение."""
    weights = {b.id: _groups.electoral_weight(world, code, b)
               for b in _groups.blocs(world, code)}
    raw = []
    for p in PARTIES.values():
        v = sum(weights.get(g, 0.0) * _groups.mood(world, code, g)
                for g in p.base_groups)
        raw.append((p.id, v))
    total = sum(v for _, v in raw) or 1.0
    return sorted(((pid, v / total) for pid, v in raw),
                  key=lambda t: -t[1])


def remember_doctrines(doctrines: dict) -> None:
    """Запомнить исходный курс: цель партии отсчитывается от него.

    Без этого `steer` считал цель от текущего значения, добавка
    накапливалась сама на себя, и за семнадцать лет любая доктрина
    упиралась в потолок шкалы.
    """
    for code, d in doctrines.items():
        DOCTRINE_SEED[code] = {
            "w_security": d.w_security, "w_economy": d.w_economy,
            "w_prestige": d.w_prestige, "w_ideology": d.w_ideology,
            "w_regime": d.w_regime, "risk_tolerance": d.risk_tolerance,
            "revisionism": d.revisionism}


def seed(world: World) -> None:
    for c in world.countries.values():
        world.government[c.code] = support(world, c.code)[0][0]
        # Календари выборов разнесены: страны не голосуют в один квартал.
        # Смещение детерминировано кодом страны, чтобы партия оставалась
        # воспроизводимой по сиду.
        term = TERM.get(c.regime, 0)
        offset = (sum(ord(ch) for ch in c.code) % term) if term else 0
        world.next_vote[c.code] = offset + 1


def due(world: World, code: str, turn: int) -> bool:
    c = world.countries[code]
    if c.regime not in TERM:
        return False
    return turn >= world.next_vote.get(code, TERM[c.regime])


def transition_risk(world: World, code: str) -> float:
    """Риск смены власти в режиме без выборов.

    Растёт, когда правящая коалиция теряет настроение: недовольные
    силовики и элита опаснее недовольного населения.
    """
    c = world.countries[code]
    if c.regime in TERM:
        return 0.0
    ruling = PARTIES.get(world.government.get(code, ""), None)
    if ruling is None:
        return COUP_BASE
    weights = {b.id: b.weight for b in _groups.blocs(world, code)}
    loyal = sum(weights.get(g, 0.0) * _groups.mood(world, code, g)
                for g in ruling.base_groups)
    span = sum(weights.get(g, 0.0) for g in ruling.base_groups) or 1.0
    return COUP_BASE * (1.0 + 6.0 * max(0.0, 0.5 - loyal / span))


def hold(world: World, code: str, turn: int, rng) -> dict | None:
    """Провести выборы или разыграть смену власти. Возвращает событие."""
    c = world.countries[code]
    old = world.government.get(code)
    ranking = support(world, code)

    if c.regime in TERM:
        world.next_vote[code] = turn + TERM[c.regime]
        winner = ranking[0][0]
        kind = "выборы"
    else:
        if rng.random() > transition_risk(world, code):
            return None
        pool = [(pid, v) for pid, v in ranking]
        pick = rng.random() * sum(v for _, v in pool)
        acc = 0.0
        winner = pool[0][0]
        for pid, v in pool:
            acc += v
            if acc >= pick:
                winner = pid
                break
        kind = "смена власти"

    world.government[code] = winner
    if winner == old:
        return {"country": code, "kind": kind, "party": PARTIES[winner].name_ru,
                "changed": False, "share": round(ranking[0][1], 3)}
    return {"country": code, "kind": kind, "from": PARTIES[old].name_ru if old else "—",
            "party": PARTIES[winner].name_ru, "changed": True,
            "share": round(dict(ranking)[winner], 3)}


def steer(world: World, code: str, doctrine) -> None:
    """Медленный поворот доктрины к профилю правящей партии.

    Ни один договор не рвётся в день инаугурации: аппарат, обязательства
    и союзники держат прежний курс, и разворот занимает годы.
    """
    p = PARTIES.get(world.government.get(code, ""))
    if p is None:
        return
    base = DOCTRINE_SEED.get(code)
    if base is None:
        return
    names = {"security": "w_security", "economy": "w_economy",
             "prestige": "w_prestige", "ideology": "w_ideology",
             "regime": "w_regime", "risk": "risk_tolerance",
             "revisionism": "revisionism"}
    for key, shift in p.shifts.items():
        attr = names.get(key)
        if attr is None:
            continue
        target = max(0.0, min(1.0, base[attr] + shift))
        cur = getattr(doctrine, attr)
        setattr(doctrine, attr, cur + (target - cur) * DOCTRINE_INERTIA)
