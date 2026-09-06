"""Tests for the hard arcade-cabinet contract with ArcadeLauncher.

- The display must be exactly 800x600.
- P1 (button 5), Esc, Backspace, and button B are all aliases of a
  single "go back one level" action: from the main menu it exits via
  ``sys.exit(0)``; live matches pause/resume; other screens return one level.
- A button already held at startup (the gallery hand-off) must not
  instantly start a match or quit.
- Attract mode starts after 15s idle, any input exits it, it re-arms,
  and it never writes the "most goals in a won 1P match" record.
- The game must survive hundreds of simulated frames without crashing.
"""
from __future__ import annotations

import os
import copy
import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from headscotter import config  # noqa: E402
from headscotter import match as match_mod  # noqa: E402
from headscotter.game import Game, GameState  # noqa: E402
from headscotter.input import RawInput  # noqa: E402
from headscotter import players, physics  # noqa: E402


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
    """Back pauses/resumes matches; other screens keep one-level navigation."""

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
            if state in (GameState.ATTRACT, GameState.MATCH, GameState.PAUSED):
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
        self.assertEqual(game2.state, GameState.PAUSED)

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
            if state in (GameState.MATCH, GameState.PAUSED):
                continue  # explicit Main Menu choice now abandons a live run
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
            elif state in (GameState.MATCH, GameState.PAUSED, GameState.RESULT):
                game.start_match("1P")
                if state is GameState.PAUSED:
                    game.state = state
                if state is GameState.RESULT:
                    game.match.score_left = 2
                    game._enter_result()
            else:
                game.state = state
            render.draw_frame(screen, game)  # must not raise


class LiveActionContractTests(unittest.TestCase):
    def live_game(self, mode="2P"):
        game = Game(rng=random.Random(5))
        game.start_match(mode)
        game.match.phase = match_mod.MatchPhase.PLAYING
        return game

    def test_rapid_normal_presses_fire_in_same_live_update_for_both_keyboards(self):
        for key, side in (("x", "left"), ("s", "left"), ("down", "right"), ("/", "right")):
            game = self.live_game()
            player = getattr(game, f"player_{side}")
            player.kick_cooldown = 0.9
            with patch("headscotter.players.normal_kick", wraps=players.normal_kick) as kick:
                for _ in range(5):
                    game.ball = physics.Ball(player.x + player.facing * 40, player.y - 10)
                    game.update(1 / 60, RawInput(pressed_keys=frozenset({key})))
                    self.assertNotEqual(game.ball.vx, 0)
                    self.assertTrue(player.just_kicked)
                    game.update(1 / 60, RawInput())
                self.assertEqual(kick.call_count, 5)
            self.assertGreater(player.kick_cooldown, 0)
            self.assertLess(game.match.time_remaining, config.MATCH_SECONDS)

    def test_polled_quick_taps_on_both_controllers_and_keyboard_are_not_lost(self):
        for mode in ("1P", "2P"):
            game = self.live_game(mode)
            game.cpu_right = None  # only human requests counted by this probe
            game._joystick_order = [40, 99]
            events = []
            for _ in range(3):
                for iid in (40, 99):
                    events += [
                        pygame.event.Event(pygame.JOYBUTTONDOWN, instance_id=iid, button=2),
                        pygame.event.Event(pygame.JOYBUTTONUP, instance_id=iid, button=2),
                    ]
                events += [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x),
                           pygame.event.Event(pygame.KEYUP, key=pygame.K_x)]
            with patch("pygame.event.get", return_value=events):
                raw = game.poll_hardware()
            self.assertEqual(raw.buttons_by_device, (frozenset(), frozenset()))
            self.assertEqual(raw.button_downs_by_device, ((2, 2, 2), (2, 2, 2)))
            with patch("headscotter.players.normal_kick", wraps=players.normal_kick) as kick:
                game.update(1 / 60, raw)
                self.assertEqual(kick.call_count, 9)
                left_calls = sum(call.args[0] is game.player_left for call in kick.call_args_list)
                self.assertEqual(left_calls, 9 if mode == "1P" else 6)
            self.assertLess(game.match.time_remaining, config.MATCH_SECONDS)

    def test_held_x_and_key_repeat_do_not_repeat_per_frame_or_substep(self):
        game = self.live_game()
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x)] * 3
        with patch("pygame.event.get", return_value=events):
            raw = game.poll_hardware()
        self.assertEqual(raw.key_downs, ("x",))
        game.ball.vx = config.BALL_MAX_SPEED
        with patch("headscotter.players.normal_kick", wraps=players.normal_kick) as kick:
            game.update(0.1, raw)  # multiple ball substeps
            for _ in range(4):
                game.update(1 / 60, RawInput(pressed_keys=frozenset({"x"})))
            self.assertEqual(kick.call_count, 1)

    def test_each_controller_can_strike_repeatedly_during_power_recovery(self):
        for device in (0, 1):
            game = self.live_game()
            player = game.player_left if device == 0 else game.player_right
            player.kick_cooldown = 0.9
            buttons = [frozenset(), frozenset()]
            buttons[device] = frozenset({2})
            with patch("headscotter.audio.play") as play:
                for _ in range(5):
                    game.ball = physics.Ball(player.x + player.facing * 40, player.y - 10)
                    game.update(1 / 60, RawInput(buttons_by_device=tuple(buttons)))
                    self.assertGreater(game.ball.vx * player.facing, 0)
                    game.update(1 / 60, RawInput())
                self.assertEqual(sum(call.args == ("kick",) for call in play.call_args_list), 5)
            self.assertGreater(player.kick_cooldown, 0)

    def test_power_charge_release_and_jump_are_separate_for_both_players(self):
        game = self.live_game()
        held = RawInput(buttons_by_device=(frozenset({1}), frozenset({1})))
        for _ in range(10):
            game.update(1 / 60, held)
        self.assertGreater(game.player_left.kick_charge, 0)
        self.assertGreater(game.player_right.kick_charge, 0)
        self.assertTrue(game.player_left.on_ground)
        self.assertFalse(game.player_left.just_kicked)
        with patch("headscotter.players.update_power_shot", wraps=players.update_power_shot) as power:
            game.update(1 / 60, RawInput(buttons_by_device=(frozenset({3}), frozenset({3}))))
            self.assertEqual(power.call_count, 2)
        self.assertFalse(game.player_left.on_ground)
        self.assertFalse(game.player_right.on_ground)
        self.assertEqual(game.player_left.kick_charge, 0)

    def test_release_then_repress_power_in_one_poll_releases_original_charge(self):
        game = self.live_game()
        player = game.player_left
        game.update(0.2, RawInput(pressed_keys=frozenset({"c"})))
        game.ball = physics.Ball(player.x + 40, player.y - 10)
        # A fresh down while the source was previously held proves an intervening up.
        game.update(1 / 60, RawInput(pressed_keys=frozenset({"c"}), key_downs=("c",)))
        self.assertGreater(game.ball.vx, 0)
        self.assertGreater(player.kick_cooldown, 0)
        self.assertEqual(player.kick_charge, 0)


class PauseContractTests(unittest.TestCase):
    DT = 1 / 60

    def snapshot(self, game):
        return copy.deepcopy((
            game.match, game.ball, game.player_left, game.player_right,
            {key: value for key, value in vars(game.cpu_right).items() if key != "rng"} if game.cpu_right else None,
            game.rng.getstate(), game._seconds_since_goal, game._priority_swap,
            game.anim_clock, game.attract_clock, game._menu_idle_seconds,
        ))

    def test_pause_freezes_every_phase_and_rng_then_resumes_existing_objects(self):
        for phase in (match_mod.MatchPhase.KICKOFF, match_mod.MatchPhase.PLAYING,
                      match_mod.MatchPhase.GOAL_CELEBRATION):
            for device in (0, 1):
                game = Game(rng=random.Random(8))
                game.start_match("1P")
                game.match.phase = match_mod.MatchPhase.PLAYING
                game.update(self.DT, RawInput())  # genuinely advance CPU/RNG/play first
                game.match.phase = phase
                game.match.phase_timer = 0.15
                game.player_left.kick_cooldown = 0.8
                objects = (game.match, game.ball, game.player_left, game.cpu_right)
                before = self.snapshot(game)
                buttons = [frozenset(), frozenset()]
                buttons[device] = frozenset({0})
                back = RawInput(buttons_by_device=tuple(buttons))
                game.update(self.DT, back)
                self.assertEqual(game.state, GameState.PAUSED)
                self.assertEqual(game.pause_index, 0)
                for _ in range(120):
                    game.update(0.25, back)
                self.assertEqual(self.snapshot(game), before)
                self.assertEqual(game.state, GameState.PAUSED)
                game.update(self.DT, RawInput())
                game.update(self.DT, back)
                self.assertEqual(game.state, GameState.MATCH)
                self.assertEqual(self.snapshot(game), before)
                for obj, actual in zip(objects, (game.match, game.ball, game.player_left, game.cpu_right)):
                    self.assertIs(obj, actual)
                game.update(self.DT, RawInput())
                self.assertNotEqual(self.snapshot(game), before)

    def test_pause_cancels_charge_and_blocks_old_actions_and_held_confirm(self):
        game = Game()
        game.start_match("2P")
        game.match.phase = match_mod.MatchPhase.PLAYING
        game.update(0.2, RawInput(pressed_keys=frozenset({"c"})))
        self.assertGreater(game.player_left.kick_charge, 0)
        old = frozenset({"c", "w", "x", "return"})
        game.update(self.DT, RawInput(pressed_keys=old | {"escape"}))
        self.assertEqual(game.player_left.kick_charge, 0)
        for _ in range(10):
            game.update(self.DT, RawInput(pressed_keys=old))
        self.assertEqual(game.state, GameState.PAUSED)  # held confirm cannot resume
        game.update(self.DT, RawInput(pressed_keys=old | {"escape"}))
        self.assertEqual(game.state, GameState.MATCH)
        with patch("headscotter.audio.play") as play:
            for _ in range(10):
                game.update(self.DT, RawInput(pressed_keys=old))
            game.update(self.DT, RawInput())  # old power release must not shoot
            play.assert_not_called()
        self.assertEqual(game.player_left.kick_charge, 0)
        self.assertTrue(game.player_left.on_ground)
        self.assertFalse(game.player_left.just_kicked)
        game.update(self.DT, RawInput(pressed_keys=frozenset({"w", "x"})))
        self.assertFalse(game.player_left.on_ground)
        self.assertTrue(game.player_left.just_kicked)

    def test_pause_main_menu_abandons_without_exit_or_record_then_fresh_match(self):
        game = Game()
        game.start_match("1P")
        game.match.score_left = 99
        old_match = game.match
        game.update(self.DT, RawInput(pressed_keys=frozenset({"escape"})))
        game.update(self.DT, RawInput())
        with patch("headscotter.match.maybe_record_high_score") as record:
            game.update(self.DT, RawInput(pressed_keys=frozenset({"down"})))
            game.update(self.DT, RawInput(pressed_keys=frozenset({"return"})))
            self.assertEqual(game.state, GameState.ATTRACT)
            for _ in range(10):
                game.update(self.DT, RawInput(pressed_keys=frozenset({"return"})))
            self.assertEqual(game.state, GameState.ATTRACT)
            record.assert_not_called()
        game.update(self.DT, RawInput())
        game.update(self.DT, RawInput(pressed_keys=frozenset({"return"})))
        self.assertEqual(game.state, GameState.MATCH)
        self.assertIsNot(game.match, old_match)
        self.assertEqual(game.match.score_left, 0)

    def test_all_back_aliases_are_release_guarded_across_pause_and_resume(self):
        controls = [RawInput(pressed_keys=frozenset({key})) for key in ("escape", "backspace")]
        controls += [RawInput(buttons_by_device=(frozenset(), frozenset({button}))) for button in (0, 5)]
        for raw in controls:
            game = Game()
            game.start_match("2P")
            game.update(self.DT, raw)
            for _ in range(20):
                game.update(self.DT, raw)
            self.assertEqual(game.state, GameState.PAUSED)
            game.update(self.DT, RawInput())
            game.update(self.DT, raw)
            for _ in range(20):
                game.update(self.DT, raw)
            self.assertEqual(game.state, GameState.MATCH)

    def test_demo_wake_input_is_consumed_and_does_not_pause_or_start_match(self):
        for raw in (RawInput(pressed_keys=frozenset({"escape"})),
                    RawInput(pressed_buttons=frozenset({9})),
                    RawInput(key_downs=("x",))):
            game = Game()
            game._enter_demo()
            game.update(self.DT, raw)
            self.assertEqual(game.state, GameState.ATTRACT)
            for _ in range(10):
                game.update(self.DT, raw)
            self.assertEqual(game.state, GameState.ATTRACT)


class MenuPresentationTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))

    def test_help_text_fits_and_table_cells_do_not_overlap(self):
        from headscotter import render
        original = render._draw_text
        for cabinet in (False, True):
            game = Game()
            game.state = GameState.HOW_TO_PLAY
            if cabinet:
                game.joysticks[0] = object()
            rects = []

            def draw(*args, **kwargs):
                rect = original(*args, **kwargs)
                self.assertTrue(self.screen.get_rect().contains(rect), args[1])
                rects.append((args[1], rect))
                return rect

            with patch("headscotter.render._draw_text", side_effect=draw):
                render.draw_frame(self.screen, game)
            for index, (text, rect) in enumerate(rects):
                for other_text, other_rect in rects[index + 1:]:
                    self.assertFalse(rect.colliderect(other_rect), f"{text} overlaps {other_text}")

    def test_selection_never_changes_label_position_or_font_size(self):
        from headscotter import render
        game = Game()
        with patch("headscotter.render._draw_text", wraps=render._draw_text) as draw:
            for selected in (False, True):
                render._draw_menu_row(self.screen, "HOW TO PLAY", 2, selected)
            calls = draw.call_args_list
            self.assertEqual(calls[0].args[2], calls[1].args[2])
            self.assertEqual(calls[0].args[4], calls[1].args[4])

    def test_static_background_and_portraits_are_cached_without_asset_lifetime_changes(self):
        from headscotter import render
        render._portrait.cache_clear()
        game = Game()
        with patch("pygame.transform.scale", wraps=pygame.transform.scale) as scale:
            render.draw_frame(self.screen, game)
            render.draw_frame(self.screen, game)
        self.assertEqual(scale.call_count, 2)  # one transform per portrait, not per frame
        self.assertIs(render._menu_background(), render._menu_background())

    def test_whiff_pose_is_visible_even_while_airborne(self):
        from headscotter import assets, render
        game = Game()
        game.start_match("2P")
        player = game.player_left
        player.on_ground = False
        result = players.normal_kick(player, game.ball)  # kickoff ball out of reach
        self.assertFalse(result.fired)
        self.assertIs(render._player_sprite(game, player), assets.get("scotty_kick"))


if __name__ == "__main__":
    unittest.main()
