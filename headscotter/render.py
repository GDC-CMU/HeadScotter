"""Rendering: draws the side-view stage (stadium, hoarding, ground, goals),
players/ball, HUD, menu, and result-screen text.

This is the one module that turns game state into pixels. Every piece of
gameplay art comes from a PNG loaded through :mod:`headscotter.assets`;
only HUD/menu text is drawn with pygame fonts, which is ordinary UI
chrome, not gameplay art, and unaffected by an art swap.

Draw order, back to front, is deliberate: stadium backdrop -> scrolling
hoarding -> grass strip -> both goals -> both players -> the ball -> the
HUD. Goals are drawn *before* the players/ball rather than split into a
"behind" and "in-front" net layer (the two-layer "ball sinks into the
net" trick some clones use): this project's asset list is one PNG per
goal end (see assets/README.md), and on an arcade cabinet viewed from
across a room, never letting the net mesh occlude the ball or a player
standing in the goal mouth matters more than that extra bit of depth --
so gameplay elements always render on top of the goal art, never behind it.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Tuple

import pygame

from . import assets, config
from . import match as match_mod
from .game import Game, GameState, MENU_ITEMS, PAUSE_ITEMS

HUD_TEXT_COLOR = (255, 255, 255)
HUD_ACCENT_COLOR = (255, 210, 90)
HUD_DIM_COLOR = (210, 220, 230)
MENU_SELECT_COLOR = (255, 210, 90)
MENU_BG_TOP = (30, 42, 70)
MENU_BG_BOTTOM = (14, 20, 34)
MENU_ROW_BG = (48, 56, 74)
MENU_ROW_Y = 280
MENU_ROW_SPACING = 62
MENU_ROW_SIZE = 34
FOOTER_Y = 570
LEFT_TEAM_COLOR = (224, 196, 140)   # matches Scotty's placeholder coat
RIGHT_TEAM_COLOR = (150, 190, 235)  # matches the rival's placeholder color

_ANIM_INTERVAL = 0.12  # seconds per run-cycle frame

_font_cache = {}


def _font(size: int) -> "pygame.font.Font":
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


def _draw_text(screen, text: str, size: int, color, center: Tuple[int, int]) -> pygame.Rect:
    surface = _font(size).render(text, True, color)
    rect = surface.get_rect(center=center)
    screen.blit(surface, rect)
    return rect


def _format_clock(seconds: float) -> str:
    total = max(0, int(seconds + 0.999))
    return f"{total // 60}:{total % 60:02d}"


def _lerp_color(c0, c1, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))


def draw_frame(screen, game: Game) -> None:
    if game.state is GameState.ATTRACT:
        _draw_menu_background(screen)
        _draw_menu(screen, game)
    elif game.state is GameState.HOW_TO_PLAY:
        _draw_menu_background(screen)
        _draw_how_to_play(screen, game)
    elif game.state in (GameState.MATCH, GameState.DEMO, GameState.PAUSED):
        _draw_stage(screen, game)
        _draw_goals(screen)
        _draw_players(screen, game)
        _draw_charge_indicator(screen, game.player_left)
        _draw_charge_indicator(screen, game.player_right)
        _draw_ball(screen, game)
        _draw_hud(screen, game)
        if game.state is not GameState.PAUSED:
            _draw_phase_banner(screen, game)
        if game.state is GameState.DEMO:
            _draw_demo_banner(screen, game)
        elif game.state is GameState.PAUSED:
            _draw_pause(screen, game)
    elif game.state is GameState.RESULT:
        _draw_stage(screen, game)
        _draw_goals(screen)
        _draw_result(screen, game)


def _draw_stage(screen, game: Game) -> None:
    """Sky/stands/crowd, the scrolling advertising hoarding, then the
    grass strip -- the side-view stage itself. No pitch markings are
    drawn anywhere: the genre research report found zero side-view
    head-soccer implementations that draw a centre circle, halfway
    line, or boundary rectangle, and drawing one is exactly what made
    the previous build read as a top-down pitch."""
    screen.blit(assets.get("bg_stadium"), (0, 0))

    # A real advertising hoarding runs along the back of the pitch and
    # stops at the goals -- it never crosses a goal mouth. Clip the
    # scrolling graphic to the span *between* the two goals
    # (config.HOARDING_SPAN_LEFT/RIGHT); behind each goal, the plain
    # wall-board colour already baked into bg_stadium.png shows through
    # instead, so the hoarding never appears to run through the net.
    hoarding = assets.get("bg_hoarding")
    hoarding_w = hoarding.get_width()
    offset = int(game.anim_clock * config.HOARDING_SCROLL_SPEED) % hoarding_w
    span_left = config.HOARDING_SPAN_LEFT
    span_width = config.HOARDING_SPAN_RIGHT - config.HOARDING_SPAN_LEFT
    previous_clip = screen.get_clip()
    screen.set_clip(pygame.Rect(span_left, config.HOARDING_Y, span_width, config.HOARDING_HEIGHT))
    x = span_left - offset
    while x < config.HOARDING_SPAN_RIGHT:
        screen.blit(hoarding, (x, config.HOARDING_Y))
        x += hoarding_w
    screen.set_clip(previous_clip)

    screen.blit(assets.get("ground"), (0, config.GROUND_SPRITE_Y))


def _draw_goals(screen) -> None:
    # Anchored flush with each screen edge -- see
    # tools/generate_placeholders.make_goal for why each image's outer
    # edge (the back of the net) lines up with the screen boundary and
    # its inner edge (the front post) opens into the pitch.
    left = assets.get("goal_left")
    left_rect = left.get_rect()
    left_rect.bottomleft = (config.PITCH_LEFT, config.GROUND_Y)
    screen.blit(left, left_rect)

    right = assets.get("goal_right")
    right_rect = right.get_rect()
    right_rect.bottomright = (config.PITCH_RIGHT, config.GROUND_Y)
    screen.blit(right, right_rect)


def _player_sprite(game: Game, player) -> "pygame.Surface":
    prefix = player.sprite_key
    if player.just_kicked:
        name = f"{prefix}_kick"
    elif not player.on_ground:
        name = f"{prefix}_jump"
    elif player.moving:
        frame = 1 if int(game.anim_clock / _ANIM_INTERVAL) % 2 == 0 else 2
        name = f"{prefix}_run_{frame}"
    else:
        name = f"{prefix}_idle"
    surface = assets.get(name)
    if player.facing < 0:
        surface = pygame.transform.flip(surface, True, False)
    return surface


def _draw_players(screen, game: Game) -> None:
    for player in (game.player_left, game.player_right):
        surface = _player_sprite(game, player)
        rect = surface.get_rect(midbottom=(round(player.x), round(player.y)))
        screen.blit(surface, rect)


_CHARGE_BAR_WIDTH = 44
_CHARGE_BAR_HEIGHT = 7
_CHARGE_BAR_COLOR_LOW = (255, 210, 90)
_CHARGE_BAR_COLOR_HIGH = (240, 60, 60)


def _draw_charge_indicator(screen, player) -> None:
    """A small meter above a charging player's head, so the power-shot
    mechanic (hold A/C/Right Shift to charge, release to strike -- see
    players.update_power_shot()/config.POWER_SHOT_*) is discoverable without a
    tutorial. Only visible while that player is actually charging."""
    if player.kick_charge <= 0.0:
        return

    head_top = player.y - config.HEAD_OFFSET_Y - config.HEAD_RADIUS
    rect = pygame.Rect(0, 0, _CHARGE_BAR_WIDTH, _CHARGE_BAR_HEIGHT)
    rect.midbottom = (round(player.x), round(head_top) - 8)

    pygame.draw.rect(screen, (20, 20, 24), rect, border_radius=3)
    fraction = player.charge_fraction
    fill_width = round(_CHARGE_BAR_WIDTH * fraction)
    if fill_width > 0:
        fill_rect = pygame.Rect(rect.left, rect.top, fill_width, _CHARGE_BAR_HEIGHT)
        color = _lerp_color(_CHARGE_BAR_COLOR_LOW, _CHARGE_BAR_COLOR_HIGH, fraction)
        pygame.draw.rect(screen, color, fill_rect, border_radius=3)
    pygame.draw.rect(screen, (245, 245, 245), rect, 1, border_radius=3)


def _draw_ball(screen, game: Game) -> None:
    ball = game.ball
    surface = assets.get("ball")
    rect = surface.get_rect(center=(round(ball.x), round(ball.y)))
    screen.blit(surface, rect)


def _team_labels(game: Game) -> Tuple[str, str]:
    if game.mode == "1P":
        return "SCOTTY", "CPU"
    if game.mode == "2P":
        return "P1", "P2"
    return "SCOTTY", "RIVAL"  # DEMO


def _draw_hud(screen, game: Game) -> None:
    """A compact scoreboard panel near the top of the sky -- replacing
    the old 110px dark band that ate a fifth of the playfield. It sits
    on top of the stage, not embedded in it, so the pitch itself keeps
    its full vertical extent."""
    panel = assets.get("scoreboard")
    panel_rect = panel.get_rect(midtop=(config.SCREEN_WIDTH // 2, config.SCOREBOARD_TOP_Y))
    screen.blit(panel, panel_rect)

    m = game.match
    left_name, right_name = _team_labels(game)
    cx = panel_rect.centerx

    _draw_text(screen, left_name, 18, LEFT_TEAM_COLOR, (panel_rect.left + 46, panel_rect.top + 14))
    _draw_text(screen, str(m.score_left), 32, HUD_TEXT_COLOR, (panel_rect.left + 46, panel_rect.top + 40))

    _draw_text(screen, right_name, 18, RIGHT_TEAM_COLOR, (panel_rect.right - 46, panel_rect.top + 14))
    _draw_text(screen, str(m.score_right), 32, HUD_TEXT_COLOR, (panel_rect.right - 46, panel_rect.top + 40))

    if m.sudden_death:
        _draw_text(screen, "SUDDEN DEATH", 16, HUD_ACCENT_COLOR, (cx, panel_rect.bottom - 10))
    else:
        _draw_text(screen, _format_clock(m.time_remaining), 22, HUD_ACCENT_COLOR, (cx, panel_rect.bottom - 12))


def _draw_phase_banner(screen, game: Game) -> None:
    m = game.match
    if m.phase is match_mod.MatchPhase.GOAL_CELEBRATION:
        _draw_text(screen, "GOAL!", 72, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 250))
    elif m.phase is match_mod.MatchPhase.KICKOFF:
        # The very first kickoff of the match is the only moment the clock
        # still reads the full match length untouched; every restart after
        # a goal has already ticked down, so this distinguishes them for free.
        if m.time_remaining >= config.MATCH_SECONDS - 0.05 and m.last_scoring_side is None:
            _draw_text(screen, "KICK OFF!", 48, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 250))
        else:
            _draw_text(screen, "READY", 40, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 250))


def _draw_demo_banner(screen, game: Game) -> None:
    _draw_text(screen, "DEMO", 22, HUD_DIM_COLOR, (config.SCREEN_WIDTH // 2, config.PITCH_TOP + 70))
    _draw_text(
        screen, "ANY CONTROL: MAIN MENU", 20, HUD_DIM_COLOR,
        (config.SCREEN_WIDTH // 2, config.PITCH_TOP + 100),
    )


@lru_cache(maxsize=1)
def _menu_background():
    """A simple vertical gradient matching the stadium's evening sky,
    instead of the old flat pitch-green fill -- keeps the menu/how-to-
    play/result screens visually part of the same game as the match."""
    background = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    for y in range(config.SCREEN_HEIGHT):
        t = y / (config.SCREEN_HEIGHT - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(MENU_BG_TOP, MENU_BG_BOTTOM))
        pygame.draw.line(background, color, (0, y), (config.SCREEN_WIDTH, y))
    return background


def _draw_menu_background(screen) -> None:
    screen.blit(_menu_background(), (0, 0))


def _draw_menu_row(screen, label: str, index: int, selected: bool) -> None:
    """Stable label geometry; selection has both a marker and a filled row."""
    y = MENU_ROW_Y + index * MENU_ROW_SPACING
    if selected:
        rect = pygame.Rect(220, y - 24, 360, 48)
        pygame.draw.rect(screen, MENU_ROW_BG, rect, border_radius=6)
        pygame.draw.rect(screen, MENU_SELECT_COLOR, (220, y - 24, 4, 48))
        pygame.draw.polygon(screen, MENU_SELECT_COLOR, [(237, y - 6), (237, y + 6), (245, y)])
    _draw_text(screen, label, MENU_ROW_SIZE, MENU_SELECT_COLOR if selected else HUD_TEXT_COLOR, (400, y))


def _draw_footer(screen, game: Game, *, select: str = "SELECT", back: str = "BACK", navigate=False) -> None:
    if game.has_joysticks:
        hint = f"START: {select}    B / P1: {back}"
        if navigate:
            hint = "STICK: NAVIGATE    " + hint
    else:
        hint = f"ENTER: {select}    ESC: {back}"
        if navigate:
            hint = "UP / DOWN: NAVIGATE    " + hint
    _draw_text(screen, hint, 20, HUD_DIM_COLOR, (400, FOOTER_Y))


@lru_cache(maxsize=1)
def _scrim():
    surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
    surface.fill((10, 16, 28, 190))
    return surface


def _draw_pause(screen, game: Game) -> None:
    screen.blit(_scrim(), (0, 0))
    _draw_text(screen, "PAUSED", 52, HUD_ACCENT_COLOR, (400, 170))
    for index, item in enumerate(PAUSE_ITEMS):
        _draw_menu_row(screen, item, index, index == game.pause_index)
    _draw_footer(screen, game, back="RESUME", navigate=True)


def _draw_menu(screen, game: Game) -> None:
    # A subtle pulse on the title/accent, driven by the free-running
    # attract clock -- cheap, but it's what separates "attract screen"
    # from "static splash image". No tagline: the title and the two
    # rivals facing off below carry the screen, which is what the genre
    # actually does -- a slogan under the logo said nothing useful.
    pulse = (math.sin(game.attract_clock * 2.0) + 1.0) / 2.0
    title_color = _lerp_color(HUD_ACCENT_COLOR, (255, 244, 214), pulse * 0.5)
    _draw_text(screen, "HEADSCOTTER", 68, title_color, (config.SCREEN_WIDTH // 2, 130))
    accent_rect = pygame.Rect(0, 0, round(220 + 30 * pulse), 4)
    accent_rect.center = (config.SCREEN_WIDTH // 2, 168)
    pygame.draw.rect(screen, title_color, accent_rect, border_radius=2)

    for index, item in enumerate(MENU_ITEMS):
        _draw_menu_row(screen, item, index, index == game.menu_index)

    _draw_menu_rivals(screen, game)

    _draw_footer(screen, game, back="GALLERY", navigate=True)


_MENU_PORTRAIT_SCALE = 1.9


@lru_cache(maxsize=8)
def _portrait(source, facing_left: bool):
    if facing_left:
        source = pygame.transform.flip(source, True, False)
    return pygame.transform.scale(source, (
        round(source.get_width() * _MENU_PORTRAIT_SCALE),
        round(source.get_height() * _MENU_PORTRAIT_SCALE),
    ))


def _draw_menu_rivals(screen, game: Game) -> None:
    """The two characters facing off at the foot of the menu -- head-
    soccer menus almost always show the two rivals this way, and it
    sells what the sprites actually look like immediately, rather than
    only ever being seen small and in motion during a match. A gentle,
    out-of-phase idle bob (driven by the free-running attract clock)
    keeps the screen visibly alive rather than a static splash image."""
    scotty_big = _portrait(assets.get("scotty_idle"), False)
    rival_big = _portrait(assets.get("rival_idle"), True)

    feet_y = config.SCREEN_HEIGHT - 105
    bob_scotty = math.sin(game.attract_clock * 3.0) * 4.0
    bob_rival = math.sin(game.attract_clock * 3.0 + math.pi) * 4.0
    screen.blit(scotty_big, scotty_big.get_rect(midbottom=(90, round(feet_y + bob_scotty))))
    screen.blit(rival_big, rival_big.get_rect(midbottom=(config.SCREEN_WIDTH - 90, round(feet_y + bob_rival))))


def _draw_how_to_play(screen, game: Game) -> None:
    _draw_text(screen, "HOW TO PLAY", 52, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 80))
    _draw_text(screen, "Score more goals in 90 seconds. Tied? Next goal wins.", 24, HUD_TEXT_COLOR, (400, 142))
    _draw_text(screen, "Defend your own goal. There is no goalkeeper.", 24, HUD_DIM_COLOR, (400, 173))
    _draw_text(screen, "1 PLAYER: vs CPU. Either stick or keyboard set controls Scotty.", 22, HUD_TEXT_COLOR, (400, 212))
    _draw_text(screen, "2 PLAYERS: stick 1 / keys P1 on the left; stick 2 / keys P2 on the right.", 22, HUD_TEXT_COLOR, (400, 237))
    columns = (125, 300, 470, 655)
    for x, label in zip(columns, ("ACTION", "CABINET", "KEYS P1", "KEYS P2")):
        _draw_text(screen, label, 20, HUD_ACCENT_COLOR, (x, 282))
    pygame.draw.line(screen, MENU_ROW_BG, (60, 299), (740, 299), 2)
    rows = (
        ("Move", "Stick left / right", "A / D", "Left / Right"),
        ("Jump", "Y", "W", "Up"),
        ("Normal kick", "X", "X / S", "Down / Slash"),
        ("Power shot", "Hold / release A", "Hold / release C", "Hold / release R Shift"),
    )
    for row, cells in enumerate(rows):
        for x, text in zip(columns, cells):
            _draw_text(screen, text, 22, HUD_TEXT_COLOR, (x, 322 + row * 38))
    _draw_text(screen, "Normal kicks fire on press, even while power is recharging.", 22, HUD_DIM_COLOR, (400, 488))
    _draw_text(screen, "B / P1 / Esc: pause. Resume or choose Main Menu.", 22, HUD_DIM_COLOR, (400, 521))
    _draw_footer(screen, game, select="MAIN MENU")


def _draw_result(screen, game: Game) -> None:
    screen.blit(_scrim(), (0, 0))
    m = game.match
    winner = game.result_winner
    if game.mode == "1P":
        headline = "YOU WIN!" if winner == "left" else "CPU WINS"
    else:
        headline = "LEFT PLAYER WINS!" if winner == "left" else "RIGHT PLAYER WINS!"

    _draw_text(screen, headline, 52, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 170))
    _draw_text(screen, f"{m.score_left} - {m.score_right}", 72, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 290))

    if game.result_new_high_score:
        _draw_text(screen, "NEW BEST: MOST GOALS IN A WIN!", 28, MENU_SELECT_COLOR, (config.SCREEN_WIDTH // 2, 360))
    elif game.mode == "1P":
        _draw_text(
            screen, f"BEST GOALS IN A WIN: {game.result_high_score}", 24, HUD_DIM_COLOR,
            (config.SCREEN_WIDTH // 2, 360),
        )

    _draw_menu_rivals(screen, game)
    _draw_menu_row(screen, "MAIN MENU", 3, True)
    _draw_footer(screen, game)
