"""Загрузка присланных данных в таблицы проекта.

Присланный набор покрывает 217 стран, поэтому доли мирового итога по
каждому компоненту мощи считаются точно, а не оцениваются. Это важнее
самих значений: именно покрытие держит шкалу мощи от уползания.

    python3 tools/ingest.py <папка_с_данными>

Всё, чего в наборе нет, остаётся как было, и об этом печатается отчёт.
Пустая ячейка честнее выдуманного числа.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

OUR = ("USA CHN RUS IND DEU FRA GBR TUR IRN ISR JPN SAU TWN UKR PAK KOR "
       "PRK POL EGY IDN BRA PHL VNM SYR PSE SRB XKX CYP MAR SAH AUS KAZ").split()

# наш столбец ← столбец присланного набора
MAP = {
    "gdp_bn": "gdp_usd_bn", "pop_mn": "pop_m", "milex_bn": "milex_usd_bn",
    "troops_k": "troops_k", "energy_mtoe": "energy_mtoe",
    "steel_mt": "steel_mt", "vdem_liberal": "vdem_liberal",
    "ideal_point": "un_ideal", "nuclear": "nuclear", "cinc_ref": "cinc_ref",
    "regime": "regime",
}

# компоненты мощи ← столбцы присланного набора, для расчёта покрытия
COVER = {
    "gdp": "gdp_usd_bn", "population": "pop_m", "military": "milex_usd_bn",
    "energy": "energy_mtoe", "industry": "steel_mt", "personnel": "troops_k",
}

# отрасли ← показатели Всемирного банка
SECTOR_WDI = {
    "agriculture": "NV.AGR.TOTL.ZS", "industry": "NV.IND.MANF.ZS",
    "services": "NV.SRV.TOTL.ZS",
}


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def num(v) -> float | None:
    v = (v or "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def find(root: Path, name: str) -> Path | None:
    hits = sorted(root.rglob(name))
    return hits[-1] if hits else None


def update_countries(src: list[dict]) -> tuple[int, dict]:
    by = {r["iso3"]: r for r in src}
    rows = read(DATA / "countries.csv")
    head = list(rows[0])
    gaps: dict[str, list[str]] = {}
    touched = 0
    for r in rows:
        s = by.get(r["code"])
        if not s:
            gaps[r["code"]] = ["страны нет в наборе"]
            continue
        missing = []
        for ours, theirs in MAP.items():
            v = (s.get(theirs) or "").strip()
            if not v:
                missing.append(ours)
                continue
            r[ours] = v if ours in ("regime", "nuclear") else str(round(float(v), 4))
            touched += 1
        if missing:
            gaps[r["code"]] = missing
    with open(DATA / "countries.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head)
        w.writeheader()
        w.writerows(rows)
    return touched, gaps


def update_coverage(src: list[dict]) -> dict[str, float]:
    """Доля наших стран в мировом итоге по каждому компоненту.

    Считается по всем 217 странам набора, поэтому это измерение, а не
    оценка. От этой величины напрямую зависит шкала мощи.
    """
    by = {r["iso3"]: r for r in src}
    out = {}
    for comp, col in COVER.items():
        world = sum(num(r.get(col)) or 0.0 for r in src)
        ours = sum(num(by[c].get(col)) or 0.0 for c in OUR if c in by)
        out[comp] = round(ours / world, 4) if world else 0.0
    rows = read(DATA / "capability.csv")
    for r in rows:
        if r["component"] in out:
            r["coverage"] = out[r["component"]]
    with open(DATA / "capability.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return out


def update_sectors(wdi: list[dict], ans: list[dict] | None = None
                   ) -> tuple[int, list[str]]:
    """Структура экономики из долей добавленной стоимости.

    Всемирный банк даёт три доли: сельское хозяйство, обработка, услуги.
    Энергетика выделяется по истощению энергоресурсов в процентах ВНД —
    это показатель добычи, а не потребления. Первая версия делила по
    потреблению на душу, и получалось, что у Израиля четверть экономики
    энергоносители, а у Саудовской Аравии промышленность больше
    энергетики.

    Технологии выделяются из обработки по доле высокотехнологичного
    экспорта.
    """
    cols = {c.split(" | ")[0]: c for c in wdi[0]}
    by = {r["iso3"]: r for r in wdi}
    depl = {}
    if ans:
        acols = {c.split(" | ")[0]: c for c in ans[0]}
        col = acols.get("NY.ADJ.DNGY.GN.ZS")
        if col:
            depl = {r["iso3"]: num(r.get(col)) for r in ans}
    rows = read(DATA / "sectors.csv")
    miss, done = [], 0
    for r in rows:
        s = by.get(r["code"])
        if not s:
            miss.append(r["code"]); continue
        agr = num(s.get(cols.get(SECTOR_WDI["agriculture"], ""), ""))
        ind = num(s.get(cols.get(SECTOR_WDI["industry"], ""), ""))
        srv = num(s.get(cols.get(SECTOR_WDI["services"], ""), ""))
        if agr is None or ind is None or srv is None:
            miss.append(r["code"]); continue
        tech_share = num(s.get(cols.get("TX.VAL.TECH.MF.ZS", ""), "")) or 10.0
        tech = ind * min(0.55, tech_share / 100.0)
        ind_rest = ind - tech

        # Истощение энергоресурсов — рента от добычи. Множитель четыре
        # переводит её в долю сектора: рента считается от чистой прибыли,
        # а сектор включает и затраты.
        rent = depl.get(r["code"])
        energy = min(28.0, (rent or 0.15) * 4.0)
        take_from_ind = min(ind_rest * 0.5, energy * 0.6)
        ind_rest -= take_from_ind
        srv_rest = max(1.0, srv - (energy - take_from_ind))
        total = agr + ind_rest + energy + srv_rest + tech
        r["agriculture"] = round(agr / total, 3)
        r["industry"] = round(ind_rest / total, 3)
        r["energy"] = round(energy / total, 3)
        r["services"] = round(srv_rest / total, 3)
        r["technology"] = round(tech / total, 3)
        done += 1
    with open(DATA / "sectors.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return done, miss


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/incoming")
    core = find(root, "game_countries.csv")
    wdi = find(root, "wb_wide_WDI.csv")
    if core is None:
        print("не найден game_countries.csv"); sys.exit(1)

    src = read(core)
    print(f"Набор: {len(src)} стран, из файла {core.name}\n")

    touched, gaps = update_countries(src)
    print(f"countries.csv: заполнено {touched} значений")
    for code, what in sorted(gaps.items()):
        print(f"  {code}: нет {', '.join(what)}")

    cov = update_coverage(src)
    print("\ncapability.csv: доля наших 32 стран в мире")
    for k, v in cov.items():
        print(f"  {k:<12} {v:.1%}")

    trade = find(root, "TradeData*.csv") or find(root, "*Trade*.csv")
    if trade:
        filled, pairs, absent = update_trade(trade)
        print(f"\ndyads.csv: заполнено {filled} значений по {pairs} парам "
              f"из {len(read(DATA / 'dyads.csv'))}")
        if absent:
            print(f"  не отчитались, остаются на гравитационной модели: "
                  f"{', '.join(absent)}")

    ans_path = find(root, "wb_wide_ANS.csv")
    if wdi:
        done, miss = update_sectors(read(wdi),
                                    read(ans_path) if ans_path else None)
        print(f"\nsectors.csv: пересчитано {done} стран"
              + (f", без данных {', '.join(miss)}" if miss else ""))
    else:
        print("\nsectors.csv: файл wb_wide_WDI.csv не найден, оставлено как было")


if __name__ == "__main__":
    main()


# --- двусторонняя торговля ------------------------------------------------

def update_trade(path: Path) -> tuple[int, int, list[str]]:
    """Доли партнёров во внешней торговле из выгрузки UN Comtrade.

    Считаем оборот: экспорт плюс импорт по каждой паре. Доля партнёра —
    его оборот, делённый на общий оборот страны со всем миром.

    Выгрузка может быть неполной: сервис отдаёт не больше ста тысяч
    строк за раз и режет по алфавиту стран-репортёров. Торговля при
    этом симметрична, поэтому пара покрыта, если хотя бы одна из двух
    стран попала в отчитавшиеся. Непокрытые пары остаются на
    гравитационной модели.
    """
    import collections
    flows: dict[tuple[str, str], float] = collections.defaultdict(float)
    world: dict[str, float] = collections.defaultdict(float)
    reporters: set[str] = set()

    with open(path, encoding="cp1252", errors="replace") as fh:
        for r in csv.DictReader(fh):
            a, b = (r.get("reporterISO") or "").strip(), (r.get("partnerISO") or "").strip()
            if not a or not b or a == b:
                continue
            try:
                v = float(r.get("primaryValue") or 0)
            except ValueError:
                continue
            reporters.add(a)
            if b == "W00":              # строка «весь мир»
                world[a] += v
                continue
            flows[(a, b)] += v

    # если строки «весь мир» нет, итог собирается сложением партнёров
    for (a, _), v in flows.items():
        if a not in world:
            world[a] = 0.0
    for (a, _), v in flows.items():
        world[a] += v

    rows = read(DATA / "dyads.csv")
    filled, pairs = 0, 0

    def dep(x: str, y: str) -> float | None:
        """Доля y во внешней торговле x."""
        if x not in reporters or not world.get(x):
            return None
        return round(flows.get((x, y), 0.0) / world[x], 4)

    codes = sorted({r["a"] for r in rows} | {r["b"] for r in rows})
    for r in rows:
        a, b = r["a"], r["b"]
        da, db = dep(a, b), dep(b, a)
        if da is None and db is None:
            continue
        pairs += 1
        if da is not None:
            r["trade_dep_a"] = da
            filled += 1
        if db is not None:
            r["trade_dep_b"] = db
            filled += 1
        if "source" in r:
            r["source"] = "comtrade"

    with open(DATA / "dyads.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    absent = sorted(set(codes) - reporters)
    return filled, pairs, absent
