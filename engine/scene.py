"""Событие как сцена.

У Paradox событие — не окно с текстом, а собранная сцена: несколько
портретов, тема со своим фоном и значком, фоновый звук. Именно это, а
не трёхмерная карта, создаёт ощущение, что в мире происходит что-то с
конкретными людьми.

Здесь то же самое из уже имеющихся частей: портреты собираются послойно,
значки берутся из набора, фон задаётся темой. Ничего нового рисовать не
нужно — нужна композиция.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import faces, government as gov, groups, personnel as hr, portrait
from .state import World

_LANG = {"v": "ru"}


def _cn(world: World, code: str) -> str:
    c = world.countries[code]
    return (c.name_en or c.name_ru) if _LANG["v"] == "en" else c.name_ru


def _pn(p) -> str:
    """Имя человека на языке выдачи."""
    return (getattr(p, "name_en", "") or p.name) if _LANG["v"] == "en" else p.name


def _t(key: str, **kw) -> str:
    from . import i18n
    return i18n.t(key, _LANG["v"], **kw)

# Тема события: настроение, палитра, значок, звуковой слой.
THEME_EN = {"crisis": "crisis", "talks": "talks", "home": "home affairs",
            "cabinet": "government", "deal": "agreement"}
MOOD_EN = {"crisis": "tense", "talks": "focused", "home": "strained",
           "cabinet": "routine", "deal": "businesslike"}

THEMES = {
    "crisis": {"name": "кризис", "tint": "#A8402F", "icon": ("scale", "threat"),
               "sound": "tension", "mood": "тревожно"},
    "talks": {"name": "переговоры", "tint": "#2E6E8E", "icon": ("direction", "diplomatic"),
              "sound": "calm", "mood": "сосредоточенно"},
    "home": {"name": "внутренняя политика", "tint": "#B07D2B", "icon": ("scale", "mood"),
             "sound": "calm", "mood": "напряжённо"},
    "cabinet": {"name": "правительство", "tint": "#3F7A5E", "icon": ("ministry", "state"),
                "sound": "calm", "mood": "буднично"},
    "deal": {"name": "соглашение", "tint": "#6B4E8E", "icon": ("issue", "tariffs"),
             "sound": "calm", "mood": "деловито"},
}

SOURCE_THEME = {
    "эскалация": "crisis", "наследство": "home",
    "живые переговоры": "talks", "наступивший срок": "deal",
    "конфликт в кабинете": "cabinet", "настроение группы": "home",
    "охлаждение клиента": "talks", "срок займа": "home",
}


@dataclass
class Figure:
    """Одно лицо в сцене.

    Если в пуле есть настоящий портрет, берётся он; иначе рисуется
    послойная фигура. Запасной вариант остаётся навсегда: пул может быть
    неполным, и игра не должна от этого ломаться.
    """
    name: str
    role: str
    face: str
    country: str
    photo: str | None = None


def _face(name: str, archetype: str, country: str, look, state=None) -> tuple:
    photo = faces.face_url(name, country,
                           bool(getattr(look, "female", False)))
    drawn = portrait.portrait(name, archetype, country, 76, look, state=state)
    return drawn, photo


@dataclass
class Scene:
    theme_id: str
    theme: str
    tint: str
    mood: str
    icon: str | None
    sound: str
    figures: list[Figure] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "theme_id": self.theme_id,
            "theme": self.theme, "tint": self.tint, "mood": self.mood,
            "icon": self.icon, "sound": self.sound,
            "figures": [f.__dict__ for f in self.figures],
        }


def _minister(world: World, code: str, ministry: str) -> Figure | None:
    held = world.ministers.get((code, ministry))
    if not held:
        return None
    p, fit = held
    mset = gov.ministries_of(code)
    mi = mset.get(ministry)
    role = ((mi.short_en or mi.short) if _LANG["v"] == "en" else mi.short) if mi else ministry
    drawn, photo = _face(p.name, p.archetype.id, code, p.look, fit)
    return Figure(_pn(p), role, drawn, code, photo)


def _envoy_or_leader(world: World, me: str, other: str) -> Figure | None:
    """Кого показать со стороны партнёра: нашего посла там или их министра."""
    held = world.ambassadors.get((me, other))
    if held:
        p = held[0]
        drawn, photo = _face(p.name, p.archetype.id, me, p.look)
        return Figure(_pn(p), _t("fig.envoy", country=_cn(world, other)),
                      drawn, me, photo)
    mset = gov.ministries_of(other)
    for mid in mset:
        f = _minister(world, other, mid)
        if f:
            f.role = _t("fig.their", role=f.role, country=_cn(world, other))
            return f
    pool = hr.pool(world, other)
    p = pool[0]
    drawn, photo = _face(p.name, p.archetype.id, other, p.look)
    return Figure(_pn(p), _cn(world, other), drawn, other, photo)


def _group_face(world: World, code: str, group_id: str) -> Figure | None:
    """Лицо недовольной группы: берём человека подходящего архетипа."""
    match = {"military": "hawk", "nationalists": "ideologue",
             "exporters": "trader", "unions": "populist",
             "urban_liberal": "technocrat", "energy": "energy_boss",
             "religious": "ideologue", "taxpayers": "technocrat",
             "farmers": "trader", "defense_industry": "hawk"}
    want = match.get(group_id, "populist")
    for p in hr.pool(world, code):
        if p.archetype.id == want:
            g = groups.GROUPS.get(group_id)
            name = ((g.name_en or g.name_ru) if _LANG["v"] == "en" else g.name_ru) if g else group_id
            drawn, photo = _face(p.name, p.archetype.id, code, p.look,
                                 groups.mood(world, code, group_id))
            return Figure(_pn(p), name, drawn, code, photo)
    return None


def compose(world: World, me: str, item, lang: str = "ru") -> dict:
    _LANG["v"] = lang if lang in ("ru", "en") else "ru"
    """Собрать сцену под вопрос повестки.

    Участники подбираются по смыслу вопроса: спор — наш глава внешней
    политики и человек с той стороны; конфликт в кабинете — оба
    министра; недовольство группы — её лицо и профильный министр.
    """
    theme_id = SOURCE_THEME.get(item.source, "home")
    t = THEMES[theme_id]
    scene = Scene(theme_id=theme_id,
                  theme=THEME_EN[theme_id] if lang == "en" else t["name"],
                  tint=t["tint"],
                  mood=MOOD_EN[theme_id] if lang == "en" else t["mood"],
                  icon=portrait.icon(*t["icon"]), sound=t["sound"])

    params = {}
    for ch in item.choices:
        params.update(ch.params or {})
    other = params.get("other")
    mset = gov.ministries_of(me)
    foreign = next((m for m in ("state",) if m in mset), next(iter(mset)))

    if item.id.startswith("friction:"):
        a, b = item.id.split(":")[1:3]
        for mid in (a, b):
            f = _minister(world, me, mid)
            if f:
                scene.figures.append(f)
    elif item.id.startswith("mood:"):
        gid = item.id.split(":", 1)[1]
        f = _group_face(world, me, gid)
        if f:
            scene.figures.append(f)
        m = _minister(world, me, foreign)
        if m:
            scene.figures.append(m)
    else:
        m = _minister(world, me, foreign)
        if m:
            scene.figures.append(m)
        if other and other in world.countries:
            f = _envoy_or_leader(world, me, other)
            if f:
                scene.figures.append(f)

    if not scene.figures:
        m = _minister(world, me, foreign)
        if m:
            scene.figures.append(m)
    return scene.as_dict()


def ambience(world: World, me: str, lang: str = "ru") -> dict:
    """Состояние мира для звукового слоя.

    Три величины от нуля до единицы. Слои звучат одновременно, громкость
    каждого зависит от своей величины — приём вертикального наслоения.
    """
    from . import escalation
    hot = escalation.hottest(world, me)
    tension = max((d.heat for d in hot), default=0.0)

    support = sum(b.weight * groups.mood(world, me, b.id)
                  for b in groups.blocs(world, me))
    c = world.countries[me]
    strain = max(0.0, 1.0 - support / 0.6) * 0.6 \
        + max(0.0, 1.0 - c.political_capital / 60.0) * 0.4

    return {
        "base": 1.0,
        "tension": round(min(1.0, tension), 3),
        "crisis": round(min(1.0, strain), 3),
        "label": (("crisis" if strain > 0.6 else
                   "tension" if tension > 0.5 else "calm") if lang == "en"
                  else ("кризис" if strain > 0.6 else
                        "напряжение" if tension > 0.5 else "спокойно")),
    }
