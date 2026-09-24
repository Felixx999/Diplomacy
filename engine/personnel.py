"""Кадры: министры и послы.

Отдельная сущность оправдана только если делает то, чего не делают
группы интересов. Здесь она делает две вещи, которых больше нет ни у
кого.

Министр исполняет. Между замыслом игрока и результатом лежит разброс, и
компетентный министр этот разброс сужает, а слабый расширяет. Курс
меняет игрок, но насколько точно он воплотится — зависит от того, кто
его проводит.

Посол открывает двери. Пригодность посла к конкретной стране зависит от
того, что там за посольство: торговый переговорщик бесполезен там, где
идёт спор о территории, а ястреб портит дело там, где нужно доверие.

Кандидаты порождаются процедурно из архетипов с фиксированным сидом,
поэтому один и тот же мир всегда даёт один и тот же кадровый резерв.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass

from . import deal, groups
from .state import DATA, World

# Какая обстановка в стране назначения кому подходит. Удалялась вместе с
# соседней функцией при вычистке мёртвого кода — третий случай, когда
# удаление блока по границам задевает лишнее.
CLIMATE = {
    "hostile": ("sovereignty", "territory", "nuclear", "sanctions", "arms"),
    "trade": ("tariffs", "energy", "aid", "maritime"),
    "friendly": ("alliance", "bases", "recognition"),
}


@dataclass
class Archetype:
    id: str
    name_ru: str
    competence: float
    loyalty: float
    branch: str
    suits: str
    note: str
    name_en: str = ""


@dataclass
class Look:
    """Внешность условной фигуры.

    Передаётся тоном кожи, причёской, головным убором и полом, а не
    чертами лица: наш силуэт намеренно без лица, чтобы в министре не
    узнавали конкретного политика, а изображать этничность формой лица
    в такой стилистике — прямая дорога к карикатуре.
    """
    tone: int
    hair: str
    female: bool


@dataclass
class Person:
    name: str            # каноническое имя: ключ личности, лица, сохранения
    archetype: Archetype
    competence: float
    loyalty: float
    country: str
    look: Look | None = None
    post: str = ""
    name_en: str = ""    # та же личность в латинской записи        # ветвь для министра, код страны для посла

    def title_in(self, lang: str = "ru") -> str:
        """Имя и архетип на выбранном языке."""
        nm = (self.name_en or self.name) if lang == "en" else self.name
        a = self.archetype
        ar = ((a.name_en or a.name_ru) if lang == "en" else a.name_ru)
        return f"{nm}, {ar}"

    @property
    def title(self) -> str:
        return self.title_in("ru")


def _load_archetypes() -> dict[str, Archetype]:
    out = {}
    with open(DATA / "archetypes.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["id"]] = Archetype(
                r["id"], r["name_ru"], float(r["competence"]),
                float(r["loyalty"]), r["branch"], r["suits"], r["note"],
                r.get("name_en", ""))
    return out


def _load_names() -> dict[str, dict[str, list[str]]]:
    out = {}
    with open(DATA / "names.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["code"]] = {
                "m": r["given_m"].split(";"), "f": r["given_f"].split(";"),
                "s": r["surnames"].split(";"),
                "m_en": (r.get("given_m_en") or r["given_m"]).split(";"),
                "f_en": (r.get("given_f_en") or r["given_f"]).split(";"),
                "s_en": (r.get("surnames_en") or r["surnames"]).split(";")}
    return out


# Тона кожи: шесть ступеней. Распределение по странам задаёт, какой тон
# встречается чаще, но диапазон в каждой стране полный — реальные
# кабинеты не однородны, и игра, где все министры на одно лицо,
# выглядит и скучно, и неправдоподобно.
TONES = ("#F2D6C0", "#E3BC9A", "#C99A6E", "#A87545", "#7E5230", "#553521")
TONE_MIX = {
    "north": (0, 0, 1, 1, 2, 3, 4), "west": (0, 1, 1, 2, 3, 4, 5),
    "east": (1, 1, 2, 2, 3, 4, 5), "south": (2, 3, 3, 4, 4, 5, 1),
    "gulf": (1, 2, 3, 3, 4, 5, 0), "isles": (0, 1, 1, 2, 3, 4, 5),
}
HAIR = ("short", "crop", "long", "bun", "cover", "bald")


ARCHETYPES = _load_archetypes()
NAMES = _load_names()


INITIALS = "АБВГДЕЖЗИКЛМНОПРСТ"
INITIALS_EN = "ABCDEFGHJKLMNPRST"


def pool(world: World, code: str, size: int = 24) -> list[Person]:
    """Кадровый резерв страны. Один сид — один и тот же резерв.

    Личность уникальна: фамилий в таблице меньше, чем людей, поэтому к
    повторяющейся фамилии добавляется инициал. Без этого назначения
    натыкались друг на друга — двенадцать министерств не заполнялись,
    а один человек оказывался послом сразу в двух столицах.
    """
    from .portrait import REGION
    rng = random.Random(f"{code}:pool")
    pool_names = NAMES.get(code) or {"m": ["Первый"], "f": ["Первая"],
                                     "s": ["Второй", "Третий"]}
    mix = TONE_MIX.get(REGION.get(code, "west"), TONE_MIX["west"])
    arch = list(ARCHETYPES.values())
    people = []
    used: set[str] = set()
    for i in range(size):
        a = arch[i % len(arch)]
        female = rng.random() < 0.38
        sex = "f" if female else "m"
        gi = rng.randrange(len(pool_names[sex]))
        given = pool_names[sex][gi]
        # Фамилия зависит и от места в круге, и от номера круга. При
        # равном числе фамилий и архетипов простой шаг давал взаимно
        # однозначное соответствие, и все ястребы страны оказывались
        # однофамильцами — сдвиг по кругу это разрывает.
        lap = i // len(arch)
        surname = pool_names["s"][(i * 3 + lap * 5) % len(pool_names["s"])]
        label = f"{given} {surname}"
        while label in used:
            gi = (gi + 1) % len(pool_names[sex])
            given = pool_names[sex][gi]
            label = f"{given} {surname}"
        used.add(label)
        # Латинская запись той же личности: индексы те же, поэтому
        # человек остаётся одним и тем же в обоих языках.
        si = (i * 3 + lap * 5) % len(pool_names["s_en"])
        label_en = f"{pool_names[sex + '_en'][gi % len(pool_names[sex + '_en'])]} " \
                   f"{pool_names['s_en'][si]}"
        look = Look(tone=mix[rng.randrange(len(mix))],
                    hair=rng.choice(HAIR[:5] if female else HAIR),
                    female=female)
        people.append(Person(
            name=label, name_en=label_en, look=look,
            archetype=a,
            competence=round(min(0.92, max(0.25,
                        a.competence + rng.uniform(-0.30, 0.16))), 2),
            loyalty=round(min(0.95, max(0.10,
                     a.loyalty + rng.uniform(-0.20, 0.20))), 2),
            country=code))
    return people


# --- министры ------------------------------------------------------------

def minister_fit(world: World, p: Person, post: str) -> tuple[float, str]:
    """Насколько человек подходит к министерству и почему."""
    base = p.competence
    if p.archetype.branch == post:
        return round(min(0.95, base + 0.10), 2), "профильный опыт"
    ruling = max(groups.blocs(world, p.country), key=lambda b: b.weight)
    if p.loyalty > 0.7:
        return round(base, 2), f"не профиль, но предан ({ruling.name_ru} не против)"
    return round(max(0.1, base - 0.20), 2), "не его область"


def appoint(world: World, code: str, post: str, p: Person) -> dict:
    """Назначить министра. Стоит влияния, действует сразу."""
    fit, why = minister_fit(world, p, post)
    world.ministers[(code, post)] = (p, fit)
    world.countries[code].political_capital -= 14.0
    return {"post": post, "who": p.title, "fit": fit, "why": why}


def minister(world: World, code: str, post: str) -> tuple[Person, float] | None:
    return world.ministers.get((code, post))


def execution_spread(world: World, code: str, post: str) -> float:
    """Разброс между замыслом и результатом, 0 — точно, 1 — как выйдет.

    Это и есть работа министра. Без назначенного министра разброс
    большой: поручать некому.
    """
    # Идеальных исполнителей не бывает: даже лучший министр оставляет
    # зазор между замыслом и результатом.
    m = minister(world, code, post)
    return 0.55 if not m else round(0.10 + 0.45 * (1.0 - m[1]), 2)


# --- послы ---------------------------------------------------------------

def climate(world: World, code: str, target: str) -> str:
    """Какая обстановка в этом посольстве: спор, торг или союз."""
    live = [t for t in deal.TYPES if deal.live(world, code, target, t)]
    for kind, types in CLIMATE.items():
        if any(t in types for t in live):
            if kind == "hostile" and world.relation(code, target) < 0.1:
                return "hostile"
            if kind == "trade":
                return "trade"
    return "friendly" if world.relation(code, target) > 0.3 else "trade"


def ambassador_fit(world: World, p: Person, target: str) -> tuple[float, str]:
    """Пригодность посла к конкретной стране."""
    # Формулировки построены без склонения названий стран: название
    # подставляется отдельной строкой, а не внутрь фразы. Иначе в демо
    # вылезает «с Россия идёт торг».
    cl = climate(world, p.country, target)
    if p.archetype.suits == cl:
        note = {"hostile": "там идёт спор — нужен именно такой",
                "trade": "там идёт торг, это его работа",
                "friendly": "там есть доверие, он его углубит"}[cl]
        return round(min(0.95, p.competence + 0.12), 2), note
    if cl == "hostile" and p.archetype.suits == "friendly":
        return round(max(0.15, p.competence - 0.30), 2), \
            "там обострение, мягкость выйдет боком"
    if cl == "friendly" and p.archetype.suits == "hostile":
        return round(max(0.15, p.competence - 0.25), 2), \
            "это союзник, ястреб здесь лишний"
    return round(max(0.15, p.competence - 0.12), 2), "справится, но без блеска"


def best_posting(world: World, code: str, target: str) -> tuple[Person, float, str]:
    """Кого из резерва стоит отправить в эту страну."""
    ranked = [(p, *ambassador_fit(world, p, target)) for p in pool(world, code)]
    ranked.sort(key=lambda x: -x[1])
    return ranked[0]


def send(world: World, code: str, target: str, p: Person) -> dict:
    fit, why = ambassador_fit(world, p, target)
    world.ambassadors[(code, target)] = (p, fit)
    world.countries[code].diplomatic_capital -= 10.0
    return {"to": world.countries[target].name_ru, "who": p.title,
            "fit": fit, "why": why}


def envoy_bonus(world: World, code: str, target: str) -> float:
    """Что даёт посол: дешевле разведка, точнее оценка чужого порога."""
    a = world.ambassadors.get((code, target))
    return 0.0 if not a else round(0.35 * a[1], 3)


# --- трения в кабинете ---------------------------------------------------

# Кто с кем не уживается. Не вкусовщина: конфликт возникает там, где два
# министерства тянут государство в разные стороны, а не там, где люди
# друг другу не нравятся.
RIVALS = {
    ("hawk", "diplomat"): "оборона требует жёсткости, дипломатия — уступок",
    ("hawk", "trader"): "военные расходы против открытой торговли",
    ("ideologue", "trader"): "идеология против выгоды",
    ("ideologue", "technocrat"): "принципы против расчёта",
    ("spymaster", "populist"): "закрытость против публичности",
    ("energy_boss", "technocrat"): "отраслевой интерес против бюджета",
    ("populist", "technocrat"): "обещания улице против арифметики",
}


def frictions(world: World, code: str) -> list[dict]:
    """Кто в правительстве тянет в разные стороны.

    Трение стоит влияния каждый ход: пока министры воюют, решения идут
    медленнее. Сильное трение попадает в повестку отдельным вопросом.
    """
    held = [(mid, p, fit) for (c, mid), (p, fit) in world.ministers.items()
            if c == code]
    out = []
    for i, (m1, p1, f1) in enumerate(held):
        for m2, p2, f2 in held[i + 1:]:
            a, b = p1.archetype.id, p2.archetype.id
            why = RIVALS.get((a, b)) or RIVALS.get((b, a))
            if not why:
                continue
            # ключ причины для перевода: пара архетипов в постоянном порядке
            pair = (a, b) if (a, b) in RIVALS else (b, a)
            key = f"{pair[0]}_{pair[1]}"
            # два сильных и уверенных спорят громче двух слабых
            force = round((f1 + f2) / 2 * (1.0 - abs(p1.loyalty - p2.loyalty)), 2)
            out.append({"a": m1, "b": m2, "who_a": p1.title, "who_b": p2.title,
                        "why": why, "key": key, "force": force})
    out.sort(key=lambda x: -x["force"])
    return out


def friction_cost(world: World, code: str) -> float:
    return round(sum(f["force"] for f in frictions(world, code)) * 1.6, 1)
