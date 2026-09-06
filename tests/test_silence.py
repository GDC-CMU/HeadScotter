"""The real game never initializes or uses audio, regardless of game state."""
from __future__ import annotations

import os
import random
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from headscotter import config, physics, render
from headscotter.game import Game, GameState, MENU_ITEMS, PAUSE_ITEMS
from headscotter.input import RawInput
from headscotter.match import MatchPhase

ROOT = Path(__file__).resolve().parent.parent
IDLE = RawInput()
START = RawInput(pressed_buttons=frozenset({config.BUTTON_START}))
BACK = RawInput(pressed_buttons=frozenset({config.BUTTON_B}))


class SilentGameTests(unittest.TestCase):
    def test_sound_features_and_assets_are_removed(self):
        self.assertNotIn("SOUND", MENU_ITEMS)
        self.assertEqual(PAUSE_ITEMS, ("RESUME", "MAIN MENU"))
        self.assertNotIn("AUDIO", GameState.__members__)
        self.assertFalse(hasattr(Game(), "sound_settings"))
        for relative in ("headscotter/audio.py", "headscotter/preferences.py",
                         "tools/generate_sounds.py"):
            self.assertFalse((ROOT / relative).exists(), relative)
        audio_files = [
            path for path in (ROOT / "assets").rglob("*")
            if path.suffix.lower() in {".wav", ".mp3", ".ogg", ".flac"}
        ]
        self.assertEqual(audio_files, [])

    def test_display_gameplay_results_and_demo_never_use_the_mixer(self):
        render.clear_caches()
        pygame.quit()

        def shutdown():
            render.clear_caches()
            pygame.quit()

        self.addCleanup(shutdown)
        error = AssertionError("HeadScotter must never initialize or play audio")
        with patch.dict(os.environ, {config.ENV_WINDOWED: "1"}), \
                patch("pygame.init", side_effect=error), \
                patch("pygame.mixer.init", side_effect=error), \
                patch("pygame.mixer.Sound", side_effect=error), \
                patch("pygame.mixer.Channel", side_effect=error), \
                patch("pygame.mixer.music.play", side_effect=error):
            game = Game(rng=random.Random(4))
            game.init_display()
            self.assertTrue(pygame.display.get_init())
            self.assertTrue(pygame.font.get_init())
            self.assertTrue(pygame.joystick.get_init())
            self.assertIsNone(pygame.mixer.get_init())
            render.draw_frame(game.screen, game)

            game._seed_input_state(frozenset(), {})
            game.update(config.INPUT_SETTLE_SECONDS + 0.1, IDLE)
            game.update(1 / 60, RawInput(pressed_keys=frozenset({"down"})))
            game.update(1 / 60, IDLE)
            game.update(1 / 60, START)
            self.assertEqual(game.mode, "2P")
            game.update(1 / 60, IDLE)
            game.match.phase = MatchPhase.PLAYING
            game.ball = physics.Ball(game.player_left.x + 35, config.GROUND_Y - config.BALL_RADIUS)
            game.update(1 / 60, RawInput(key_downs=("x",)))
            self.assertTrue(game.feedback.impacts)
            render.draw_frame(game.screen, game)

            game.update(1 / 60, BACK)
            self.assertIs(game.state, GameState.PAUSED)
            render.draw_frame(game.screen, game)
            game.update(1 / 60, IDLE)
            game.update(1 / 60, START)
            self.assertIs(game.state, GameState.MATCH)
            game.update(1 / 60, IDLE)
            game.ball = physics.Ball(config.PITCH_RIGHT - 1,
                                     config.GROUND_Y - config.BALL_RADIUS, vx=100)
            game.update(1 / 60, IDLE)
            self.assertEqual(game.match.score_left, 1)
            render.draw_frame(game.screen, game)
            game.match.phase = MatchPhase.FULL_TIME
            game.update(1 / 60, IDLE)
            self.assertIs(game.state, GameState.RESULT)
            render.draw_frame(game.screen, game)
            game.update(1 / 60, IDLE)
            game.update(1 / 60, START)
            self.assertIs(game.state, GameState.MATCH)
            self.assertEqual((game.match.score_left, game.match.score_right), (0, 0))

            game._enter_demo()
            for _ in range(180):
                game.update(1 / 60, IDLE)
            render.draw_frame(game.screen, game)
            self.assertIsNone(pygame.mixer.get_init())
