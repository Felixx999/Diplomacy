"""Первая команда каждой сессии.

Регламент требует начинать с чтения журнала решений. Требование
нарушается легко: кажется, что помнишь состояние проекта, и работа
начинается сразу. Один такой случай уже стоил затёртых файлов данных —
в контейнере лежала готовая реализация трёх пунктов, а сессия началась
с попытки написать их заново.

    python3 tools/status.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * 66)


def decisions() -> list[str]:
    text = (DOCS / "DECISIONS.md").read_text(encoding="utf-8")
    return re.findall(r"^## (Р-\d+ · .+)$", text, re.M)


def backlog() -> tuple[list[str], list[str]]:
    text = (DOCS / "BACKLOG.md").read_text(encoding="utf-8")
    items = re.findall(r"^\*\*(Б-\d+ · [^*]+)\*\*", text, re.M)
    closed = [i for i in items if "закрыт" in i]
    open_ = [i for i in items if "закрыт" not in i]
    return open_, closed


def modules() -> list[tuple[str, int]]:
    out = []
    for p in sorted((ROOT / "engine").glob("*.py")):
        if p.name == "__init__.py":
            continue
        out.append((p.name, len(p.read_text(encoding="utf-8").splitlines())))
    return out


def main() -> None:
    print("Депеша — состояние проекта")

    ds = decisions()
    section(f"Решения: {len(ds)}")
    for d in ds[-5:]:
        print("  " + d)
    if len(ds) > 5:
        print(f"  ...ещё {len(ds) - 5} выше в journal")

    open_, closed = backlog()
    section(f"Очередь: закрыто {len(closed)}, открыто {len(open_)}")
    for i in open_[:8]:
        print("  " + i.strip())
    if len(open_) > 8:
        print(f"  ...ещё {len(open_) - 8}")

    section("Модули движка")
    for name, n in modules():
        print(f"  {name:<14} {n:>4} строк")

    section("Проверка")
    for name, cmd in (("демо", [sys.executable, "run_demo.py"]),
                      ("мёртвые точки", [sys.executable, "tools/deadend.py", "20"])):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        mark = "ок" if r.returncode == 0 else "ОШИБКА"
        print(f"  {name:<16} {mark}")
        if r.returncode != 0:
            print("    " + (r.stderr.strip().splitlines() or ["?"])[-1])

    print("\nПрежде чем писать код: прочитать docs/DECISIONS.md по теме пункта.")


if __name__ == "__main__":
    main()
