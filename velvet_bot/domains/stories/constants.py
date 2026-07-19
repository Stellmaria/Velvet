STORY_REQUIRED_UNIVERSES = frozenset({"shs", "kr", "lm", "idm", "lagerta"})
KNOWN_UNIVERSES = frozenset(
    {"shs", "kr", "lm", "idm", "bg3", "re", "lagerta", "original", "other"}
)
RELEASE_PRECISIONS = frozenset({"day", "month", "year", "unknown"})

__all__ = (
    "KNOWN_UNIVERSES",
    "RELEASE_PRECISIONS",
    "STORY_REQUIRED_UNIVERSES",
)
