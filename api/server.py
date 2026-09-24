"""Сервер прототипа. Только стандартная библиотека.

    python3 api/server.py
    открыть http://localhost:8000

Каждый раздел из docs/UI.md получает свою точку. Числа наружу уходят
уже разложенными по делениям шкалы: интерфейс не должен знать, как
устроен движок, и не должен уметь округлять.
"""

from __future__ import annotations

import json
import random
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import (  # noqa: E402
    agenda, economy, execution, faces, government as gov, groups, i18n,
    intel,
    legible, package as pkg, personnel as hr, policy, portrait, scene,
    valves,
)
from engine.channels import Action  # noqa: E402
from engine.deal import (  # noqa: E402
    TYPES, Issue, acceptance_with_aspiration, failure_reason, feasible,
    live, ratification_ceiling, stake,
)
from engine import save as savegame  # noqa: E402
from engine.sim import Sim  # noqa: E402

SAVE = ROOT / "savegame.json"

WEB = ROOT / "web"
SIM = Sim(player="IND", seed=3)
RNG = random.Random(9)
POOLS: dict[str, list] = {}
CLIMATE_RU = {"hostile": "спор", "trade": "торг", "friendly": "союз"}


LANG = {"v": "ru"}          # выбранный язык, общий на сессию


def lang() -> str:
    return LANG["v"]


def band(scale, value):
    return legible.read(scale, value, lang()).__dict__


def cn(code: str) -> str:
    """Название страны на выбранном языке."""
    c = SIM.world.countries[code]
    return (c.name_en or c.name_ru) if lang() == "en" else c.name_ru


REGIME_RU = {"democracy": "демократия", "hybrid": "гибридный режим",
             "autocracy": "автократия"}
REGIME_EN = {"democracy": "democracy", "hybrid": "hybrid regime",
             "autocracy": "autocracy"}


def regime(r: str) -> str:
    return (REGIME_EN if lang() == "en" else REGIME_RU).get(r, r)


def name_of(row_like, field="name") -> str:
    """Название сущности на выбранном языке."""
    if lang() == "en":
        v = getattr(row_like, f"{field}_en", "") or ""
        if v.strip():
            return v
    return getattr(row_like, f"{field}_ru", "") or getattr(row_like, field, "")


def person_pool(code):
    if code not in POOLS:
        POOLS[code] = hr.pool(SIM.world, code)
    return POOLS[code]


def person_card(p, fit, why):
    return {"id": p.name,
            "name": (p.name_en or p.name) if lang() == "en" else p.name, "archetype": name_of(p.archetype),
            "face": portrait.portrait(p.name, p.archetype.id, p.country, 64, p.look),
            "note": p.archetype.note, "fit": band("mood", fit),
            "competence": band("mood", p.competence),
            "loyalty": band("mood", p.loyalty), "why": why}


def graph():
    w, me = SIM.world, SIM.player
    nodes = [{"code": c.code, "name": cn(c.code), "lat": c.lat, "lon": c.lon,
              "flag_url": portrait.flag_url(c.code),
              "tier": c.tier, "me": c.code == me,
              "power": band("power", c.power()),
              "relation": None if c.code == me
              else band("relation", w.relation(me, c.code))}
             for c in w.countries.values()]
    edges = []
    for d in w.dyads.values():
        r = w.relation(d.a, d.b)
        if abs(r) < 0.25 and d.alliance == "none":
            continue
        edges.append({"a": d.a, "b": d.b, "tone": "warm" if r >= 0 else "cold",
                      "weight": round(min(1.0, (d.trade_dep_a + d.trade_dep_b) * 6), 2),
                      "alliance": d.alliance, "strength": round(abs(r), 2)})
    return {"nodes": nodes, "edges": edges}


def openings():
    """Первый экран: вопрос, а не меню выбора страны.

    Позиции сформулированы так, как их формулирует человек в разговоре.
    Выбор запускает партию и становится первым ходом игрока.
    """
    import csv as _csv
    rows = []
    with open(ROOT / "data" / "openings.csv", encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            c = SIM.world.countries[r["country"]]
            rows.append({"id": r["id"], "label": r["label"], "body": r["body"],
                         "country": r["country"], "country_name": cn(r["country"]),
                         "note": r["note"], "effect": r["effect"]})
    return {"question": "С чего начнёте?", "options": rows}


def restore() -> dict:
    """Загрузить сохранённую партию."""
    global SIM, POOLS
    if not SAVE.exists():
        return {"ok": False, "note": "сохранения нет"}
    SIM = savegame.load(SAVE)
    POOLS = {}
    return {"ok": True, "note": "партия загружена"}


def start(choice: str) -> dict:
    """Запустить партию с выбранной позиции."""
    global SIM, POOLS
    import csv as _csv
    row = None
    with open(ROOT / "data" / "openings.csv", encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            if r["id"] == choice:
                row = r
    if row is None:
        return {"ok": False}
    SIM = Sim(player=row["country"], seed=3)
    POOLS = {}
    w, me = SIM.world, SIM.player
    eff = row["effect"]
    if eff == "open_talks":
        gov.set_effort(w, me, {"diplomatic": 55, "military": 20,
                               "economic": 20, "cultural": 5})
    elif eff == "open_arm":
        gov.set_effort(w, me, {"diplomatic": 15, "military": 55,
                               "economic": 25, "cultural": 5})
    elif eff == "open_trade":
        gov.set_effort(w, me, {"diplomatic": 20, "military": 15,
                               "economic": 60, "cultural": 5})
    elif eff == "open_bloc":
        gov.set_effort(w, me, {"diplomatic": 30, "military": 40,
                               "economic": 20, "cultural": 10})
    return {"ok": True, "player": me, "country": cn(me)}


def search(q: str) -> dict:
    """Единый поиск по всему, что есть в игре.

    В Democracy 4 поиск — то, что делает глубину переносимой: любой
    рычаг, группа или показатель находятся набором пары букв, вместо
    хождения по вкладкам. Здесь то же: страны, министерства, рычаги,
    группы, типы вопросов, действующие соглашения.

    Каждый ответ несёт адрес перехода, поэтому от строки поиска до
    нужного экрана всегда один клик.
    """
    w, me = SIM.world, SIM.player
    q = (q or "").strip().lower()
    if len(q) < 2:
        return {"query": q, "results": []}
    out = []

    def add(kind, label, note, tab, arg=None, icon=None, score=0):
        out.append({"kind": kind, "label": label, "note": note,
                    "tab": tab, "arg": arg, "icon": icon, "score": score})

    def hit(text: str) -> int:
        t = (text or "").lower()
        if t.startswith(q):
            return 3
        if q in t:
            return 2
        return 0

    for c in w.countries.values():
        sc = max(hit(c.name_ru), hit(c.code))
        if sc:
            add(i18n.t("kind.country", lang()), cn(c.code),
                f"{c.regime} · {legible.read('power', c.power()).label}",
                "doss", c.code, portrait.flag_url(c.code), sc)

    for m in gov.ministries_of(me).values():
        sc = max(hit(m.name_ru), hit(m.short))
        if sc:
            held = w.ministers.get((me, m.id))
            add(i18n.t("kind.ministry", lang()), name_of(m, "short"),
                held[0].title_in(lang()) if held else "без руководителя",
                "cabinet", m.id, portrait.icon("ministry", m.id), sc)

    own = gov.ministries_of(me)
    for pol in policy.POLICIES.values():
        if pol.ministry not in own:
            continue
        sc = hit(pol.name_ru)
        if sc:
            add(i18n.t("kind.lever", lang()), name_of(pol), name_of(own[pol.ministry], "short"), "course",
                pol.id, portrait.icon("ministry", pol.ministry), sc)

    for g in groups.GROUPS.values():
        sc = hit(g.name_ru)
        if sc:
            add(i18n.t("kind.group", lang()), name_of(g),
                legible.read("mood", groups.mood(w, me, g.id)).label,
                "course", g.id, portrait.icon("group", g.id), sc)

    for tid, t in TYPES.items():
        sc = hit(t.name_ru)
        if sc:
            add(i18n.t("kind.issue", lang()), name_of(t),
                f"делимость {t.divisibility:.0%}", "doss", None,
                portrait.icon("issue", tid), sc)

    for p in w.ministers.values():
        sc = hit(p[0].name)
        if sc:
            add(i18n.t("kind.person", lang()), p[0].name, name_of(p[0].archetype),
                "cabinet", None, None, sc)

    for d in execution.active(w, me):
        sc = max(hit(d.label(w)), hit(TYPES[d.type_id].name_ru))
        if sc:
            other = d.receiver if d.giver == me else d.giver
            add(i18n.t("kind.deal", lang()), name_of(TYPES[d.type_id]),
                f"{cn(other)}, {d.delivered:.0%}",
                "doss", other, portrait.icon("issue", d.type_id), sc)

    out.sort(key=lambda x: (-x["score"], x["label"]))
    return {"query": q, "results": out[:12]}


CLIP_FOR_THEME_ID = {"crisis": "crisis", "talks": "talks", "deal": "signing",
                     "cabinet": "oath", "home": "speech"}


def _with_clip(sc: dict) -> dict:
    """Подставить ролик по ключу темы сцены.

    По ключу, а не по названию: название переводится, и после
    переключения на английский ролики переставали находиться.
    """
    sc["clip"] = faces.clip_url_by_kind(
        CLIP_FOR_THEME_ID.get(sc.get("theme_id", ""), ""))
    return sc


def dashboard():
    w, me = SIM.world, SIM.player
    c = w.countries[me]
    items = agenda.build(w, me, SIM.turn_no, lang())
    coalition = sum(b.weight * groups.mood(w, me, b.id)
                    for b in groups.blocs(w, me))
    econ = economy.profile(w, me)
    return {
        "date": w.date(), "turn": SIM.turn_no, "player": me,
        "country": cn(me),
        "flag_url": portrait.flag_url(me),
        "state": [
            {"label": "влияние дома", "icon": portrait.icon("scale", "capital"),
             **band("capital", c.political_capital)},
            {"label": "дипломатия", **band("capital", c.diplomatic_capital)},
            {"label": "коалиция", **band("support", coalition)},
            {"label": "курс валюты", **band("capital", econ["currency"])},
            {"label": "вес страны", "icon": portrait.icon("scale", "power"),
             **band("power", c.power())},
        ],
        "ambience": scene.ambience(w, me, lang()),
        "agenda": [{"id": i.id, "area": i.area_label or i.area,
                    "title": i.title, "body": i.body,
                    "source": i.source_label or i.source,
                    "urgency": round(i.urgency, 2),
                    "scene": _with_clip(scene.compose(w, me, i, lang())),
                    "choices": [{"label": ch.label, "hint": ch.hint,
                                 "effect": ch.effect, "params": ch.params,
                                 "blocked": ch.blocked} for ch in i.choices]}
                   for i in items],
        "graph": graph(),
        "hot": [{"name": name_of(d),
                 "stage": i18n.t("esc.stage." + agenda.STAGE_KEY.get(
                     __import__("engine.escalation",
                                fromlist=["x"]).stage(d.heat), "calm"), lang()),
                 **band("threat", d.heat)}
                for d in __import__("engine.escalation",
                                    fromlist=["x"]).hottest(w, me)[:3]],
    }


def cabinet():
    w, me = SIM.world, SIM.player
    rows = []
    for m in gov.cabinet(w, me, lang()):
        held = w.ministers.get((me, m["id"]))
        rows.append({"id": m["id"], "name": m["name"], "short": m["short"],
                     "note": m["note"], "minister": m["minister"],
                     "icon": portrait.icon("ministry", m["id"]),
                     "face": (portrait.portrait(held[0].name, held[0].archetype.id,
                                                me, 40, held[0].look)
                              if held else None),
                     "fit": band("mood", m["fit"]) if m["fit"] is not None else None,
                     "precision": band("mood", 1.0 - m["spread"]),
                     "levers": len(m["levers"])})
    return {"ministries": rows,
            "vacant": len([r for r in rows if not r["minister"]]),
            "capital": band("capital", w.countries[me].political_capital)}


def course():
    w, me = SIM.world, SIM.player
    out = []
    for m in gov.cabinet(w, me, lang()):
        levers = []
        for pid, name, lvl in m["levers"]:
            name = name_of(policy.POLICIES[pid]) if pid in policy.POLICIES else name
            stances = policy.POSITIONS.get(pid, {})
            cares = sorted(stances.items(), key=lambda kv: -abs(kv[1]))[:3]
            levers.append({"id": pid, "name": name, "value": round(lvl * 100),
                           "cares": [{"group": name_of(groups.GROUPS[g]),
                                      "for": st > 0}
                                     for g, st in cares if g in groups.GROUPS]})
        if levers:
            mi = gov.ministries_of(me).get(m["id"])
            out.append({"id": m["id"],
                        "name": name_of(mi, "short") if mi else m["short"],
                        "icon": portrait.icon("ministry", m["id"]),
                        "minister": m["minister"], "levers": levers})
    return {"branches": out,
            "capital": band("capital", w.countries[me].political_capital)}


def world_panel():
    w, me = SIM.world, SIM.player
    dirs = [{"id": d["id"],
             "name": name_of(gov.DIRECTIONS[d["id"]]) if d["id"] in gov.DIRECTIONS else d["name"],
             "note": d["note"],
             "icon": portrait.icon("direction", d["id"]),
             "effort": round(d["effort"]), "ministry": d["ministry"],
             "works": d["works"], "blocked": d["blocked"],
             "unlocks": d["unlocks"]} for d in gov.foreign_panel(w, me)]
    posts = []
    for code in w.others(me):
        held = w.ambassadors.get((me, code))
        posts.append({"code": code, "name": cn(code),
                      "flag_url": portrait.flag_url(code),
                      "climate": CLIMATE_RU[hr.climate(w, me, code)],
                      "envoy": held[0].title_in(lang()) if held else None,
                      "face": (portrait.portrait(held[0].name,
                               held[0].archetype.id, me, 32, held[0].look)
                               if held else None),
                      "fit": band("mood", held[1]) if held else None,
                      "relation": band("relation", w.relation(me, code))})
    # Столицы с послами наверх: иначе при обрезке списка они
    # оказывались в отрезанной части, и раздел выглядел пустым.
    posts.sort(key=lambda x: (x["envoy"] is None, -x["relation"]["step"]))
    blocs = []
    for patron in sorted({c.patron for c in w.countries.values() if c.patron}):
        n = sum(1 for c in w.countries.values() if c.patron == patron)
        blocs.append({"patron": cn(patron),
                      "clients": n, "mine": patron == me,
                      "emblem": portrait.bloc_emblem(patron, "defense", 34)})
    blocs.sort(key=lambda x: -x["clients"])
    return {"directions": dirs, "posts": posts[:18], "blocs": blocs[:6],
            "vacant": len(gov.vacancies(w, me))}


def recognition_note(code: str) -> str | None:
    """Для спорных образований — сколько стран признаёт претензию."""
    for d in SIM.world.disputes.values():
        if d.claimant == code or d.controller == code:
            if 0.02 < d.recognition_share < 0.9:
                return (f"статус оспаривается: претензию признаёт "
                        f"{d.recognition_share:.0%} государств")
    return None


def dossier(code):
    w, me = SIM.world, SIM.player
    c = w.countries[code]
    econ = economy.profile(w, code)
    issues = []
    for tid in TYPES:
        if not live(w, me, code, tid):
            continue
        issue = Issue("x", TYPES[tid].name_ru, me, code, type_id=tid)
        ceil_ = ratification_ceiling(w, issue)
        floor_ = acceptance_with_aspiration(w, issue, ceil_)
        issues.append({"id": tid, "name": name_of(TYPES[tid]),
                       "icon": portrait.icon("issue", tid),
                       "zone": band("zone", max(0.0, ceil_.hi - floor_.lo))})
    disputes = [{"name": name_of(d), "heat": band("threat", d.heat),
                 "we_hold": d.controller == me}
                for d in w.disputes.values()
                if {d.controller, d.claimant} == {me, code}]
    deals = [{"label": d.label(w), "progress": round(d.delivered * 100)}
             for d in execution.active(w, me) if code in (d.giver, d.receiver)]
    held = w.ambassadors.get((me, code))
    return {"code": code, "name": cn(code), "regime": regime(c.regime),
            "flag_url": portrait.flag_url(code),
            "flag": portrait.flag(code, 34, 22),
            "recognition": recognition_note(code),
            "terrain": portrait.terrain(code, 320, 30),
            "power": band("power", c.power()),
            "power_parts": [{"name": n, "share": round(v * 100, 1)}
                            for n, v in __import__(
                                "engine.power", fromlist=["x"]).breakdown(w, code)],
            "economy": {"gdp": econ["gdp"], "per_capita": econ["gdp_per_capita"],
                        "currency": econ["currency"], "balance": econ["balance"],
                        "basket": [{"name": n, "share": round(v * 100)}
                                   for n, v in econ["basket"]],
                        "to": econ["to"][:4], "from": econ["from"][:4]},
            "bands": {"alignment": band("alignment", w.alignment(me, code)),
                      "threat": band("threat", w.threat(me, code)),
                      "trust": band("trust", w.trust(me, code)),
                      "intel": band("intel", intel.level(w, me, code))},
            "issues": issues, "disputes": disputes, "deals": deals,
            "envoy": held[0].title_in(lang()) if held else None}


def package_view(other: str, type_id: str, level: float) -> dict:
    """Пакет: трудная уступка плюс встречная, делающая её проходимой."""
    w, me = SIM.world, SIM.player
    solo = pkg.solo_fails(w, me, other, type_id, level)
    p = pkg.sweeten(w, me, other, type_id, level)
    if p is None:
        return {"ok": False, "solo_fails": solo,
                "note": "встречной уступки, которая сделала бы пакет "
                        "проходимым, не нашлось"}
    verdict = pkg.ratify_package(w, me, p)
    ok, why = pkg.workable(w, p)
    return {
        "ok": ok, "solo_fails": solo, "why": why,
        "label": p.label(w),
        "legs": [{"type": l.type_id, "name": l.name(),
                  "giver": cn(l.giver),
                  "mine": l.giver == me, "level": round(l.level),
                  "icon": portrait.icon("issue", l.type_id)} for l in p.legs],
        "home": verdict.why(),
        "detail": [{"group": n, "net": round(v, 2), "stays": st}
                   for n, v, st in verdict.detail],
        "value_me": pkg.value_for(w, me, p),
        "value_them": pkg.value_for(w, other, p),
    }


def negotiation(other, type_id):
    w, me = SIM.world, SIM.player
    avail = [t for t in TYPES if live(w, me, other, t)]
    if type_id not in avail:
        # Открываем не первый попавшийся вопрос, а тот, где вообще есть о
        # чём говорить: иначе демонстрация начиналась с мёртвого экрана.
        best, chosen = -1.0, (avail[0] if avail else "tariffs")
        for t in avail:
            iss = Issue("x", TYPES[t].name_ru, me, other, type_id=t)
            c = ratification_ceiling(w, iss)
            f = acceptance_with_aspiration(w, iss, c)
            if feasible(iss, c, f) and c.hi - f.lo > best:
                best, chosen = c.hi - f.lo, t
        type_id = chosen
    kind = TYPES[type_id]
    issue = Issue(f"{me}-{other}", kind.name_ru, me, other, type_id=kind.id)
    ceil_ = ratification_ceiling(w, issue)
    floor_ = acceptance_with_aspiration(w, issue, ceil_)
    pts = feasible(issue, ceil_, floor_)
    lo, hi, lv = intel.estimate(w, me, other, floor_.lo)
    r = groups.ratify(w, me, kind.id)
    return {"other": other, "name": cn(other),
            "type": kind.id, "type_name": name_of(kind),
            "types": [[t, name_of(TYPES[t]), portrait.icon("issue", t)]
                      for t in avail],
            "ceiling": round(ceil_.hi), "est_lo": round(lo), "est_hi": round(hi),
            "points": [round(p) for p in pts[:40]],
            "reason": failure_reason(issue, ceil_, floor_),
            "misjudged": intel.misjudged(w, me, other,
                                         (lo + hi) / 2, floor_.lo),
            "zone": band("zone", max(0.0, ceil_.hi - floor_.lo)),
            "intel": band("intel", lv),
            "intel_cost": round(intel.cost_to_gain(lv, 0.12)),
            "opposition": [{"group": n, "leaves_at": round(l)}
                           for n, l, _ in r.order],
            "why": r.why()}


def receipt(turn):
    """Квитанция: чего хотели, что вышло, кто заплатил.

    Не сводка событий, а разбор. Формулировка «не получилось» запрещена
    решением о тоне: вместо неё называется ограничение, которое
    сработало.
    """
    w, me = SIM.world, SIM.player
    paid, gained = [], []
    for b in groups.blocs(w, me):
        m = groups.mood(w, me, b.id)
        prev = w.agenda_prev.get(f"mood:{b.id}", m)
        w.agenda_prev[f"mood:{b.id}"] = m
        if m - prev < -0.012:
            paid.append(name_of(b))
        elif m - prev > 0.012:
            gained.append(name_of(b))
    lines = []
    for m in turn.get("ai_moves", [])[:4]:
        lines.append(i18n.t("rc.move", lang(), actor=cn(m["actor"]),
                            kind=i18n.t("act." + m["kind"], lang()),
                            target=cn(m["target"])))
    for d in turn.get("deliveries", [])[:3]:
        lines.append(f"{d['deal']} — доставлено {round(d['progress'] * 100)}%")
    for p in turn.get("promises", [])[:3]:
        lines.append(i18n.t("rc.kept" if p["kept"] else "rc.broken", lang(),
                            who=cn(p["creditor"])))
    for s in turn.get("patron_switches", []):
        lines.append(i18n.t("rc.switch", lang(), who=cn(s["client"])))
    for f in turn.get("flashpoints", [])[:2]:
        lines.append(f"{f['dispute']}: {f['verdict']}")
    # Направление изменения словом, не числом
    moves = []
    for b in groups.blocs(w, me)[:4]:
        m = groups.mood(w, me, b.id)
        prev = w.agenda_prev.get(f"shown:{b.id}", m)
        w.agenda_prev[f"shown:{b.id}"] = m
        if abs(m - prev) > 0.004:
            moves.append(f"{name_of(b).lower()}: "
                         f"{legible.describe('mood', prev, m, lang())}")
    who = []
    if gained:
        who.append("довольны: " + ", ".join(gained[:3]).lower())
    if paid:
        who.append("заплатили: " + ", ".join(paid[:3]).lower())
    return {"date": turn.get("date"),
            "lines": lines or ["Месяц прошёл тихо."],
            "who": who, "moves": moves[:4]}


def act(payload):
    w, me = SIM.world, SIM.player
    kind = payload.get("effect", "noop")
    p = payload.get("params", {}) or {}
    if kind == "sign_package":
        p = pkg.sweeten(w, me, p["other"], p["type"], float(p.get("level", 60)))
        if p is None:
            return {"ok": False, "note": "пакет не собрался"}
        for leg in p.legs:
            execution.sign(w, leg.giver,
                           p.b if leg.giver == p.a else p.a,
                           leg.type_id, leg.level, SIM.turn_no)
        return {"ok": True, "note": "пакет подписан"}
    if kind == "cancel_deal":
        for d in execution.active(w, me):
            if d.type_id == p.get("deal") or d.receiver == p.get("other"):
                r = execution.cancel(w, d)
                return {"ok": "error" not in r, "note": r.get("error")
                        or f"соглашение расторгнуто, доверие упало"}
        return {"ok": False, "note": "нечего расторгать"}
    if kind == "sign":
        execution.sign(w, me, p["other"], p["type"], float(p["level"]), SIM.turn_no)
        return {"ok": True, "note": "соглашение подписано"}
    if kind == "spy":
        r = intel.invest(w, me, p["other"], float(p.get("spend", 25)), RNG, SIM.turn_no)
        return {"ok": True, "note": f"осведомлённость {r['after']}"}
    if kind == "breach":
        return {"ok": True, **valves.breach(w, me, p["creditor"])}
    if kind == "keep":
        for pr in w.promises:
            if pr.debtor == me and pr.creditor == p["creditor"] and pr.kept is None:
                pr.kept = True
                w.countries[me].political_capital -= pr.cost
                break
        return {"ok": True, "note": "обещание исполнено"}
    if kind in ("aid", "negotiate", "hold", "concede"):
        SIM.player_action(Action(me, p.get("other", me),
                                 "aid" if kind == "aid" else "deal", 0.5))
        return {"ok": True, "note": "ход сделан"}
    if kind == "drop_client":
        for o in valves.assets(w, me):
            if o.ref == p.get("other"):
                return {"ok": True, **valves.sell(w, me, o)}
        return {"ok": False, "note": "не найдено"}
    if kind == "sell_asset":
        opts = valves.assets(w, me)
        return ({"ok": True, **valves.sell(w, me, opts[0])} if opts
                else {"ok": False, "note": "продавать нечего"})
    if kind == "borrow":
        return {"ok": True, **valves.borrow(w, me, SIM.turn_no)}
    if kind == "back_minister":
        w.ministers.pop((me, p["drop"]), None)
        w.countries[me].political_capital -= 6.0
        return {"ok": True, "note": "министр отправлен в отставку"}
    if kind == "appoint":
        person = next((x for x in person_pool(me) if x.name == p["who"]), None)
        if not person:
            return {"ok": False, "note": "нет такого кандидата"}
        return {"ok": True, **hr.appoint(w, me, p["ministry"], person)}
    if kind == "send_envoy":
        person = next((x for x in person_pool(me) if x.name == p["who"]), None)
        if not person:
            return {"ok": False, "note": "нет такого кандидата"}
        return {"ok": True, **hr.send(w, me, p["other"], person)}
    if kind == "set_policy":
        want = float(p["value"]) / 100.0
        policy.set_level(w, me, p["id"], want, RNG)
        got = policy.level(w, me, p["id"])
        w.countries[me].political_capital -= 2.0
        gap = abs(got - want)
        note = ("курс изменён" if gap < 0.02
                else f"провели не совсем как задумано: вышло {round(got * 100)}")
        return {"ok": True, "note": note, "actual": round(got * 100)}
    if kind == "set_effort":
        return {"ok": True, "effort": gov.set_effort(w, me, p["weights"])}
    return {"ok": True, "note": "решение отложено"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, code=200, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._send((WEB / "index.html").read_bytes(), ctype="text/html")
            if u.path.startswith(("/faces/", "/clips/", "/sfx/", "/music/")):
                f = WEB / u.path.lstrip("/")
                if f.exists() and f.is_file():
                    kind = ("image/jpeg" if f.suffix in (".jpg", ".jpeg")
                            else "image/png" if f.suffix == ".png"
                            else "video/mp4" if f.suffix == ".mp4"
                            else "audio/wav" if f.suffix == ".wav"
                            else "image/svg+xml" if f.suffix == ".svg"
                            else "audio/ogg" if f.suffix == ".ogg"
                            else "application/octet-stream")
                    return self._send(f.read_bytes(), ctype=kind)
                return self._send({"error": "нет файла"}, 404)
            if u.path.startswith("/icons/") and u.path.endswith(".svg"):
                f = WEB / "icons" / Path(u.path).name
                if f.exists():
                    return self._send(f.read_bytes(), ctype="image/svg+xml")
                return self._send({"error": "нет иконки"}, 404)
            if u.path.startswith("/flags/") and u.path.endswith(".svg"):
                f = WEB / "flags" / Path(u.path).name
                if f.exists():
                    return self._send(f.read_bytes(), ctype="image/svg+xml")
                return self._send({"error": "нет флага"}, 404)
            if u.path.endswith(".css"):
                return self._send((WEB / u.path.lstrip("/")).read_bytes(), ctype="text/css")
            if u.path.endswith(".js"):
                return self._send((WEB / u.path.lstrip("/")).read_bytes(),
                                  ctype="application/javascript")
            if u.path == "/api/openings":
                return self._send(openings())
            if u.path == "/api/lang":
                LANG["v"] = i18n.norm(q.get("to", ["ru"])[0])
                return self._send({"lang": LANG["v"],
                                   "strings": {k: i18n.t(k, LANG["v"])
                                               for k in i18n.table()}})
            if u.path == "/api/strings":
                return self._send({"lang": lang(),
                                   "strings": {k: i18n.t(k, lang())
                                               for k in i18n.table()}})
            if u.path == "/api/search":
                return self._send(search(q.get("q", [""])[0]))
            if u.path == "/api/dashboard":
                return self._send(dashboard())
            if u.path == "/api/cabinet":
                return self._send(cabinet())
            if u.path == "/api/course":
                return self._send(course())
            if u.path == "/api/world":
                return self._send(world_panel())
            if u.path == "/api/dossier":
                return self._send(dossier(q.get("code", ["USA"])[0]))
            if u.path == "/api/package":
                return self._send(package_view(
                    q.get("other", ["USA"])[0], q.get("type", ["territory"])[0],
                    float(q.get("level", ["60"])[0])))
            if u.path == "/api/negotiation":
                # Пустой тип означает «выбери сам лучший», а не тарифы.
                return self._send(negotiation(q.get("other", ["USA"])[0],
                                              q.get("type", [""])[0]))
            if u.path == "/api/shortlist":
                w, me = SIM.world, SIM.player
                m = q.get("ministry", [None])[0]
                if m:
                    rows = [person_card(x["person"], x["fit"], x["why"])
                            for x in gov.shortlist(w, me, m, 4)]
                else:
                    t = q.get("target", ["USA"])[0]
                    best, bfit, bwhy = hr.best_posting(w, me, t)
                    rows = [person_card(best, bfit, "лучший из резерва: " + bwhy)]
                    for pp in person_pool(me):
                        if pp.name == best.name:
                            continue
                        fit, why = hr.ambassador_fit(w, pp, t)
                        rows.append(person_card(pp, fit, why))
                    rows = rows[:1] + sorted(rows[1:],
                                             key=lambda x: -x["fit"]["step"])[:3]
                return self._send({"candidates": rows})
        except Exception as e:
            return self._send({"error": str(e)}, 500)
        self._send({"error": "не найдено"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n) or b"{}")
        try:
            if u.path == "/api/save":
                savegame.save(SIM, SAVE)
                return self._send({"ok": True, "note": "партия сохранена"})
            if u.path == "/api/load":
                return self._send(restore())
            if u.path == "/api/start":
                return self._send(start(payload.get("choice", "")))
            if u.path == "/api/act":
                return self._send(act(payload))
            if u.path == "/api/tick":
                turn = SIM.tick()
                return self._send({"turn": turn, "receipt": receipt(turn),
                                   "timeline": turn.get("timeline"),
                                   "ending": turn.get("ending")})
        except Exception as e:
            return self._send({"error": str(e)}, 500)
        self._send({"error": "не найдено"}, 404)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Депеша слушает http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()
