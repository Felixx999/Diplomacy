"""Цикл партии: квартал за квартал, 2026Q1 → 2042Q4, всего 68 ходов.

Порядок внутри хода: якоря → ход игрока → ходы ИИ → проверка споров →
затухание отношений → журнал.
"""

from __future__ import annotations

import random

from . import (deal, ending, escalation, execution, groups, intel,
               legible, opening, personnel, policy, politics, power, valves)
from .ai import (Doctrine, choose, doctrine_of, keep_or_break,
                 load_doctrines, war_check)
from .channels import Action, apply, propagate
from .state import World, haversine, load

END_YEAR = 2042

# Демография и рост — самые надёжные якоря на горизонте шестнадцати лет.
# Тем, кому в 2042 будет шестнадцать, уже родились. Эти величины
# удерживают мир от расползания в бессмыслицу.
POP_GROWTH = {
    "USA": 0.0045, "CHN": -0.0035, "RUS": -0.0045, "IND": 0.0070,
    "DEU": -0.0010, "FRA": 0.0015, "GBR": 0.0030, "TUR": 0.0055,
    "IRN": 0.0055, "ISR": 0.0150, "JPN": -0.0055, "SAU": 0.0110,
    # уровень B: без своих темпов эти двадцать стран стояли на месте
    "TWN": -0.0020, "UKR": -0.0060, "PAK": 0.0170, "KOR": -0.0020,
    "PRK": 0.0040, "POL": -0.0010, "EGY": 0.0150, "IDN": 0.0075,
    "BRA": 0.0040, "PHL": 0.0140, "VNM": 0.0060, "SYR": 0.0110,
    "PSE": 0.0210, "SRB": -0.0050, "XKX": 0.0020, "CYP": 0.0060,
    "MAR": 0.0090, "SAH": 0.0180, "AUS": 0.0090, "KAZ": 0.0090,
}
GDP_GROWTH = {
    "USA": 0.020, "CHN": 0.038, "RUS": 0.011, "IND": 0.060,
    "DEU": 0.009, "FRA": 0.011, "GBR": 0.013, "TUR": 0.031,
    "IRN": 0.020, "ISR": 0.030, "JPN": 0.008, "SAU": 0.028,
    "TWN": 0.022, "UKR": 0.035, "PAK": 0.030, "KOR": 0.019,
    "PRK": 0.010, "POL": 0.028, "EGY": 0.036, "IDN": 0.048,
    "BRA": 0.021, "PHL": 0.052, "VNM": 0.055, "SYR": 0.025,
    "PSE": 0.018, "SRB": 0.025, "XKX": 0.030, "CYP": 0.024,
    "MAR": 0.033, "SAH": 0.015, "AUS": 0.020, "KAZ": 0.037,
}

ALIGN_DECAY = 0.99497      # выравнивание сползает к нейтрали медленно
THREAT_DECAY = 0.9761     # тревога забывается быстрее, чем интересы расходятся
CAPITAL_REGEN = 2.0      # базовый приток дипломатического капитала
CAPITAL_FLOOR = 0.30     # минимальная доля притока даже у слабейших

CLIENT_UPKEEP = 0.6      # дипломатический капитал за клиента в ход
IDEAL_DRIFT = 0.004     # скорость сползания позиции в ГА к патрону
CLIENT_PULL = 0.02       # с какой скоростью клиент подтягивается к позициям патрона
SWITCH_BASE = 0.15       # порог перехода к другому покровителю
SWITCH_COOLDOWN = 36     # кварталов выдержки после смены покровителя
PROMISE_WINDOW = 18       # через сколько кварталов наступает срок по сделке
IDEO_VETO = 2.5          # запретная дистанция для авторитарных клиентов


class Sim:
    def __init__(self, player: str = "RUS", seed: int = 1):
        self.world: World = load(2026, 1)
        self.doctrines: dict[str, Doctrine] = load_doctrines()
        self.player = player
        self.rng = random.Random(seed)
        self.history: list[dict] = []
        self.turn_no = 0
        # Отключаемые фазы хода. Нужны, чтобы измерять вклад
        # каждого источника в общий дрейф мира, а не гадать.
        self.off: set[str] = set()
        self.memory: dict[tuple[str, str, str], tuple[int, int]] = {}
        self._switched: dict[str, int] = {}
        intel.seed_levels(self.world)
        # Игрок приходит не на пустое место: правительство, послы и
        # начатые соглашения достались ему от предшественника.
        self.opening = opening.setup(self.world, player, 0)
        policy.seed(self.world)
        politics.seed(self.world)
        politics.remember_doctrines(self.doctrines)
        self._prev_power = {c: v.power() for c, v in self.world.countries.items()}

    # --- фазы хода ---

    def anchors(self) -> None:
        """Демография и экономика идут своим ходом почти независимо от политики."""
        for c in self.world.countries.values():
            g = GDP_GROWTH.get(c.code, 0.0) / 12
            c.pop_mn *= (1 + POP_GROWTH.get(c.code, 0.0) / 12)
            c.gdp_bn *= (1 + g)
            c._growth = g * 12
            # военные расходы держат постоянную долю ВВП, пока это не
            # стало политикой игрока; промышленность и энергия растут
            # медленнее — развитая экономика прибавляет в услугах
            c.milex_bn *= (1 + g)
            c.steel_mt *= (1 + g * power.INDUSTRY_ELASTICITY)
            c.energy_mtoe *= (1 + g * power.ENERGY_ELASTICITY)
            # база для политик растёт вместе с экономикой, иначе
            # apply_macro вернёт показатели к стартовым значениям
            pg = 1 + POP_GROWTH.get(c.code, 0.0) / 12
            for attr, f in (("gdp_bn", 1 + g), ("milex_bn", 1 + g),
                            ("pop_mn", pg),
                            ("steel_mt", 1 + g * power.INDUSTRY_ELASTICITY),
                            ("energy_mtoe", 1 + g * power.ENERGY_ELASTICITY)):
                policy.grow_base(c.code, attr, f)
            c.troops_k *= (1 + POP_GROWTH.get(c.code, 0.0) / 24)
        # Дипломатическая пропускная способность не одинакова: у
        # державы больше посольств, переговорщиков и внимания партнёров.
        # И приток, и потолок выводятся из веса страны, а не задаются
        # общей константой — иначе Кипр вёл переговоры наравне с Китаем.
        # Два капитала разной природы. Дипломатический — пропускная
        # способность вовне: посольства, переговорщики, чужое внимание,
        # и он выводится из веса страны. Политический — способность
        # проводить решения внутри, и он выводится из внутреннего
        # состояния: поддержки коалиции и легитимности режима.
        top = max(x.power() for x in self.world.countries.values()) or 1.0
        for c in self.world.countries.values():
            share = CAPITAL_FLOOR + (1.0 - CAPITAL_FLOOR) * (c.power() / top) ** 0.5
            cap_out = 45.0 + 105.0 * share
            c.diplomatic_capital = min(cap_out,
                                       c.diplomatic_capital + CAPITAL_REGEN * share)

            support = sum(b.weight * groups.mood(self.world, c.code, b.id)
                          for b in groups.blocs(self.world, c.code))
            standing = 0.55 * support + 0.45 * c.legitimacy
            cap_in = 40.0 + 110.0 * standing
            gain = CAPITAL_REGEN * standing * 1.4
            # Пока министры воюют, решения идут медленнее.
            gain -= personnel.friction_cost(self.world, c.code) * 0.25
            c.political_capital = min(cap_in, max(0.0, c.political_capital + gain))

        power.recompute(self.world)

    def ai_turn(self) -> list[dict]:
        moves = []
        for code, doc in self.doctrines.items():
            if code == self.player:
                continue
            ev = choose(self.world, doc, self.rng, self.memory, self.turn_no)
            if ev is None:
                continue
            country = self.world.countries[code]
            cost = 12.0 * ev.action.magnitude
            if country.diplomatic_capital < cost:
                continue
            country.diplomatic_capital -= cost
            shocks = propagate(self.world, ev.action)
            apply(self.world, shocks)
            if ev.action.kind == "deal":
                self.sign_best(code, ev.action.target)
            key = (code, ev.action.target, ev.action.kind)
            _, cnt = self.memory.get(key, (0, 0))
            self.memory[key] = (self.turn_no, cnt + 1)
            moves.append({
                "actor": code, "target": ev.action.target,
                "kind": ev.action.kind, "utility": round(ev.utility, 3),
                "shocks": len(shocks),
            })
        return moves

    def sign_best(self, giver: str, receiver: str) -> dict | None:
        """Превратить абстрактный ход «сделка» в конкретное соглашение.

        Из живых вопросов берётся тот, где зона согласия шире всего:
        договариваться проще там, где меньше риск не сойтись. Уровень —
        середина законных исходов.
        """
        best = None
        for tid in deal.TYPES:
            if not deal.live(self.world, giver, receiver, tid):
                continue
            issue = deal.Issue(f"{giver}-{receiver}", deal.TYPES[tid].name_ru,
                               giver, receiver, type_id=tid)
            ceil_ = deal.ratification_ceiling(self.world, issue)
            floor_ = deal.acceptance_with_aspiration(self.world, issue, ceil_)
            pts = deal.feasible(issue, ceil_, floor_)
            if not pts:
                continue
            width = ceil_.hi - floor_.lo
            if best is None or width > best[0]:
                best = (width, tid, pts[len(pts) // 2])
        if best is None:
            return None
        _, tid, level = best
        d = execution.sign(self.world, giver, receiver, tid, level, self.turn_no)
        return {"giver": giver, "receiver": receiver, "type": tid,
                "level": round(level, 1), "horizon": d.horizon}

    def player_action(self, action: Action) -> list:
        shocks = propagate(self.world, action)
        apply(self.world, shocks)
        if action.kind == "deal":
            self.sign_best(action.actor, action.target)
            # проведённая уступка бьёт по тем, кто был против: в
            # следующий раз потолок по этому вопросу будет ниже
            groups.concession_backlash(self.world, action.actor,
                                       getattr(action, "type_id", "tariffs"),
                                       action.magnitude * 100.0)
        self.world.countries[action.actor].diplomatic_capital -= \
            12.0 * action.magnitude
        return shocks

    def clients(self) -> list[dict]:
        """Поведение уровня B: следование за патроном и смена покровителя.

        Клиент не перебирает ходы, он повторяет курс патрона тем точнее,
        чем ниже его автономия. Но если другая держава становится ему
        заметно ближе собственного покровителя, он переходит. Порог
        перехода тем выше, чем сильнее клиент привязан.
        """
        w = self.world
        events: list[dict] = []
        patrons = w.tier("A")
        for c in w.countries.values():
            if c.tier != "B" or not c.patron:
                continue
            # Покровительство стоит денег каждый ход. Перерастянутый
            # патрон перестаёт платить, и связь начинает эродировать —
            # именно так союзы и разваливаются на практике.
            patron = w.countries[c.patron]
            # Держава несёт блок дешевле: у неё для этого институты.
            # Но и блок у неё больше, поэтому равновесие хрупкое.
            top = max(x.power() for x in w.countries.values()) or 1.0
            ease = 0.40 + 0.60 * (1.0 - patron.power() / top)
            fee = CLIENT_UPKEEP * (0.5 + 0.5 * (1.0 - c.autonomy)) * ease
            if patron.diplomatic_capital >= fee:
                patron.diplomatic_capital -= fee
                pull = CLIENT_PULL * (1.0 - c.autonomy)
            else:
                pull = 0.0
                d0 = w.dyad(c.code, c.patron)
                d0.alignment *= 0.975
            for x in w.countries:
                if x in (c.code, c.patron):
                    continue
                gap = w.alignment(c.patron, x) - w.alignment(c.code, x)
                d = w.dyad(c.code, x)
                v = d.alignment + gap * pull
                # Ограничение применяется только к самому притяжению, а
                # не к итогу. Притяжение по цепочке не может поднять
                # связь выше, чем связь с самим патроном, — иначе она
                # уходила в потолок шкалы. Но чужие ухаживания и прочие
                # каналы этим ограничением не зажимаются: иначе никакие
                # усилия игрока не могли бы перевесить.
                ceiling = max(d.alignment, w.alignment(c.code, c.patron))
                d.alignment = max(-1.0, min(1.0, min(v, ceiling) if v > 0 else v))

            # Голосование в ГА следует за покровительством: клиент
            # медленно сползает к позиции патрона. Без этого страна
            # навсегда закреплена за своим идеологическим лагерем, и
            # смена блока ничего не меняет в её поведении.
            c.ideal_point = round(
                c.ideal_point + (patron.ideal_point - c.ideal_point)
                * IDEAL_DRIFT * (1.0 - c.autonomy), 4)

            # Покровителем может стать не всякий, к кому лучше отношения.
            # Нужен вес: кандидат должен быть заметно сильнее клиента, —
            # и досягаемость: далёкий покровитель защищает хуже.
            # Без этих условий Филиппины уходили под Израиль.
            def attractiveness(p: str) -> float:
                # Расстояние штрафует тем слабее, чем сильнее держава:
                # глобальная держава тем и отличается, что дотягивается
                # далеко. При плоском штрафе США систематически
                # проигрывали Германии в Европе и Японии в Азии просто
                # по километрам.
                dist = haversine(w.countries[c.code], w.countries[p])
                reach = 1.0 + 6.0 * w.countries[p].power()
                # Коэффициент 0.20, не 0.35: на шестибалльной шкале
                # больший вес перебивал все остальные слагаемые и делал
                # переход невозможным при любых усилиях.
                gap = abs(w.countries[c.code].ideal_point
                          - w.countries[p].ideal_point)
                # Покровителя заводят ради защиты и денег, поэтому вес
                # кандидата входит напрямую. Без этого слагаемого
                # притягивала любая страна из середины идеологической
                # шкалы: Турция становилась покровителем всем подряд,
                # потому что она ближе всех к каждому.
                return (w.relation(c.code, p)
                        + 1.5 * w.countries[p].power()
                        - 0.020 * dist / reach
                        - 0.20 * gap)

            # Запрет, а не штраф: режим, чья легитимность построена на
            # противостоянии, не уходит под противника ни за какие
            # деньги. Плавного штрафа для этого не хватает — при любом
            # весе он либо пропускал КНДР под США, либо запрещал все
            # переходы вообще.
            def vetoed(p: str) -> bool:
                gap = abs(w.countries[c.code].ideal_point
                          - w.countries[p].ideal_point)
                return c.regime == "autocracy" and gap > IDEO_VETO

            pool = [p for p in patrons
                    if w.countries[p].power() > 2.5 * c.power()
                    and not vetoed(p)]
            if not pool:
                continue
            best = max(pool, key=attractiveness)
            gain = attractiveness(best) - attractiveness(c.patron) \
                if c.patron in patrons else attractiveness(best)
            threshold = SWITCH_BASE + 0.60 * (1.0 - c.autonomy)
            # Выдержка: свежесменившийся клиент не мечется обратно.
            if self.turn_no - self._switched.get(c.code, -99) < SWITCH_COOLDOWN:
                continue
            if best != c.patron and gain > threshold:
                events.append({"client": c.code, "from": c.patron, "to": best,
                               "gain": round(gain, 3)})
                c.patron = best
                self._switched[c.code] = self.turn_no
        return events

    def check_disputes(self) -> list[dict]:
        trend = {c: self.world.countries[c].power() - self._prev_power.get(c, 0)
                 for c in self.world.countries}
        out = []
        for did in self.world.disputes:
            d = self.world.disputes[did]
            if d.claimant not in self.world.countries:
                continue
            a = war_check(self.world, doctrine_of(self.world, self.doctrines, d.claimant),
                          did, trend)
            if a.verdict != "статус-кво":
                out.append({"dispute": d.name_ru, "verdict": a.verdict,
                            "pressure": round(a.pressure, 3)})
        self._prev_power = {c: v.power() for c, v in self.world.countries.items()}
        return out

    def elections(self) -> list[dict]:
        """Выборы там, где они есть, и риск смены власти там, где их нет."""
        out = []
        for code in self.world.countries:
            if politics.due(self.world, code, self.turn_no) or \
                    self.world.countries[code].regime not in politics.TERM:
                ev = politics.hold(self.world, code, self.turn_no, self.rng)
                if ev and ev.get("changed"):
                    out.append(ev)
        for code, doc in self.doctrines.items():
            politics.steer(self.world, code, doc)
        return out

    def settle_promises(self) -> list[dict]:
        """Наступившие сроки. Каждый — выбор должника, а не автоматика."""
        out = []
        for pr in self.world.promises:
            if pr.kept is not None or pr.due > self.turn_no:
                continue
            doc = doctrine_of(self.world, self.doctrines, pr.debtor)
            kept, info = keep_or_break(self.world, doc, pr)
            pr.kept = kept
            out.append(info)
        return out

    def decay(self) -> None:
        for d in self.world.dyads.values():
            d.alignment *= ALIGN_DECAY
            d.threat_ab *= THREAT_DECAY
            d.threat_ba *= THREAT_DECAY

    # --- публичный интерфейс ---

    def tick(self, action: Action | None = None) -> dict:
        self.turn_no += 1
        if "anchors" not in self.off:
            self.anchors()
        player_shocks = self.player_action(action) if action else []
        # Обязательства раньше желаний: содержание блока оплачивается
        # до того, как страна тратит капитал на новые ходы. Иначе плата
        # никогда не доходила — всё уже было израсходовано.
        switches = [] if "clients" in self.off else self.clients()
        moves = [] if "ai" in self.off else self.ai_turn()
        for code, doc in self.doctrines.items():
            if code != self.player:
                policy.ai_adjust(self.world, code, doc)
        policy.apply_macro(self.world)
        pressure = {c: {g: v * policy.MOOD_WEIGHT
                        for g, v in policy.mood_pressure(self.world, c).items()}
                    for c in self.world.countries}
        groups.drift(self.world, {c: GDP_GROWTH.get(c, 0.02) / 12
                                  for c in self.world.countries}, pressure)
        votes = self.elections()
        trend = {c: self.world.countries[c].power() - self._prev_power.get(c, 0)
                 for c in self.world.countries}
        crises = ([] if "escalation" in self.off
                  else escalation.tick(self.world, self.doctrines,
                                       self.turn_no, trend))
        self.world.recent_crises = crises
        settled = [] if "promises" in self.off else self.settle_promises()
        loans = valves.settle_loans(self.world, self.turn_no)
        deliveries = ([] if "deals" in self.off
                      else execution.tick(self.world, self.turn_no))
        flashpoints = self.check_disputes()
        if "decay" not in self.off:
            self.decay()
        intel.decay_all(self.world)
        turn = {
            "date": self.world.date(),
            "player_shocks": len(player_shocks),
            "ai_moves": moves,
            "flashpoints": flashpoints,
            "patron_switches": switches,
            "promises": settled,
            "crises": [c.__dict__ for c in crises],
            "loans": loans,
            "deliveries": deliveries,
            "elections": votes,
        }
        turn["timeline"] = ending.timeline_note(self.world, self.turn_no)
        turn["ending"] = None
        fin = ending.check(self.world, self.player, self.turn_no)
        if fin is not None:
            turn["ending"] = {
                "kind": fin.kind, "title": fin.title, "body": fin.body,
                "divergence": fin.divergence, "highlights": fin.highlights,
                "share": fin.share(),
            }
        self.history.append(turn)
        self.world.advance()
        return turn

    def snapshot(self) -> dict:
        """Срез мира для консольных проверок и демонстрации."""
        return {
            "date": self.world.date(), "player": self.player,
            "countries": [{
                "code": c.code, "name": c.name_ru, "gdp": round(c.gdp_bn),
                "power_band": legible.read("power", c.power()).__dict__,
                "relation_band": (legible.read(
                    "relation", self.world.relation(self.player, c.code)).__dict__
                    if c.code != self.player else None),
            } for c in self.world.countries.values()],
        }
