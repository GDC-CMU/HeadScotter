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

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from headscotter import audio  # noqa: E402


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
            raise RuntimeError("no audio device (simulated)")

        pygame.mixer.init = failing_init
        try:
            audio.init()  # must not raise
        finally:
            pygame.mixer.init = original_init
        self.assertFalse(audio.is_enabled())


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
