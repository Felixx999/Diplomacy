"""Как решение одной страны расходится по остальным.

Четыре канала, у каждого своя скорость и своё затухание. Каждый вклад
несёт с собой объяснение — именно оно потом показывается игроку при
наведении курсора на изменившееся число.
"""

from __future__ import annotations

from dataclasses import dataclass

from .state import World

# Коэффициенты затухания. Вынесены наверх намеренно: это то, что
# балансируется таблицей, а не переписыванием кода.
ALLY_DECAY = 0.85      # союзный канал почти не затухает: обязательство есть или нет
TRADE_DECAY = 0.55     # торговый бьёт слабее, но по всем сразу
IDEO_DECAY = 0.30      # идеологический определяет, кто присоединится бесплатно
SECURITY_DECAY = 0.65  # безопасностный работает только по соседям

IDEAL_SPAN = 6.0       # ширина шкалы идеальных точек ГА

# Рябь не может быть сильнее камня. Совокупная реакция третьих стран на
# двусторонний шаг ограничена долей от прямого эффекта: сам шаг всегда
# весомее его отголосков.
#
# Без этого предела сумма по каналам росла вместе со связностью мира. На
# выдуманных данных это не бросалось в глаза — союзов было мало, позиции
# в ГА стояли тесно. На настоящих оказалось, что одно действие меняет
# расклад по пятидесяти шести парам суммарно вшестеро сильнее прямого
# эффекта.
#
# Предел нормирует сумму, но сохраняет пропорции: кто именно откликнулся
# и насколько сильно относительно других — остаётся как было. Игроку
# важна цепочка причин, а не абсолютная величина.
RIPPLE_CAP = 0.65


@dataclass
class Shock:
    """Один вклад в изменение состояния пары, с указанием происхождения.

    Поле `field` говорит, во что именно попадает вклад. Три канала из
    четырёх меняют выравнивание, безопасностный — угрозу. Доверие
    каналами не меняется: оно живёт в реестре обещаний.
    """
    source: str      # чьё восприятие меняется
    target: str      # относительно кого
    delta: float
    channel: str
    why: str
    field: str = "alignment"   # alignment | threat

    def line(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        mark = "" if self.field == "alignment" else f" ({self.field})"
        return (f"  {self.source}→{self.target} {sign}{self.delta:.3f}"
                f"  [{self.channel}{mark}] {self.why}")


@dataclass
class Action:
    actor: str
    target: str
    kind: str        # sanction | aid | arms | recognize | escalate | concede | deal
    magnitude: float  # 0..1, сила действия

    #                      прямой эффект на отношения актор-цель
    DIRECT = {
        "sanction": -0.45,
        "escalate": -0.60,
        "arms": -0.25,       # поставки оружия противнику цели
        "recognize": -0.35,  # признание претензии против цели
        "aid": +0.35,
        "concede": +0.40,
        "deal": +0.30,
    }

    def sign(self) -> float:
        return 1.0 if self.DIRECT.get(self.kind, 0.0) >= 0 else -1.0

    def base(self) -> float:
        return self.DIRECT.get(self.kind, 0.0) * self.magnitude


def affinity(world: World, x: str, y: str) -> float:
    """Идеологическая близость по позициям в ГА ООН, 0..1."""
    dx = abs(world.countries[x].ideal_point - world.countries[y].ideal_point)
    return max(0.0, 1.0 - dx / IDEAL_SPAN)


def propagate(world: World, action: Action) -> list[Shock]:
    """Возвращает полный список вкладов, не применяя их."""
    a, t = action.actor, action.target
    base = action.base()
    shocks: list[Shock] = [
        Shock(a, t, base, "прямой", f"{action.kind}, сила {action.magnitude:.2f}")
    ]
    if action.kind in ("escalate", "arms", "sanction"):
        shocks.append(Shock(t, a, abs(base) * 0.5, "прямой",
                            f"{t} видит во враждебном шаге угрозу", "threat"))
    if a == t or abs(base) < 1e-6:
        return shocks

    ca = world.countries[a]

    for third in world.others(a):
        if third == t:
            continue
        ct = world.countries[third]

        # 1. Союзный: третья страна связана обязательством с целью
        obl = world.dyad(third, t).obligation()
        if obl > 0:
            d = base * obl * ALLY_DECAY
            shocks.append(Shock(a, third, d, "союзный",
                                f"{third} связан(а) обязательством с {t} ({world.dyad(third, t).alliance})"))

        # 2. Торговый: третья страна зависит от цели, ей достаётся рикошетом
        dep = world.trade_dep(third, t)
        if dep > 0.02:
            d = base * dep * TRADE_DECAY
            shocks.append(Shock(a, third, d, "торговый",
                                f"доля {t} во внешней торговле {third}: {dep:.0%}"))

        # 3. Идеологический: близкие к цели воспринимают это как удар по себе,
        #    близкие к актору — как санкцию против чужого
        aff_t = affinity(world, third, t)
        aff_a = affinity(world, third, a)
        lean = aff_t - aff_a
        if abs(lean) > 0.05:
            d = base * lean * IDEO_DECAY
            shocks.append(Shock(a, third, d, "идеологический",
                                f"позиция {third} в ГА ближе к {'цели' if lean > 0 else 'актору'} на {abs(lean):.2f}"))

        # 4. Безопасностный: усиление актора рядом с третьей страной.
        #    Направление обратное остальным каналам — меняется не
        #    отношение актора к соседу, а тревога соседа относительно
        #    актора. Работает без злого умысла, в этом весь смысл.
        if action.kind in ("escalate", "arms") and world.dyad(third, t).contiguous:
            ratio = ca.power() / max(ca.power() + ct.power(), 1e-6)
            d = abs(base) * ratio * SECURITY_DECAY * 0.5
            shocks.append(Shock(third, a, d, "безопасностный",
                                f"{third} граничит с {t}, соотношение сил {ratio:.2f}",
                                "threat"))

    return _limit(shocks, abs(base))


def _limit(shocks: list[Shock], direct: float) -> list[Shock]:
    """Ограничить суммарную рябь долей от прямого эффекта."""
    ripple = [s for s in shocks if s.channel != "прямой"]
    total = sum(abs(s.delta) for s in ripple)
    ceiling = direct * RIPPLE_CAP
    if total <= ceiling or total < 1e-9:
        return shocks
    k = ceiling / total
    for s in ripple:
        s.delta *= k
        s.why += f" (доля от предела ряби {k:.2f})"
    return shocks


def apply(world: World, shocks: list[Shock]) -> None:
    """Применяет вклады. Выравнивание симметрично, угроза направленна."""
    for s in shocks:
        d = world.dyad(s.source, s.target)
        if s.field == "threat":
            d.add_threat(s.source, s.delta)
        else:
            d.alignment = max(-1.0, min(1.0, d.alignment + s.delta))


def projected(world: World, shocks: list[Shock], me: str) -> dict[str, float]:
    """Оценка изменения составного отношения `me` к остальным.

    Коэффициенты повторяют свёртку в World.relation: выравнивание
    входит целиком, угроза с обратным знаком и весом.
    """
    out: dict[str, float] = {}
    for s in shocks:
        if s.field == "alignment" and me in (s.source, s.target):
            other = s.target if s.source == me else s.source
            out[other] = out.get(other, 0.0) + s.delta
        elif s.field == "threat" and s.source == me:
            out[s.target] = out.get(s.target, 0.0) - 0.45 * s.delta
    out.pop(me, None)
    return out


def trace(shocks: list[Shock], target: str | None = None) -> str:
    """Причинная цепочка для интерфейса: почему это число такое."""
    rows = [s for s in shocks if target is None or s.target == target]
    rows.sort(key=lambda s: -abs(s.delta))
    total = sum(s.delta for s in rows)
    head = f"Суммарно {total:+.3f} из {len(rows)} вкладов"
    return "\n".join([head] + [s.line() for s in rows])
