"""Tests for the audio module: graceful degradation, and that nothing
here can ever crash the game.

Audio is only ever turned on by Game.init_display(), which these tests
never call, so audio.is_enabled() is false throughout unless a test
explicitly flips it with set_enabled_for_testing() -- exactly mirroring
how headless tests and the build-time generator tools stay silent (and
therefore fully deterministic) without any special-casing.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from headscotter import audio, config, physics, players  # noqa: E402
from headscotter.game import Game  # noqa: E402
from headscotter.input import RawInput  # noqa: E402
from headscotter.match import MatchPhase  # noqa: E402


class AudioDisabledByDefaultTests(unittest.TestCase):
    def setUp(self):
        audio.clear_cache()

    def tearDown(self):
        audio.set_enabled_for_testing(False)
        audio.clear_cache()

    def test_audio_is_disabled_until_init_is_called(self):
        self.assertFalse(audio.is_enabled())

    def test_play_is_a_silent_no_op_when_disabled(self):
        # Must not raise, must not require a real audio device.
        audio.play("kick")
        audio.play("goal")
        audio.play("not_a_real_sound_name")

    def test_play_of_an_unknown_name_is_a_no_op_even_when_enabled(self):
        audio.set_enabled_for_testing(True)
        try:
            audio.play("not_a_real_sound_name")  # must not raise
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"audio.play() raised on an unknown name: {exc}")


class AudioInitGracefulDegradationTests(unittest.TestCase):
    def setUp(self):
        # Other test modules call the real pygame.init(), which also
        # brings up pygame.mixer using this machine's real audio
        # hardware (there is no dummy audio driver forced globally).
        # Force a clean, uninitialised mixer here so this test's
        # simulated failure is actually exercised regardless of what
        # ran before it in the same process.
        pygame.mixer.quit()
        audio.set_enabled_for_testing(False)

    def tearDown(self):
        audio.set_enabled_for_testing(False)

    def test_init_never_raises_even_if_the_mixer_cannot_start(self):
        original_init = pygame.mixer.init

        def failing_init(*args, **kwargs):
            raise pygame.error("no audio device (simulated)")

        pygame.mixer.init = failing_init
        try:
            audio.init()  # must not raise
        finally:
            pygame.mixer.init = original_init
        self.assertFalse(audio.is_enabled())

    def test_missing_sound_warns_once_without_crashing(self):
        audio.clear_cache()
        audio.set_enabled_for_testing(True)
        with patch("pygame.mixer.Sound", side_effect=FileNotFoundError("missing")), patch("sys.stderr") as stderr:
            audio.play("kick")
            audio.play("kick")
            self.assertEqual("".join(call.args[0] for call in stderr.write.call_args_list).count("could not play"), 1)

    def test_programming_errors_are_not_swallowed(self):
        with patch("pygame.mixer.init", side_effect=TypeError("bug")):
            with self.assertRaises(TypeError):
                audio.init()


class ImpactRequestTests(unittest.TestCase):
    """Capture requests at audio.play, not at a disabled mixer backend."""

    def live_game(self):
        game = Game()
        game.start_match("2P")
        game.match.phase = MatchPhase.PLAYING
        return game

    def test_floor_rest_and_rolling_request_no_bounce_sounds_in_live_play(self):
        for speed in (0.0, 150.0, 850.0):
            with self.subTest(speed=speed):
                game = self.live_game()
                game.ball.vx = speed
                # Keep rolling probe clear of bodies/goals without changing vy.
                with patch("headscotter.audio.play") as play:
                    for _ in range(240):
                        game.ball.x = config.PITCH_CENTER_X
                        game.update(1 / 60, RawInput())
                    self.assertEqual(play.call_count, 0)
                self.assertLess(game.match.time_remaining, config.MATCH_SECONDS)
                self.assertEqual(game.ball.vy, 0.0)

    def test_real_drop_requests_impacts_then_becomes_silent(self):
        game = self.live_game()
        game.ball.y -= 160
        with patch("headscotter.audio.play") as play:
            for _ in range(600):
                game.update(1 / 60, RawInput())
            requests = [call.args[0] for call in play.call_args_list]
            self.assertGreater(requests.count("bounce"), 1)
            self.assertEqual(game.ball.vy, 0.0)
            play.reset_mock()
            for _ in range(120):
                game.update(1 / 60, RawInput())
            play.assert_not_called()
            # No permanent throttling: another real drop remains audible.
            game.ball.y -= 100
            for _ in range(120):
                game.update(1 / 60, RawInput())
            self.assertTrue(any(call.args == ("bounce",) for call in play.call_args_list))

    def test_header_correction_and_separation_are_silent_but_incoming_hit_is_audible(self):
        for vy, expected in ((0, 0), (-200, 0), (200, 1)):
            game = self.live_game()
            player = game.player_left
            hx, hy = player.head_center
            game.ball = physics.Ball(hx, hy - config.HEAD_RADIUS - 5, vy=vy)
            with patch("headscotter.audio.play") as play:
                game.update(1 / 60, RawInput())
            self.assertEqual(sum(call.args == ("header",) for call in play.call_args_list), expected)

    def test_same_header_contact_is_coalesced_until_real_separation(self):
        player = players.new_player(400, 1)
        hx, hy = player.head_center
        ball = physics.Ball(hx, hy - config.HEAD_RADIUS - 5, vy=200)
        with patch("headscotter.audio.play") as play:
            for _ in range(5):
                # Repeated correction of one wedged contact in substeps.
                ball.y = hy - config.HEAD_RADIUS - 5
                ball.vy = 200
                players.apply_head_collision(player, ball, Game._on_header)
            self.assertEqual(play.call_count, 1)
            ball.y -= 100
            players.apply_head_collision(player, ball, Game._on_header)
            ball.y = hy - config.HEAD_RADIUS - 5
            ball.vy = 200
            players.apply_head_collision(player, ball, Game._on_header)
            self.assertEqual(play.call_count, 2)

    def test_ball_resting_on_a_head_does_not_manufacture_repeat_headers(self):
        game = self.live_game()
        hx, hy = game.player_left.head_center
        game.ball = physics.Ball(hx, hy - config.HEAD_RADIUS - config.BALL_RADIUS)
        with patch("headscotter.audio.play") as play:
            for _ in range(600):
                game.update(1 / 60, RawInput())
            play.assert_not_called()

    def test_header_sound_uses_relative_incoming_evidence(self):
        for player_vy, expected in ((-200, 1), (200, 0)):
            player = players.new_player(400, 1)
            player.vy = player_vy
            hx, hy = player.head_center
            ball = physics.Ball(hx, hy - config.HEAD_RADIUS - 5, vy=100)
            with patch("headscotter.audio.play") as play:
                players.apply_head_collision(player, ball, Game._on_header)
                self.assertEqual(play.call_count, expected)


class AudioSoundSpecsTests(unittest.TestCase):
    """Every sound the game actually plays (see game.py's audio.play()
    call sites) must be declared, exactly like assets.SPRITE_SPECS is
    the single contract for art -- see assets/README.md."""

    def test_every_gameplay_sound_is_declared(self):
        expected = {
            "kick", "power_shot", "bounce", "header", "goal", "whistle",
            "menu_move", "menu_select",
        }
        self.assertEqual(set(audio.SOUND_SPECS.keys()), expected)


if __name__ == "__main__":
    unittest.main()
