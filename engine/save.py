"""Сохранение и загрузка партии.

Ядро детерминировано, поэтому теоретически партию можно восстановить
одним сидом и списком ходов. На практике этого мало: игрок вмешивается,
и повтор всей истории занимает время. Здесь сохраняется состояние
целиком.

Что важно: восстановленная партия должна вести себя ровно так же, как
если бы её не прерывали. Поэтому сохраняется и внутреннее состояние
генератора случайных чисел, и память повестки, и накопленные усталости.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

FORMAT = 3


def _plain(v):
    if is_dataclass(v):
        return asdict(v)
    if isinstance(v, dict):
        return {"|".join(k) if isinstance(k, tuple) else str(k): _plain(x)
                for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def dump(sim) -> dict:
    w = sim.world
    return {
        "format": FORMAT,
        "player": sim.player,
        "turn": sim.turn_no,
        "year": w.year, "month": w.quarter,
        "rng": list(sim.rng.getstate()[1]),
        "countries": {c.code: {k: v for k, v in asdict(c).items()}
                      for c in w.countries.values()},
        "dyads": {f"{a}|{b}": asdict(d) for (a, b), d in w.dyads.items()},
        "disputes": {k: asdict(d) for k, d in w.disputes.items()},
        "promises": [asdict(p) for p in w.promises],
        "deliveries": [asdict(d) for d in w.deliveries],
        "loans": [asdict(l) for l in w.loans],
        "intel": {f"{a}|{b}": v for (a, b), v in w.intel.items()},
        "moods": {f"{a}|{b}": v for (a, b), v in w.moods.items()},
        "policies": {f"{a}|{b}": v for (a, b), v in w.policies.items()},
        "directions": {f"{a}|{b}": v for (a, b), v in w.directions.items()},
        "ministers": {f"{a}|{b}": [p.name, p.archetype.id, fit]
                      for (a, b), (p, fit) in w.ministers.items()},
        "ambassadors": {f"{a}|{b}": [p.name, p.archetype.id, fit]
                        for (a, b), (p, fit) in w.ambassadors.items()},
        "memory": {"|".join(k): list(v) for k, v in sim.memory.items()},
        "agenda_seen": {k: list(v) for k, v in w.agenda_seen.items()},
        "agenda_prev": dict(w.agenda_prev),
        "next_vote": dict(w.next_vote),
        "government": dict(w.government),
        "switched": dict(sim._switched),
    }


def save(sim, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(dump(sim), ensure_ascii=False), encoding="utf-8")
    return p


def load(path: str | Path):
    """Восстановить партию. Возвращает готовый Sim."""
    from . import personnel as hr
    from .sim import Sim

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"чужой формат сохранения: {data.get('format')}")

    sim = Sim(player=data["player"], seed=1)
    w = sim.world
    sim.turn_no = data["turn"]
    w.year, w.quarter = data["year"], data["month"]

    for code, fields in data["countries"].items():
        c = w.countries.get(code)
        if not c:
            continue
        for k, v in fields.items():
            if hasattr(c, k):
                setattr(c, k, v)

    for key, fields in data["dyads"].items():
        a, b = key.split("|")
        d = w.dyads.get((a, b))
        if not d:
            continue
        for k, v in fields.items():
            if hasattr(d, k) and not isinstance(getattr(type(d), k, None), property):
                setattr(d, k, v)

    for did, fields in data["disputes"].items():
        d = w.disputes.get(did)
        if d:
            for k, v in fields.items():
                if hasattr(d, k):
                    setattr(d, k, v)

    from .execution import Delivery
    from .state import Promise
    from .valves import Loan
    w.promises = [Promise(**p) for p in data["promises"]]
    w.deliveries = [Delivery(**d) for d in data["deliveries"]]
    w.loans = [Loan(**l) for l in data["loans"]]

    w.intel = {tuple(k.split("|")): v for k, v in data["intel"].items()}
    w.moods = {tuple(k.split("|")): v for k, v in data["moods"].items()}
    w.policies = {tuple(k.split("|")): v for k, v in data["policies"].items()}
    w.directions = {tuple(k.split("|")): v for k, v in data["directions"].items()}
    w.agenda_seen = {k: tuple(v) for k, v in data["agenda_seen"].items()}
    w.agenda_prev = dict(data["agenda_prev"])
    w.next_vote = dict(data["next_vote"])
    w.government = dict(data["government"])
    sim.memory = {tuple(k.split("|")): tuple(v)
                  for k, v in data["memory"].items()}
    sim._switched = dict(data["switched"])

    def find(code, name, arch):
        for p in hr.pool(w, code):
            if p.name == name and p.archetype.id == arch:
                return p
        return None

    w.ministers = {}
    for key, (name, arch, fit) in data["ministers"].items():
        code, post = key.split("|")
        person = find(code, name, arch)
        if person:
            w.ministers[(code, post)] = (person, fit)
    w.ambassadors = {}
    for key, (name, arch, fit) in data["ambassadors"].items():
        code, target = key.split("|")
        person = find(code, name, arch)
        if person:
            w.ambassadors[(code, target)] = (person, fit)
    return sim
