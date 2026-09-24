"""Договор о подаче.

Игрок не видит ни одного сырого числа. Всё, что выходит наружу, —
полоса из пяти-семи делений, слово и стрелка направления.

Двигатель при этом остаётся точным: у Democracy 4 внутри тоже числа с
плавающей точкой. Упрощать расчёт не надо, надо не пускать его наружу.

Из договора следует проверка на осмысленность. Если эффект механики не
способен сдвинуть полосу за разумное время, механика декоративна, даже
если считается верно. `tools/legibility.py` ищет такие случаи.

Единственное место, где определяется словарь: если понадобится
переименовать деление, это делается здесь и меняется везде сразу.
"""

from __future__ import annotations

from dataclasses import dataclass

SCALES: dict[str, tuple[float, float, list[str]]] = {
    "relation": (-1.0, 1.0, [
        "вражда", "напряжение", "прохладно", "нейтрально",
        "доброжелательно", "партнёрство", "союз"]),
    "alignment": (-1.0, 1.0, [
        "интересы расходятся", "трения", "мало общего", "нейтрально",
        "есть общее", "интересы сходятся", "единый фронт"]),
    "threat": (0.0, 1.0, [
        "спокойно", "настороже", "тревожно", "опасно", "на грани"]),
    "trust": (0.0, 1.0, [
        "слову не верят", "сомневаются", "верят с оглядкой",
        "доверяют", "полагаются"]),
    "intel": (0.0, 1.0, [
        "вслепую", "смутно", "в общих чертах", "хорошо", "знают точно"]),
    "mood": (0.0, 1.0, [
        "в ярости", "недовольны", "равнодушны", "довольны", "воодушевлены"]),
    "support": (0.0, 1.0, [
        "разваливается", "шатко", "держится", "прочно", "монолит"]),
    "zone": (0.0, 100.0, [
        "не сойтись", "на волоске", "тесно", "есть простор", "торга нет"]),
    "capital": (0.0, 150.0, [
        "пусто", "в обрез", "хватает", "с запасом", "полная свобода"]),
    "power": (0.0, 0.25, [
        "малая страна", "средняя", "крупная", "великая держава", "сверхдержава"]),
    "level": (0.0, 100.0, [
        "символически", "немного", "заметно", "серьёзно", "почти всё"]),
}

# Некоторые величины распределены неравномерно, и равномерные деления
# на них бессмысленны: при линейной шкале Россия, Япония и Кипр попадали
# в одно деление «малая страна». Показатель степени растягивает нижнюю
# часть шкалы, где сгрудилось большинство.
CURVES: dict[str, float] = {"power": 0.5, "capital": 0.8}

ARROWS = ["резко вниз", "вниз", "ровно", "вверх", "резко вверх"]

# Деления по-английски. Порядок в точности как в SCALES: подпись берётся
# по тому же индексу, поэтому сдвиг в одном списке сломает другой.
SCALES_EN: dict[str, list[str]] = {
    "relation": ["hostility", "friction", "cool", "neutral",
                 "cordial", "partnership", "alliance"],
    "alignment": ["interests diverge", "friction", "little in common",
                  "neutral", "some common ground", "interests converge",
                  "common front"],
    "threat": ["calm", "watchful", "uneasy", "dangerous", "on the brink"],
    "trust": ["word means nothing", "doubtful", "trusted warily",
              "trusted", "relied upon"],
    "intel": ["blind", "vague", "in outline", "well informed", "certain"],
    "mood": ["furious", "unhappy", "indifferent", "content", "enthusiastic"],
    "support": ["collapsing", "shaky", "holding", "solid", "unshakeable"],
    "zone": ["no overlap", "hair's breadth", "tight", "some room",
             "no bargaining"],
    "capital": ["empty", "barely enough", "adequate", "comfortable",
                "free hand"],
    "power": ["small state", "middling", "major", "great power", "superpower"],
    "level": ["token", "modest", "notable", "serious", "nearly all"],
}
ARROWS_EN = ["sharply down", "down", "steady", "up", "sharply up"]


@dataclass
class Reading:
    """То, что видит игрок вместо числа."""
    label: str
    step: int      # какое деление занято, от 1
    steps: int     # всего делений
    scale: str

    def bar(self) -> str:
        """Текстовая полоса для консоли и проверок."""
        return "▰" * self.step + "▱" * (self.steps - self.step)

    def __str__(self) -> str:
        return f"{self.bar()} {self.label}"


def read(scale: str, value: float, lang: str = "ru") -> Reading:
    lo, hi, names = SCALES[scale]
    if lang == "en" and scale in SCALES_EN:
        names = SCALES_EN[scale]
    span = hi - lo or 1.0
    frac = min(1.0, max(0.0, (value - lo) / span))
    frac **= CURVES.get(scale, 1.0)
    idx = min(len(names) - 1, int(frac * len(names)))
    return Reading(names[idx], idx + 1, len(names), scale)


def moved(scale: str, before: float, after: float) -> bool:
    """Сдвинулась ли полоса. Основа проверки на осмысленность."""
    return read(scale, before).step != read(scale, after).step


def arrow(scale: str, delta: float, lang: str = "ru") -> str:
    """Направление изменения. Тоже словом, а не числом."""
    lo, hi, names = SCALES[scale]
    words = ARROWS_EN if lang == "en" else ARROWS
    step = (hi - lo) / len(names)
    if abs(delta) < step * 0.25:
        return words[2]
    if delta < 0:
        return words[0] if delta < -step else words[1]
    return words[4] if delta > step else words[3]


def describe(scale: str, before: float, after: float,
             lang: str = "ru") -> str:
    """Полная строка для депеши: где стало и куда двинулось."""
    r = read(scale, after, lang)
    a = arrow(scale, after - before, lang)
    steady = ARROWS_EN[2] if lang == "en" else ARROWS[2]
    return f"{r.label}" + ("" if a == steady else f", {a}")


# Средство проверки: ищет сырые числа, используется tools/legibility.py.
def leaks(text: str) -> list[str]:
    """Найти сырые числа в тексте, предназначенном игроку.

    Дробь в интерфейсе — почти всегда протёкший внутренний расчёт.
    """
    import re
    return re.findall(r"-?\d+\.\d+", text)
