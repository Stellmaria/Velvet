from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.administration import WorkspaceAdministrationService
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_repository import WorkspaceProductRepository
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.repository import WorkspaceRepository


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLWorkspaceAdministrationTests(unittest.IsolatedAsyncioTestCase):
    TEST_USER_ID = 98001

    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        await self._cleanup()

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.database.close()

    async def _cleanup(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspace_creation_grants WHERE user_id = $1::BIGINT",
                self.TEST_USER_ID,
            )

    async def test_list_and_get_creation_grants_execute_on_postgresql(self) -> None:
        product_service = WorkspaceProductService(
            product_repository=WorkspaceProductRepository(self.database),
            workspace_repository=WorkspaceRepository(self.database),
        )
        await product_service.grant_creation_access(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=self.TEST_USER_ID,
            allowed_modules=("characters", "archive"),
        )

        administration = WorkspaceAdministrationService(self.database)
        item = await administration.get_creation_grant(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            user_id=self.TEST_USER_ID,
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(self.TEST_USER_ID, item.user_id)
        self.assertEqual(("characters", "archive"), item.allowed_modules)

        listed = await administration.list_creation_grants(
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            limit=50,
        )
        self.assertIn(self.TEST_USER_ID, {grant.user_id for grant in listed})


if __name__ == "__main__":
    unittest.main()
