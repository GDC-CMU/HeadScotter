"""Tests for the asset loader: fallback placeholders and cwd independence."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from headscotter import assets  # noqa: E402


class AssetLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def setUp(self):
        assets.clear_cache()
        self._original_root = assets.ASSETS_ROOT

    def tearDown(self):
        assets.ASSETS_ROOT = self._original_root
        assets.clear_cache()

    def test_all_declared_sprites_load_without_raising(self):
        for name in assets.SPRITE_SPECS:
            surface = assets.get(name)
            self.assertIsNotNone(surface)

    def test_loaded_sprite_matches_declared_nominal_size(self):
        for name, (_, size) in assets.SPRITE_SPECS.items():
            surface = assets.get(name)
            self.assertEqual(surface.get_size(), tuple(size))

    def test_missing_asset_returns_placeholder_without_raising(self):
        assets.ASSETS_ROOT = Path(__file__).resolve().parent / "does_not_exist"
        try:
            surface = assets.get("ball")  # must not raise
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"assets.get() raised on a missing file: {exc}")
        self.assertEqual(surface.get_size(), assets.SPRITE_SPECS["ball"][1])
        _, height = surface.get_size()
        color = surface.get_at((0, height // 2))
        self.assertEqual((color.r, color.g, color.b), assets.PLACEHOLDER_COLOR)

    def test_missing_asset_warns_exactly_once_to_stderr(self):
        assets.ASSETS_ROOT = Path(__file__).resolve().parent / "does_not_exist"
        original_stderr = sys.stderr

        class _Capture:
            def __init__(self):
                self.lines = []

            def write(self, text):
                self.lines.append(text)

            def flush(self):
                pass

        capture = _Capture()
        sys.stderr = capture
        try:
            assets.get("goal_left")
            assets.get("goal_left")  # second call must not warn again
            assets.get("goal_left")
        finally:
            sys.stderr = original_stderr

        warning_lines = [line for line in capture.lines if "goal_left" in line]
        self.assertEqual(len(warning_lines), 1)

    def test_unknown_sprite_name_raises_keyerror(self):
        with self.assertRaises(KeyError):
            assets.get("not_a_real_sprite_name")

    def test_asset_paths_resolve_regardless_of_cwd(self):
        original_cwd = os.getcwd()
        parent_dir = str(Path(__file__).resolve().parent.parent.parent)
        try:
            os.chdir(parent_dir)
            assets.clear_cache()
            surface = assets.get("ball")
            self.assertEqual(surface.get_size(), assets.SPRITE_SPECS["ball"][1])
            # It must have loaded the real committed file, not a placeholder.
            color = surface.get_at((0, 0))
            self.assertNotEqual((color.r, color.g, color.b), assets.PLACEHOLDER_COLOR)
        finally:
            os.chdir(original_cwd)

    def test_preload_all_touches_every_sprite(self):
        assets.preload_all()
        for name in assets.SPRITE_SPECS:
            self.assertIn(name, assets._cache)


if __name__ == "__main__":
    unittest.main()
