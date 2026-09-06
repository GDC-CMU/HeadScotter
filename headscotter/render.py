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

from typing import Tuple

import pygame

from . import assets, config
from . import match as match_mod
from .game import Game, GameState, MENU_ITEMS

HUD_TEXT_COLOR = (255, 255, 255)
HUD_ACCENT_COLOR = (255, 210, 90)
HUD_DIM_COLOR = (210, 220, 230)
MENU_SELECT_COLOR = (255, 210, 90)
MENU_BG_TOP = (30, 42, 70)
MENU_BG_BOTTOM = (14, 20, 34)
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


def draw_frame(screen, game: Game) -> None:
    if game.state is GameState.ATTRACT:
        _draw_menu_background(screen)
        _draw_menu(screen, game)
    elif game.state is GameState.HOW_TO_PLAY:
        _draw_menu_background(screen)
        _draw_how_to_play(screen)
    elif game.state in (GameState.MATCH, GameState.DEMO):
        _draw_stage(screen, game)
        _draw_goals(screen)
        _draw_players(screen, game)
        _draw_ball(screen, game)
        _draw_hud(screen, game)
        _draw_phase_banner(screen, game)
        if game.state is GameState.DEMO:
            _draw_demo_banner(screen)
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

    hoarding = assets.get("bg_hoarding")
    hoarding_w = hoarding.get_width()
    offset = int(game.anim_clock * config.HOARDING_SCROLL_SPEED) % hoarding_w
    x = -offset
    while x < config.SCREEN_WIDTH:
        screen.blit(hoarding, (x, config.HOARDING_Y))
        x += hoarding_w

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
    if not player.on_ground:
        name = f"{prefix}_jump"
    elif player.just_kicked:
        name = f"{prefix}_kick"
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


def _draw_demo_banner(screen) -> None:
    _draw_text(screen, "DEMO", 22, HUD_DIM_COLOR, (config.SCREEN_WIDTH // 2, config.PITCH_TOP + 70))
    _draw_text(
        screen, "PRESS START TO PLAY", 20, HUD_DIM_COLOR,
        (config.SCREEN_WIDTH // 2, config.PITCH_TOP + 100),
    )


def _draw_menu_background(screen) -> None:
    """A simple vertical gradient matching the stadium's evening sky,
    instead of the old flat pitch-green fill -- keeps the menu/how-to-
    play/result screens visually part of the same game as the match."""
    for y in range(config.SCREEN_HEIGHT):
        t = y / (config.SCREEN_HEIGHT - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(MENU_BG_TOP, MENU_BG_BOTTOM))
        pygame.draw.line(screen, color, (0, y), (config.SCREEN_WIDTH, y))


def _draw_menu(screen, game: Game) -> None:
    _draw_text(screen, "HEADSCOTTER", 68, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 130))
    _draw_text(screen, "HEAD SOCCER, CMU STYLE", 24, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 185))

    top = 280
    spacing = 62
    for index, item in enumerate(MENU_ITEMS):
        selected = index == game.menu_index
        color = MENU_SELECT_COLOR if selected else HUD_TEXT_COLOR
        label = f"> {item} <" if selected else item
        _draw_text(screen, label, 40 if selected else 34, color, (config.SCREEN_WIDTH // 2, top + index * spacing))

    _draw_text(
        screen, "STICK: MOVE    A: SELECT / JUMP    X: KICK    P1: BACK", 20, HUD_DIM_COLOR,
        (config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 30),
    )


def _draw_how_to_play(screen) -> None:
    _draw_text(screen, "HOW TO PLAY", 52, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 80))
    lines = [
        "Knock the ball into the other goal more times than they knock it into yours.",
        "",
        "STICK LEFT/RIGHT   move",
        "A                  jump",
        "X                  kick the ball when it's right in front of you",
        "",
        "There is no goalkeeper -- you defend your own goal.",
        "",
        "Matches last 90 seconds. Tied at full time? Next goal wins -- sudden death.",
        "",
        "1 PLAYER is you against the CPU. 2 PLAYERS is head to head --",
        "stick 1 controls the left player, stick 2 controls the right player.",
        "",
        "P1 / Esc: back",
    ]
    y = 160
    for line in lines:
        if line:
            _draw_text(screen, line, 24, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, y))
        y += 32


def _draw_result(screen, game: Game) -> None:
    m = game.match
    winner = game.result_winner
    if game.mode == "1P":
        headline = "YOU WIN!" if winner == "left" else "CPU WINS"
    else:
        headline = "LEFT PLAYER WINS!" if winner == "left" else "RIGHT PLAYER WINS!"

    _draw_text(screen, headline, 60, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 200))
    _draw_text(screen, f"{m.score_left} - {m.score_right}", 72, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 290))

    if game.result_new_high_score:
        _draw_text(screen, "NEW BEST: MOST GOALS IN A WIN!", 28, MENU_SELECT_COLOR, (config.SCREEN_WIDTH // 2, 360))
    elif game.mode == "1P":
        _draw_text(
            screen, f"BEST GOALS IN A WIN: {game.result_high_score}", 24, HUD_DIM_COLOR,
            (config.SCREEN_WIDTH // 2, 360),
        )

    _draw_text(screen, "PRESS START", 28, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 440))
