"""Внутренний уровень: группы интересов и ратификация.

Потолок ратификации здесь не вычисляется формулой, а находится. Для
каждого уровня уступки считается, кто ещё поддерживает правительство;
потолок — последний уровень, на котором коалиция удерживает
большинство.

Из этого сразу следует то, ради чего затевался крючок: известно не
только что сделка не прошла, но и какая именно группа её похоронила.

Веса групп выведены из атрибутов страны, а не заданы таблицей на
триста восемьдесят четыре строки. Позиции групп по типам вопросов
вывести неоткуда — это содержание, оно записано явно в
`data/issue_positions.csv`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field

from .state import DATA, World

# Порог поддержки для ратификации. В автократии победная коалиция
# меньше: достаточно удержать силовиков и элиту, а не большинство
# населения. Это и делает уступки для авторитарных режимов проще.
THRESHOLD = {"democracy": 0.50, "hybrid": 0.42, "autocracy": 0.34}

LOYALTY = 0.35        # насколько настроение группы удерживает её от разрыва
REGIME_PRESSURE = 0.28  # добавка лояльности от несвободы: несогласие дороже


@dataclass
class Group:
    id: str
    name_ru: str
    base: float
    k_autoc: float
    k_milex: float
    k_gdppc: float
    k_industry: float
    k_energy: float
    k_troops: float
    econ_sens: float = 0.6
    mass: float = 0.8
    note: str = ""
    name_en: str = ""


def electoral_weight(world: World, code: str, b) -> float:
    """Вес группы на выборах, а не в ратификации.

    Влияние в парламенте и доля голосов — разные вещи. У военных
    огромный вес при ратификации и малая доля избирателей; в автократии
    разница исчезает, потому что голосуют не все.
    """
    autoc = 1.0 - world.countries[code].vdem_liberal
    m = GROUPS[b.id].mass
    return b.weight * (m + (1.0 - m) * autoc)


@dataclass
class Bloc:
    """Группа в конкретной стране: вес, настроение, позиция по вопросу."""
    id: str
    name_ru: str
    weight: float
    mood: float
    stance: float = 0.0

    def goodwill(self, autocracy: float) -> float:
        return LOYALTY * self.mood + REGIME_PRESSURE * autocracy

    def breaks_at(self, autocracy: float) -> float:
        """Уровень уступки, на котором группа уходит в оппозицию.

        Больше ста означает, что группа не уйдёт ни при каком уровне.
        """
        if self.stance >= 0:
            return 1e9
        return min(1e9, -self.goodwill(autocracy) / self.stance * 100.0)


def _load_groups() -> dict[str, Group]:
    out = {}
    with open(DATA / "groups.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["id"]] = Group(
                id=r["id"], name_ru=r["name_ru"], base=float(r["base"]),
                k_autoc=float(r["k_autoc"]), k_milex=float(r["k_milex"]),
                k_gdppc=float(r["k_gdppc"]), k_industry=float(r["k_industry"]),
                k_energy=float(r["k_energy"]), k_troops=float(r["k_troops"]),
                econ_sens=float(r.get("econ_sens", 0.6)),
                mass=float(r.get("mass", 0.8)), note=r["note"], name_en=r.get("name_en", ""))
    return out


def _load_positions() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    with open(DATA / "issue_positions.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["issue_type"], {})[r["group"]] = float(r["stance"])
    return out


GROUPS = _load_groups()
POSITIONS = _load_positions()

MOOD_BASE = 0.55       # к чему настроение сползает само по себе
MOOD_PULL = 0.01833      # скорость возврата к базе за квартал
GROWTH_NORM = 0.005    # стартовое ожидание, дальше подстраивается
EXPECT_ADAPT = 0.015   # скорость привыкания к своему темпу роста


def mood(world: World, country: str, group: str) -> float:
    return world.moods.get((country, group), 0.60)


def set_mood(world: World, country: str, group: str, value: float) -> None:
    world.moods[(country, group)] = max(0.02, min(0.98, value))


def nudge(world: World, country: str, group: str, delta: float) -> None:
    set_mood(world, country, group, mood(world, country, group) + delta)


def drift(world: World, growth: dict[str, float],
          policy_pressure: dict[str, dict[str, float]] | None = None) -> None:
    """Квартальный сдвиг настроений: экономика и возврат к базе.

    Настроение — не украшение. Оно входит в терпимость группы, значит
    прямо двигает потолок ратификации. Пока оно было константой, одни и
    те же группы блокировали одно и то же всю партию.

    Ожидания подстраиваются под собственный темп страны: привыкший к
    шести процентам недоволен четырьмя. Без этого постоянный рост за
    семнадцать лет загонял настроения в потолок шкалы, и они снова
    становились константой, просто разной по странам.
    """
    for code in world.countries:
        c = world.countries[code]
        g = growth.get(code, GROWTH_NORM)
        econ = (g - c.growth_expect) * 4.0
        c.growth_expect += (g - c.growth_expect) * EXPECT_ADAPT
        press = (policy_pressure or {}).get(code, {})
        for grp in GROUPS.values():
            cur = mood(world, code, grp.id)
            cur += (MOOD_BASE - cur) * MOOD_PULL
            cur += econ * grp.econ_sens
            cur += press.get(grp.id, 0.0)
            set_mood(world, code, grp.id, cur)


def concession_backlash(world: World, code: str, issue_type: str,
                        level: float) -> list[tuple[str, float]]:
    """Последствия проведённой уступки для тех, кто был против.

    Здесь замыкается обратная связь двухуровневой игры: сделка проходит,
    противники беднеют настроением, и в следующий раз потолок по этому
    вопросу ниже. Уступки покупаются не только капиталом, но и будущей
    гибкостью.
    """
    out = []
    for b in blocs(world, code, issue_type):
        if abs(b.stance) < 0.05:
            continue
        d = b.stance * (level / 100.0) * 0.16
        nudge(world, code, b.id, d)
        out.append((b.id, round(d, 4)))
    return out


def _attributes(world: World, code: str) -> dict[str, float]:
    """Нормированные признаки страны, на которых стоят веса групп."""
    c = world.countries[code]
    gdppc = c.gdp_bn / max(c.pop_mn, 0.1)          # тысяч долларов на человека
    return {
        "autoc": 1.0 - c.vdem_liberal,
        "milex": min(1.0, (c.milex_bn / max(c.gdp_bn, 1.0)) * 25.0),
        "gdppc": min(1.0, gdppc / 60.0),
        "industry": min(1.0, (c.steel_mt / max(c.gdp_bn, 1.0)) * 25.0),
        "energy": min(1.0, (c.energy_mtoe / max(c.gdp_bn, 1.0)) * 4.0),
        "troops": min(1.0, (c.troops_k / max(c.pop_mn, 0.1)) * 0.12),
    }


def blocs(world: World, code: str, issue_type: str | None = None) -> list[Bloc]:
    """Группы страны с весами и позициями по конкретному вопросу."""
    a = _attributes(world, code)
    stances = POSITIONS.get(issue_type or "", {})
    raw: list[Bloc] = []
    for g in GROUPS.values():
        w = (g.base
             + g.k_autoc * a["autoc"] + g.k_milex * a["milex"]
             + g.k_gdppc * a["gdppc"] + g.k_industry * a["industry"]
             + g.k_energy * a["energy"] + g.k_troops * a["troops"])
        raw.append(Bloc(g.id, g.name_ru, max(0.01, w),
                        mood(world, code, g.id), stances.get(g.id, 0.0)))
    total = sum(b.weight for b in raw)
    for b in raw:
        b.weight = round(b.weight / total, 4)
    return raw


@dataclass
class Ratification:
    ceiling: float
    threshold: float
    pivotal: str | None          # группа, чей уход обрушил коалицию
    pivotal_id: str | None
    support_at_zero: float
    order: list[tuple[str, float, float]] = field(default_factory=list)

    def why(self) -> str:
        if self.ceiling >= 99.9:
            return "внутренних препятствий нет: уступку некому блокировать"
        if self.ceiling <= 0.0:
            return (f"коалиция рассыпается сразу: поддержка {self.support_at_zero:.0%} "
                    f"при пороге {self.threshold:.0%}")
        return (f"выше {self.ceiling:.0f} не проходит: {self.pivotal} уходят в "
                f"оппозицию, и коалиция теряет большинство")


def ratify(world: World, code: str, issue_type: str,
           capital_bonus: float = 0.0) -> Ratification:
    """Найти потолок ратификации перебором уровней уступки.

    Группы уходят в оппозицию по очереди, в порядке своей терпимости.
    Потолок — уровень непосредственно перед тем, как уход очередной
    группы опускает поддержку ниже порога.
    """
    c = world.countries[code]
    # Политический капитал не двигает потолок напрямую — он повышает
    # терпимость групп. Правительство с запасом капитала выкручивает
    # руки, а не переписывает арифметику голосов.
    autocracy = min(1.0, (1.0 - c.vdem_liberal) + capital_bonus)
    bs = blocs(world, code, issue_type)
    thr = THRESHOLD.get(c.regime, 0.45)

    # Голос имеют те, кому вопрос небезразличен. Равнодушная группа не
    # засчитывается в сторонники: иначе, чтобы обрушить коалицию,
    # уйти в оппозицию должна была бы половина всей страны, и потолок
    # никогда не связывал.
    engaged = sum(b.weight for b in bs if b.stance != 0.0)
    if engaged < 1e-6:
        return Ratification(100.0, 0.0, None, None, 1.0, [])
    # Недовольный сторонник — вялый сторонник. Правительство с
    # рухнувшими рейтингами не проводит даже то, за что все «за»:
    # поддержка есть, а нести её к урнам некому.
    backing = sum(b.weight * (0.40 + 0.60 * b.mood)
                  for b in bs if b.stance > 0)
    passive = sum(b.weight * (0.40 + 0.60 * b.mood)
                  for b in bs if b.stance < 0)
    support = (backing + passive) / engaged if engaged else 1.0
    order = sorted(((b.breaks_at(autocracy), b) for b in bs if b.stance < 0),
                   key=lambda t: t[0])

    trace: list[tuple[str, float, float]] = []
    ceiling = 100.0
    pivotal = pivotal_id = None
    running = support
    for level, b in order:
        if level > 100.0:
            break
        share = b.weight * (0.40 + 0.60 * b.mood) / engaged
        trace.append((b.name_ru, round(level, 1), round(share, 3)))
        running -= share
        if running < thr:
            ceiling = max(0.0, level)
            pivotal, pivotal_id = b.name_ru, b.id
            break

    return Ratification(round(ceiling, 1), round(thr, 3), pivotal, pivotal_id,
                        round(support, 3), trace)
