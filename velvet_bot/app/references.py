from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.references import ReferenceRepository, ReferenceService


def build_reference_service(database: Database) -> ReferenceService:
    return ReferenceService(ReferenceRepository(database))


__all__ = ("build_reference_service",)
