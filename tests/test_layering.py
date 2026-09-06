"""Enforces the layering rule: gameplay-logic modules must never import
pygame, so they stay unit-testable without a display. Only game.py,
render.py, and assets.py are allowed to touch pygame."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "headscotter"

PURE_MODULES = (
    "config.py",
    "physics.py",
    "world.py",
    "players.py",
    "cpu.py",
    "match.py",
    "input.py",
    "feedback.py",
)


class LayeringTests(unittest.TestCase):
    def test_pure_modules_do_not_import_pygame(self):
        for filename in PURE_MODULES:
            path = PACKAGE_DIR / filename
            with self.subTest(module=filename):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotEqual(
                                alias.name.split(".")[0], "pygame",
                                f"{filename} imports pygame directly",
                            )
                    elif isinstance(node, ast.ImportFrom):
                        module_root = (node.module or "").split(".")[0]
                        self.assertNotEqual(
                            module_root, "pygame", f"{filename} imports from pygame",
                        )

    def test_pure_modules_are_importable_without_a_display(self):
        # A real import (not just AST inspection) with no SDL video driver
        # configured -- this would raise if any pure module secretly
        # touched pygame at import time.
        import importlib

        for filename in PURE_MODULES:
            module_name = f"headscotter.{filename[:-3]}"
            with self.subTest(module=module_name):
                importlib.import_module(module_name)


if __name__ == "__main__":
    unittest.main()
