"""Из чего складывается фоновый дрейф мира.

Проверка на осмысленность показала, что мир сам по себе двигает
отношения примерно с той же силой, что и действия игрока. Каждый
механизм по отдельности откалиброван, их сумма — нет.

Подкручивать множители вслепую нельзя: это компенсация одной ошибки
другой. Здесь вклад каждого источника меряется отключением: прогон
без него сравнивается с полным прогоном.

    python3 tools/drift.py [кварталов]
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.sim import Sim  # noqa: E402

BAND = 2.0 / 7.0     # ширина деления шкалы отношений
SEEDS = (3, 11, 42)
SOURCES = ("ai", "deals", "clients", "escalation", "promises", "decay", "anchors")
NAMES = {
    "ai": "ходы других стран", "deals": "исполнение соглашений",
    "clients": "притяжение клиентов к патронам", "escalation": "эскалация споров",
    "promises": "сдержанные и нарушенные обещания",
    "decay": "затухание отношений", "anchors": "рост экономики и мощи",
}


def drift(player: str, quarters: int, off=(), seed: int = 3) -> float:
    """Медианный сдвиг отношений с державами, в делениях шкалы."""
    s = Sim(player=player, seed=seed)
    s.off = set(off)
    peers = [c for c in s.world.tier("A") if c != player]
    start = {c: s.world.relation(player, c) for c in peers}
    for _ in range(quarters):
        s.tick()
    return statistics.median(
        abs(s.world.relation(player, c) - v) / BAND for c, v in start.items())


def average(player: str, quarters: int, off=()) -> float:
    return statistics.mean(drift(player, quarters, off, s) for s in SEEDS)


def main() -> None:
    q = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    player = "RUS"
    base = average(player, q)
    print(f"Фоновый дрейф за {q} кварталов без единого действия игрока")
    print(f"Полный мир: {base:.2f} деления\n")
    rows = []
    for src in SOURCES:
        without = average(player, q, (src,))
        rows.append((base - without, src, without))
    rows.sort(reverse=True)
    print(f"{'источник':<38}{'без него':>10}{'вклад':>10}")
    print("-" * 58)
    for delta, src, without in rows:
        print(f"  {NAMES[src]:<36}{without:>10.2f}{delta:>+10.2f}")
    print()
    top = rows[0]
    print(f"Больше всего даёт: {NAMES[top[1]]} — {top[0]:+.2f} деления.")
    print("Ориентир: фон должен быть заметно слабее одного действия игрока,")
    print("которое даёт около 1.0 деления сразу.")


if __name__ == "__main__":
    main()
