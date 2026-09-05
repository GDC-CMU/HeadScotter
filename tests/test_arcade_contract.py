"""Tests for the hard arcade-cabinet contract with ArcadeLauncher.

- The display must be exactly 800x600.
- P1 (button 5), Esc, Backspace, and button B are all aliases of a
  single "go back one level" action: from the main menu it exits via
  ``sys.exit(0)``; from every other state it returns to the main menu.
- A button already held at startup (the gallery hand-off) must not
  instantly start a match or quit.
- Attract mode starts after 15s idle, any input exits it, it re-arms,
  and it never writes the "most goals in a won 1P match" record.
- The game must survive hundreds of simulated frames without crashing.
"""
from __future__ import annotations

import os
import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from headscotter import config  # noqa: E402
from headscotter import match as match_mod  # noqa: E402
from headscotter.game import Game, GameState  # noqa: E402
from headscotter.input import RawInput  # noqa: E402


class DisplayContractTests(unittest.TestCase):
    def test_configured_resolution_is_800x600(self):
        self.assertEqual(config.SCREEN_WIDTH, 800)
        self.assertEqual(config.SCREEN_HEIGHT, 600)

    def test_display_surface_matches_configured_resolution(self):
        pygame.init()
        screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        self.assertEqual(screen.get_size(), (800, 600))

    def test_fullscreen_is_the_default_unless_windowed_env_is_set(self):
        os.environ.pop(config.ENV_WINDOWED, None)
        self.assertFalse(config.windowed_requested())
        os.environ[config.ENV_WINDOWED] = "1"
        try:
            self.assertTrue(config.windowed_requested())
        finally:
            os.environ.pop(config.ENV_WINDOWED, None)


class BackOneLevelContractTests(unittest.TestCase):
    """P1/Esc/Backspace/B are equivalent everywhere: from the main menu
    they exit to the gallery; from every other state they return to the
    main menu. No reachable state may trap a visitor -- repeated presses
    always eventually reach process exit."""

    def test_p1_from_the_main_menu_exits_with_code_zero(self):
        game = Game(rng=random.Random(0))
        self.assertEqual(game.state, GameState.ATTRACT)
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        with self.assertRaises(SystemExit) as cm:
            game.maybe_go_back(raw)
        self.assertEqual(cm.exception.code, 0)

    def test_p1_from_every_other_state_returns_to_the_menu_not_exit(self):
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        for state in GameState:
            if state is GameState.ATTRACT:
                continue
            with self.subTest(state=state):
                game = Game(rng=random.Random(0))
                if state is GameState.DEMO:
                    game._enter_demo()
                elif state is GameState.MATCH:
                    game.start_match("2P")
                elif state is GameState.RESULT:
                    game.start_match("2P")
                    game.match.score_left = 3
                    game._enter_result()
                else:
                    game.state = state
                try:
                    game.maybe_go_back(raw)
                except SystemExit:
                    self.fail(f"P1 exited the process directly from {state}")
                self.assertEqual(game.state, GameState.ATTRACT)

    def test_escape_key_mirrors_p1_exactly(self):
        raw = RawInput(pressed_keys=frozenset({"escape"}))
        game = Game(rng=random.Random(0))
        with self.assertRaises(SystemExit) as cm:
            game.maybe_go_back(raw)
        self.assertEqual(cm.exception.code, 0)

        game2 = Game(rng=random.Random(0))
        game2.start_match("2P")
        try:
            game2.maybe_go_back(raw)
        except SystemExit:
            self.fail("Esc exited the process directly from MATCH")
        self.assertEqual(game2.state, GameState.ATTRACT)

    def test_button_b_also_mirrors_p1(self):
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_B}))
        game = Game(rng=random.Random(0))
        with self.assertRaises(SystemExit):
            game.maybe_go_back(raw)

    def test_no_go_back_without_a_back_input(self):
        game = Game(rng=random.Random(0))
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_A}))
        try:
            game.maybe_go_back(raw)
        except SystemExit:
            self.fail("maybe_go_back() exited without a back input present")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_from_any_state_repeated_p1_presses_eventually_exit(self):
        press = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        release = RawInput()
        for state in GameState:
            with self.subTest(state=state):
                game = Game(rng=random.Random(0))
                if state is GameState.DEMO:
                    game._enter_demo()
                elif state in (GameState.MATCH, GameState.RESULT):
                    game.start_match("2P")
                    if state is GameState.RESULT:
                        game.match.score_left = 2
                        game._enter_result()
                else:
                    game.state = state
                exited = False
                for _ in range(4):
                    try:
                        game.maybe_go_back(press)
                    except SystemExit as exc:
                        self.assertEqual(exc.code, 0)
                        exited = True
                        break
                    game.maybe_go_back(release)
                self.assertTrue(exited, f"P1 never reached process exit from {state}")


class StartupResidueGuardTests(unittest.TestCase):
    """The seeded-state guard must be honoured for *every* control that
    can trigger a state transition on its own -- confirm (start a match)
    and back/P1 (exit or return to the menu) -- not just the one the
    settle window happens to also cover. See _seed_input_state(), which
    is the direct testing seam ArcadeLauncher hand-off scenarios are
    meant to be reproduced through, without needing a real display or
    joystick device."""

    def test_a_held_confirm_button_at_startup_does_not_start_a_match(self):
        game = Game(rng=random.Random(0))
        game._seed_input_state({}, {0: {config.BUTTON_A}})
        held = RawInput(buttons_by_device=(frozenset({config.BUTTON_A}),), pressed_buttons=frozenset({config.BUTTON_A}))
        for _ in range(10):
            game.update(1 / 60.0, held)
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_a_confirm_button_continuously_held_past_the_settle_window_still_does_not_start_a_match(self):
        # The startup settle window (config.INPUT_SETTLE_SECONDS, 0.3s =
        # 18 frames) is a belt-and-braces *second* guard on top of the
        # seeded edge latch -- it must not be the only thing preventing
        # a false "fresh press" here. Hold for well past 18 frames with
        # no release at all.
        game = Game(rng=random.Random(0))
        game._seed_input_state({}, {0: {config.BUTTON_A}})
        held = RawInput(buttons_by_device=(frozenset({config.BUTTON_A}),), pressed_buttons=frozenset({config.BUTTON_A}))
        for _ in range(120):  # 2s, well past the 0.3s settle window, never released
            game.update(1 / 60.0, held)
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_a_held_back_button_at_startup_does_not_immediately_exit(self):
        game = Game(rng=random.Random(0))
        game._seed_input_state({}, {0: {config.BUTTON_P1}})
        held = RawInput(buttons_by_device=(frozenset({config.BUTTON_P1}),), pressed_buttons=frozenset({config.BUTTON_P1}))
        try:
            for _ in range(10):
                game.maybe_go_back(held)
        except SystemExit:
            self.fail("a button already held at startup triggered an immediate exit")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_a_continuously_held_p1_from_startup_never_exits(self):
        """Regression test: a P1/back button already held when the
        process starts, and NEVER released across many frames, must
        never fire -- only a genuine release-then-press may. This is
        the real-world case (a visitor's finger still down as the
        process starts), and previously failed: _seed_input_state()
        seeded _back_armed as if the button were *not* held (because
        the device wasn't yet registered in _joystick_order), so the
        very first maybe_go_back() call read it as a fresh press and
        exited immediately despite the continuous hold."""
        game = Game(rng=random.Random(0))
        game._seed_input_state({}, {0: {config.BUTTON_P1}})
        held = RawInput(buttons_by_device=(frozenset({config.BUTTON_P1}),), pressed_buttons=frozenset({config.BUTTON_P1}))
        try:
            for _ in range(180):  # 3s, continuously held, never released even once
                game.maybe_go_back(held)
                game.update(1 / 60.0, held)
        except SystemExit:
            self.fail("a continuously held P1 (never released) exited the process")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_a_continuously_held_p1_on_the_second_joystick_never_exits(self):
        """The guard must be per-device, not just device 0 -- P2's
        stick (device index 1) must be covered identically."""
        game = Game(rng=random.Random(0))
        game._seed_input_state({}, {1: {config.BUTTON_P1}})
        held = RawInput(
            buttons_by_device=(frozenset(), frozenset({config.BUTTON_P1})),
            pressed_buttons=frozenset({config.BUTTON_P1}),
        )
        try:
            for _ in range(180):
                game.maybe_go_back(held)
                game.update(1 / 60.0, held)
        except SystemExit:
            self.fail("a continuously held P1 on the second joystick exited the process")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_a_continuously_held_escape_key_from_startup_never_exits(self):
        """Same guarantee for the keyboard Esc alias of back/P1."""
        game = Game(rng=random.Random(0))
        game._seed_input_state({"escape"}, {})
        held = RawInput(pressed_keys=frozenset({"escape"}))
        try:
            for _ in range(180):
                game.maybe_go_back(held)
                game.update(1 / 60.0, held)
        except SystemExit:
            self.fail("a continuously held Esc (never released) exited the process")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_releasing_and_pressing_again_after_seeding_still_works(self):
        game = Game(rng=random.Random(0))
        game._seed_input_state({}, {0: {config.BUTTON_A}})
        held = RawInput(buttons_by_device=(frozenset({config.BUTTON_A}),), pressed_buttons=frozenset({config.BUTTON_A}))
        released = RawInput()
        game.update(1 / 60.0, held)
        game.update(1 / 60.0, released)
        for _ in range(20):  # let the input settle window fully elapse
            game.update(1 / 60.0, released)
        game.update(1 / 60.0, held)
        self.assertEqual(game.state, GameState.MATCH)

    def test_releasing_and_pressing_p1_again_after_seeding_still_exits(self):
        """The flip side of the never-exits guarantee: once a seeded,
        held P1 is genuinely released and pressed again, back/exit must
        still work -- the fix must not have over-corrected into "P1 can
        never fire after being seeded held"."""
        game = Game(rng=random.Random(0))
        game._seed_input_state({}, {0: {config.BUTTON_P1}})
        held = RawInput(buttons_by_device=(frozenset({config.BUTTON_P1}),), pressed_buttons=frozenset({config.BUTTON_P1}))
        released = RawInput()
        game.maybe_go_back(held)  # still held from seeding -- must not fire
        game.maybe_go_back(released)  # released
        with self.assertRaises(SystemExit):
            game.maybe_go_back(held)  # pressed again -- a genuine fresh press


class AttractModeTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = TemporaryDirectory()
        self._original_path = config.HIGHSCORE_PATH
        config.HIGHSCORE_PATH = Path(self._tempdir.name) / "highscore.json"

    def tearDown(self):
        config.HIGHSCORE_PATH = self._original_path
        self._tempdir.cleanup()

    def test_demo_does_not_start_before_15_seconds(self):
        game = Game(rng=random.Random(1))
        idle = RawInput()
        for _ in range(int(config.DEMO_IDLE_SECONDS * 60) - 5):
            game.update(1 / 60.0, idle)
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_demo_starts_at_15_seconds_idle(self):
        game = Game(rng=random.Random(1))
        idle = RawInput()
        for _ in range(int(config.DEMO_IDLE_SECONDS * 60) + 5):
            game.update(1 / 60.0, idle)
        self.assertEqual(game.state, GameState.DEMO)

    def test_any_input_exits_the_demo_immediately(self):
        game = Game(rng=random.Random(1))
        game._enter_demo()
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"escape"})))
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_idle_timer_rearms_after_input(self):
        game = Game(rng=random.Random(1))
        idle = RawInput()
        active = RawInput(pressed_keys=frozenset({"a"}))
        for _ in range(int(config.DEMO_IDLE_SECONDS * 60) - 5):
            game.update(1 / 60.0, idle)
        game.update(1 / 60.0, active)  # re-arms the idle timer
        for _ in range(10):
            game.update(1 / 60.0, idle)
        self.assertEqual(game.state, GameState.ATTRACT)  # not yet another 15s of idling

    def test_demo_never_writes_the_high_score(self):
        game = Game(rng=random.Random(1))
        idle = RawInput()
        # Run well past several simulated matches' worth of frames.
        for _ in range(int((config.DEMO_IDLE_SECONDS + config.MATCH_SECONDS * 2) * 60)):
            game.update(1 / 60.0, idle)
        self.assertEqual(match_mod.load_high_score(), 0)


class HeadlessStabilityTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = TemporaryDirectory()
        self._original_path = config.HIGHSCORE_PATH
        config.HIGHSCORE_PATH = Path(self._tempdir.name) / "highscore.json"

    def tearDown(self):
        config.HIGHSCORE_PATH = self._original_path
        self._tempdir.cleanup()

    def test_survives_several_hundred_frames_of_varied_input(self):
        game = Game(rng=random.Random(42))
        game.start_match("2P")
        keys_cycle = [
            frozenset({"a"}), frozenset({"d"}), frozenset({"left"}), frozenset({"right"}),
            frozenset({"w"}), frozenset({"s"}), frozenset({"up"}), frozenset({"down"}),
        ]
        for frame in range(600):
            raw = RawInput(pressed_keys=keys_cycle[frame % len(keys_cycle)])
            game.update(1 / 60.0, raw)  # must not raise
        self.assertIn(game.state, list(GameState))

    def test_full_match_simulation_does_not_crash_and_score_is_sane(self):
        game = Game(rng=random.Random(7))
        game.start_match("1P")
        idle = RawInput()
        # A generous frame budget. Reaching FULL_TIME requires 90s of
        # *actual PLAYING time*, every goal also spends
        # GOAL_CELEBRATION_SECONDS + KICKOFF_FREEZE_SECONDS frozen, and a
        # tied match continues into sudden death with no clock at all --
        # so, especially against an entirely passive human opponent
        # (which this test deliberately is), the wall-clock time to
        # reach a result has no small fixed ceiling. See
        # tests/test_balance.py, which uses the same generous budget for
        # the same reason. This is all pure headless computation, so a
        # large budget is still fast to actually run.
        for _ in range(int(20 * 60 * 60)):
            game.update(1 / 60.0, idle)
            if game.state is GameState.RESULT:
                break
        self.assertEqual(game.state, GameState.RESULT)
        self.assertGreaterEqual(game.match.score_left, 0)
        self.assertGreaterEqual(game.match.score_right, 0)
        # The ball can travel up to BALL_MAX_SPEED px/sec; the instant it
        # fully crosses a goal line (potentially at full speed, e.g. in
        # sudden death) the match ends and physics stops immediately, so
        # its final frozen position can be up to one frame's worth of
        # travel past the line -- not just BALL_RADIUS past it.
        max_travel_per_frame = config.BALL_MAX_SPEED * (1 / 60.0)
        self.assertGreaterEqual(
            game.ball.x, config.PITCH_LEFT - config.BALL_RADIUS - max_travel_per_frame - 5.0,
        )
        self.assertLessEqual(
            game.ball.x, config.PITCH_RIGHT + config.BALL_RADIUS + max_travel_per_frame + 5.0,
        )

    def test_render_frame_does_not_raise(self):
        from headscotter import render

        pygame.init()
        screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        game = Game(rng=random.Random(1))
        game.start_match("2P")
        for _ in range(5):
            game.update(1 / 60.0, RawInput())
            render.draw_frame(screen, game)  # must not raise

    def test_render_frame_does_not_raise_on_every_state(self):
        from headscotter import render

        pygame.init()
        screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        for state in GameState:
            game = Game(rng=random.Random(1))
            if state is GameState.DEMO:
                game._enter_demo()
            elif state in (GameState.MATCH, GameState.RESULT):
                game.start_match("1P")
                if state is GameState.RESULT:
                    game.match.score_left = 2
                    game._enter_result()
            else:
                game.state = state
            render.draw_frame(screen, game)  # must not raise


if __name__ == "__main__":
    unittest.main()
