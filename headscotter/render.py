"""Rendering: draws players/ball/pitch from headscotter.assets surfaces,
plus HUD, menu, and result-screen text.

This is the one module that turns game state into pixels. Every piece of
gameplay art comes from a PNG loaded through :mod:`headscotter.assets`;
only HUD/menu text is drawn with pygame fonts, which is ordinary UI
chrome, not gameplay art, and unaffected by an art swap.
"""
from __future__ import annotations

from typing import Tuple

import pygame

from . import assets, config
from . import match as match_mod
from .game import Game, GameState, MENU_ITEMS

BACKGROUND_COLOR = (18, 100, 46)
HUD_BG_COLOR = (12, 34, 20)
HUD_TEXT_COLOR = (255, 255, 255)
HUD_ACCENT_COLOR = (255, 210, 90)
HUD_DIM_COLOR = (170, 200, 180)
MENU_SELECT_COLOR = (255, 210, 90)
LEFT_TEAM_COLOR = (224, 196, 140)   # matches Scotty's placeholder coat
RIGHT_TEAM_COLOR = (150, 190, 235)  # matches the rival's placeholder color
LINE_COLOR = (240, 240, 240)

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
    screen.fill(BACKGROUND_COLOR)
    if game.state is GameState.ATTRACT:
        _draw_menu(screen, game)
    elif game.state is GameState.HOW_TO_PLAY:
        _draw_how_to_play(screen)
    elif game.state in (GameState.MATCH, GameState.DEMO):
        _draw_pitch(screen)
        _draw_goals(screen)
        _draw_keepers(screen, game)
        _draw_players(screen, game)
        _draw_ball(screen, game)
        _draw_hud(screen, game)
        _draw_phase_banner(screen, game)
        if game.state is GameState.DEMO:
            _draw_demo_banner(screen)
    elif game.state is GameState.RESULT:
        _draw_pitch(screen)
        _draw_goals(screen)
        _draw_result(screen, game)


def _draw_pitch(screen) -> None:
    bg = assets.get("pitch_bg")
    screen.blit(bg, (0, 0))
    # Halfway line, center circle, and touchline -- cheap chrome drawn
    # directly, not gameplay art, so it never needs an asset swap.
    pygame.draw.line(
        screen, LINE_COLOR,
        (config.PITCH_CENTER_X, config.PITCH_TOP), (config.PITCH_CENTER_X, config.GROUND_Y), 2,
    )
    pygame.draw.circle(screen, LINE_COLOR, (round(config.PITCH_CENTER_X), config.GROUND_Y), 60, 2)
    pygame.draw.rect(
        screen, LINE_COLOR,
        (
            config.PITCH_LEFT, config.PITCH_TOP,
            config.PITCH_RIGHT - config.PITCH_LEFT, config.GROUND_Y - config.PITCH_TOP,
        ),
        2,
    )


def _draw_goals(screen) -> None:
    # The goal art is authored with its front post at the image's right
    # edge (see tools/generate_placeholders.make_goal) so the goal mouth
    # opens into the pitch and the net trails off into "out of bounds".
    goal = assets.get("goal")
    left_rect = goal.get_rect()
    left_rect.bottomright = (config.PITCH_LEFT, config.GROUND_Y)
    screen.blit(goal, left_rect)

    flipped = pygame.transform.flip(goal, True, False)
    right_rect = flipped.get_rect()
    right_rect.bottomleft = (config.PITCH_RIGHT, config.GROUND_Y)
    screen.blit(flipped, right_rect)


def _draw_keepers(screen, game: Game) -> None:
    left = assets.get("keeper_left")
    rect = left.get_rect(center=(round(game.keeper_left.x), round(game.keeper_left.y)))
    screen.blit(left, rect)

    right = assets.get("keeper_right")
    rect = right.get_rect(center=(round(game.keeper_right.x), round(game.keeper_right.y)))
    screen.blit(right, rect)


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
        name = f"{prefix}_run_1"
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
    pygame.draw.rect(screen, HUD_BG_COLOR, (0, 0, config.SCREEN_WIDTH, config.HUD_HEIGHT))
    pygame.draw.line(screen, HUD_ACCENT_COLOR, (0, config.HUD_HEIGHT), (config.SCREEN_WIDTH, config.HUD_HEIGHT), 2)

    m = game.match
    left_name, right_name = _team_labels(game)

    _draw_text(screen, left_name, 30, LEFT_TEAM_COLOR, (150, 32))
    _draw_text(screen, str(m.score_left), 54, HUD_TEXT_COLOR, (150, 74))

    icon = assets.get("hud_ball_icon")
    icon_rect = icon.get_rect(center=(config.SCREEN_WIDTH // 2, 60))
    screen.blit(icon, icon_rect)

    _draw_text(screen, right_name, 30, RIGHT_TEAM_COLOR, (config.SCREEN_WIDTH - 150, 32))
    _draw_text(screen, str(m.score_right), 54, HUD_TEXT_COLOR, (config.SCREEN_WIDTH - 150, 74))

    if m.sudden_death:
        _draw_text(screen, "SUDDEN DEATH", 28, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 90))
    else:
        _draw_text(screen, _format_clock(m.time_remaining), 46, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 92))


def _draw_phase_banner(screen, game: Game) -> None:
    m = game.match
    if m.phase is match_mod.MatchPhase.GOAL_CELEBRATION:
        _draw_text(screen, "GOAL!", 72, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 300))
    elif m.phase is match_mod.MatchPhase.KICKOFF:
        # The very first kickoff of the match is the only moment the clock
        # still reads the full match length untouched; every restart after
        # a goal has already ticked down, so this distinguishes them for free.
        if m.time_remaining >= config.MATCH_SECONDS - 0.05 and m.last_scoring_side is None:
            _draw_text(screen, "KICK OFF!", 48, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 300))
        else:
            _draw_text(screen, "READY", 40, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 300))


def _draw_demo_banner(screen) -> None:
    # Positioned in the clear grass strip just below the pitch boundary
    # line (config.PITCH_TOP) and well above the center circle/keepers,
    # so neither line collides with a pitch marking or any gameplay art.
    _draw_text(screen, "DEMO", 24, HUD_DIM_COLOR, (config.SCREEN_WIDTH // 2, config.PITCH_TOP + 30))
    _draw_text(
        screen, "PRESS START TO PLAY", 22, HUD_DIM_COLOR,
        (config.SCREEN_WIDTH // 2, config.PITCH_TOP + 62),
    )


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
        y += 34


def _draw_result(screen, game: Game) -> None:
    m = game.match
    winner = game.result_winner
    if game.mode == "1P":
        headline = "YOU WIN!" if winner == "left" else "CPU WINS"
    else:
        headline = "LEFT PLAYER WINS!" if winner == "left" else "RIGHT PLAYER WINS!"

    _draw_text(screen, headline, 60, HUD_ACCENT_COLOR, (config.SCREEN_WIDTH // 2, 220))
    _draw_text(screen, f"{m.score_left} - {m.score_right}", 72, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 310))

    if game.result_new_high_score:
        _draw_text(screen, "NEW BEST: MOST GOALS IN A WIN!", 28, MENU_SELECT_COLOR, (config.SCREEN_WIDTH // 2, 380))
    elif game.mode == "1P":
        _draw_text(
            screen, f"BEST GOALS IN A WIN: {game.result_high_score}", 24, HUD_DIM_COLOR,
            (config.SCREEN_WIDTH // 2, 380),
        )

    _draw_text(screen, "PRESS START", 28, HUD_TEXT_COLOR, (config.SCREEN_WIDTH // 2, 460))
