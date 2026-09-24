"""Исполнение сделок.

Подписанное соглашение — не событие, а график. Уступка поставляется
частями в течение горизонта, заданного типом вопроса, и каждая часть
делает две вещи: меняет реальное состояние мира и рассылает возмущения
по каналу этого типа.

Отсюда впервые становится настоящей обратимость из Р-12. Обратимую
сделку можно отменить посреди исполнения — доставленное останется, но
остаток не придёт. Необратимую отменить нельзя ни за какие деньги: то,
что отдано, отдано.

Задержка тоже не украшение. Сделка, подписанная сегодня, начинает
влиять на расклад через кварталы, и за это время может смениться
правительство, испортиться отношения или отпасть повод. Именно
поэтому долгие соглашения требуют доверия, а короткие нет.
"""

from __future__ import annotations

from dataclasses import dataclass

from .channels import Shock, apply as apply_shocks
from .deal import TYPES
from .state import World

ALIGN_PER_LEVEL = 0.0045    # прирост выравнивания за пункт уступки
TRADE_PER_LEVEL = 0.0010    # прирост зависимости за пункт
THREAT_PER_LEVEL = 0.0035   # снижение угрозы за пункт
HEAT_PER_LEVEL = 0.0040     # остывание спора за пункт


@dataclass
class Delivery:
    giver: str
    receiver: str
    type_id: str
    level: float          # 0..100, размер уступки
    signed: int           # ход подписания
    horizon: int          # за сколько кварталов доставляется
    delivered: float = 0.0   # уже доставленная доля, 0..1
    cancelled: bool = False

    def done(self) -> bool:
        return self.cancelled or self.delivered >= 0.999

    def label(self, world: World) -> str:
        return (f"{world.countries[self.giver].name_ru} → "
                f"{world.countries[self.receiver].name_ru}: "
                f"{TYPES[self.type_id].name_ru.lower()} на {self.level:.0f}")


def sign(world: World, giver: str, receiver: str, type_id: str,
         level: float, turn: int) -> Delivery:
    """Подписать соглашение. Обещание заводится тем же действием."""
    kind = TYPES[type_id]
    d = Delivery(giver, receiver, type_id, max(0.0, min(100.0, level)),
                 turn, max(1, kind.horizon_q))
    world.deliveries.append(d)
    world.promise(giver, receiver, kind.name_ru,
                  due=turn + kind.horizon_q,
                  cost=8.0 + 0.22 * level)
    return d


def can_cancel(type_id: str) -> bool:
    """Отменить можно только достаточно обратимое соглашение."""
    return TYPES[type_id].reversibility >= 0.40


def cancel(world: World, d: Delivery) -> dict:
    """Разорвать соглашение на полпути. Доставленное остаётся.

    Отмена ломает обещание, поэтому платится доверием по кривой Р-10, а
    не капиталом. Дешёвая сегодня, дорогая потом.
    """
    if d.done():
        return {"error": "нечего отменять"}
    if not can_cancel(d.type_id):
        return {"error": f"{TYPES[d.type_id].name_ru.lower()} необратимо"}
    d.cancelled = True
    for p in world.promises:
        if (p.debtor == d.giver and p.creditor == d.receiver
                and p.kept is None):
            p.kept = False
            break
    return {"cancelled": d.label(world),
            "delivered": round(d.delivered, 2),
            "trust_after": round(world.trust(d.receiver, d.giver), 3)}


def _state_effects(world: World, d: Delivery, part: float) -> list[str]:
    """Что меняется в мире от одной поставленной части.

    Канал типа вопроса определяет, куда именно приходится эффект: у
    торгового соглашения растёт взаимная зависимость, у соглашения по
    безопасности падает воспринимаемая угроза, у союзного крепнут
    обязательства.
    """
    kind = TYPES[d.type_id]
    amount = d.level * part
    notes: list[str] = []
    dy = world.dyad(d.giver, d.receiver)

    if kind.channel == "trade":
        add = TRADE_PER_LEVEL * amount
        if dy.a == d.receiver:
            dy.trade_dep_a = min(0.9, dy.trade_dep_a + add)
        else:
            dy.trade_dep_b = min(0.9, dy.trade_dep_b + add)
        notes.append(f"зависимость получателя +{add:.3f}")

    elif kind.channel == "security":
        dy.add_threat(d.receiver, -THREAT_PER_LEVEL * amount)
        notes.append(f"угроза со стороны донора −{THREAT_PER_LEVEL * amount:.3f}")

    elif kind.channel == "alliance":
        order = ["none", "nonaggression", "entente", "defense"]
        if d.delivered + part >= 0.999 and dy.alliance in order[:-1]:
            dy.alliance = order[order.index(dy.alliance) + 1]
            notes.append(f"обязательства повышены до «{dy.alliance}»")

    elif kind.channel == "ideological":
        gc, rc = world.countries[d.giver], world.countries[d.receiver]
        step = (rc.ideal_point - gc.ideal_point) * 0.02 * part * (d.level / 100.0)
        gc.ideal_point = round(gc.ideal_point + step, 3)
        notes.append(f"позиция донора в ГА сдвинулась на {step:+.3f}")

    # спор по этому вопросу остывает по мере исполнения
    for disp in world.disputes.values():
        if {disp.controller, disp.claimant} == {d.giver, d.receiver}:
            disp.heat = max(0.0, disp.heat - HEAT_PER_LEVEL * amount)
            notes.append(f"накал спора «{disp.name_ru}» {disp.heat:.2f}")
            break
    return notes


def tick(world: World, turn: int) -> list[dict]:
    """Доставить очередные части всех действующих соглашений."""
    events = []
    for d in world.deliveries:
        if d.done() or turn <= d.signed:
            continue
        part = min(1.0 / d.horizon, 1.0 - d.delivered)
        if part <= 0:
            continue
        notes = _state_effects(world, d, part)
        gain = ALIGN_PER_LEVEL * d.level * part
        apply_shocks(world, [
            Shock(d.giver, d.receiver, gain, "исполнение",
                  f"поставлена часть соглашения ({d.delivered + part:.0%})")
        ])
        d.delivered += part
        events.append({"deal": d.label(world),
                       "progress": round(d.delivered, 2),
                       "effects": notes,
                       "complete": d.done()})
    return events


def active(world: World, code: str | None = None) -> list[Delivery]:
    return [d for d in world.deliveries
            if not d.done() and (code is None or code in (d.giver, d.receiver))]
