"""Детектор мёртвых точек.

Прогоняет полную партию за каждую играбельную страну и на каждом
кварталe считает, сколько у игрока вообще есть законных ходов:
осуществимых сделок и действий по карману.

Ноль на любом ходу — поломка, а не сложность. Игрок в такой ситуации
может только жать «следующий квартал».

    python3 tools/deadend.py [кварталов]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.ai import ACTION_COST  # noqa: E402
from engine.deal import (  # noqa: E402
    TYPES, Issue, acceptance_with_aspiration, feasible, live, ratification_ceiling)
from engine.sim import Sim  # noqa: E402


def options(sim: Sim) -> dict:
    """Что игрок реально может сделать прямо сейчас."""
    w, me = sim.world, sim.player
    dc = w.countries[me].diplomatic_capital

    deals, widths = 0, []
    for other in w.others(me):
        for t in TYPES:
            if not live(w, me, other, t):
                continue
            issue = Issue(f"{me}-{other}", TYPES[t].name_ru, me, other, type_id=t)
            ceil_ = ratification_ceiling(w, issue)
            floor_ = acceptance_with_aspiration(w, issue, ceil_)
            if feasible(issue, ceil_, floor_):
                deals += 1
                widths.append(max(0.0, ceil_.hi - floor_.lo))

    acts = sum(1 for cost in ACTION_COST.values() if dc >= cost * 0.5)
    widths.sort()
    med = widths[len(widths) // 2] if widths else 0.0
    tight = sum(1 for x in widths if x < 10.0)
    return {"deals": deals, "actions": acts, "dc": round(dc, 1),
            "median_width": round(med, 1), "tight": tight}


def run(player: str, quarters: int) -> dict:
    sim = Sim(player=player, seed=3)
    dead, thin, log = [], [], []
    for _ in range(quarters):
        turn = sim.tick()
        o = options(sim)
        total = o["deals"] + o["actions"]
        log.append((turn["date"], o["deals"], o["actions"], o["dc"],
                    o["median_width"], o["tight"]))
        if total == 0:
            dead.append(turn["date"])
        elif o["deals"] == 0:
            thin.append(turn["date"])
    return {"player": player, "dead": dead, "thin": thin, "log": log}


if __name__ == "__main__":
    quarters = int(sys.argv[1]) if len(sys.argv) > 1 else 68
    print(f"Прогон {quarters} кварталов. Ищем ходы, где у игрока нет вариантов.\n")
    for code in ("USA", "CHN", "RUS", "IND"):
        r = run(code, quarters)
        lo = min(r["log"], key=lambda x: x[1] + x[2])
        print(f"{code}: мёртвых ходов {len(r['dead'])}, "
              f"ходов без единой сделки {len(r['thin'])}")
        print(f"     худший квартал {lo[0]}: сделок {lo[1]}, действий {lo[2]}, "
              f"дипкапитал {lo[3]}")
        mw = sum(x[4] for x in r["log"]) / len(r["log"])
        tg = sum(x[5] for x in r["log"]) / len(r["log"])
        print(f"     средняя ширина зоны {mw:.1f} пунктов, "
              f"узких сделок (менее 10) в среднем {tg:.0f}")
        if r["thin"][:6]:
            print(f"     без сделок: {', '.join(r['thin'][:6])}"
                  + (" …" if len(r["thin"]) > 6 else ""))
        print()
