"""The HeadScotter state machine: attract -> menu -> match -> result -> ... .

This is one of the four modules (with :mod:`headscotter.render`,
:mod:`headscotter.assets`, and :mod:`headscotter.audio`) allowed to
import pygame, since it owns the real event loop, hardware polling, and
timing. All of the actual rules (physics, match scoring, CPU behaviour)
live in the pure modules and are simply orchestrated here.
"""
from __future__ import annotations

import math
import random
import sys
from enum import Enum, auto
from typing import Dict, List, Optional, Set

import pygame

from . import audio, config, cpu, input as input_mod, match as match_mod, physics, players
from .input import RawInput


class GameState(Enum):
    ATTRACT = auto()       # the main menu
    HOW_TO_PLAY = auto()
    MATCH = auto()
    PAUSED = auto()
    RESULT = auto()
    DEMO = auto()          # self-playing attract-mode demo (CPU vs CPU)


MENU_ONE_PLAYER = "1 PLAYER"
MENU_TWO_PLAYERS = "2 PLAYERS"
MENU_HOW_TO_PLAY = "HOW TO PLAY"
MENU_EXIT_TO_GALLERY = "EXIT TO GALLERY"
MENU_ITEMS = (MENU_ONE_PLAYER, MENU_TWO_PLAYERS, MENU_HOW_TO_PLAY, MENU_EXIT_TO_GALLERY)
PAUSE_ITEMS = ("RESUME", "MAIN MENU")


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
        self.pause_index = 0
        self._actions = input_mod.ActionTracker()
        self._transition_pending = False

        # Attract mode: how long the main menu has sat with no genuine
        # input (see config.DEMO_IDLE_SECONDS / input.any_genuine_input()).
        # Reset to 0 every time ATTRACT is (re)entered, so it always
        # re-arms for another full idle period.
        self._menu_idle_seconds = 0.0
        # Purely cosmetic, free-running clock for attract-screen animation
        # (the menu portraits' idle bob -- see render._draw_menu_rivals())
        # -- accumulated every update() call regardless of state, never
        # reset, and never read by any gameplay logic.
        self.attract_clock = 0.0

        # Match state -- None until a match/demo actually starts.
        self.mode: Optional[str] = None  # "1P", "2P", or "DEMO"
        self.match: Optional[match_mod.MatchState] = None
        self.ball: Optional[physics.Ball] = None
        self.player_left: Optional[players.Player] = None
        self.player_right: Optional[players.Player] = None
        self.cpu_left: Optional[cpu.CPUController] = None
        self.cpu_right: Optional[cpu.CPUController] = None
        # Live-play elapsed since the last goal/kickoff. Kept for match
        # diagnostics and pause snapshots; CPU pursuit no longer waits on it.
        self._seconds_since_goal = 0.0
        # Toggled every gameplay frame -- see _step_gameplay()'s note on
        # why a perfectly symmetric CPU-vs-CPU tie must not always be
        # resolved in the same player's favour.
        self._priority_swap = False

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
        self._key_downs: List[str] = []
        self._button_downs_by_instance: Dict[int, List[int]] = {}

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
        self.player_left.kick_charge = 0.0
        self.player_left.kick_pose_timer = 0.0
        self.player_left.facing = 1

        self.player_right.x = config.PITCH_RIGHT - config.PLAYER_START_INSET
        self.player_right.y = config.GROUND_Y
        self.player_right.vy = 0.0
        self.player_right.on_ground = True
        self.player_right.moving = False
        self.player_right.kick_cooldown = 0.0
        self.player_right.kick_charge = 0.0
        self.player_right.kick_pose_timer = 0.0
        self.player_right.facing = -1

        self.ball = physics.new_kickoff_ball()
        if self.cpu_left is not None:
            self.cpu_left.reset()
        if self.cpu_right is not None:
            self.cpu_right.reset()
        self._seconds_since_goal = 0.0

    # -- pure per-frame update --------------------------------------------------
    def update(self, dt: float, raw: RawInput) -> None:
        # Own back handling here as well as at the public testing seam. The
        # latch makes an external maybe_go_back() + update() pair safe.
        self.maybe_go_back(raw)
        if self._transition_pending:
            self._transition_pending = False
            return
        self._update_frame(dt, raw)
        self._transition_pending = False

    def _update_frame(self, dt: float, raw: RawInput) -> None:
        if self.state is GameState.PAUSED:
            self._actions.suspend(raw)
            self._update_pause(raw)
            return  # no gameplay, RNG, animation, phase, idle or settle clocks

        self.attract_clock += dt
        if self._input_settle_remaining > 0.0:
            self._input_settle_remaining = max(0.0, self._input_settle_remaining - dt)

        if self.state is GameState.ATTRACT:
            self._actions.suspend(raw)
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
                self._consume_transition(raw)
                return
            self._advance_match(dt, RawInput())  # both sides are CPU-controlled; raw is unused
            return

        if self.state is GameState.HOW_TO_PLAY:
            if self._menu_confirm_pressed(raw):
                self._return_to_menu()
                self._consume_transition(raw)
            return

        if self.state is GameState.MATCH:
            self._advance_match(dt, raw)
            return

        if self.state is GameState.RESULT:
            if self._menu_confirm_pressed(raw):
                self._return_to_menu()
                self._consume_transition(raw)
            return

    # -- main menu ----------------------------------------------------------------
    @property
    def has_joysticks(self) -> bool:
        """Whether any real joystick is currently connected -- used only
        to pick which control legend render.py shows (arcade button
        names on the cabinet, keyboard key names on a dev laptop with
        none attached). Never true in headless tests or the build-time
        preview/placeholder tools, since neither ever calls
        init_display()."""
        return bool(self.joysticks)

    def _update_menu(self, raw: RawInput) -> None:
        direction = self._menu_direction_pressed(raw)
        if direction is input_mod.MenuDirection.UP:
            self.menu_index = (self.menu_index - 1) % len(MENU_ITEMS)
            audio.play("menu_move")
        elif direction is input_mod.MenuDirection.DOWN:
            self.menu_index = (self.menu_index + 1) % len(MENU_ITEMS)
            audio.play("menu_move")
        if self._menu_confirm_pressed(raw):
            audio.play("menu_select")
            self._activate_menu_item()
            self._consume_transition(raw)

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
        current = input_mod.wants_confirm(raw, paused=self.state is GameState.PAUSED)
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

    def _consume_transition(self, raw: RawInput) -> None:
        """Discard actions/charges and require release before another select.

        Existing committed poses/cooldowns remain frozen on pause. Only
        uncommitted charge is cancelled, and each held action source is gated.
        """
        self._transition_pending = True
        self._menu_last_confirm = True
        self._menu_last_direction = input_mod.resolve_menu_direction(raw)
        self._actions.suspend(raw)
        for player in (self.player_left, self.player_right):
            if player is not None:
                player.kick_charge = 0.0

    def _update_pause(self, raw: RawInput) -> None:
        if self._menu_direction_pressed(raw) is not None:
            self.pause_index = 1 - self.pause_index
            audio.play("menu_move")
        if self._menu_confirm_pressed(raw):
            audio.play("menu_select")
            if self.pause_index == 0:
                self.state = GameState.MATCH
            else:
                self._return_to_menu()  # abandonment; never records a score or exits
            self._consume_transition(raw)

    # -- match / demo progression -------------------------------------------------
    def _advance_match(self, dt: float, raw: RawInput) -> None:
        prev_phase = self.match.phase
        match_mod.tick(self.match, dt)
        if (
            prev_phase is match_mod.MatchPhase.GOAL_CELEBRATION
            and self.match.phase is match_mod.MatchPhase.KICKOFF
        ):
            self._reset_positions()

        # Whistle: once at kickoff (the very first one and every restart
        # after a goal, exactly like a real referee resuming play), and
        # once at full time. Both are edge-triggered off the phase
        # captured *before* this tick, so each fires exactly once per
        # transition rather than every frame the new phase holds.
        if prev_phase is match_mod.MatchPhase.KICKOFF and self.match.phase is match_mod.MatchPhase.PLAYING:
            audio.play("whistle")
        just_ended = prev_phase is not match_mod.MatchPhase.FULL_TIME and match_mod.is_match_over(self.match)
        if just_ended:
            audio.play("whistle")

        if match_mod.is_match_over(self.match):
            if self.state is GameState.DEMO:
                self._enter_demo()  # bounds the demo: start a fresh one rather than stopping
            else:
                self._enter_result()
                self._consume_transition(raw)
            return

        if match_mod.is_ball_live(self.match):
            self._step_gameplay(dt, raw)
        else:
            # No buffered kick/jump/charge from a frozen kickoff/goal phase.
            self._actions.suspend(raw)

    def _step_gameplay(self, dt: float, raw: RawInput) -> None:
        self._seconds_since_goal += dt

        # A perfectly symmetric CPU-vs-CPU approach to a resting ball
        # (e.g. every kickoff) has both sides reaching kick range on the
        # *exact same tick* -- a genuine tie. Always resolving left's
        # kick/collision first, every single time, silently handed left
        # the winning touch on every such tie (confirmed by simulation:
        # CPU-vs-CPU matches were scoring 100% one-sided before this
        # fix). Alternating which side is resolved first frame to frame
        # breaks that determinism without touching either side's actual
        # skill/positioning logic, so ties split roughly evenly across a
        # match instead of always going the same way.
        self._priority_swap = not self._priority_swap
        swap = self._priority_swap
        actions_l, actions_r = self._actions.sample(raw, single_player=self.mode == "1P")

        if self.cpu_left is not None:
            intent = self.cpu_left.update(dt, self.ball, self.player_left, self.player_right)
            move_l = intent.move
            actions_l = input_mod.PlayerActions(normal_kicks=int(intent.normal_kick), jump=intent.jump,
                                               power_held=intent.power_held)
        elif self.mode == "1P":
            move_l = input_mod.resolve_move_single_player(raw)
        else:
            move_l = input_mod.resolve_move_p1(raw)
        if self.cpu_right is not None:
            intent = self.cpu_right.update(dt, self.ball, self.player_right, self.player_left)
            move_r = intent.move
            actions_r = input_mod.PlayerActions(normal_kicks=int(intent.normal_kick), jump=intent.jump,
                                               power_held=intent.power_held)
        else:
            move_r = input_mod.resolve_move_p2(raw)
        # Both CPUs observe the same pre-movement frame, not a privileged
        # already-updated opponent on the right-hand side.
        players.update_player(self.player_left, dt, move_l, actions_l.jump)
        players.update_player(self.player_right, dt, move_r, actions_r.jump)

        # Keep the two field-player bodies from interpenetrating -- after
        # both have moved for the frame and before any ball interaction,
        # so everything below resolves from an already-legal, separated
        # position.
        players.separate_players(self.player_left, self.player_right)

        # Attempts are consumed once per render update, before ball substeps.
        if swap:
            kicked_r = self._apply_actions(self.player_right, actions_r, dt)
            kicked_l = self._apply_actions(self.player_left, actions_l, dt)
        else:
            kicked_l = self._apply_actions(self.player_left, actions_l, dt)
            kicked_r = self._apply_actions(self.player_right, actions_r, dt)

        # Substep the ball's movement so a fast ball can never tunnel
        # through a thin collider (a goalpost, the crossbar, or a
        # player's body) between two discrete overlap checks -- see
        # config.BALL_MAX_STEP_PX. Player-vs-ball collisions are checked
        # at the start of every substep, against the ball's position as
        # it actually is right then, not just once for the whole frame
        # (which is what let a fast ball skip clean through a player).
        #
        # A successful kick and the passive header/body bounce are
        # mutually exclusive for the same player this frame -- otherwise
        # a kick could be immediately re-reflected by an overlapping
        # hit-box before the ball has even moved.
        n_substeps = max(1, math.ceil(self.ball.speed() * dt / config.BALL_MAX_STEP_PX))
        sub_dt = dt / n_substeps
        event = None
        contacts = [(self.player_left, kicked_l), (self.player_right, kicked_r)]
        if swap:
            contacts.reverse()
        for _ in range(n_substeps):
            for player, kicked in contacts:
                if not kicked:
                    players.apply_head_collision(player, self.ball, on_impact=self._on_header)
                    players.apply_body_collision(player, self.ball)

            sub_event = physics.step_ball(self.ball, sub_dt, on_bounce=self._on_ball_bounce)
            if sub_event is not None:
                event = sub_event

        if event == "left_goal":
            audio.play("goal")
            match_mod.register_goal(self.match, side="right")
            self._seconds_since_goal = 0.0
        elif event == "right_goal":
            audio.play("goal")
            match_mod.register_goal(self.match, side="left")
            self._seconds_since_goal = 0.0

        self.anim_clock += dt

    def _apply_actions(self, player, actions: input_mod.PlayerActions, dt: float) -> bool:
        fired = False
        power_results = []
        if actions.power_released:
            power_results.append(players.update_power_shot(player, self.ball, False, 0.0))
        # A same-frame power tap still releases an ordinary-strength shot.
        if actions.power_tap:
            players.update_power_shot(player, self.ball, True, dt)
        if not actions.power_released or actions.power_held or actions.power_tap:
            power_results.append(players.update_power_shot(player, self.ball, actions.power_held, dt))
        for power in power_results:
            if power.fired:
                audio.play("power_shot" if power.is_power_shot else "kick")
                fired = True
        # Normal presses remain independent, including during an A charge.
        for _ in range(actions.normal_kicks):
            result = players.normal_kick(player, self.ball)
            if result.fired:
                audio.play("kick")
                fired = True
        return fired

    @staticmethod
    def _on_header() -> None:
        audio.play("header")

    @staticmethod
    def _on_ball_bounce(surface: str) -> None:
        """Notification hook passed to physics.step_ball() -- see its
        ``on_bounce`` parameter. One shared "bounce" sound for the
        ground, a wall, or the ceiling; a header has its own distinct
        sound (see _step_gameplay())."""
        audio.play("bounce")

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
        - MATCH pauses in place (including kickoff/goal); PAUSED resumes.
        - HOW_TO_PLAY, RESULT and DEMO return one level to the main menu.
        - Abandoning a live run is an explicit Main Menu choice while paused.

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
        elif self.state is GameState.MATCH:
            self.state = GameState.PAUSED
            self.pause_index = 0
        elif self.state is GameState.PAUSED:
            self.state = GameState.MATCH
        else:
            self._return_to_menu()
        self._consume_transition(raw)

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
        # Sound is entirely optional -- see audio.py's module docstring.
        # This is the only place audio is ever turned on: headless tests
        # and the build-time preview/placeholder generator tools never
        # call init_display(), so audio stays off there automatically.
        audio.init()
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
                axes.append((0.0, 0.0))
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
            key_downs=tuple(self._key_downs),
            button_downs_by_device=tuple(
                tuple(self._button_downs_by_instance.get(iid, ())) for iid in self._joystick_order
            ),
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
        self._key_downs.clear()
        self._button_downs_by_instance.clear()
        self._buttons_by_instance = {iid: set(buttons) for iid, buttons in buttons_by_instance.items()}
        seeded = self._build_raw_input()
        self._menu_last_confirm = input_mod.wants_confirm(seeded)
        self._menu_last_direction = input_mod.resolve_menu_direction(seeded)
        self._back_armed = not input_mod.wants_go_back(seeded)
        self._actions.suspend(seeded)
        self._input_settle_remaining = config.INPUT_SETTLE_SECONDS

    def poll_hardware(self) -> RawInput:
        """Read real pygame events/hardware into a RawInput this frame."""
        self._key_downs.clear()
        self._button_downs_by_instance.clear()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.pressed_keys.add("escape")
            elif event.type == pygame.KEYDOWN:
                key = pygame.key.name(event.key)
                if key not in self.pressed_keys:
                    self._key_downs.append(key)
                self.pressed_keys.add(key)
            elif event.type == pygame.KEYUP:
                self.pressed_keys.discard(pygame.key.name(event.key))
            elif event.type == pygame.JOYBUTTONDOWN:
                held = self._buttons_by_instance.setdefault(event.instance_id, set())
                if event.button not in held:
                    self._button_downs_by_instance.setdefault(event.instance_id, []).append(event.button)
                held.add(event.button)
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
            dt = self.clock.tick(config.FPS) / 1000.0
            dt = min(dt, 0.25)  # guard against huge stalls tunneling actors through walls
            self.update(dt, raw)
            render.draw_frame(self.screen, self)
            pygame.display.flip()
