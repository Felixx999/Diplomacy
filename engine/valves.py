"""Три клапана.

Исполнение Р-14: ограничение никогда не звучит как «ты не можешь ничего
сделать». Оно звучит как «всё, что ты можешь, стоит того, чего тебе
жалко».

Клапаны открыты всегда, поэтому у игрока по определению не бывает хода
без вариантов. Но каждый берёт плату из разного кармана: актив уходит
насовсем, заём возвращается с процентом, нарушенное слово обесценивает
все будущие сигналы.

Отказ от всех трёх достаточно долго ведёт к тому, что игрока снимают, —
и это концовка, а не проигрыш.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import groups
from .state import World

LOAN_RATE = 0.55        # переплата: занял сто, вернул сто пятьдесят пять
LOAN_TERM = 24           # кварталов до возврата
LOAN_LIMIT = 2          # больше двух непогашенных займов не дают
ASSET_MOOD_HIT = 0.16   # насколько продажа актива бьёт по настроению групп


@dataclass
class Option:
    """Один доступный выход с указанием, чем именно за него платят."""
    kind: str          # asset | loan | breach
    label: str
    gain: float        # сколько дипломатического капитала приносит
    price: str         # чем платим, словами
    ref: str = ""      # к чему относится: клиент, кредитор, обещание

    def line(self) -> str:
        return f"{self.label} · +{self.gain:.0f} капитала · цена: {self.price}"


@dataclass
class Loan:
    debtor: str
    amount: float
    due: int
    repaid: bool = False


# --- клапан первый: продать актив ----------------------------------------

def assets(world: World, code: str) -> list[Option]:
    """Что можно заложить. Каждый актив уходит насовсем.

    Список не задаётся, а собирается из состояния: отказ от клиента,
    вывод базы, снятие союзного обязательства. Чем ценнее актив, тем
    больше он приносит и тем больнее по нему бьют группы.
    """
    out: list[Option] = []
    for c in world.countries.values():
        if c.tier == "B" and c.patron == code:
            worth = 25.0 + 120.0 * c.power()
            out.append(Option("asset", f"Отказаться от покровительства над {c.name_ru}",
                              worth, "клиент уходит, националисты и военные против",
                              c.code))
    for other in world.others(code):
        d = world.dyad(code, other)
        if d.alliance in ("defense", "entente"):
            worth = 18.0 + 90.0 * world.countries[other].power()
            out.append(Option("asset", f"Разорвать обязательства перед {world.countries[other].name_ru}",
                              worth, "союз распадается, доверие партнёров падает", other))
    out.sort(key=lambda o: -o.gain)
    return out[:6]


def sell(world: World, code: str, opt: Option) -> dict:
    c = world.countries[code]
    c.diplomatic_capital += opt.gain
    for gid in ("nationalists", "military"):
        groups.nudge(world, code, gid, -ASSET_MOOD_HIT)
    if opt.kind == "asset" and opt.ref in world.countries:
        target = world.countries[opt.ref]
        if target.patron == code:
            target.patron = ""
        else:
            world.dyad(code, opt.ref).alliance = "none"
    return {"valve": "asset", "label": opt.label, "gain": round(opt.gain, 1)}


# --- клапан второй: занять у будущего ------------------------------------

def can_borrow(world: World, code: str) -> bool:
    return sum(1 for l in world.loans
               if l.debtor == code and not l.repaid) < LOAN_LIMIT


def loan_option(world: World, code: str) -> Option | None:
    if not can_borrow(world, code):
        return None
    amount = 40.0
    return Option("loan", "Занять политический капитал под будущие уступки",
                  amount, f"через {LOAN_TERM} кварталов вернуть "
                          f"{amount * (1 + LOAN_RATE):.0f}")


def borrow(world: World, code: str, turn: int, amount: float = 40.0) -> dict:
    world.countries[code].diplomatic_capital += amount
    world.loans.append(Loan(code, amount * (1.0 + LOAN_RATE), turn + LOAN_TERM))
    return {"valve": "loan", "amount": round(amount, 1),
            "repay": round(amount * (1 + LOAN_RATE), 1), "due": turn + LOAN_TERM}


def settle_loans(world: World, turn: int) -> list[dict]:
    """Наступившие сроки возврата. Нечем платить — платят группы."""
    out = []
    for l in world.loans:
        if l.repaid or l.due > turn:
            continue
        c = world.countries[l.debtor]
        if c.political_capital >= l.amount:
            c.political_capital -= l.amount
            out.append({"debtor": l.debtor, "repaid": True,
                        "amount": round(l.amount, 1)})
        else:
            short = l.amount - max(0.0, c.political_capital)
            c.political_capital = 0.0
            for b in groups.blocs(world, l.debtor):
                groups.nudge(world, l.debtor, b.id, -short / 600.0)
            out.append({"debtor": l.debtor, "repaid": False,
                        "shortfall": round(short, 1)})
        l.repaid = True
    return out


# --- клапан третий: нарушить слово ---------------------------------------

def breaches(world: World, code: str) -> list[Option]:
    """Незакрытые обещания, от которых можно отказаться прямо сейчас."""
    out = []
    for p in world.promises:
        if p.debtor != code or p.kept is not None:
            continue
        out.append(Option("breach",
                          f"Отказаться от обещания перед "
                          f"{world.countries[p.creditor].name_ru}",
                          p.cost, "доверие падает надолго, а нарушение весит "
                                  "вдвое с лишним против сдержанного слова",
                          p.creditor))
    out.sort(key=lambda o: -o.gain)
    return out[:4]


def breach(world: World, code: str, creditor: str) -> dict:
    for p in world.promises:
        if p.debtor == code and p.creditor == creditor and p.kept is None:
            p.kept = False
            world.countries[code].diplomatic_capital += p.cost
            return {"valve": "breach", "creditor": creditor,
                    "gain": round(p.cost, 1),
                    "trust_after": round(world.trust(creditor, code), 3)}
    return {"valve": "breach", "error": "нет открытых обещаний"}


# --- общий вход ----------------------------------------------------------

def options(world: World, code: str, turn: int) -> list[Option]:
    """Всё, что игрок может сделать, когда обычные ходы кончились.

    Список никогда не бывает пустым: заём доступен, пока не выбран
    лимит, а если выбран — остаются активы и обещания. Если пусто и
    здесь, значит страна распродала всё и никому ничего не обещала, и
    тогда её просто снимают.
    """
    out = assets(world, code) + breaches(world, code)
    lo = loan_option(world, code)
    if lo:
        out.append(lo)
    return out
