"""Генератор пула портретов.

Заполняет `web/faces/<регион>/<пол>/` рисованными фигурами — по
шестнадцать мужских и десять женских на каждый из шести регионов, всего
сто пятьдесят шесть.

Это заглушки, но не пустые: разброс здесь шире, чем у портрета,
собираемого на лету, потому что варьируется больше слоёв — телосложение,
причёска, тон кожи, одежда, осанка, фон. Пока не появятся настоящие
изображения, пул уже даёт узнаваемость и разнообразие, а система его
подхватывает без всяких переделок.

Лица нет намеренно: фигура опознаётся по силуэту и детали. Это же
избавляет от вопроса о сходстве с реальными людьми.

    python3 tools/portraits.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.faces import TARGET  # noqa: E402
from engine.personnel import TONE_MIX, TONES  # noqa: E402
from engine.portrait import PALETTES  # noqa: E402

OUT = ROOT / "web" / "faces"
W = H = 312          # удвоенный размер портрета в Hearts of Iron IV

HAIR_M = ("short", "crop", "bald", "cover", "wave")
HAIR_F = ("long", "bun", "short", "cover", "wave")
HAIR_COLORS = ("#17130F", "#2A2119", "#4A3728", "#6B5A44", "#8C8378", "#BAB4AB")

COLLARS = (
    "<path d='M126 214 L156 262 L186 214' fill='none' stroke-width='11'/>",
    "<path d='M118 220 h76 v22 h-76 z'/>",
    "<path d='M132 214 L156 244 L180 214' fill='none' stroke-width='8'/>"
    "<circle cx='156' cy='252' r='7'/>",
    "<path d='M120 216 L156 250 L192 216 M120 216 L120 268 M192 216 L192 268'"
    " fill='none' stroke-width='9'/>",
)

MARKS = (
    "",                                                      # без детали
    "<rect x='96' y='150' width='44' height='13' rx='5'/>"    # очки
    "<rect x='172' y='150' width='44' height='13' rx='5'/>"
    "<rect x='140' y='153' width='32' height='6'/>",
    "<path d='M74 224 h44 l11 30 H63 z'/>"                    # погоны
    "<path d='M194 224 h44 l11 30 h-66 z'/>",
    "<rect x='186' y='250' width='72' height='50' rx='7'/>",  # папка
    "<path d='M62 268 q94 -42 188 0' fill='none' stroke-width='11'/>",  # шарф
)

HAIRS = {
    "short": "M96 112 Q96 56 156 56 Q216 56 216 112 Q216 82 156 82 "
             "Q96 82 96 112 Z",
    "crop": "M100 106 Q112 64 156 64 Q200 64 212 106 Q184 78 156 78 "
            "Q128 78 100 106 Z",
    "bald": "",
    "cover": "M88 126 Q88 44 156 44 Q224 44 224 126 Q224 156 208 172 "
             "L104 172 Q88 156 88 126 Z",
    "wave": "M96 116 Q100 58 156 58 Q212 58 216 116 Q200 92 182 104 "
            "Q168 84 144 100 Q120 88 96 116 Z",
    "long": "M92 120 Q92 52 156 52 Q220 52 220 120 L220 196 "
            "Q202 158 200 116 Q156 92 112 116 Q110 158 92 196 Z",
    "bun": "M96 112 Q96 56 156 56 Q216 56 216 112 Q216 82 156 82 "
           "Q96 82 96 112 Z M156 30 m-23 0 a23 23 0 1 0 46 0 a23 23 0 1 0 -46 0",
}


def figure(region: str, sex: str, i: int) -> str:
    rng = random.Random(f"{region}:{sex}:{i}")
    ink, tint = PALETTES.get(region, PALETTES["west"])
    mix = TONE_MIX.get(region, TONE_MIX["west"])
    skin = TONES[mix[rng.randrange(len(mix))]]
    hair_key = rng.choice(HAIR_F if sex == "f" else HAIR_M)
    hair = HAIRS[hair_key]
    hair_col = rng.choice(HAIR_COLORS)
    collar = rng.choice(COLLARS)
    mark = rng.choice(MARKS)

    # телосложение и осанка: плечи шире или уже, голова чуть смещена
    span = rng.uniform(0.82, 1.16) * (0.94 if sex == "f" else 1.0)
    lean = rng.uniform(-7, 7)
    head_w = rng.uniform(52, 62)
    head_h = head_w * rng.uniform(1.10, 1.26)
    left = 156 - 130 * span
    right = 156 + 130 * span
    shoulders = f"M{left:.0f} {H} Q156 {H - 118:.0f} {right:.0f} {H} Z"

    # фон: мягкий вертикальный переход, чтобы фигура не висела в пустоте
    gid = f"g{region}{sex}{i}"
    bg = (f"<defs><linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'>"
          f"<stop offset='0' stop-color='{tint}'/>"
          f"<stop offset='1' stop-color='{ink}' stop-opacity='0.22'/>"
          f"</linearGradient></defs>"
          f"<rect width='{W}' height='{H}' fill='url(#{gid})'/>")

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" aria-label="условный портрет">'
        f'{bg}'
        f'<g transform="translate({lean:.1f},0)">'
        f'<g fill="{ink}" stroke="{ink}" stroke-linejoin="round">'
        f'<path d="{shoulders}"/></g>'
        f'<ellipse cx="156" cy="140" rx="{head_w:.0f}" ry="{head_h:.0f}" '
        f'fill="{skin}"/>'
        + (f'<path d="{hair}" fill="{hair_col}"/>' if hair else "")
        + f'<g fill="{ink}" stroke="{ink}" stroke-linejoin="round">'
          f'{collar}{mark}</g>'
        f'</g></svg>'
    )


def main() -> None:
    total = 0
    print("Генерация пула портретов\n")
    for region in sorted(PALETTES):
        for sex, need in TARGET.items():
            d = OUT / region / sex
            d.mkdir(parents=True, exist_ok=True)
            for i in range(need):
                (d / f"{i:02d}.svg").write_text(figure(region, sex, i),
                                                encoding="utf-8")
                total += 1
            print(f"  {region:<8} {sex}: {need}")
    size = sum(f.stat().st_size for f in OUT.rglob("*.svg"))
    print(f"\nвсего {total} файлов, {size / 1024:.0f} КБ")
    print("Это заглушки: заменяются настоящими изображениями простой "
          "заменой файлов в тех же папках.")


if __name__ == "__main__":
    main()
