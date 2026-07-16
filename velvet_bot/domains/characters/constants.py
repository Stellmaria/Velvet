CATEGORY_ORDER = ("female", "male", "mf", "mfm", "mm", "ff")
CATEGORY_LABELS = {
    "female": "Женский",
    "male": "Мужской",
    "mf": "МЖ",
    "mfm": "МЖМ",
    "mm": "ММ",
    "ff": "ЖЖ",
    "uncategorized": "Без категории",
}
CATEGORY_EMOJI = {
    "female": "👩",
    "male": "👨",
    "mf": "👩‍❤️‍👨",
    "mfm": "👨‍👩‍👨",
    "mm": "👨‍❤️‍👨",
    "ff": "👩‍❤️‍👩",
    "uncategorized": "📦",
}
CATEGORY_ALIASES = {
    "женский": "female",
    "женская": "female",
    "женщина": "female",
    "ж": "female",
    "female": "female",
    "мужской": "male",
    "мужская": "male",
    "мужчина": "male",
    "м": "male",
    "male": "male",
    "мж": "mf",
    "жм": "mf",
    "mf": "mf",
    "fm": "mf",
    "мжм": "mfm",
    "mfm": "mfm",
    "мм": "mm",
    "mm": "mm",
    "жж": "ff",
    "ff": "ff",
    "без": "uncategorized",
    "нет": "uncategorized",
    "none": "uncategorized",
    "uncategorized": "uncategorized",
}

UNIVERSE_ORDER = ("shs", "kr", "lm", "idm", "bg3", "lagerta", "original")
UNIVERSE_LABELS = {
    "shs": "SHS",
    "kr": "КР",
    "lm": "ЛМ",
    "idm": "ИДМ",
    "bg3": "BG3",
    "lagerta": "Лагерта",
    "original": "Original",
    "unassigned": "Без вселенной",
}
UNIVERSE_EMOJI = {
    "shs": "🖤",
    "kr": "💎",
    "lm": "🌙",
    "idm": "🕯",
    "bg3": "🎲",
    "lagerta": "⚔️",
    "original": "✨",
    "unassigned": "📦",
}
UNIVERSE_ALIASES = {
    "shs": "shs",
    "схс": "shs",
    "кр": "kr",
    "kr": "kr",
    "лм": "lm",
    "lm": "lm",
    "идм": "idm",
    "idm": "idm",
    "bg3": "bg3",
    "бг3": "bg3",
    "baldursgate3": "bg3",
    "baldur'sgate3": "bg3",
    "лагерта": "lagerta",
    "lagerta": "lagerta",
    "original": "original",
    "оригинал": "original",
    "ориджинал": "original",
    "без": "unassigned",
    "нет": "unassigned",
    "none": "unassigned",
    "unassigned": "unassigned",
}

STORY_REQUIRED_UNIVERSES = frozenset({"shs", "kr", "lm", "idm"})
STORY_REQUIRED_SQL = "('shs', 'kr', 'lm', 'idm')"

__all__ = (
    "CATEGORY_ALIASES",
    "CATEGORY_EMOJI",
    "CATEGORY_LABELS",
    "CATEGORY_ORDER",
    "STORY_REQUIRED_SQL",
    "STORY_REQUIRED_UNIVERSES",
    "UNIVERSE_ALIASES",
    "UNIVERSE_EMOJI",
    "UNIVERSE_LABELS",
    "UNIVERSE_ORDER",
)
