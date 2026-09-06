"""Tests for input intent resolution (two joysticks + keyboard)."""
from __future__ import annotations

import unittest

from headscotter import config, input as input_mod
from headscotter.input import MenuDirection, RawInput


class SingleDeviceMoveTests(unittest.TestCase):
    def test_p1_move_reads_device_0_axis(self):
        raw = RawInput(axes=((1.0, 0.0), (0.0, 0.0)))
        self.assertEqual(input_mod.resolve_move_p1(raw), 1)

    def test_p2_move_reads_device_1_axis(self):
        raw = RawInput(axes=((0.0, 0.0), (-1.0, 0.0)))
        self.assertEqual(input_mod.resolve_move_p2(raw), -1)

    def test_p1_ignores_device_1s_axis(self):
        raw = RawInput(axes=((0.0, 0.0), (1.0, 0.0)))
        self.assertEqual(input_mod.resolve_move_p1(raw), 0)

    def test_below_deadzone_is_no_movement(self):
        raw = RawInput(axes=((0.1, 0.0),))
        self.assertEqual(input_mod.resolve_move_p1(raw), 0)

    def test_p1_keyboard_fallback(self):
        raw = RawInput(pressed_keys=frozenset({"a"}))
        self.assertEqual(input_mod.resolve_move_p1(raw), -1)
        raw = RawInput(pressed_keys=frozenset({"d"}))
        self.assertEqual(input_mod.resolve_move_p1(raw), 1)

    def test_p2_keyboard_fallback(self):
        raw = RawInput(pressed_keys=frozenset({"left"}))
        self.assertEqual(input_mod.resolve_move_p2(raw), -1)
        raw = RawInput(pressed_keys=frozenset({"right"}))
        self.assertEqual(input_mod.resolve_move_p2(raw), 1)

    def test_p2_keys_do_not_leak_into_p1(self):
        raw = RawInput(pressed_keys=frozenset({"left"}))
        self.assertEqual(input_mod.resolve_move_p1(raw), 0)


class SinglePlayerModeMoveTests(unittest.TestCase):
    def test_either_connected_stick_can_drive_the_solo_player(self):
        raw = RawInput(axes=((0.0, 0.0), (1.0, 0.0)))
        self.assertEqual(input_mod.resolve_move_single_player(raw), 1)

    def test_either_keyboard_mapping_works_in_1p_mode(self):
        self.assertEqual(input_mod.resolve_move_single_player(RawInput(pressed_keys=frozenset({"d"}))), 1)
        self.assertEqual(input_mod.resolve_move_single_player(RawInput(pressed_keys=frozenset({"right"}))), 1)


class JumpKickButtonTests(unittest.TestCase):
    def test_p1_jump_is_device_0_button_y(self):
        raw = RawInput(buttons_by_device=(frozenset({config.BUTTON_Y}), frozenset()))
        self.assertTrue(input_mod.wants_jump_p1(raw))
        self.assertFalse(input_mod.wants_jump_p2(raw))

    def test_p2_kick_is_device_1_button_x(self):
        raw = RawInput(buttons_by_device=(frozenset(), frozenset({config.BUTTON_X})))
        self.assertTrue(input_mod.wants_kick_p2(raw))
        self.assertFalse(input_mod.wants_kick_p1(raw))

    def test_button_b_never_triggers_kick_or_jump(self):
        # B is reserved for the back/exit contract; it must never double
        # as a gameplay action, or every kick would also trigger "back".
        raw = RawInput(buttons_by_device=(frozenset({config.BUTTON_B}),))
        self.assertFalse(input_mod.wants_jump_p1(raw))
        self.assertFalse(input_mod.wants_kick_p1(raw))

    def test_p1_keyboard_jump_and_kick(self):
        self.assertTrue(input_mod.wants_jump_p1(RawInput(pressed_keys=frozenset({"w"}))))
        self.assertTrue(input_mod.wants_kick_p1(RawInput(pressed_keys=frozenset({"s"}))))

    def test_p1_keyboard_kick_also_works_with_the_literal_x_key(self):
        # "x" is the primary keyboard kick key -- it matches the on-screen
        # legend ("X: KICK") literally; "s" is kept as an alternate so
        # nothing regresses for anyone used to it.
        self.assertTrue(input_mod.wants_kick_p1(RawInput(pressed_keys=frozenset({"x"}))))

    def test_p2_keyboard_jump_and_kick(self):
        self.assertTrue(input_mod.wants_jump_p2(RawInput(pressed_keys=frozenset({"up"}))))
        self.assertTrue(input_mod.wants_kick_p2(RawInput(pressed_keys=frozenset({"down"}))))

    def test_p2_keyboard_kick_also_works_with_the_slash_key(self):
        self.assertTrue(input_mod.wants_kick_p2(RawInput(pressed_keys=frozenset({"/"}))))

    def test_single_player_jump_from_either_device(self):
        raw = RawInput(buttons_by_device=(frozenset(), frozenset({config.BUTTON_Y})))
        self.assertTrue(input_mod.wants_jump_single(raw))


class MenuDirectionTests(unittest.TestCase):
    def test_stick_up_navigates_up(self):
        raw = RawInput(axes=((0.0, -1.0),))
        self.assertEqual(input_mod.resolve_menu_direction(raw), MenuDirection.UP)

    def test_stick_down_navigates_down(self):
        raw = RawInput(axes=((0.0, 1.0),))
        self.assertEqual(input_mod.resolve_menu_direction(raw), MenuDirection.DOWN)

    def test_keyboard_up_down(self):
        self.assertEqual(input_mod.resolve_menu_direction(RawInput(pressed_keys=frozenset({"up"}))), MenuDirection.UP)
        self.assertEqual(input_mod.resolve_menu_direction(RawInput(pressed_keys=frozenset({"s"}))), MenuDirection.DOWN)

    def test_no_input_is_none(self):
        self.assertIsNone(input_mod.resolve_menu_direction(RawInput()))


class ConfirmBackTests(unittest.TestCase):
    def test_confirm_via_keyboard_and_buttons(self):
        for key in ("return", "space", "enter"):
            self.assertTrue(input_mod.wants_confirm(RawInput(pressed_keys=frozenset({key}))))
        self.assertTrue(input_mod.wants_confirm(RawInput(pressed_buttons=frozenset({config.BUTTON_A}))))
        self.assertTrue(input_mod.wants_confirm(RawInput(pressed_buttons=frozenset({config.BUTTON_START}))))

    def test_go_back_via_keyboard_and_buttons(self):
        self.assertTrue(input_mod.wants_go_back(RawInput(pressed_keys=frozenset({"escape"}))))
        self.assertTrue(input_mod.wants_go_back(RawInput(pressed_keys=frozenset({"backspace"}))))
        self.assertTrue(input_mod.wants_go_back(RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))))
        self.assertTrue(input_mod.wants_go_back(RawInput(pressed_buttons=frozenset({config.BUTTON_B}))))

    def test_no_false_positive_go_back(self):
        raw = RawInput(pressed_keys=frozenset({"a"}), pressed_buttons=frozenset({config.BUTTON_A}))
        self.assertFalse(input_mod.wants_go_back(raw))


class AnyGenuineInputTests(unittest.TestCase):
    def test_true_on_movement(self):
        self.assertTrue(input_mod.any_genuine_input(RawInput(axes=((1.0, 0.0),))))

    def test_true_on_jump_or_kick(self):
        raw = RawInput(buttons_by_device=(frozenset({config.BUTTON_A}),))
        self.assertTrue(input_mod.any_genuine_input(raw))

    def test_false_on_nothing(self):
        self.assertFalse(input_mod.any_genuine_input(RawInput()))

    def test_false_on_a_drifting_stick_within_the_deadzone(self):
        raw = RawInput(axes=((0.2, 0.15),))
        self.assertFalse(input_mod.any_genuine_input(raw))


class ActionEdgeTests(unittest.TestCase):
    def test_confirmed_button_map_is_separate_on_both_devices(self):
        for device in (0, 1):
            for button, expected in ((2, "normal_kicks"), (3, "jump"), (1, "power_held")):
                tracker = input_mod.ActionTracker()
                buttons = [frozenset(), frozenset()]
                buttons[device] = frozenset({button})
                actions = tracker.sample(RawInput(buttons_by_device=tuple(buttons)))
                self.assertTrue(getattr(actions[device], expected))
                self.assertEqual(actions[1 - device], input_mod.PlayerActions())
                for field in ("normal_kicks", "jump", "power_held"):
                    if field != expected:
                        self.assertFalse(getattr(actions[device], field))

    def test_two_quick_taps_survive_a_frame_with_no_held_buttons(self):
        tracker = input_mod.ActionTracker()
        actions = tracker.sample(RawInput(button_downs_by_device=((2, 2), (2, 2))))
        self.assertEqual([action.normal_kicks for action in actions], [2, 2])
        self.assertEqual(tracker.sample(RawInput())[0].normal_kicks, 0)

    def test_held_source_does_not_hide_new_device_or_keyboard_edges_in_1p(self):
        tracker = input_mod.ActionTracker()
        held = (frozenset({2}), frozenset())
        self.assertEqual(tracker.sample(RawInput(buttons_by_device=held), True)[0].normal_kicks, 1)
        raw = RawInput(buttons_by_device=(held[0], frozenset({2})), pressed_keys=frozenset({"x"}))
        self.assertEqual(tracker.sample(raw, True)[0].normal_kicks, 2)
        self.assertEqual(tracker.sample(raw, True)[0].normal_kicks, 0)

    def test_hardware_down_plus_held_counts_once_not_twice(self):
        tracker = input_mod.ActionTracker()
        raw = RawInput(pressed_keys=frozenset({"x"}), key_downs=("x",))
        self.assertEqual(tracker.sample(raw)[0].normal_kicks, 1)

    def test_release_to_arm_is_per_source(self):
        tracker = input_mod.ActionTracker()
        tracker.suspend(RawInput(buttons_by_device=(frozenset({2, 3, 1}), frozenset())))
        raw = RawInput(buttons_by_device=(frozenset({2, 3, 1}), frozenset({2})))
        actions = tracker.sample(raw, True)
        self.assertEqual(actions[0], input_mod.PlayerActions(normal_kicks=1))
        tracker.sample(RawInput())
        self.assertEqual(tracker.sample(raw, True)[0].normal_kicks, 2)

    def test_power_owner_release_is_not_hidden_by_other_device(self):
        tracker = input_mod.ActionTracker()
        self.assertTrue(tracker.sample(RawInput(buttons_by_device=(frozenset({1}), frozenset())), True)[0].power_held)
        self.assertTrue(tracker.sample(RawInput(buttons_by_device=(frozenset({1}), frozenset({1}))), True)[0].power_held)
        self.assertFalse(tracker.sample(RawInput(buttons_by_device=(frozenset(), frozenset({1}))), True)[0].power_held)

    def test_keyboard_power_keys_do_not_kick_or_jump(self):
        actions = input_mod.ActionTracker().sample(RawInput(pressed_keys=frozenset({"c", "right shift"})))
        self.assertEqual(actions, (input_mod.PlayerActions(power_held=True),) * 2)

    def test_power_is_not_pause_confirm(self):
        self.assertFalse(input_mod.wants_confirm(RawInput(pressed_buttons=frozenset({1})), paused=True))
        self.assertTrue(input_mod.wants_confirm(RawInput(pressed_buttons=frozenset({9})), paused=True))

    def test_blocked_source_can_physically_release_and_repress_in_one_poll(self):
        tracker = input_mod.ActionTracker()
        tracker.suspend(RawInput(pressed_keys=frozenset({"x"})))
        # poll_hardware only emits a new x down after an actual intervening up.
        raw = RawInput(pressed_keys=frozenset({"x"}), key_downs=("x",))
        self.assertEqual(tracker.sample(raw)[0].normal_kicks, 1)


if __name__ == "__main__":
    unittest.main()
