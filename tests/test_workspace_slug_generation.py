from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService


class WorkspaceSlugGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_creation_does_not_reuse_count_based_slug(self) -> None:
        now = datetime.now(UTC)
        product = SimpleNamespace(
  get_creation_grant=AsyncMock(
      return_value=SimpleNamespace(
          is_active=True,
          max_workspaces=2,
          allowed_modules=("characters",),
          granted_by_user_id=7221553045,
      )
  ),
  count_owned_personal_workspaces=AsyncMock(return_value=0),
  initialize_modules=AsyncMock(),
  upsert_category=AsyncMock(),
        )
        workspaces = SimpleNamespace(
  create=AsyncMock(
      side_effect=(
          Workspace(10, "first", "First", False, now, now),
          Workspace(11, "second", "Second", False, now, now),
      )
  ),
  get_settings=AsyncMock(
      return_value=SimpleNamespace(public_archive_enabled=False)
  ),
        )
        service = WorkspaceProductService(
  product_repository=product,
  workspace_repository=workspaces,
        )

        await service.create_personal_workspace(owner_user_id=1830672477, name="First")
        await service.create_personal_workspace(owner_user_id=1830672477, name="Second")

        slugs = [call.kwargs["slug"] for call in workspaces.create.await_args_list]
        self.assertEqual(2, len(slugs))
        self.assertNotEqual(slugs[0], slugs[1])
        self.assertTrue(all(slug.startswith("user-1830672477-") for slug in slugs))


if __name__ == "__main__":
    unittest.main()
