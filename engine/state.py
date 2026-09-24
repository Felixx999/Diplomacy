"""Состояние мира: страны, пары, спорные территории.

Всё здесь — обычные числа. Никакой генерации, никакой языковой модели.
Одинаковый сид даёт одинаковую партию.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def _f(row: dict, key: str, default: float = 0.0) -> float:
    raw = (row.get(key) or "").strip()
    return float(raw) if raw else default


@dataclass
class Country:
    code: str
    name_ru: str
    name_en: str
    lat: float
    lon: float
    gdp_bn: float
    pop_mn: float
    milex_bn: float
    energy_mtoe: float = 0.0   # потребление первичной энергии
    steel_mt: float = 0.0      # выплавка стали, промышленный компонент
    troops_k: float = 0.0      # численность вооружённых сил, тысяч
    cinc: float = 0.0          # совокупная мощь, считается в engine/power.py
    cinc_ref: float = 0.0      # справочное значение для сверки, не участвует
    vdem_liberal: float = 0.0  # 0..1, качество либеральной демократии
    ideal_point: float = 0.0   # -3..+3, позиция по голосованиям в ГА ООН
    nuclear: int = 0
    regime: str = "hybrid"
    playable: int = 0
    tier: str = "A"       # A — полная модель, B — свёрнутая
    patron: str = ""      # чей курс страна в основном повторяет
    autonomy: float = 1.0  # 0 — полностью следует патрону, 1 — сама по себе

    political_capital: float = 100.0    # внутренний ресурс
    diplomatic_capital: float = 100.0   # внешний ресурс
    legitimacy: float = 0.6             # запас прочности режима, 0..1
    growth_expect: float = 0.005        # к какому росту страна привыкла

    def power(self) -> float:
        """Совокупная мощь. Отдельно от cinc, чтобы менялась по ходу партии."""
        return self.cinc


@dataclass
class Dyad:
    """Пара стран.

    Три величины разной природы, а не одно число. Выравнивание —
    симметричный запас, меняется медленно. Угроза — направленная
    память о враждебных действиях, поверх структурной части. Доверие
    здесь не хранится вообще: оно считается из реестра обещаний.
    """
    a: str
    b: str
    alliance: str = "none"      # none | nonaggression | entente | defense
    alignment: float = 0.0      # -1..+1, симметрично: совпадение интересов
    threat_ab: float = 0.0      # 0..1, сколько a боится b сверх структурного
    threat_ba: float = 0.0
    trade_dep_a: float = 0.0    # доля b во внешней торговле a
    trade_dep_b: float = 0.0
    contiguous: int = 0

    ALLIANCE_WEIGHT = {"none": 0.0, "nonaggression": 0.2, "entente": 0.5, "defense": 1.0}

    def obligation(self) -> float:
        return self.ALLIANCE_WEIGHT.get(self.alliance, 0.0)

    def threat_memory(self, of: str) -> float:
        """Накопленная тревога страны `of` относительно партнёра."""
        return self.threat_ab if self.a == of else self.threat_ba

    REASSURANCE_FLOOR = -0.60   # насколько меры доверия могут увести ниже нуля

    def add_threat(self, of: str, delta: float) -> None:
        """Память угрозы может уходить в минус.

        Ноль снизу означал бы, что тревога умеет только накапливаться, и
        соглашения по безопасности не давали бы ничего там, где памяти
        ещё нет. Отрицательная память — это меры доверия: инспекции,
        демилитаризованные зоны, взаимные уведомления. Они покупают
        снижение угрозы ниже структурного уровня.
        """
        cur = max(self.REASSURANCE_FLOOR, min(1.0, self.threat_memory(of) + delta))
        if self.a == of:
            self.threat_ab = cur
        else:
            self.threat_ba = cur


@dataclass
class Promise:
    """Запись в реестре обещаний. Основание доверия."""
    debtor: str      # кто обещал
    creditor: str    # кому
    subject: str
    turn: str
    due: int = 0               # ход, на котором наступает срок
    cost: float = 12.0         # во что обходится исполнение
    kept: bool | None = None   # None пока срок не наступил


@dataclass
class Dispute:
    id: str
    name_ru: str
    controller: str
    claimant: str
    recognition_share: float   # доля стран мира, признающих претензию истца
    salience_controller: float
    salience_claimant: float
    heat: float                # 0..1, текущий накал
    type: str
    issue_type: str = "territory"
    settled_turn: int = -99   # когда спор в последний раз разрешался
    name_en: str = ""


class World:
    """Контейнер состояния. Пары хранятся по канонически отсортированному ключу."""

    def __init__(self, year: int = 2026, quarter: int = 1):
        self.year = year
        self.quarter = quarter
        self.countries: dict[str, Country] = {}
        self.dyads: dict[tuple[str, str], Dyad] = {}
        self.disputes: dict[str, Dispute] = {}
        self.promises: list[Promise] = []
        self.intel: dict[tuple[str, str], dict] = {}
        self.moods: dict[tuple[str, str], float] = {}
        self.deliveries: list = []   # действующие соглашения в поставке
        self.recent_crises: list = []   # события эскалации прошлого хода
        self.agenda_seen: dict[str, tuple[int, float]] = {}
        self.agenda_prev: dict[str, float] = {}
        self.ministers: dict[tuple[str, str], tuple] = {}
        self.directions: dict[tuple[str, str], float] = {}
        self.ambassadors: dict[tuple[str, str], tuple] = {}
        self.loans: list = []   # непогашенные займы политического капитала
        self.policies: dict[tuple[str, str], float] = {}
        self.government: dict[str, str] = {}
        self.next_vote: dict[str, int] = {}
        self.log: list[str] = []

    # --- доступ ---

    @staticmethod
    def key(a: str, b: str) -> tuple[str, str]:
        return (a, b) if a < b else (b, a)

    def dyad(self, a: str, b: str) -> Dyad:
        return self.dyads[self.key(a, b)]

    # --- три величины и их свёртка ---

    def alignment(self, a: str, b: str) -> float:
        return self.dyad(a, b).alignment

    def trust(self, a: str, b: str) -> float:
        """Насколько a верит обещаниям b. Направленно, 0..1.

        Без истории — ровно половина. Нарушенное обещание весит вдвое с
        лишним больше сдержанного: репутация теряется быстрее, чем
        зарабатывается. Логистика не даёт величине упереться в край.
        """
        score = 0.0
        for p in self.promises:
            if p.debtor == b and p.creditor == a and p.kept is not None:
                score += 1.0 if p.kept else -2.5
        return 1.0 / (1.0 + math.exp(-score / 3.0))

    def threat(self, a: str, b: str) -> float:
        """Насколько a чувствует угрозу от b. Направленно, 0..1.

        Структурная часть возникает сама, без чьего-либо злого умысла:
        соседство с более сильным уже создаёт тревогу. Поверх неё
        ложится память о конкретных враждебных действиях.
        """
        d = self.dyad(a, b)
        ca, cb = self.countries[a], self.countries[b]
        ratio = cb.power() / max(ca.power() + cb.power(), 1e-9)
        structural = max(0.0, (ratio - 0.5) * 2.0) * (0.35 + 0.65 * d.contiguous)
        if cb.nuclear and not ca.nuclear:
            structural += 0.12
        for disp in self.disputes.values():
            if disp.claimant == b and disp.controller == a:
                structural += 0.30 * disp.salience_claimant
        return max(0.0, min(1.0, structural + d.threat_memory(a)))

    def relation(self, a: str, b: str) -> float:
        """Свёртка для интерфейса и быстрых оценок. Несимметрична.

        Выравнивание симметрично, угроза и доверие — нет, поэтому
        итоговое отношение США к Китаю не равно отношению Китая к США.
        """
        v = (self.alignment(a, b)
             - 0.45 * self.threat(a, b)
             + 0.20 * (2.0 * self.trust(a, b) - 1.0))
        return max(-1.0, min(1.0, v))

    def promise(self, debtor: str, creditor: str, subject: str,
                due: int = 0, cost: float = 12.0) -> Promise:
        p = Promise(debtor, creditor, subject, self.date(), due, cost)
        self.promises.append(p)
        return p

    def trade_dep(self, a: str, b: str) -> float:
        """Насколько a зависит от b. Несимметрично."""
        d = self.dyad(a, b)
        return d.trade_dep_a if d.a == a else d.trade_dep_b

    def tier(self, t: str) -> list[str]:
        return [c.code for c in self.countries.values() if c.tier == t]

    def others(self, code: str) -> list[str]:
        return [c for c in self.countries if c != code]

    MONTHS = ("янв", "фев", "мар", "апр", "май", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек")

    def date(self) -> str:
        return f"{self.MONTHS[self.quarter - 1]} {self.year}"

    def advance(self) -> None:
        """Ход равен месяцу. Поле quarter хранит номер месяца, 1..12."""
        self.quarter += 1
        if self.quarter > 12:
            self.quarter = 1
            self.year += 1


def haversine(a: Country, b: Country) -> float:
    """Расстояние между столицами в тысячах километров."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h)) / 1000.0


def gravity_trade(world: World) -> dict[tuple[str, str], float]:
    """Гравитационная модель: торговля растёт с ВВП партнёра и падает с расстоянием.

    Упрощение, которое надо помнить: доли нормируются внутри двенадцати
    смоделированных стран, остальной мир в знаменатель не входит. Для
    относительных сравнений этого достаточно, для абсолютных — нет.
    Заменяется реальными данными UN Comtrade при калибровке.
    """
    raw: dict[str, dict[str, float]] = {}
    for a in world.countries.values():
        raw[a.code] = {}
        for b in world.countries.values():
            if a.code == b.code:
                continue
            dist = max(haversine(a, b), 0.5)
            raw[a.code][b.code] = b.gdp_bn / (dist ** 0.9)

    out: dict[tuple[str, str], float] = {}
    for code, partners in raw.items():
        total = sum(partners.values()) or 1.0
        for other, v in partners.items():
            out[(code, other)] = round(v / total, 4)
    return out


def load(year: int = 2026, quarter: int = 1) -> World:
    world = World(year, quarter)

    with open(DATA / "countries.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            world.countries[row["code"]] = Country(
                code=row["code"],
                name_ru=row["name_ru"],
                name_en=row["name_en"],
                lat=_f(row, "lat"),
                lon=_f(row, "lon"),
                gdp_bn=_f(row, "gdp_bn"),
                pop_mn=_f(row, "pop_mn"),
                milex_bn=_f(row, "milex_bn"),
                energy_mtoe=_f(row, "energy_mtoe"),
                steel_mt=_f(row, "steel_mt"),
                troops_k=_f(row, "troops_k"),
                cinc_ref=_f(row, "cinc_ref"),
                vdem_liberal=_f(row, "vdem_liberal"),
                ideal_point=_f(row, "ideal_point"),
                nuclear=int(_f(row, "nuclear")),
                regime=row["regime"],
                playable=int(_f(row, "playable")),
                tier=(row.get("tier") or "A").strip(),
                patron=(row.get("patron") or "").strip(),
                autonomy=_f(row, "autonomy", 1.0),
            )

    # все пары получают значения по умолчанию из гравитационной модели
    grav = gravity_trade(world)
    codes = sorted(world.countries)
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            world.dyads[(a, b)] = Dyad(
                a=a, b=b,
                trade_dep_a=grav[(a, b)],
                trade_dep_b=grav[(b, a)],
            )

    # ручные значения перекрывают расчётные
    with open(DATA / "dyads.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            d = world.dyad(row["a"], row["b"])
            d.alliance = row["alliance"] or "none"
            d.alignment = _f(row, "alignment")
            d.contiguous = int(_f(row, "contiguous"))
            # столбец source — пометка происхождения, движком не читается
            dep_a, dep_b = _f(row, "trade_dep_a", -1), _f(row, "trade_dep_b", -1)
            forward = d.a == row["a"]
            if dep_a >= 0:
                setattr(d, "trade_dep_a" if forward else "trade_dep_b", dep_a)
            if dep_b >= 0:
                setattr(d, "trade_dep_b" if forward else "trade_dep_a", dep_b)

    from .power import recompute
    recompute(world)   # мощь считается одной формулой и на старте, и в ходе

    with open(DATA / "disputes.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            world.disputes[row["id"]] = Dispute(
                id=row["id"],
                name_ru=row["name_ru"],
                controller=row["controller"],
                claimant=row["claimant"],
                recognition_share=_f(row, "recognition_share"),
                salience_controller=_f(row, "salience_controller"),
                salience_claimant=_f(row, "salience_claimant"),
                heat=_f(row, "heat"),
                type=row["type"],
                issue_type=row.get("issue_type", "territory"),
                name_en=row.get("name_en", ""),
            )

    return world
