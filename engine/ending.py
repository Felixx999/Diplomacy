"""Концовки.

Партия заканчивается четырьмя способами, и ни один из них не называется
проигрышем. Тон задан отдельным решением: игра соглашается с целью
игрока и показывает цену.

Оценки баллами нет намеренно. Вместо неё — расхождение: насколько мир,
который получился, отличается от того, в котором мы живём. Считается по
четырём осям, каждая берётся из состояния, а не назначается.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import economy, groups
from .state import World

END_YEAR = 2042
COLLAPSE_SUPPORT = 0.22      # ниже этого коалиция не держится
COLLAPSE_LEGITIMACY = 0.15


@dataclass
class Ending:
    kind: str            # срок | отставка | переворот | распад
    title: str
    body: str
    divergence: list[tuple[str, float, str]] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)

    def share(self) -> float:
        return round(sum(v for _, v, _ in self.divergence)
                     / max(len(self.divergence), 1), 3)


def check(world: World, code: str, turn: int) -> Ending | None:
    """Пора ли заканчивать. None — партия продолжается."""
    c = world.countries[code]
    support = sum(b.weight * groups.mood(world, code, b.id)
                  for b in groups.blocs(world, code))

    if world.year > END_YEAR:
        return finish(world, code, "срок",
                      "Срок истёк",
                      "Вы довели страну до 2042 года. Что из этого вышло — ниже.")
    if c.legitimacy <= COLLAPSE_LEGITIMACY:
        return finish(world, code, "переворот",
                      "Вас сместили",
                      "Легитимность исчерпана. Смена власти прошла без вашего "
                      "участия — и это тоже итог, а не поражение.")
    if support <= COLLAPSE_SUPPORT:
        return finish(world, code, "отставка",
                      "Коалиция рассыпалась",
                      "Поддержки не осталось ни у кого из тех, на ком держалось "
                      "правительство. Дальше вести страну было бы некому.")
    lost = [d for d in world.disputes.values()
            if d.claimant == code and d.settled_turn > 0
            and turn - d.settled_turn < 3]
    if lost and c.legitimacy < 0.3:
        return finish(world, code, "распад",
                      "Территория потеряна",
                      "Поражение в споре наложилось на слабую легитимность.")
    return None


# --- расхождение с нашей хронологией -------------------------------------

REAL_2042 = {
    # Ориентиры нашей хронологии на конец партии. Не предсказание, а
    # точка отсчёта: если мир игрока ушёл от неё, значит он что-то
    # изменил. Заменяется на прогон 2020–2026 при калибровке.
    "power_leader": "CHN",
    "blocs": {"USA": 7, "CHN": 4, "RUS": 3},
    "disputes_held": {"taiwan": "TWN", "kashmir": "IND", "westbank": "ISR",
                      "kuriles": "RUS", "cyprus": "TUR"},
}


def finish(world: World, code: str, kind: str, title: str, body: str) -> Ending:
    div: list[tuple[str, float, str]] = []
    hi: list[str] = []

    leader = max(world.countries.values(), key=lambda x: x.power()).code
    same = leader == REAL_2042["power_leader"]
    div.append(("расстановка сил", 0.0 if same else 1.0,
                f"сильнейшая держава: {world.countries[leader].name_ru}"))
    if not same:
        hi.append(f"Мировым лидером стал не тот, кто в нашей хронологии, "
                  f"а {world.countries[leader].name_ru}.")

    moved = 0
    for did, holder in REAL_2042["disputes_held"].items():
        d = world.disputes.get(did)
        if d and d.controller != holder:
            moved += 1
            hi.append(f"{d.name_ru}: контроль перешёл к "
                      f"{world.countries[d.controller].name_ru}"
                      if d.controller in world.countries else
                      f"{d.name_ru}: контроль сменился")
    div.append(("спорные территории",
                round(moved / len(REAL_2042["disputes_held"]), 3),
                f"сменили хозяина: {moved} из {len(REAL_2042['disputes_held'])}"))

    blocs = {}
    for c in world.countries.values():
        if c.patron:
            blocs[c.patron] = blocs.get(c.patron, 0) + 1
    drift = 0.0
    for patron, was in REAL_2042["blocs"].items():
        now = blocs.get(patron, 0)
        drift += abs(now - was) / max(was, 1)
    div.append(("блоки", round(min(1.0, drift / len(REAL_2042["blocs"])), 3),
                "; ".join(f"{p}: {blocs.get(p, 0)}" for p in REAL_2042["blocs"])))
    for patron, was in REAL_2042["blocs"].items():
        now = blocs.get(patron, 0)
        if abs(now - was) >= 2:
            hi.append(f"Блок {world.countries[patron].name_ru}: "
                      f"{was} клиентов было, {now} стало.")

    me = world.countries[code]
    econ = economy.profile(world, code)
    div.append(("своя страна", 0.0,
                f"ВВП {econ['gdp']} млрд, курс {econ['currency']}, "
                f"{econ['dominant']} в вывозе"))

    return Ending(kind, title, body, div, hi[:5])


# --- сверка с реальностью ------------------------------------------------

def timeline_note(world, turn: int) -> dict | None:
    """Короткая вставка о том, что происходило в нашей хронологии.

    Только факты, без морали. Игра не поучает, а даёт точку отсчёта:
    расхождение игрок замечает сам. Вставка необязательная и появляется
    редко, иначе превращается в назойливую справку.
    """
    import csv
    from .state import DATA
    key = (world.year, world.quarter)
    if not hasattr(timeline_note, "_rows"):
        rows = {}
        with open(DATA / "timeline.csv", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows[(int(r["year"]), int(r["month"]))] = {
                    "text": r["text"], "tags": r["tags"].split(";")}
        timeline_note._rows = rows
    row = timeline_note._rows.get(key)
    if not row:
        return None
    return {"date": world.date(), "text": row["text"], "tags": row["tags"]}
