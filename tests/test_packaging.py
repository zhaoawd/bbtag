from __future__ import annotations

import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"


class PackagingTests(unittest.TestCase):
    def test_readme_documents_uv_tool_installation(self) -> None:
        readme = README.read_text(encoding="utf-8")

        self.assertIn("uv tool install .", readme)
        self.assertIn("uv tool run --from . bluetag scan", readme)

    def test_pyproject_exposes_console_script_without_numpy_dependency(self) -> None:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["scripts"]["bluetag"], "bluetag.cli:main")
        self.assertNotIn("numpy>=1.24.0", data["project"]["dependencies"])


if __name__ == "__main__":
    unittest.main()
