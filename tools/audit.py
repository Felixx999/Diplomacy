"""Ревизия проекта: что написано, но не подключено.

Ищет три вида дыр. Функции, определённые и ни разу не вызванные, —
кандидаты в мёртвый код. Столбцы данных, которых код не читает, и поля,
которые код ждёт, а в данных их нет. Точки API, к которым интерфейс не
обращается.

    python3 tools/audit.py
"""

from __future__ import annotations

import ast
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = list((ROOT / "engine").glob("*.py")) + list((ROOT / "api").glob("*.py")) \
    + list((ROOT / "tools").glob("*.py"))
ALL = "\n".join(p.read_text(encoding="utf-8") for p in CODE)
WEB = "\n".join(p.read_text(encoding="utf-8")
                for p in (ROOT / "web").glob("*.js"))
# Новый интерфейс (client/, Р-56) зовёт движок и через HTTP, и напрямую
# через Pyodide: его вызовы тоже считаются использованием.
CLIENT = "\n".join(p.read_text(encoding="utf-8")
                   for p in (ROOT / "client" / "src").rglob("*.ts")) \
    if (ROOT / "client" / "src").exists() else ""


def defined_functions():
    out = {}
    for p in CODE:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                out.setdefault(node.name, []).append(p.name)
    return out


# Не мёртвый код: методы обработчика HTTP вызывает библиотека,
# замыкания внутри проверок — сама проверка, свойства — интерфейс.
FRAMEWORK = {"do_GET", "do_POST", "log_message", "main", "title", "width",
             "line", "why", "share", "bar", "label", "done", "available",
             "live_choices", "goodwill", "breaks_at", "obligation",
             "threat_memory", "add_threat", "power", "date", "advance",
             "give", "get", "steps", "grid", "kind", "sign", "base"}


def unused_functions():
    dead = []
    for name, files in defined_functions().items():
        if name in FRAMEWORK or files[0] == "legibility.py":
            continue
        uses = len(re.findall(rf"\b{re.escape(name)}\s*\(", ALL))
        page = len(re.findall(rf"\.{re.escape(name)}\s*\(", CLIENT))
        if uses <= len(files) and not page:   # только определение, вызовов нет
            dead.append((name, files[0]))
    return sorted(dead)


def data_columns():
    rows = []
    for f in sorted((ROOT / "data").glob("*.csv")):
        with open(f, encoding="utf-8") as fh:
            head = next(csv.reader(fh), [])
        # Столбец может читаться и по префиксу: код собирает имя вида
        # "d_" + ключ. Проверяем и целое имя, и его хвост после
        # подчёркивания, иначе ревизия ругается на живые таблицы.
        unread = []
        for c in head:
            if not c:
                continue
            tail = c.split("_", 1)[-1]
            if re.search(rf'["\']{re.escape(c)}["\']', ALL):
                continue
            if "_" in c and re.search(rf'["\']{re.escape(tail)}["\']', ALL):
                continue
            unread.append(c)
        rows.append((f.name, len(head), unread))
    return rows


def api_endpoints():
    routes = sorted(set(re.findall(r'\bpath == "(/api/[a-z_]+)"', ALL)))
    unused = [r for r in routes
              if r.replace("/api", "") not in WEB + CLIENT]
    return routes, unused


def engine_modules():
    mods = sorted(p.stem for p in (ROOT / "engine").glob("*.py")
                  if p.stem != "__init__")
    server = (ROOT / "api" / "server.py").read_text(encoding="utf-8")
    sim = (ROOT / "engine" / "sim.py").read_text(encoding="utf-8")
    orphan = [m for m in mods
              if m not in server and m not in sim and m != "sim"]
    return mods, orphan


def translation_gaps() -> dict:
    """Чего не хватает во втором языке."""
    import csv as _csv
    sys.path.insert(0, str(ROOT))
    from engine import i18n
    gaps = {"phrases": i18n.missing(), "tables": {}}
    for name, field in (("ministries", "name"), ("ministry_sets", "name"),
                        ("directions", "name"), ("groups", "name"),
                        ("issue_types", "name"), ("archetypes", "name"),
                        ("disputes", "name"), ("policies", "name")):
        p = ROOT / "data" / f"{name}.csv"
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as fh:
            rows = list(_csv.DictReader(fh))
        miss = [r.get(f"{field}_ru", "") for r in rows
                if not (r.get(f"{field}_en") or "").strip()]
        if miss:
            gaps["tables"][name] = miss
    return gaps


def csv_integrity() -> list[tuple[str, int, int]]:
    """Строки таблиц, где число полей не совпадает с шапкой.

    Запятая внутри значения без кавычек разносит строку на лишние поля.
    Код, читающий по именам столбцов, это молча терпит, а значение
    обрезается на первой запятой. Так за проект пострадали пять таблиц:
    группы, архетипы, министерства, словарь фраз — и последний показывал
    в английском интерфейсе вторую половину русской строки вместо
    перевода. Проверка ловит это при каждом прогоне ревизии.
    """
    import csv as _csv
    bad = []
    for f in sorted((ROOT / "data").glob("*.csv")):
        with open(f, encoding="utf-8") as fh:
            rd = _csv.reader(fh)
            head = next(rd, [])
            for i, r in enumerate(rd, start=2):
                if r and len(r) != len(head):
                    bad.append((f.name, i, len(r)))
    return bad


def main() -> None:
    print("Ревизия проекта\n")

    dead = unused_functions()
    print(f"Функции без вызовов: {len(dead)}")
    for name, f in dead:
        print(f"  {f:<16} {name}")

    print("\nСтолбцы данных, которых код не читает:")
    holes = 0
    for name, total, unread in data_columns():
        if unread:
            holes += len(unread)
            print(f"  {name:<24} {', '.join(unread)}")
    if not holes:
        print("  нет")

    routes, unused = api_endpoints()
    print(f"\nТочек API: {len(routes)}, не используются интерфейсом: "
          f"{len(unused)}")
    for r in unused:
        print(f"  {r}")

    mods, orphan = engine_modules()
    print(f"\nМодулей движка: {len(mods)}, не подключены нигде: {len(orphan)}")
    for m in orphan:
        print(f"  {m}")

    broken = csv_integrity()
    print(f"\nРазъехавшихся строк в таблицах: {len(broken)}")
    for name, line, n in broken[:8]:
        print(f"  {name}, строка {line}: {n} полей")

    g = translation_gaps()
    n_tr = len(g["phrases"]) + sum(len(v) for v in g["tables"].values())
    print(f"\nБез английского перевода: {n_tr}")
    for k in g["phrases"][:5]:
        print(f"  фраза: {k}")
    for name, miss in g["tables"].items():
        print(f"  {name}: {', '.join(miss[:3])}")

    print(f"\nИтого дыр: {len(dead) + holes + len(unused) + len(orphan) + n_tr + len(broken)}")


if __name__ == "__main__":
    main()
