"""The HeadScotter state machine: attract -> menu -> match -> result -> ... .

This is one of the three modules (with :mod:`headscotter.render` and
:mod:`headscotter.assets`) allowed to import pygame, since it owns the
real event loop, hardware polling, and timing. All of the actual rules
(physics, match scoring, CPU behaviour) live in the pure modules and are
simply orchestrated here.
"""
from __future__ import annotations

import random
import sys
from enum import Enum, auto
from typing import Dict, List, Optional, Set

import pygame

from . import config, cpu, input as input_mod, match as match_mod, physics, players
from .input import RawInput


class GameState(Enum):
    ATTRACT = auto()       # the main menu
    HOW_TO_PLAY = auto()
    MATCH = auto()
    RESULT = auto()
    DEMO = auto()          # self-playing attract-mode demo (CPU vs CPU)


MENU_ONE_PLAYER = "1 PLAYER"
MENU_TWO_PLAYERS = "2 PLAYERS"
MENU_HOW_TO_PLAY = "HOW TO PLAY"
MENU_EXIT_TO_GALLERY = "EXIT TO GALLERY"
MENU_ITEMS = (MENU_ONE_PLAYER, MENU_TWO_PLAYERS, MENU_HOW_TO_PLAY, MENU_EXIT_TO_GALLERY)


class Game:
    """Owns all game state and advances it one frame at a time.

    ``update()`` contains no pygame calls and can be driven directly by
    tests with a synthetic :class:`~headscotter.input.RawInput`. Only
    ``run()`` (and the small helpers it uses to talk to real hardware)
    touch pygame.
    """

    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self.state = GameState.ATTRACT

        # Main menu navigation.
        self.menu_index = 0
        self._menu_last_direction: Optional[input_mod.MenuDirection] = None
        self._menu_last_confirm = False

        # Attract mode: how long the main menu has sat with no genuine
        # input (see config.DEMO_IDLE_SECONDS / input.any_genuine_input()).
        # Reset to 0 every time ATTRACT is (re)entered, so it always
        # re-arms for another full idle period.
        self._menu_idle_seconds = 0.0

        # Match state -- None until a match/demo actually starts.
        self.mode: Optional[str] = None  # "1P", "2P", or "DEMO"
        self.match: Optional[match_mod.MatchState] = None
        self.ball: Optional[physics.Ball] = None
        self.player_left: Optional[players.Player] = None
        self.player_right: Optional[players.Player] = None
        self.cpu_left: Optional[cpu.CPUController] = None
        self.cpu_right: Optional[cpu.CPUController] = None
        # Anti-stalemate timer (config.CPU_STALEMATE_SECONDS): seconds of
        # live play since the last goal (or kickoff). Reset on every goal
        # and every fresh match; once it crosses the threshold, every CPU
        # abandons its defensive leash entirely until the next goal, so a
        # prolonged deadlock (e.g. against a human who never moves at
        # all) always eventually resolves. See _step_gameplay().
        self._seconds_since_goal = 0.0

        # Result screen.
        self.result_winner: Optional[str] = None
        self.result_new_high_score = False
        self.result_high_score = match_mod.load_high_score()

        # Purely cosmetic clock consumed by render.py for walk-cycle timing;
        # never affects gameplay logic.
        self.anim_clock = 0.0

        # pygame handles, created lazily by run()/init_display().
        self.screen = None
        self.clock = None
        self.joysticks: Dict[int, "pygame.joystick.Joystick"] = {}
        # Stable per-device ordering (by first-seen instance id), so device
        # index 0 always means "player 1's stick" and index 1 "player 2's
        # stick", regardless of pygame's internal instance-id numbering.
        self._joystick_order: List[int] = []
        self._buttons_by_instance: Dict[int, Set[int]] = {}
        self.pressed_keys: Set[str] = set()

        # Startup input-residue guard (see config.INPUT_SETTLE_SECONDS): the
        # gallery may hand us a still-held select button, so menu confirm is
        # ignored for a short settle window. The single "go back" action
        # (P1/Esc/B/Backspace -- see maybe_go_back()) has its own "armed"
        # latch, true whenever none of those four are currently held, and
        # only lets a back-navigation fire while armed. Defaults to "clean
        # start" here; init_display() re-derives both from real hardware.
        self._input_settle_remaining = 0.0
        self._back_armed = True

    # -- match setup ------------------------------------------------------------
    def start_match(self, mode: str) -> None:
        """Begin a fresh match. ``mode`` is "1P" (human vs CPU) or "2P"
        (human vs human). Public so tests can drive it directly without
        going through menu navigation."""
        cpu_left = None
        cpu_right = cpu.CPUController(rng=self.rng, defend_x=config.PITCH_RIGHT) if mode == "1P" else None
        self._start_match_common(mode, cpu_left, cpu_right)
        self.state = GameState.MATCH

    def _start_match_common(
        self, mode: str, cpu_left: Optional[cpu.CPUController], cpu_right: Optional[cpu.CPUController]
    ) -> None:
        self.mode = mode
        self.match = match_mod.new_match()
        self.player_left = players.new_player(
            config.PITCH_LEFT + config.PLAYER_START_INSET, facing=1, sprite_key="scotty"
        )
        self.player_right = players.new_player(
            config.PITCH_RIGHT - config.PLAYER_START_INSET, facing=-1, sprite_key="rival"
        )
        self.ball = physics.new_kickoff_ball()
        self.cpu_left = cpu_left
        self.cpu_right = cpu_right
        if self.cpu_left is not None:
            self.cpu_left.reset()
        if self.cpu_right is not None:
            self.cpu_right.reset()
        self._seconds_since_goal = 0.0

    def _reset_positions(self) -> None:
        """Put both players and the ball back at kickoff, without
        touching the score or clock -- used after every goal."""
        self.player_left.x = config.PITCH_LEFT + config.PLAYER_START_INSET
        self.player_left.y = config.GROUND_Y
        self.player_left.vy = 0.0
        self.player_left.on_ground = True
        self.player_left.moving = False
        self.player_left.kick_cooldown = 0.0
        self.player_left.facing = 1

        self.player_right.x = config.PITCH_RIGHT - config.PLAYER_START_INSET
        self.player_right.y = config.GROUND_Y
        self.player_right.vy = 0.0
        self.player_right.on_ground = True
        self.player_right.moving = False
        self.player_right.kick_cooldown = 0.0
        self.player_right.facing = -1

        self.ball = physics.new_kickoff_ball()
        if self.cpu_left is not None:
            self.cpu_left.reset()
        if self.cpu_right is not None:
            self.cpu_right.reset()
        self._seconds_since_goal = 0.0

    # -- pure per-frame update --------------------------------------------------
    def update(self, dt: float, raw: RawInput) -> None:
        if self._input_settle_remaining > 0.0:
            self._input_settle_remaining = max(0.0, self._input_settle_remaining - dt)

        if self.state is GameState.ATTRACT:
            if input_mod.any_genuine_input(raw):
                self._menu_idle_seconds = 0.0
            else:
                self._menu_idle_seconds += dt
                if self._menu_idle_seconds >= config.DEMO_IDLE_SECONDS:
                    self._enter_demo()
                    return
            self._update_menu(raw)
            return

        if self.state is GameState.DEMO:
            if input_mod.any_genuine_input(raw):
                self._exit_demo()
                return
            self._advance_match(dt, RawInput())  # both sides are CPU-controlled; raw is unused
            return

        if self.state is GameState.HOW_TO_PLAY:
            if self._menu_confirm_pressed(raw):
                self._return_to_menu()
            return

        if self.state is GameState.MATCH:
            self._advance_match(dt, raw)
            return

        if self.state is GameState.RESULT:
            if self._menu_confirm_pressed(raw):
                self._return_to_menu()
            return

    # -- main menu ----------------------------------------------------------------
    def _update_menu(self, raw: RawInput) -> None:
        direction = self._menu_direction_pressed(raw)
        if direction is input_mod.MenuDirection.UP:
            self.menu_index = (self.menu_index - 1) % len(MENU_ITEMS)
        elif direction is input_mod.MenuDirection.DOWN:
            self.menu_index = (self.menu_index + 1) % len(MENU_ITEMS)
        if self._menu_confirm_pressed(raw):
            self._activate_menu_item()

    def _menu_direction_pressed(self, raw: RawInput) -> Optional[input_mod.MenuDirection]:
        """Edge-triggered steer: fires only the frame a *new* direction is
        pressed, so holding a direction doesn't rapid-fire through every
        menu entry in a single held press."""
        current = input_mod.resolve_menu_direction(raw)
        pressed = current if (current is not None and current is not self._menu_last_direction) else None
        self._menu_last_direction = current
        return pressed

    def _menu_confirm_pressed(self, raw: RawInput) -> bool:
        """Edge-triggered confirm, additionally suppressed during the
        brief startup settle window (config.INPUT_SETTLE_SECONDS) as a
        belt-and-braces second guard on top of hardware-state seeding."""
        current = input_mod.wants_confirm(raw)
        settling = self._input_settle_remaining > 0.0
        pressed = current and not self._menu_last_confirm and not settling
        self._menu_last_confirm = current
        return pressed

    def _activate_menu_item(self) -> None:
        item = MENU_ITEMS[self.menu_index]
        if item == MENU_ONE_PLAYER:
            self.start_match("1P")
        elif item == MENU_TWO_PLAYERS:
            self.start_match("2P")
        elif item == MENU_HOW_TO_PLAY:
            self.state = GameState.HOW_TO_PLAY
        elif item == MENU_EXIT_TO_GALLERY:
            self._exit_to_gallery()

    # -- match / demo progression -------------------------------------------------
    def _advance_match(self, dt: float, raw: RawInput) -> None:
        prev_phase = self.match.phase
        match_mod.tick(self.match, dt)
        if (
            prev_phase is match_mod.MatchPhase.GOAL_CELEBRATION
            and self.match.phase is match_mod.MatchPhase.KICKOFF
        ):
            self._reset_positions()

        if match_mod.is_match_over(self.match):
            if self.state is GameState.DEMO:
                self._enter_demo()  # bounds the demo: start a fresh one rather than stopping
            else:
                self._enter_result()
            return

        if match_mod.is_ball_live(self.match):
            self._step_gameplay(dt, raw)

    def _step_gameplay(self, dt: float, raw: RawInput) -> None:
        # Anti-stalemate: once neither side has scored for long enough,
        # every CPU drops its defensive leash entirely -- see
        # config.CPU_STALEMATE_SECONDS and CPUController._defensive_target_x().
        self._seconds_since_goal += dt
        force_full_advance = self._seconds_since_goal >= config.CPU_STALEMATE_SECONDS

        if self.cpu_left is not None:
            intent = self.cpu_left.update(dt, self.ball, self.player_left, force_full_advance)
            move_l, jump_l, kick_l = intent.move, intent.jump, intent.kick
        elif self.mode == "1P":
            move_l = input_mod.resolve_move_single_player(raw)
            jump_l = input_mod.wants_jump_single(raw)
            kick_l = input_mod.wants_kick_single(raw)
        else:
            move_l = input_mod.resolve_move_p1(raw)
            jump_l = input_mod.wants_jump_p1(raw)
            kick_l = input_mod.wants_kick_p1(raw)
        players.update_player(self.player_left, dt, move_l, jump_l)

        if self.cpu_right is not None:
            intent = self.cpu_right.update(dt, self.ball, self.player_right, force_full_advance)
            move_r, jump_r, kick_r = intent.move, intent.jump, intent.kick
        else:
            move_r = input_mod.resolve_move_p2(raw)
            jump_r = input_mod.wants_jump_p2(raw)
            kick_r = input_mod.wants_kick_p2(raw)
        players.update_player(self.player_right, dt, move_r, jump_r)

        # Keep the two field-player bodies from interpenetrating -- after
        # both have moved for the frame and before any ball interaction,
        # so everything below resolves from an already-legal, separated
        # position.
        players.separate_players(self.player_left, self.player_right)

        # A successful kick and the passive header bounce are mutually
        # exclusive in the same frame for the same player -- otherwise a
        # kick could be immediately re-reflected by an overlapping head
        # hit-box before the ball has even moved.
        kicked_l = players.try_kick(self.player_left, self.ball, kick_l)
        kicked_r = players.try_kick(self.player_right, self.ball, kick_r)
        if not kicked_l:
            players.apply_head_collision(self.player_left, self.ball)
        if not kicked_r:
            players.apply_head_collision(self.player_right, self.ball)

        event = physics.step_ball(self.ball, dt)
        if event == "left_goal":
            match_mod.register_goal(self.match, side="right")
            self._seconds_since_goal = 0.0
        elif event == "right_goal":
            match_mod.register_goal(self.match, side="left")
            self._seconds_since_goal = 0.0

        self.anim_clock += dt

    # -- result screen --------------------------------------------------------------
    def _enter_result(self) -> None:
        self.result_winner = match_mod.winner(self.match)
        if self.mode == "1P" and self.result_winner == "left":
            self.result_high_score = match_mod.maybe_record_high_score(self.match.score_left)
            self.result_new_high_score = self.match.score_left >= self.result_high_score and (
                self.match.score_left > 0
            )
        else:
            self.result_high_score = match_mod.load_high_score()
            self.result_new_high_score = False
        self.state = GameState.RESULT

    # -- attract-mode demo ------------------------------------------------------------
    def _enter_demo(self) -> None:
        """Attract mode: reuse the real match/physics/CPU systems, both
        sides driven by :class:`~headscotter.cpu.CPUController`, so the
        demo can never drift out of sync with real gameplay. Since
        HeadScotter's only persisted record is per-1P-win, a CPU vs CPU
        demo structurally can never write it."""
        self._start_match_common(
            "DEMO",
            cpu.CPUController(rng=self.rng, defend_x=config.PITCH_LEFT),
            cpu.CPUController(rng=self.rng, defend_x=config.PITCH_RIGHT),
        )
        self.state = GameState.DEMO

    def _exit_demo(self) -> None:
        self._return_to_menu()

    # -- back-one-level contract ------------------------------------------------------
    def maybe_go_back(self, raw: RawInput) -> None:
        """P1, Esc, Backspace, and button B are all equivalent aliases of
        a single "go back one level" action (this club's cross-game
        arcade contract), used identically from *every* state:

        - From the main menu (ATTRACT), back means exit to the gallery
          (``sys.exit(0)``) -- there is nothing above the menu to go
          back to.
        - From every other state -- HOW_TO_PLAY, RESULT, the self-playing
          DEMO (see _exit_demo()), or a MATCH in progress -- back returns
          to the main menu, treating a match in progress as abandoned
          (no high score is ever recorded for an abandoned match).

        So leaving mid-match takes two presses: once back to the menu,
        once more to exit. That is deliberate -- it makes an accidental
        press recoverable instead of instantly dumping a visitor out.

        Edge-triggered with a single armed/disarmed latch tracked against
        the raw physical signal, not against what it currently does: it
        disarms every frame any of the four controls is held and re-arms
        the instant none of them are, regardless of state. This guards
        both a control already held over from process startup, and
        holding the same control through one transition from chaining
        straight through a second one in the same hold.
        """
        active = input_mod.wants_go_back(raw)
        was_armed = self._back_armed
        self._back_armed = not active

        if not (active and was_armed):
            return

        if self.state is GameState.ATTRACT:
            self._exit_to_gallery()
        elif self.state is GameState.DEMO:
            self._exit_demo()
        else:
            self._return_to_menu()

    def _return_to_menu(self) -> None:
        self.state = GameState.ATTRACT
        self.menu_index = 0
        self._menu_idle_seconds = 0.0

    def _exit_to_gallery(self) -> None:
        """The top-level exit path: back from the main menu, or the
        menu's EXIT TO GALLERY entry. Quits via sys.exit(0) -- the
        documented contract the launcher relies on to reclaim control."""
        try:
            pygame.quit()
        except Exception:
            pass
        sys.exit(0)

    # -- pygame plumbing ----------------------------------------------------------------
    def init_display(self) -> None:
        pygame.init()
        pygame.display.set_caption(config.WINDOW_TITLE)
        # SCALED keeps the game rendering at its logical 800x600 while SDL
        # letterboxes that onto whatever panel is fitted, so the cabinet and a
        # laptop of any resolution both get a correct picture. FULLSCREEN is
        # the default because that is how the cabinet is played;
        # HEADSCOTTER_WINDOWED gives a window for development.
        flags = pygame.SCALED
        if not config.windowed_requested():
            flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), flags)
        self.clock = pygame.time.Clock()
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            self._add_joystick(i)
        # The gallery is left with a button still physically held -- it is
        # how the visitor *selected* HeadScotter -- and SDL can surface that
        # held state to us the instant we open the joystick/keyboard. Flush
        # anything already queued, then seed our own pressed-state from the
        # real hardware so that held control must be released once before it
        # counts as a fresh press.
        pygame.event.clear()
        self._seed_input_state_from_hardware()

    def _add_joystick(self, device_index: int) -> None:
        try:
            joy = pygame.joystick.Joystick(device_index)
            joy.init()
            instance_id = joy.get_instance_id()
            self.joysticks[instance_id] = joy
            if instance_id not in self._joystick_order:
                self._joystick_order.append(instance_id)
        except pygame.error:
            pass  # device vanished between enumeration and init; ignore

    def _remove_joystick(self, instance_id: int) -> None:
        self.joysticks.pop(instance_id, None)
        self._buttons_by_instance.pop(instance_id, None)
        if instance_id in self._joystick_order:
            self._joystick_order.remove(instance_id)

    def _read_axes(self) -> tuple:
        axes = []
        for instance_id in self._joystick_order:
            joy = self.joysticks.get(instance_id)
            if joy is None:
                continue
            try:
                x = joy.get_axis(config.JOYSTICK_AXIS_X) if joy.get_numaxes() > config.JOYSTICK_AXIS_X else 0.0
                y = joy.get_axis(config.JOYSTICK_AXIS_Y) if joy.get_numaxes() > config.JOYSTICK_AXIS_Y else 0.0
                axes.append((x, y))
            except pygame.error:
                axes.append((0.0, 0.0))  # disconnected mid-frame; treat as neutral
        return tuple(axes)

    def _read_buttons_by_device(self) -> tuple:
        return tuple(frozenset(self._buttons_by_instance.get(iid, ())) for iid in self._joystick_order)

    def _build_raw_input(self) -> RawInput:
        buttons_by_device = self._read_buttons_by_device()
        merged_buttons = frozenset().union(*buttons_by_device)
        return RawInput(
            axes=self._read_axes(),
            pressed_keys=frozenset(self.pressed_keys),
            pressed_buttons=merged_buttons,
            buttons_by_device=buttons_by_device,
        )

    def _seed_input_state_from_hardware(self) -> None:
        """Prime pressed_keys/_buttons_by_instance (and the menu's edge-
        and back-arming latches) from what is *actually* physically held
        right now, instead of an empty set. See init_display()."""
        pressed_keys: Set[str] = set()
        try:
            keys = pygame.key.get_pressed()
            for key_const in range(len(keys)):
                if keys[key_const]:
                    pressed_keys.add(pygame.key.name(key_const))
        except Exception:
            pass  # headless/dummy video driver may not support key state
        buttons_by_instance: Dict[int, Set[int]] = {}
        for instance_id, joy in self.joysticks.items():
            held: Set[int] = set()
            try:
                for button in range(joy.get_numbuttons()):
                    if joy.get_button(button):
                        held.add(button)
            except pygame.error:
                pass  # device vanished mid-enumeration; ignore
            buttons_by_instance[instance_id] = held
        self._seed_input_state(pressed_keys, buttons_by_instance)

    def _seed_input_state(self, pressed_keys, buttons_by_instance) -> None:
        """Prime our tracked pressed-state and the startup guards from an
        explicit already-held set. Split out from
        _seed_input_state_from_hardware() so the "launched with a button
        already held" scenario is directly testable without a real
        display or joystick device.

        Synchronizes ``_joystick_order`` with whatever device indices
        appear in ``buttons_by_instance`` first: ``_build_raw_input()``
        (and therefore every button lookup below) only ever considers
        devices listed there, so a device seeded here without also being
        registered would have its held buttons silently ignored -- which
        previously let a P1/back button held continuously from process
        startup fall through as "not held" and fire immediately on the
        very first frame, instead of being correctly latched disarmed.
        Preserves any already-known order and only appends devices not
        yet seen, so this is also safe to call after real joysticks have
        already been added via _add_joystick().
        """
        for instance_id in buttons_by_instance:
            if instance_id not in self._joystick_order:
                self._joystick_order.append(instance_id)
        self.pressed_keys = set(pressed_keys)
        self._buttons_by_instance = {iid: set(buttons) for iid, buttons in buttons_by_instance.items()}
        seeded = self._build_raw_input()
        self._menu_last_confirm = input_mod.wants_confirm(seeded)
        self._menu_last_direction = input_mod.resolve_menu_direction(seeded)
        self._back_armed = not input_mod.wants_go_back(seeded)
        self._input_settle_remaining = config.INPUT_SETTLE_SECONDS

    def poll_hardware(self) -> RawInput:
        """Read real pygame events/hardware into a RawInput this frame."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.pressed_keys.add("escape")
            elif event.type == pygame.KEYDOWN:
                self.pressed_keys.add(pygame.key.name(event.key))
            elif event.type == pygame.KEYUP:
                self.pressed_keys.discard(pygame.key.name(event.key))
            elif event.type == pygame.JOYBUTTONDOWN:
                self._buttons_by_instance.setdefault(event.instance_id, set()).add(event.button)
            elif event.type == pygame.JOYBUTTONUP:
                self._buttons_by_instance.setdefault(event.instance_id, set()).discard(event.button)
            elif event.type == pygame.JOYDEVICEADDED:
                self._add_joystick(event.device_index)
            elif event.type == pygame.JOYDEVICEREMOVED:
                self._remove_joystick(event.instance_id)

        return self._build_raw_input()

    def run(self) -> None:
        """The real, blocking game loop. Never returns except via exit."""
        from . import render  # imported lazily to keep this module importable headless

        self.init_display()
        while True:
            raw = self.poll_hardware()
            self.maybe_go_back(raw)
            dt = self.clock.tick(config.FPS) / 1000.0
            dt = min(dt, 0.25)  # guard against huge stalls tunneling actors through walls
            self.update(dt, raw)
            render.draw_frame(self.screen, self)
            pygame.display.flip()
