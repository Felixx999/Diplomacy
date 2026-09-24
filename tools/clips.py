"""Заглушки роликов.

Настоящее видео здесь сделать нечем — нужен кодировщик. Но слот для
ролика в сцене уже есть, и оставлять его пустым до съёмки жалко: без
движения карточка события выглядит мёртвой.

Поэтому пять анимированных сцен на SVG: силуэты, свет, движение камеры.
Они честно условны, зацикливаются без рывка и весят килобайты вместо
мегабайт. Заменяются настоящими файлами простой заменой в той же папке.

    python3 tools/clips.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "clips"
W, H = 640, 200

INK = "#1F2A2E"
PAPER = "#DFE4E1"


def frame(body: str, tint: str, dur: float) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img">'
        f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{tint}" stop-opacity="0.55"/>'
        f'<stop offset="1" stop-color="{PAPER}"/></linearGradient></defs>'
        f'<rect width="{W}" height="{H}" fill="url(#sky)"/>'
        f'{body}'
        f'<rect width="{W}" height="{H}" fill="none" '
        f'stroke="rgba(31,42,46,.25)"/></svg>'
    )


def person(x: int, scale: float = 1.0, tone: str = INK) -> str:
    h = 62 * scale
    return (f'<g transform="translate({x},{H - 20}) scale({scale})" fill="{tone}">'
            f'<ellipse cx="0" cy="-{h:.0f}" rx="13" ry="16"/>'
            f'<path d="M-26 0 Q0 -{h - 12:.0f} 26 0 Z"/></g>')


def anim(attr: str, values: str, dur: float, extra: str = "") -> str:
    return (f'<animate attributeName="{attr}" values="{values}" '
            f'dur="{dur}s" repeatCount="indefinite" {extra}/>')


def speech() -> str:
    """Выступление: фигура за трибуной, вспышки камер."""
    flashes = "".join(
        f'<circle cx="{90 + i * 105}" cy="{135 + (i % 3) * 14}" r="5" '
        f'fill="#FFFFFF" opacity="0">'
        f'{anim("opacity", "0;0.9;0", 4.8, f"begin={i * 0.7:.1f}s")}</circle>'
        for i in range(5))
    return frame(
        f'<rect x="255" y="112" width="130" height="88" fill="{INK}" '
        f'opacity="0.9"/>'
        f'<rect x="268" y="126" width="104" height="8" fill="{PAPER}" '
        f'opacity="0.5"/>'
        + person(320, 1.35)
        + f'<g opacity="0.30">{person(120, 0.8)}{person(500, 0.8)}</g>'
        + flashes,
        "#B07D2B", 4.8)


def talks() -> str:
    """Приезд делегации: две группы сходятся к середине."""
    return frame(
        f'<g>{person(90, 1.0)}{person(140, 0.9)}'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="0 0;92 0;92 0;0 0" dur="6s" repeatCount="indefinite"/></g>'
        f'<g>{person(550, 1.0)}{person(500, 0.9)}'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="0 0;-92 0;-92 0;0 0" dur="6s" repeatCount="indefinite"/></g>'
        f'<rect x="316" y="40" width="8" height="{H - 60}" fill="{INK}" '
        f'opacity="0.18"/>',
        "#2E6E8E", 6.0)


def oath() -> str:
    """Присяга: фигура с поднятой рукой, свет усиливается."""
    return frame(
        person(320, 1.4)
        + f'<path d="M348 118 L348 74" stroke="{INK}" stroke-width="9" '
        f'stroke-linecap="round"/>'
        f'<rect x="250" y="150" width="140" height="50" fill="{INK}" '
        f'opacity="0.25"/>'
        f'<rect width="{W}" height="{H}" fill="#FFFFFF" opacity="0">'
        f'{anim("opacity", "0;0.22;0", 5.0)}</rect>'
        + f'<g opacity="0.25">{person(150, 0.75)}{person(490, 0.75)}</g>',
        "#3F7A5E", 5.0)


def signing() -> str:
    """Подписание: двое за столом, папка переходит из рук в руки."""
    return frame(
        f'<rect x="180" y="146" width="280" height="14" fill="{INK}" '
        f'opacity="0.75"/>'
        + person(232, 1.05) + person(408, 1.05)
        + f'<rect y="132" width="44" height="26" rx="3" fill="{INK}">'
        f'{anim("x", "244;372;372;244", 5.4)}</rect>',
        "#6B4E8E", 5.4)


def crisis() -> str:
    """Экстренное совещание: полутёмный зал, мигающий сигнал."""
    people = "".join(person(120 + i * 84, 0.95, INK) for i in range(6))
    return frame(
        f'<rect width="{W}" height="{H}" fill="{INK}" opacity="0.40"/>'
        + people
        + f'<circle cx="{W - 44}" cy="36" r="12" fill="#A8402F">'
        f'{anim("opacity", "0.25;1;0.25", 1.6)}</circle>'
        f'<rect width="{W}" height="{H}" fill="#A8402F" opacity="0">'
        f'{anim("opacity", "0;0.14;0", 3.2)}</rect>',
        "#A8402F", 3.2)


CLIPS = {"speech": speech, "talks": talks, "oath": oath,
         "signing": signing, "crisis": crisis}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Заглушки роликов\n")
    for name, fn in CLIPS.items():
        p = OUT / f"{name}.svg"
        p.write_text(fn(), encoding="utf-8")
        print(f"  {name:<10} {p.stat().st_size / 1024:5.1f} КБ")
    print("\nЗаменяются настоящим видео простой заменой файлов "
          "на mp4 в той же папке.")


if __name__ == "__main__":
    main()
