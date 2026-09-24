"""Двухуровневая игра: сделка должна одновременно устроить партнёра
и пройти внутреннюю ратификацию.

Шкала вопроса — 0..100, где 0 это «уступающая сторона не уступает
ничего», 100 это «отдаёт всё». Уступающий может ратифицировать не
больше некоторого потолка, принимающий не примет меньше некоторого
порога. Сделка существует, только если между ними есть зазор.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field

from . import groups
from .state import DATA, World

@dataclass
class IssueType:
    """Физические свойства предмета торга.

    Сложность вопроса не задаётся вручную — она выводится из делимости
    и обратимости. Делимость определяет, существуют ли вообще законные
    точки внутри зоны согласия. Обратимость связывает вопрос с доверием.
    """
    id: str
    name_ru: str
    divisibility: float      # 0 — только да или нет, 1 — режется как угодно
    reversibility: float     # 0 — навсегда, 1 — отменяется следующим ходом
    ratify_difficulty: float  # множитель к болезненности внутри страны
    channel: str             # каким каналом расходится исполнение сделки
    horizon_q: int           # кварталов до полного эффекта
    opposes_giver: str       # группы, которые будут против (для фазы 2)
    stake_source: str = "trade"   # откуда берётся повод для переговоров
    name_en: str = ""

    def steps(self) -> int:
        """На сколько частей режется вопрос. Единица — неделимый.

        Зависимость квадратичная, а не линейная. При линейной полностью
        делимый тариф резался шагом в пять пунктов и вёл себя как
        ступенчатый: узкая зона согласия не содержала ни одной законной
        точки. Найдено проверкой, см. Р-12.
        """
        return max(1, round(self.divisibility ** 2 * 100))

    def grid(self) -> list[float]:
        """Все юридически возможные исходы по шкале 0..100."""
        n = self.steps()
        return [round(i * 100.0 / n, 2) for i in range(n + 1)]


def load_issue_types() -> dict[str, IssueType]:
    out = {}
    with open(DATA / "issue_types.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["id"]] = IssueType(
                id=r["id"], name_ru=r["name_ru"],
                divisibility=float(r["divisibility"]),
                reversibility=float(r["reversibility"]),
                ratify_difficulty=float(r["ratify_difficulty"]),
                channel=r["channel"], horizon_q=int(r["horizon_q"]),
                opposes_giver=r["opposes_giver"],
                stake_source=r.get("stake_source", "trade"),
                name_en=r.get("name_en", ""),
            )
    return out


TYPES = load_issue_types()


@dataclass
class Issue:
    id: str
    name_ru: str
    giver: str          # кто уступает
    receiver: str       # кто получает
    salience_giver: float = 0.5     # насколько вопрос болезнен внутри страны-донора
    salience_receiver: float = 0.5
    dispute_id: str | None = None
    type_id: str = "tariffs"

    def kind(self) -> IssueType:
        return TYPES[self.type_id]


@dataclass
class Commitment:
    """Публичное обещание. Сужает собственный диапазон, но повышает доверие."""
    country: str
    issue_id: str
    ceiling: float       # публично заявленный предел уступки
    turn: str
    broken: bool = False


@dataclass
class Range:
    lo: float
    hi: float
    parts: list[tuple[str, float]] = field(default_factory=list)

    def width(self) -> float:
        return max(0.0, self.hi - self.lo)


def ratification_ceiling(world: World, issue: Issue,
                         commitments: list[Commitment] | None = None) -> Range:
    """Верхняя граница того, что уступающая сторона сможет провести дома.

    Основание — состояние групп интересов (`engine/groups.py`). Здесь
    только поправки, относящиеся к конкретной сделке: острота вопроса,
    необратимость при нехватке доверия, публично данное слово.
    """
    c = world.countries[issue.giver]
    parts: list[tuple[str, float]] = []

    # Потолок не вычисляется формулой, а находится: группы уходят в
    # оппозицию по очереди, и потолок — последний уровень, на котором
    # коалиция держит большинство.
    bonus = max(0.0, (c.political_capital - 100.0) / 100.0) * 0.25
    r = groups.ratify(world, issue.giver, issue.type_id, bonus)
    v = r.ceiling
    parts.append(("потолок по группам интересов", v))
    if r.pivotal:
        parts.append((f"ломает коалицию: {r.pivotal.lower()}", 0.0))

    kind = issue.kind()
    pain = -issue.salience_giver * 40.0 * kind.ratify_difficulty
    v += pain
    parts.append((f"болезненность вопроса ({kind.name_ru.lower()})", pain))

    # необратимое отдавать страшнее, если партнёру не верят: отыграть
    # будет нечем. При полном доверии штраф исчезает.
    irrev = -(1.0 - kind.reversibility) * (1.0 - world.trust(issue.giver, issue.receiver)) * 34.0
    v += irrev
    parts.append(("необратимость при нехватке доверия", irrev))

    for com in (commitments or []):
        if com.country == issue.giver and com.issue_id == issue.id and not com.broken:
            cost = min(0.0, com.ceiling - v)
            if cost < 0:
                v = com.ceiling
                parts.append(("публичное обещание связывает руки", cost))

    v = max(0.0, min(100.0, v))
    return Range(0.0, v, parts)


def acceptance_floor(world: World, issue: Issue) -> Range:
    """Нижняя граница того, что принимающая сторона согласится взять."""
    r = world.countries[issue.receiver]
    g = world.countries[issue.giver]
    parts: list[tuple[str, float]] = []

    v = 30.0
    parts.append(("базовый порог", v))

    ratio = r.power() / max(r.power() + g.power(), 1e-6)
    adv = (ratio - 0.5) * 60.0
    v += adv
    parts.append(("соотношение сил", adv))

    sal = issue.salience_receiver * 20.0
    v += sal
    parts.append(("значимость вопроса для получателя", sal))

    dep = world.trade_dep(issue.receiver, issue.giver) * 60.0
    v -= dep
    parts.append(("зависимость получателя от донора", -dep))

    align = world.alignment(issue.giver, issue.receiver) * 10.0
    v -= align
    parts.append(("выравнивание интересов", -align))

    # доверие и угроза тянут в разные стороны: тому, кому верят,
    # уступают охотнее, того, кого боятся, стараются связать жёстче
    tr = (world.trust(issue.receiver, issue.giver) - 0.5) * 22.0
    v -= tr
    parts.append(("доверие к обещаниям донора", -tr))

    thr = world.threat(issue.receiver, issue.giver) * 14.0
    v += thr
    parts.append(("воспринимаемая угроза от донора", thr))

    # обратимую уступку могут забрать завтра, поэтому её требуют больше
    rev = issue.kind().reversibility * 13.0
    v += rev
    parts.append(("уступку легко отыграть назад", rev))

    v = max(0.0, min(100.0, v))
    return Range(v, 100.0, parts)


def acceptance_with_aspiration(world: World, issue: Issue,
                               ceiling: Range) -> Range:
    """Порог принятия с учётом того, сколько получатель рассчитывает взять.

    Резервная цена — минимум, ниже которого он встанет из-за стола.
    Притязание — сколько он попросит, глядя на оценку чужого потолка.
    Требует он большего из двух, и именно поэтому зона согласия узка:
    обе стороны давят навстречу друг другу.
    """
    base = acceptance_floor(world, issue)
    asp, note = aspiration(world, issue, ceiling)
    if asp > base.lo:
        base.parts.append((f"притязание: {note}", asp - base.lo))
        base.lo = min(100.0, asp)
    return base


def zopa(ceiling: Range, floor: Range) -> tuple[float, float] | None:
    """Зона возможного соглашения как интервал. None — торг провалился."""
    lo, hi = floor.lo, ceiling.hi
    return (lo, hi) if hi >= lo else None


def feasible(issue: Issue, ceiling: Range, floor: Range) -> list[float]:
    """Законные исходы: точки сетки, попавшие в зону согласия.

    Здесь и вылезает главное следствие делимости. У делимого вопроса
    сетка густая, и почти любая непустая зона содержит точку. У
    неделимого сетка состоит из нуля и ста: зона может быть широкой, а
    законной точки в ней нет ни одной. Неделимые ставки конфликтны не
    из-за вражды, а из-за геометрии.
    """
    z = zopa(ceiling, floor)
    if z is None:
        return []
    return [p for p in issue.kind().grid() if z[0] <= p <= z[1]]


def failure_reason(issue: Issue, ceiling: Range, floor: Range) -> str | None:
    """Почему сделки нет. Нужно интерфейсу, чтобы называть ограничение."""
    if feasible(issue, ceiling, floor):
        return None
    if zopa(ceiling, floor) is None:
        return (f"зона пуста: дома проходит до {ceiling.hi:.0f}, "
                f"партнёр не берёт меньше {floor.lo:.0f}")
    return (f"вопрос неделим: зона {floor.lo:.0f}..{ceiling.hi:.0f} есть, "
            f"но {issue.kind().name_ru.lower()} нельзя уступить частично")


def explain(ceiling: Range, floor: Range) -> str:
    """Разбор для интерфейса: из чего сложились обе границы."""
    out = [f"Потолок ратификации: {ceiling.hi:.1f}"]
    out += [f"  {n:<42} {v:+7.1f}" for n, v in ceiling.parts]
    out.append(f"Порог принятия: {floor.lo:.1f}")
    out += [f"  {n:<42} {v:+7.1f}" for n, v in floor.parts]
    z = zopa(ceiling, floor)
    out.append(f"Зона сделки: {f'{z[0]:.1f}..{z[1]:.1f}' if z else 'пуста'}")
    return "\n".join(out)


# Средство проверки: полный разбор вопроса для консоли.
def explain_issue(world: World, issue: Issue) -> str:
    """Полный разбор конкретного вопроса вместе с законными исходами."""
    kind = issue.kind()
    ceiling = ratification_ceiling(world, issue)
    floor = acceptance_floor(world, issue)
    pts = feasible(issue, ceiling, floor)
    head = (f"{issue.name_ru} · {kind.name_ru} · делимость {kind.divisibility:.2f}, "
            f"обратимость {kind.reversibility:.2f}")
    body = explain(ceiling, floor)
    if pts:
        tail = f"Законные исходы: {', '.join(f'{p:.0f}' for p in pts[:8])}" + \
               ("…" if len(pts) > 8 else "")
    else:
        tail = "Сделки нет — " + (failure_reason(issue, ceiling, floor) or "")
    return f"{head}\n{body}\n{tail}"


# --- живые переговоры и притязания ---------------------------------------

MIN_STAKE = 0.15   # ниже этого обсуждать нечего
GREED = 0.82       # какую долю оцененного потолка получатель пытается взять


def stake(world: World, giver: str, receiver: str, type_id: str) -> float:
    """Есть ли вообще повод для переговоров по этому вопросу.

    Ставка не назначается списком, а берётся из состояния: спор в
    таблице территорий, торговая зависимость, враждебность, союзные
    обязательства. Тип вопроса лишь указывает, какой источник смотреть.

    Без этой проверки движок считал зону согласия для всех сочетаний
    подряд, включая переговоры Германии с Бразилией о суверенитете —
    и средняя ширина зоны получалась бессмысленно большой.
    """
    src = TYPES[type_id].stake_source
    d = world.dyad(giver, receiver)

    if src == "dispute":
        for disp in world.disputes.values():
            pair = {disp.controller, disp.claimant}
            if pair == {giver, receiver}:
                return min(1.0, 0.55 + 0.45 * disp.heat)
        return 0.0
    if src == "trade":
        return min(1.0, 5.0 * max(world.trade_dep(giver, receiver),
                                  world.trade_dep(receiver, giver)))
    if src == "hostility":
        # Угроза усиливает антагонизм, но не заменяет его. Иначе у
        # России с Казахстаном возникали переговоры о снятии санкций,
        # которых нет: одного соседства с более сильным хватало.
        hostile = max(0.0, -world.alignment(giver, receiver))
        return min(1.0, hostile * 1.4 * (1.0 + 0.5 * world.threat(receiver, giver)))
    if src == "alliance":
        return min(1.0, d.obligation() * 0.8
                   + 0.5 * world.threat(receiver, giver)
                   + 0.3 * d.contiguous)
    return 0.0


def live(world: World, giver: str, receiver: str, type_id: str) -> bool:
    return stake(world, giver, receiver, type_id) >= MIN_STAKE


def aspiration(world: World, issue: Issue, ceiling: Range) -> tuple[float, str]:
    """Сколько получатель запрашивает, исходя из оценки чужого потолка.

    Стороны просят не минимум, который согласны принять, а столько,
    сколько рассчитывают выторговать. Истинного потолка получатель не
    знает — он оценивает его разведкой, поэтому при плохой
    осведомлённости либо запрашивает лишнего и срывает сделку, либо
    продешевит.
    """
    from . import intel
    from .ai import client_doctrine, load_doctrines
    lo, hi, lv = intel.estimate(world, issue.receiver, issue.giver, ceiling.hi)
    guess = (lo + hi) / 2.0
    # Жадность не одна для всех: ревизионист торгуется жёстче,
    # осторожная держава оставляет запас, чтобы не сорвать сделку.
    docs = load_doctrines()
    doc = docs.get(issue.receiver) or client_doctrine(world, issue.receiver)
    greed = GREED + 0.16 * (doc.revisionism - 0.35)
    greed = max(0.62, min(0.95, greed))
    return guess * greed, f"оценка чужого потолка {guess:.0f}, запрос {greed:.0%}"
