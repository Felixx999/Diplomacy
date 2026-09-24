"""Проверка на осмысленность.

Механика, чей эффект не способен сдвинуть полосу за разумное время,
декоративна — даже если считается верно. Игрок её не заметит, а значит
она не участвует в игре.

Проверка запускает каждую механику в чистом мире и смотрит, меняется ли
деление шкалы. Заодно ищет сырые числа, протёкшие в интерфейс.

    python3 tools/legibility.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import execution, groups, intel, legible, valves  # noqa: E402
from engine.channels import Action  # noqa: E402
from engine.sim import Sim  # noqa: E402

# Разумное время — три года. Ход равен месяцу, поэтому тридцать шесть.
# Константа осталась от квартальных времён и после перехода на месяцы
# молча превратила три года в один: проверка ужесточилась втрое, и
# эскалация, работающая медленнее торговли, перестала в неё укладываться.
MONTHS = 36


def probe(name: str, scale: str, setup, quarters: int = MONTHS,
          measure: str = "end") -> dict:
    """Запустить механику и посмотреть, сдвинулась ли полоса.

    `measure="end"` берёт конечное значение — так меряются механики,
    которые двигают величину и оставляют её сдвинутой.

    `measure="peak"` берёт наибольшее отклонение по ходу — так меряются
    механики, которые нарастают и разрешаются. Эскалация спора за три
    года поднимает накал до 0.85 и возвращает его к порогу покоя;
    замер по остатку показывал 0.43 деления и называл живую механику
    слабой, замер по пику — 1.48.
    """
    s = Sim(player="RUS", seed=3)
    before_val, step = setup(s)
    peak = before_val
    for _ in range(quarters):
        s.tick()
        if measure == "peak":
            v = step(s)
            if abs(v - before_val) > abs(peak - before_val):
                peak = v
    after_val = peak if measure == "peak" else step(s)
    lo, hi, names = legible.SCALES[scale]
    band = (hi - lo) / len(names)
    return {
        "name": name,
        "before": legible.read(scale, before_val),
        "after": legible.read(scale, after_val),
        "moved": legible.moved(scale, before_val, after_val),
        # Пересечь границу деления можно и случайно, оказавшись рядом с
        # ней. Сила эффекта в долях деления честнее: она не зависит от
        # того, где стояло исходное значение.
        "strength": abs(after_val - before_val) / band,
        "raw": (before_val, after_val),
    }


def build() -> list[dict]:
    out = []

    def security_deal(s):
        w = s.world
        before = w.threat("UKR", "RUS")
        execution.sign(w, "RUS", "UKR", "arms", 75, s.turn_no)
        return before, lambda s2: s2.world.threat("UKR", "RUS")
    out.append(probe("Меры доверия по соглашению", "threat", security_deal))

    def trade_deal(s):
        w = s.world
        before = w.relation("RUS", "IND")
        execution.sign(w, "RUS", "IND", "tariffs", 80, s.turn_no)
        return before, lambda s2: s2.world.relation("RUS", "IND")
    out.append(probe("Торговое соглашение", "relation", trade_deal))

    def promises(s):
        w = s.world
        before = w.trust("USA", "RUS")
        for _ in range(4):
            p = w.promise("RUS", "USA", "проверка")
            p.kept = True
        return before, lambda s2: s2.world.trust("USA", "RUS")
    out.append(probe("Четыре сдержанных обещания", "trust", promises, 1))

    def spying(s):
        w = s.world
        rng = random.Random(2)
        before = intel.level(w, "RUS", "USA")
        intel.invest(w, "RUS", "USA", 45, rng, s.turn_no)
        return before, lambda s2: intel.level(s2.world, "RUS", "USA")
    out.append(probe("Одно вложение в разведку", "intel", spying, 1))

    def asset_sale(s):
        w = s.world
        before = groups.mood(w, "RUS", "nationalists")
        opts = [o for o in valves.assets(w, "RUS") if o.kind == "asset"]
        if opts:
            valves.sell(w, "RUS", opts[0])
        return before, lambda s2: groups.mood(s2.world, "RUS", "nationalists")
    out.append(probe("Продажа актива", "mood", asset_sale, 1))

    def hostility(s):
        w = s.world
        before = w.relation("RUS", "DEU")
        from engine.channels import apply, propagate
        apply(w, propagate(w, Action("RUS", "DEU", "sanction", 0.9)))
        return before, lambda s2: s2.world.relation("RUS", "DEU")
    out.append(probe("Жёсткие санкции", "relation", hostility, 1))

    def escalate(s):
        w = s.world
        d = w.disputes["taiwan"]
        before = d.heat
        return before, lambda s2: s2.world.disputes["taiwan"].heat
    out.append(probe("Разгорание спора за три года", "threat", escalate,
                     measure="peak"))

    # Контроль меряется по медиане всех пар, а не по одной выбранной.
    # Прежняя версия брала пару Россия — Турция, которая оказалась самой
    # подвижной из девяноста трёх, и объявляла фон вчетверо сильнее, чем
    # он есть. Замер по одной паре может соврать в любую сторону.
    def idle(s):
        w = s.world
        peers = [c for c in w.countries if c != "RUS"]
        start = {c: w.relation("RUS", c) for c in peers}
        anchor = 0.0            # точка отсчёта фиксируется здесь, не потом

        def after(s2):
            shifts = sorted(abs(s2.world.relation("RUS", c) - v)
                            for c, v in start.items())
            return anchor + shifts[len(shifts) // 2]
        return anchor, after
    out.append(probe("Бездействие три года (контроль)", "relation", idle))

    return out


# Разметка SVG — не текст для игрока: толщина линии и координаты
# обязаны быть дробными. Проверка ищет числа в том, что читают.
GEOMETRY = ("stroke-width", "opacity", "cx=", "cy=", " r=", "x1=", "y1=",
            "text-anchor", "viewBox", "width:", "left:", "r.toFixed", "y + r")


def scan_interface() -> list[tuple[str, list[str]]]:
    """Сырые числа, протёкшие в текст интерфейса."""
    found = []
    for path in list((ROOT / "web").glob("*.html")) + list((ROOT / "web").glob("*.js")):
        hits = []
        for ln in path.read_text(encoding="utf-8").splitlines():
            if "toFixed" not in ln and "%" not in ln:
                continue
            if any(g in ln for g in GEOMETRY):
                continue
            if "toFixed" in ln:
                hits.append(ln.strip())
        if hits:
            found.append((path.name, hits[:8]))
    return found


def main() -> None:
    print("Проверка на осмысленность: двигает ли механика полосу\n")
    rows = build()
    width = max(len(r["name"]) for r in rows)
    invisible = []
    for r in rows:
        st = r["strength"]
        if st >= 0.9:
            mark = "уверенно"
        elif st >= 0.45:
            mark = "заметно"
        elif st >= 0.15:
            mark = "СЛАБО"
        else:
            mark = "НЕ ВИДНО"
        print(f"  {r['name']:<{width}}  {r['before'].label:>18} → "
              f"{r['after'].label:<18} {mark:<9} {st:.2f} деления")
        if st < 0.45 and "контроль" not in r["name"]:
            invisible.append(r)

    print()
    if invisible:
        print(f"Слабых или декоративных механик: {len(invisible)}")
        for r in invisible:
            print(f"  {r['name']}: {r['strength']:.2f} деления за отведённый "
                  f"срок — игрок такое пропустит")
    else:
        print("Все проверенные механики заметны игроку.")

    leaks = scan_interface()
    print()
    if leaks:
        print("Сырые числа в интерфейсе:")
        for name, hits in leaks:
            print(f"  {name}: {len(hits)} мест")
    else:
        print("Сырых чисел в интерфейсе не найдено.")


if __name__ == "__main__":
    main()
