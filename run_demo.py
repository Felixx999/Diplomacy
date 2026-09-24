"""Проверочный прогон: трассировка последствий, разбор сделки, 8 ходов."""
import random

from engine.channels import Action, propagate, trace
from engine.deal import Issue, acceptance_floor, explain, ratification_ceiling
from engine.sim import Sim
from engine.state import load

W = 74

def head(t):
    print("\n" + t)
    print("-" * W)

world = load()

head("1. Причинная цепочка: США вводят санкции против Ирана")
sh = propagate(world, Action("USA", "IRN", "sanction", 0.8))
print(trace(sh))

head("2. Двухуровневая игра: Израиль уступает по Западному берегу")
issue = Issue("westbank", "Западный берег", giver="ISR", receiver="IND",
              salience_giver=0.65, salience_receiver=0.40)
c, f = ratification_ceiling(world, issue), acceptance_floor(world, issue)
print(explain(c, f))
rng = random.Random(7)
from engine import intel as _int
_int.seed_levels(world)
lo, hi, lv = _int.estimate(world, "ISR", "IND", f.lo)
print("Игрок видит порог как %.1f..%.1f при осведомлённости %.2f" % (lo, hi, lv))

head("3. Делимость: одна и та же зона, разные типы вопроса")
from engine.deal import TYPES, Range, feasible
ceil_, floor_ = Range(0.0, 45.0), Range(30.0, 100.0)
print("Зона согласия зафиксирована: 30..45. Меняется только предмет торга.")
for tid in ("tariffs", "sanctions", "maritime", "territory", "sovereignty"):
    t = TYPES[tid]
    iss = Issue("x", t.name_ru, "AAA", "BBB", type_id=tid)
    pts = feasible(iss, ceil_, floor_)
    verdict = ", ".join(f"{p:.0f}" for p in pts) if pts else "нет ни одной точки"
    print(f"  {t.name_ru:<28} делимость {t.divisibility:.2f}  →  {verdict}")
print("Суверенитет режется только на ноль и сто. Зона есть, решения нет.")
print("Неделимые ставки конфликтны из-за геометрии, а не из-за вражды.")

head("4. Что стало возможным после разделения relation")
w2 = load()
d = w2.dyad("USA", "RUS")
print("Исходно  США→Россия  отношение %+.3f  выравнивание %+.3f  доверие %.2f  угроза %.2f"
      % (w2.relation("USA","RUS"), w2.alignment("USA","RUS"),
         w2.trust("USA","RUS"), w2.threat("USA","RUS")))
for i in range(4):
    p1 = w2.promise("RUS", "USA", "контроль над вооружениями")
    p1.kept = True
print("Четыре сдержанных обещания по контролю над вооружениями:")
print("         США→Россия  отношение %+.3f  выравнивание %+.3f  доверие %.2f  угроза %.2f"
      % (w2.relation("USA","RUS"), w2.alignment("USA","RUS"),
         w2.trust("USA","RUS"), w2.threat("USA","RUS")))
print("Выравнивание не сдвинулось: интересы как расходились, так и расходятся.")
print("Но обещаниям теперь верят — и это разные вещи, чего одно число не умело.")

head("5. Уровень B: клиенты и покровители")
w3 = load()
print("Клиент          патрон  автономия  порог перехода")
for c in sorted(w3.countries.values(), key=lambda x: x.autonomy):
    if c.tier != "B" or not c.patron:
        continue
    print(f"  {c.name_ru:<14} {c.patron:<6}  {c.autonomy:.2f}      {0.15 + 0.6*(1-c.autonomy):.2f}")
print("Тесно привязанного клиента перекупить дорого, самостоятельного дёшево.")

head("6. Разведка: чужой порог виден интервалом")
import random as _r
from engine import intel as _intel
w4 = load(); _intel.seed_levels(w4); rng4 = _r.Random(5)
truth = 63.4
print(f"Истинный порог партнёра {truth}. Что видит Россия про Китай:")
for spend in (0, 25, 35, 45):
    if spend:
        _intel.invest(w4, "RUS", "CHN", spend, rng4, 1)
    lo, hi, lv = _intel.estimate(w4, "RUS", "CHN", truth)
    note = _intel.misjudged(w4, "RUS", "CHN", (lo + hi) / 2, truth)
    print(f"  вложено {spend:>3}  осведомлённость {lv:.2f}  "
          f"интервал {lo:.1f}..{hi:.1f}"
          + ("   предложение по центру сорвётся" if note else "   центр интервала выше порога"))
print("Свой парламент страна знает точно, чужой — приблизительно.")
print("Отсюда главное явление: сделка срывается из-за неверной оценки.")

head("7. Совокупная мощь: шесть компонентов, доли мирового итога")
from engine import power as _pw
w5 = load()
print(f"Сумма индекса {_pw.scale_total(w5):.3f} — по построению равна среднему покрытию,")
print("поэтому шкала не может уехать сама по себе.\n")
print("Страна   мощь    справка   ВВП   насел  армия  энерг  сталь  личн.состав")
for c in sorted(w5.countries.values(), key=lambda x: -x.cinc)[:5]:
    b = "  ".join(f"{v:.3f}" for _, v in _pw.breakdown(w5, c.code))
    print(f"  {c.code}   {c.cinc:.4f}  {c.cinc_ref:.4f}   {b}")
print("\nПромышленные компоненты возвращают Китаю первое место, как в индексе COW.")
print("Без них расходы на оборону весили треть, и США выходили вперёд.")

head("8. Восемь кварталов за Россию")
sim = Sim(player="RUS", seed=3)
for _ in range(8):
    t = sim.tick()
    fp = "; ".join(f"{x['dispute']}: {x['verdict']}" for x in t["flashpoints"]) or "—"
    sw = "; ".join(f"{x['client']} {x['from']}→{x['to']}" for x in t["patron_switches"])
    print(f"{t['date']}  ходов ИИ: {len(t['ai_moves']):2d}   очаги: {fp}"
          + (f"   переходы: {sw}" if sw else ""))

head("9. Состояние на конец прогона")
snap = sim.snapshot()
for c in sorted(snap["countries"],
                key=lambda x: -x["power_band"]["step"])[:6]:
    b = c["relation_band"]
    print(f"  {c['code']}  {c['power_band']['label']:<16} ВВП {c['gdp']:>6}  "
          + ("сам игрок" if b is None
             else f"{'▰'*b['step']}{'▱'*(b['steps']-b['step'])} {b['label']}"))
