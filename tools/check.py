"""Одна команда вместо шести.

Запускать перед каждым коммитом. Проверки движка были и раньше, но
интерфейс не открывала ни одна — и синтаксическая ошибка в `app.js`
прожила несколько сессий, пока страница вовсе не загружалась. Поэтому
сюда входит и проверка разметки: скрипты разбираются, страница
поднимается в эмуляторе браузера и отвечает на действия.

    python3 tools/check.py           полный прогон
    python3 tools/check.py --fast    без долгих прогонов и без интерфейса
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAST = "--fast" in sys.argv


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def run(cmd: list[str], cwd: Path = ROOT, timeout: int = 600):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       timeout=timeout)
    return r.returncode == 0, (r.stdout + r.stderr)


def tail(text: str, n: int = 2) -> str:
    lines = [x for x in text.strip().splitlines() if x.strip()]
    return " | ".join(lines[-n:])[:150]


def node_available() -> bool:
    return shutil.which("node") is not None


def jsdom_path() -> str | None:
    """jsdom нужен только для проверки интерфейса и ставится отдельно."""
    for base in (ROOT / "node_modules", Path("/tmp/smoke/node_modules")):
        if (base / "jsdom").exists():
            return str(base)
    return None


def main() -> None:
    checks: list[tuple[str, bool, str]] = []

    def add(name, ok, note=""):
        checks.append((name, ok, note))
        mark = "ок    " if ok else "ОШИБКА"
        print(f"  {mark} {name}" + (f" — {note}" if note else ""))

    print("Проверка проекта\n")
    print("движок")
    ok, out = run([sys.executable, "run_demo.py"])
    add("демонстрационный прогон", ok, "" if ok else tail(out))

    ok, out = run([sys.executable, "tools/deadend.py", "24" if FAST else "68"])
    add("у игрока всегда есть ход", ok and "мёртвых ходов 0" in out,
        "" if ok else tail(out))

    ok, out = run([sys.executable, "tools/legibility.py"])
    add("механики заметны игроку",
        ok and "Все проверенные механики заметны" in out, tail(out, 1))

    if not FAST:
        ok, out = run([sys.executable, "tools/macro.py", "192"])
        add("макропоказатели живые", ok, tail(out, 1))

    ok, out = run([sys.executable, "tools/audit.py"])
    holes = [l for l in out.splitlines() if l.startswith("Итого дыр")]
    broken = [l for l in out.splitlines() if l.startswith("Разъехавшихся")]
    no_tr = [l for l in out.splitlines() if l.startswith("Без английского")]
    add("ревизия проходит", ok and "Разъехавшихся строк в таблицах: 0" in out,
        " ".join(broken + no_tr + holes))

    print("\nинтерфейс")
    if not node_available():
        add("разметка разбирается", False, "node не установлен, проверка пропущена")
    else:
        bad = []
        for js in sorted((ROOT / "web").glob("*.js")):
            k, o = run(["node", "--check", str(js)])
            if not k:
                bad.append(f"{js.name}: {tail(o, 1)}")
        add("скрипты разбираются", not bad, "; ".join(bad))

        mods = jsdom_path()
        if FAST:
            pass
        elif not mods:
            add("страница работает", False,
                "нет jsdom: npm install jsdom (нужен только для этой проверки)")
        else:
            port = free_port()
            srv = subprocess.Popen(
                [sys.executable, "api/server.py", str(port)], cwd=ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                time.sleep(2.0)
                env = dict(os.environ, NODE_PATH=mods)
                r = subprocess.run(
                    ["node", "tools/smoke.js", f"http://localhost:{port}"],
                    cwd=ROOT, capture_output=True, text=True, timeout=180, env=env)
                out = r.stdout + r.stderr
                line = [l for l in out.splitlines() if l.startswith("проверок")]
                add("страница работает", r.returncode == 0,
                    line[0] if line else tail(out))
                if r.returncode != 0:
                    for l in out.splitlines():
                        if "ОШИБКА" in l:
                            print("         " + l.strip())
            finally:
                srv.terminate()

    bad = sum(1 for _, ok, _ in checks if not ok)
    print(f"\nпроверок {len(checks)}, провалено {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
