"""ИИ стран.

Это не языковая модель. Каждая страна — функция полезности с весами,
которые берутся из доктрины и калибруются по данным: торговая
зависимость даёт экономический вес, дистанция по позициям в ГА ООН —
идеологический, договорные обязательства — союзный.

Страна перебирает доступные ходы, оценивает их с учётом того, как
отреагируют третьи стороны, и берёт лучший. Поведение объяснимо:
можно всегда показать, из чего сложилась оценка.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass

from .channels import Action, affinity, projected, propagate
from .deal import Issue, acceptance_floor, feasible, ratification_ceiling
from .state import DATA, Promise, World

ACTION_COST = {
    "sanction": 12.0, "escalate": 25.0, "arms": 10.0,
    "recognize": 8.0, "aid": 14.0, "concede": 6.0, "deal": 5.0,
}


@dataclass
class Doctrine:
    code: str
    w_security: float
    w_economy: float
    w_prestige: float
    w_ideology: float
    w_regime: float
    risk_tolerance: float
    revisionism: float
    horizon: int


def load_doctrines() -> dict[str, Doctrine]:
    out = {}
    with open(DATA / "doctrines.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["code"]] = Doctrine(
                code=r["code"],
                w_security=float(r["w_security"]),
                w_economy=float(r["w_economy"]),
                w_prestige=float(r["w_prestige"]),
                w_ideology=float(r["w_ideology"]),
                w_regime=float(r["w_regime"]),
                risk_tolerance=float(r["risk_tolerance"]),
                revisionism=float(r["revisionism"]),
                horizon=int(r["horizon"]),
            )
    return out


def client_doctrine(world: World, code: str) -> Doctrine:
    """Доктрина страны уровня B. Не задаётся в таблице, а выводится.

    У клиента нет собственной большой стратегии: его веса определяются
    режимом и тем, насколько он вообще самостоятелен. Чем ниже
    автономия, тем меньше он готов рисковать в одиночку.
    """
    c = world.countries[code]
    survival = 0.30 if c.regime != "democracy" else 0.10
    return Doctrine(
        code=code,
        w_security=0.40, w_economy=0.25, w_prestige=0.10,
        w_ideology=0.10 if c.regime == "democracy" else 0.03,
        w_regime=survival,
        risk_tolerance=0.20 + 0.45 * c.autonomy,
        revisionism=0.20 + 0.50 * (1.0 - c.vdem_liberal) * c.autonomy,
        horizon=6 + int(10 * c.autonomy),
    )


def doctrine_of(world: World, doctrines: dict, code: str) -> Doctrine:
    return doctrines.get(code) or client_doctrine(world, code)


@dataclass
class Evaluation:
    action: Action
    utility: float
    parts: dict[str, float]

    def explain(self) -> str:
        rows = sorted(self.parts.items(), key=lambda kv: -abs(kv[1]))
        body = "\n".join(f"    {k:<16} {v:+7.3f}" for k, v in rows)
        return (f"  {self.action.actor}→{self.action.target} {self.action.kind} "
                f"({self.action.magnitude:.2f}) = {self.utility:+.3f}\n{body}")


def evaluate(world: World, doc: Doctrine, action: Action) -> Evaluation:
    """Полезность хода для актора с учётом реакции третьих стран."""
    me = action.actor
    shocks = propagate(world, action)
    drel = projected(world, shocks, me)

    security = economy = prestige = ideology = 0.0
    for other, d in drel.items():
        o = world.countries[other]
        dy = world.dyad(me, other)
        security += o.power() * (1.0 + dy.contiguous) * d
        economy += world.trade_dep(me, other) * d
        prestige += o.power() * d
        ideology += affinity(world, me, other) * d

    # авторитарные режимы конвертируют внешнюю жёсткость во внутреннюю опору
    regime = 0.0
    if world.countries[me].regime != "democracy" and action.sign() < 0:
        regime = 0.35 * action.magnitude

    cost = ACTION_COST.get(action.kind, 0.0) * action.magnitude / 100.0

    # доверие партнёров входит отдельно: страна, которой верят, дешевле
    # добивается своего, поэтому враждебные шаги для неё дороже
    trust_cost = 0.0
    if action.sign() < 0:
        trust_cost = -world.trust(action.target, me) * 0.25 * action.magnitude

    parts = {
        "безопасность": doc.w_security * security * 4.0,
        "экономика": doc.w_economy * economy * 3.0,
        "престиж": doc.w_prestige * prestige * 4.0,
        "идеология": doc.w_ideology * ideology,
        "режим": doc.w_regime * regime,
        "издержки": -cost,
        "репутация": trust_cost,
    }
    return Evaluation(action, sum(parts.values()), parts)


def candidates(world: World, me: str) -> list[Action]:
    acts: list[Action] = []
    for other in world.others(me):
        rel = world.relation(me, other)
        if rel < -0.1:
            acts.append(Action(me, other, "sanction", 0.5))
            acts.append(Action(me, other, "arms", 0.4))
        if rel > -0.4:
            acts.append(Action(me, other, "aid", 0.4))
            acts.append(Action(me, other, "deal", 0.5))
    return acts


# Усталость от повторения. Одно и то же действие в адрес одной и той же
# страны быстро перестаёт что-либо давать: партнёр к нему привыкает,
# собственная бюрократия сопротивляется, эффект уже израсходован.
FATIGUE_BASE = 0.22      # штраф за только что сделанный ход
FATIGUE_HALFLIFE = 15.0   # за сколько кварталов штраф падает вдвое
FATIGUE_STACK = 0.30     # добавка за каждое повторение сверх первого


def fatigue(memory: dict, turn: int, action: Action) -> float:
    """Насколько ход приелся. Ноль, если так ещё не делали."""
    key = (action.actor, action.target, action.kind)
    rec = memory.get(key)
    if not rec:
        return 0.0
    last, count = rec
    recency = 0.5 ** ((turn - last) / FATIGUE_HALFLIFE)
    return FATIGUE_BASE * recency * (1.0 + FATIGUE_STACK * min(count, 6))


def patience(doc: Doctrine) -> float:
    """Порог, ниже которого страна предпочитает не дёргаться.

    Растёт с горизонтом планирования: держава, думающая на десятилетия,
    не меняет курс каждые три месяца ради малого выигрыша.
    """
    return 0.05 + 0.0045 * doc.horizon


def choose(world: World, doc: Doctrine, rng: random.Random,
           memory: dict | None = None, turn: int = 0) -> Evaluation | None:
    """Лучший ход по доктрине с поправкой на усталость и терпение."""
    evals = [evaluate(world, doc, a) for a in candidates(world, doc.code)]
    if not evals:
        return None
    for e in evals:
        e.utility += rng.gauss(0.0, 0.03)
        if memory is not None:
            f = fatigue(memory, turn, e.action)
            if f:
                e.utility -= f
                e.parts["приелось"] = -f
    best = max(evals, key=lambda e: e.utility)
    return best if best.utility > patience(doc) else None


# --- исполнение обещаний ---

def keep_or_break(world: World, doc: Doctrine, p: Promise) -> tuple[bool, dict]:
    """Держать слово или нарушить. Это выбор, а не случайность.

    Исполнение стоит политического капитала здесь и сейчас. Нарушение
    бесплатно сегодня и обесценивает все будущие сигналы в адрес этого
    кредитора. Поэтому обещания сильному и нужному держат, а слабому и
    далёкому — нет. Из этого само собой выходит, что репутация
    зарабатывается там, где за ней следят.
    """
    debtor = world.countries[p.debtor]
    creditor = world.countries[p.creditor]

    # чего стоит доверие этого кредитора: его вес, наши связи, горизонт
    # Вес кредитора решает почти всё: слово держат перед теми, чьё
    # мнение будет иметь значение завтра. Коэффициент при мощи поднят,
    # прочие слагаемые ужаты — иначе разрыв между сильными и слабыми
    # кредиторами смазывался до нескольких процентов.
    worth = (5.0 * creditor.power()
             + 0.45 * world.trade_dep(p.debtor, p.creditor)
             + 0.30 * max(0.0, world.alignment(p.debtor, p.creditor))
             + 0.25 * world.dyad(p.debtor, p.creditor).obligation())
    value_of_word = worth * (0.5 + doc.horizon / 40.0) * 100.0
    price = p.cost * (1.0 + 0.5 * (1.0 - debtor.political_capital / 100.0))

    # Нехватка капитала не должна ровнять всех кредиторов. Ради важного
    # обещания страна находит средства, пусть и в долг перед своими:
    # платит сколько может и теряет часть легитимности. Ради неважного —
    # не находит. Без этого градиент доверия смазывался: должник
    # нарушал слово всем подряд просто потому, что был на мели.
    worth_it = value_of_word >= price
    can_pay = debtor.political_capital >= price
    keep = worth_it and (can_pay or value_of_word >= price * 2.6)
    if keep:
        if can_pay:
            debtor.political_capital -= price
        else:
            short = price - debtor.political_capital
            debtor.political_capital = 0.0
            debtor.legitimacy = max(0.05, debtor.legitimacy - short / 900.0)
    return keep, {"debtor": p.debtor, "creditor": p.creditor,
                  "subject": p.subject, "kept": keep,
                  "worth": round(value_of_word, 1), "price": round(price, 1)}


# --- решение о войне -------------------------------------------------------

@dataclass
class WarAssessment:
    dispute_id: str
    bargaining_failed: bool
    commitment_problem: bool
    deterred: bool
    capability: float
    pressure: float
    verdict: str


def war_check(world: World, doc: Doctrine, dispute_id: str,
              power_trend: dict[str, float]) -> WarAssessment:
    """Война как провал торга, а не как порог отношений.

    Два классических механизма. Первый: зона соглашения пуста — стороны
    просто не могут договориться. Второй: сдвиг силы делает будущие
    обещания недостоверными, то есть «договоримся сейчас, но через
    несколько лет ты передоговоришься с позиции силы».
    """
    d = world.disputes[dispute_id]
    claimant, controller = d.claimant, d.controller
    if claimant not in world.countries or controller not in world.countries:
        return WarAssessment(dispute_id, False, False, False, 0.0, 0.0, "вне модели")

    issue = Issue(
        id=dispute_id, name_ru=d.name_ru,
        giver=controller, receiver=claimant,
        salience_giver=d.salience_controller,
        salience_receiver=d.salience_claimant,
        dispute_id=dispute_id,
        type_id=d.issue_type,
    )
    ceiling = ratification_ceiling(world, issue)
    floor = acceptance_floor(world, issue)
    # провал торга — это отсутствие законных исходов, а не пустой интервал.
    # У неделимого вопроса зона может быть, а точки в ней нет.
    failed = not feasible(issue, ceiling, floor)

    # неблагоприятный сдвиг силы: контролирующая сторона растёт быстрее
    shift = power_trend.get(controller, 0.0) - power_trend.get(claimant, 0.0)
    commitment = shift > 0.002

    # взаимное ядерное сдерживание почти закрывает прямую войну
    both_nuclear = world.countries[claimant].nuclear and world.countries[controller].nuclear
    deterred = bool(both_nuclear)

    # Способность эскалировать, а не только желание. Претендент с
    # ничтожной долей мощи не начинает межгосударственную войну, каким
    # бы решительным он ни был. Асимметричные формы борьбы этой моделью
    # не описываются — они пойдут отдельной механикой.
    pc = world.countries[claimant].power()
    cc = world.countries[controller].power()
    capability = pc / max(pc + cc, 1e-9)
    gate = min(1.5, 0.20 + 1.6 * capability)

    pressure = (0.5 * failed + 0.3 * commitment + 0.2 * d.heat) * \
               doc.risk_tolerance * (0.5 + doc.revisionism) * gate
    if deterred:
        pressure *= 0.15

    if pressure > 0.35:
        verdict = "эскалация"
    elif pressure > 0.2:
        verdict = "давление ниже порога войны"
    else:
        verdict = "статус-кво"

    return WarAssessment(dispute_id, failed, commitment, deterred,
                        round(capability, 3), pressure, verdict)
