"""Проверка макропоказателей.

Мёртвая экономика прожила несколько сессий незамеченной: проверки
смотрели на отношения, повестку и читаемость, но никто не смотрел на
ВВП. `apply_macro` каждый ход возвращал показатели к стартовой базе, и
рост стирался.

Эта проверка гоняет полную партию и требует от каждого показателя трёх
вещей: он движется, движется в правдоподобную сторону и траектории
разных стран расходятся. Замер идёт по распределению, а не по одной
стране — урок Р-38.

    python3 tools/macro.py [ходов]
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import economy  # noqa: E402
from engine.sim import Sim  # noqa: E402

WATCH = ("gdp_bn", "pop_mn", "milex_bn", "steel_mt", "energy_mtoe", "troops_k")
LABEL = {"gdp_bn": "ВВП", "pop_mn": "население", "milex_bn": "военные расходы",
         "steel_mt": "промышленность", "energy_mtoe": "энергия",
         "troops_k": "армия"}
DEAD = 0.005     # ниже этого изменения показатель считается неподвижным


def run(turns: int) -> dict:
    s = Sim(player="IND", seed=3)
    peers = list(s.world.countries)
    start = {a: {c: getattr(s.world.countries[c], a) for c in peers}
             for a in WATCH}
    cur0 = {c: economy.currency(s.world, c) for c in s.world.tier("A")}
    pow0 = {c: s.world.countries[c].power() for c in peers}
    for _ in range(turns):
        s.tick()
    return {"sim": s, "start": start, "cur0": cur0, "pow0": pow0,
            "peers": peers}


def main() -> None:
    turns = int(sys.argv[1]) if len(sys.argv) > 1 else 192
    r = run(turns)
    s, peers = r["sim"], r["peers"]
    years = turns / 12.0
    print(f"Прогон {turns} ходов ({years:.0f} лет), {len(peers)} стран\n")
    print(f"{'показатель':<18}{'медиана':>12}{'разброс':>12}{'вердикт':>14}")
    print("-" * 58)

    bad = []
    for a in WATCH:
        rel = []
        for c in peers:
            was = r["start"][a][c]
            now = getattr(s.world.countries[c], a)
            if was > 0:
                rel.append((now - was) / was)
        med = statistics.median(rel)
        spread = statistics.pstdev(rel)
        if abs(med) < DEAD and spread < DEAD:
            verdict, ok = "НЕПОДВИЖЕН", False
        elif spread < DEAD:
            verdict, ok = "БЕЗ РАЗБРОСА", False
        else:
            verdict, ok = "живой", True
        if not ok:
            bad.append(a)
        print(f"  {LABEL[a]:<16}{med:>+11.1%}{spread:>12.3f}{verdict:>14}")

    print()
    powers = sorted(((s.world.countries[c].power(), c) for c in peers),
                    reverse=True)[:5]
    print("Первая пятёрка по мощи в конце партии:")
    for p, c in powers:
        was = r["pow0"][c]
        print(f"  {s.world.countries[c].name_ru:<22}{p:.3f}  ({p - was:+.3f})")

    print("\nКурс валют держав:")
    for c, v0 in list(r["cur0"].items())[:6]:
        v = economy.currency(s.world, c)
        print(f"  {c}  {v0:.0f} → {v:.0f}")

    print()
    if bad:
        print("СЛОМАНО: " + ", ".join(LABEL[a] for a in bad))
        sys.exit(1)
    print("Все показатели живые и расходятся между странами.")


if __name__ == "__main__":
    main()
