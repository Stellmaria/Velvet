from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HermesRouterImagePermissionsContractTests(unittest.TestCase):
    def test_router_python_sources_are_readable_by_non_root_user(self) -> None:
        dockerfile = (ROOT / "deploy/hermes-operator/Dockerfile").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "COPY --chmod=0555 deploy/hermes-operator/gateway.py /app/gateway.py",
            dockerfile,
        )
        self.assertIn(
            "COPY --chmod=0555 deploy/hermes-operator/coder_router.py "
            "/app/coder_router.py",
            dockerfile,
        )
        self.assertNotIn(
            "\nCOPY deploy/hermes-operator/gateway.py /app/gateway.py\n",
            dockerfile,
        )
        self.assertNotIn(
            "\nCOPY deploy/hermes-operator/coder_router.py /app/coder_router.py\n",
            dockerfile,
        )
        self.assertIn("USER 10001:10001", dockerfile)


if __name__ == "__main__":
    unittest.main()
