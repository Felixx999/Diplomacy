"""Повестка месяца.

То, чего в движке не было вовсе: механизм, который приносит проблемы
игроку, а не ждёт, пока игрок сам их найдёт.

Вопросы не написаны заранее. Каждый порождается конкретным состоянием:
накалившийся спор, наступивший срок обещания, шаткая коалиция,
уходящий клиент, подошедший заём, разгневанная группа. Если в мире
ничего не происходит, повестка пуста и месяц проматывается сам — игрока
незачем дёргать двести четыре раза за партию.

Каждый вариант ответа — настоящее действие движка, а не текст. И у
каждого есть предпосылка: доступность отдельна от цены, накопить очки
и купить что угодно нельзя.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import deal, groups, intel, legible, politics, valves
from .state import World

# Язык текущей выдачи. Задаётся в build() и читается генераторами через
# L(). Сервер однопоточный и строит повестку на каждый запрос, поэтому
# модульной переменной здесь достаточно.
_LANG = {"v": "ru"}


def L(key: str, **kw) -> str:
    from . import i18n
    return i18n.t(key, _LANG["v"], **kw)


def CN(world: World, code: str) -> str:
    """Название страны на языке выдачи."""
    c = world.countries[code]
    return (c.name_en or c.name_ru) if _LANG["v"] == "en" else c.name_ru


def EN(obj, field: str = "name") -> str:
    """Название сущности из таблицы на языке выдачи."""
    if _LANG["v"] == "en":
        v = getattr(obj, f"{field}_en", "") or ""
        if v.strip():
            return v
    return getattr(obj, f"{field}_ru", "") or getattr(obj, field, "")


# Стадии и исходы эскалации приходят из escalation.py по-русски; здесь они
# служат ключами для перевода.
STAGE_KEY = {"спокойно": "calm", "напряжение": "tension", "кризис": "crisis",
             "развязка": "showdown"}
RESOLVED_KEY = {"смена контроля": "control", "отступление": "retreat"}

MAX_ITEMS = 4        # больше четырёх вопросов за раз человек не удержит
QUIET_BELOW = 0.25   # ниже этой срочности вопрос не стоит внимания
COOLDOWN = 24         # ходов молчания после того, как вопрос уже поднимали
WORSENED = 0.15      # насколько должно ухудшиться, чтобы поднять повторно


@dataclass
class Choice:
    """Вариант ответа. Всегда настоящее действие, никогда просто текст."""
    label: str
    effect: str
    params: dict = field(default_factory=dict)
    hint: str = ""
    blocked: str = ""        # если непусто — почему недоступно

    def available(self) -> bool:
        return not self.blocked


@dataclass
class Item:
    id: str
    area: str            # внешняя | внутренняя — ключ, не для показа
    title: str
    body: str
    urgency: float
    source: str          # ключ темы сцены, не для показа
    choices: list[Choice] = field(default_factory=list)
    area_label: str = ""     # подписи на языке выдачи
    source_label: str = ""

    def live_choices(self) -> list[Choice]:
        return [c for c in self.choices if c.available()]


# --- источники вопросов --------------------------------------------------

def _disputes(world: World, me: str, turn: int) -> list[Item]:
    """Спор попадает в повестку по событию эскалации, а не по уровню.

    Раньше генератор сам заново вычислял рост накала и почти никогда не
    срабатывал. Теперь он читает готовые события из `escalation`: ход
    вверх по лестнице, развязка, отступление. Высокий накал сам по себе
    остаётся фоном и в повестку не попадает.
    """
    out = []
    events = {e.dispute: e for e in getattr(world, "recent_crises", [])}
    for d in world.disputes.values():
        if me not in (d.controller, d.claimant):
            continue
        ev = events.get(d.id)
        if ev is None:
            continue
        other = d.claimant if d.controller == me else d.controller
        if other not in world.countries:
            continue
        name = CN(world, other)
        giving = d.controller == me
        what = (L("esc.res." + RESOLVED_KEY.get(ev.resolved, "control"))
                if ev.resolved else
                L("esc.stage." + STAGE_KEY.get(ev.stage, "tension")))
        title = L("ag.dispute.title", dispute=EN(d), what=what)
        out.append(Item(
            id=f"dispute:{d.id}:{turn}", area="внешняя",
            area_label=L("area.foreign"),
            title=title,
            body=L("ag.dispute.raises", who=name) + " "
                 + (L("ag.dispute.we_give") if giving
                    else L("ag.dispute.we_claim")),
            urgency=min(1.0, 0.45 + d.heat), source="эскалация",
            source_label=L("src.escalation"),
            choices=[
                Choice(L("ch.negotiate"), "negotiate",
                       {"other": other, "type": d.issue_type},
                       L("ch.negotiate.h")),
                Choice(L("ch.hold"), "hold", {"other": other},
                       L("ch.hold.h")),
                Choice(L("ch.package"), "package",
                       {"other": other, "type": d.issue_type},
                       L("ch.package.h")),
                Choice(L("ch.concede"), "concede",
                       {"other": other, "type": d.issue_type},
                       L("ch.concede.h"),
                       blocked="" if groups.mood(world, me, "nationalists") > 0.35
                       else L("ch.concede.b")),
            ]))
    return out


def _promises(world: World, me: str, turn: int) -> list[Item]:
    out = []
    for p in world.promises:
        if p.debtor != me or p.kept is not None:
            continue
        if p.due - turn > 2:
            continue
        cred = CN(world, p.creditor)
        out.append(Item(
            id=f"promise:{p.creditor}:{p.turn}", area="внешняя",
            area_label=L("area.foreign"),
            title=L("ag.promise.title", who=cred),
            body=L("ag.promise.body", what=p.subject),
            urgency=0.55 + 0.2 * (p.due <= turn), source="наступивший срок",
            source_label=L("src.due"),
            choices=[
                Choice(L("ch.keep"), "keep", {"creditor": p.creditor},
                       L("ch.keep.h")),
                Choice(L("ch.breach"), "breach", {"creditor": p.creditor},
                       L("ch.breach.h")),
            ]))
    return out


def _coalition(world: World, me: str, turn: int) -> list[Item]:
    support = politics.support(world, me) if hasattr(politics, "support") else None
    angry = [b for b in groups.blocs(world, me)
             if groups.mood(world, me, b.id) < 0.28]
    if not angry:
        return []
    worst = min(angry, key=lambda b: groups.mood(world, me, b.id))
    reading = legible.read("mood", groups.mood(world, me, worst.id), _LANG["v"])
    return [Item(
        id=f"mood:{worst.id}", area="внутренняя",
        area_label=L("area.home"),
        title=L("ag.mood.title", group=EN(worst)),
        body=L("ag.mood.body", mood=reading.label),
        urgency=0.45 + 0.5 * (1.0 - groups.mood(world, me, worst.id)),
        source="настроение группы", source_label=L("src.mood"),
        choices=[
            Choice(L("ch.toward"), "policy_toward",
                   {"group": worst.id}, L("ch.toward.h")),
            Choice(L("ch.buy"), "spend_on_group",
                   {"group": worst.id}, L("ch.buy.h"),
                   blocked="" if world.countries[me].political_capital > 25
                   else L("ch.buy.b")),
            Choice(L("ch.ignore"), "noop", {}, L("ch.ignore.h")),
        ])]


def _clients(world: World, me: str, turn: int) -> list[Item]:
    out = []
    for c in world.countries.values():
        if c.patron != me:
            continue
        rel = world.relation(c.code, me)
        if rel > 0.25:
            continue
        out.append(Item(
            id=f"client:{c.code}", area="внешняя",
            area_label=L("area.foreign"),
            title=L("ag.client.title", who=CN(world, c.code)),
            body=L("ag.client.body"),
            urgency=0.4 + 0.4 * (0.25 - rel), source="охлаждение клиента",
            source_label=L("src.client"),
            choices=[
                Choice(L("ch.invest"), "aid", {"other": c.code},
                       L("ch.invest.h")),
                Choice(L("ch.release"), "drop_client", {"other": c.code},
                       L("ch.release.h")),
                Choice(L("ch.wait"), "noop", {}, L("ch.wait.h")),
            ]))
    return out


def _loans(world: World, me: str, turn: int) -> list[Item]:
    out = []
    for l in world.loans:
        if l.repaid or l.debtor != me or l.due - turn > 2:
            continue
        out.append(Item(
            id=f"loan:{l.due}", area="внутренняя",
            area_label=L("area.home"),
            title=L("ag.loan.title"), body=L("ag.loan.body"),
            urgency=0.6, source="срок займа", source_label=L("src.loan"),
            choices=[
                Choice(L("ch.budget"), "policy_austerity", {},
                       L("ch.budget.h")),
                Choice(L("ch.sell"), "sell_asset", {}, L("ch.sell.h"),
                       blocked="" if valves.assets(world, me)
                       else L("ch.sell.b")),
                Choice(L("ch.await"), "noop", {}, L("ch.await.h")),
            ]))
    return out


def _offers(world: World, me: str, turn: int) -> list[Item]:
    """Предложения от других стран.

    Не сканирование всех живых переговоров подряд — иначе четыре
    одинаковых тарифных предложения в каждом месяце. Предложение
    приходит от той страны, чьи отношения с нами заметно потеплели за
    последние ходы: у неё появился повод заговорить.
    """
    out = []
    for other in world.tier("A"):
        if other == me or world.relation(other, me) < 0.2:
            continue
        key = f"rel:{other}"
        prev = world.agenda_prev.get(key, world.relation(other, me))
        world.agenda_prev[key] = world.relation(other, me)
        if world.relation(other, me) - prev < 0.015:
            continue
        for tid in deal.TYPES:
            if not deal.live(world, me, other, tid):
                continue
            issue = deal.Issue(f"{me}-{other}", deal.TYPES[tid].name_ru,
                               me, other, type_id=tid)
            ceiling = deal.ratification_ceiling(world, issue)
            floor = deal.acceptance_with_aspiration(world, issue, ceiling)
            pts = deal.feasible(issue, ceiling, floor)
            if not pts or ceiling.hi - floor.lo < 8:
                continue
            lo, hi, lv = intel.estimate(world, me, other, floor.lo)
            band = legible.read("intel", lv, _LANG["v"])
            out.append(Item(
                id=f"offer:{other}:{tid}", area="внешняя",
                area_label=L("area.foreign"),
                title=L("ag.offer.title", who=CN(world, other),
                        what=EN(deal.TYPES[tid]).lower()),
                body=L("ag.offer.body", lo=f"{lo:.0f}", hi=f"{hi:.0f}",
                       intel=band.label),
                urgency=0.3 + 0.003 * (ceiling.hi - floor.lo),
                source="живые переговоры", source_label=L("src.offer"),
                choices=[
                    Choice(L("ch.accept"), "sign",
                           {"other": other, "type": tid,
                            "level": pts[len(pts) // 2]},
                           L("ch.accept.h")),
                    Choice(L("ch.spy"), "spy", {"other": other},
                           L("ch.spy.h"),
                           blocked="" if world.countries[me].diplomatic_capital > 20
                           else L("ch.spy.b")),
                    Choice(L("ch.decline"), "noop", {}, L("ch.decline.h")),
                ]))
            break
    return out


def _inherited(world: World, me: str, turn: int) -> list[Item]:
    """Что досталось от предшественника.

    Повестка порождается изменениями, а на первом ходу изменений ещё не
    было — экран оказывался пустым. Но новый глава государства и не
    приходит на чистое место: у него уже есть вакансии в кабинете,
    открытые споры и чужие соглашения на исполнении. Генератор работает
    только первые ходы и потом умолкает.
    """
    if turn > 2:
        return []
    from .government import ministries_of as _mo
    MINISTRIES = _mo(me)
    out = []

    vacant = [m for m in MINISTRIES if (me, m) not in world.ministers]
    if vacant:
        names = ", ".join(EN(MINISTRIES[m], "short").lower() for m in vacant[:3])
        out.append(Item(
            id="inherit:cabinet", area="внутренняя",
            area_label=L("area.home"),
            title=L("ag.inh.cab.title"), body=L("ag.inh.cab.body", names=names),
            urgency=0.72, source="наследство", source_label=L("src.inherit"),
            choices=[
                Choice(L("ch.appoint"), "goto_cabinet", {}, L("ch.appoint.h")),
                Choice(L("ch.leave"), "noop", {}, L("ch.leave.h")),
            ]))

    hot = [d for d in world.disputes.values()
           if me in (d.controller, d.claimant) and d.heat >= 0.30]
    for d in hot[:2]:
        other = d.claimant if d.controller == me else d.controller
        if other not in world.countries:
            continue
        out.append(Item(
            id=f"inherit:{d.id}", area="внешняя",
            area_label=L("area.foreign"),
            title=L("ag.inh.disp.title", dispute=EN(d)),
            body=L("ag.inh.disp.body"),
            urgency=0.60 + 0.3 * d.heat, source="наследство",
            source_label=L("src.inherit"),
            choices=[
                Choice(L("ch.talks"), "negotiate",
                       {"other": other, "type": d.issue_type}, L("ch.talks.h")),
                Choice(L("ch.freeze"), "noop", {}, L("ch.freeze.h")),
            ]))

    active = [d for d in world.deliveries
              if not d.done() and me in (d.giver, d.receiver)]
    if active:
        d = active[0]
        out.append(Item(
            id="inherit:deals", area="внешняя",
            area_label=L("area.foreign"),
            title=L("ag.inh.deals.title"),
            body=L("ag.inh.deals.body",
                   giver=CN(world, d.giver), receiver=CN(world, d.receiver),
                   what=EN(__import__("engine.deal", fromlist=["x"]).TYPES[d.type_id]).lower(),
                   pct=f"{d.delivered:.0%}"),
            urgency=0.45, source="наследство", source_label=L("src.inherit"),
            choices=[
                Choice(L("ch.honour"), "noop", {}, L("ch.honour.h")),
                Choice(L("ch.revise"), "cancel_deal", {"deal": d.type_id},
                       L("ch.revise.h"),
                       blocked="" if execution_reversible(d) else L("ch.revise.b")),
            ]))
    return out


def execution_reversible(d) -> bool:
    from .execution import can_cancel
    return can_cancel(d.type_id)


def _frictions(world: World, me: str, turn: int) -> list[Item]:
    """Конфликт в правительстве как отдельный вопрос."""
    from . import personnel as hr
    from .government import ministries_of
    rows = [f for f in hr.frictions(world, me) if f["force"] >= 0.45]
    if not rows:
        return []
    f = rows[0]
    mset = ministries_of(me)
    a = EN(mset[f["a"]], "short") if f["a"] in mset else f["a"]
    b = EN(mset[f["b"]], "short") if f["b"] in mset else f["b"]
    why = L("fr." + f.get("key", "generic"))
    return [Item(
        id=f"friction:{f['a']}:{f['b']}", area="внутренняя",
        area_label=L("area.home"),
        title=L("ag.fr.title", a=a, b=b),
        body=L("ag.fr.body", why=why),
        urgency=0.40 + 0.35 * f["force"], source="конфликт в кабинете",
        source_label=L("src.friction"),
        choices=[
            Choice(L("ch.back_a", who=a), "back_minister",
                   {"keep": f["a"], "drop": f["b"]}, L("ch.back.h", who=b)),
            Choice(L("ch.back_a", who=b), "back_minister",
                   {"keep": f["b"], "drop": f["a"]}, L("ch.back.h", who=a)),
            Choice(L("ch.letargue"), "noop", {}, L("ch.letargue.h")),
        ])]


GENERATORS = (_inherited, _frictions, _disputes, _promises, _coalition, _clients,
              _loans, _offers)


def build(world: World, me: str, turn: int, lang: str = "ru") -> list[Item]:
    """Повестка месяца. Пустой список означает спокойный месяц."""
    _LANG["v"] = lang if lang in ("ru", "en") else "ru"
    items: list[Item] = []
    for gen in GENERATORS:
        try:
            items += gen(world, me, turn)
        except Exception:
            continue
    fresh: list[Item] = []
    for i in items:
        if i.urgency < QUIET_BELOW or not i.live_choices():
            continue
        seen = world.agenda_seen.get(i.id)
        if seen:
            last_turn, last_urgency = seen
            # Повестка одного хода неизменна, сколько раз её ни спроси.
            # Без этого второй запрос в том же ходу возвращал пустоту:
            # интерфейс обращается к пульту дважды — при загрузке и при
            # отрисовке, — и игрок в браузере ни разу не видел депеш.
            if last_turn == turn:
                fresh.append(i)
                continue
            if (turn - last_turn < COOLDOWN
                    and i.urgency - last_urgency < WORSENED):
                continue
        fresh.append(i)
    fresh.sort(key=lambda i: -i.urgency)
    fresh = fresh[:MAX_ITEMS]
    for i in fresh:
        world.agenda_seen[i.id] = (turn, i.urgency)
    return fresh


# Средство проверки: повестка одной строкой для консоли.
def summary(world: World, items: list[Item]) -> str:
    if not items:
        return "Спокойный месяц. Обязательных решений нет."
    head = f"Требуют решения: {len(items)}"
    rows = [f"  [{i.area}] {i.title} — {i.source}" for i in items]
    return "\n".join([head] + rows)
