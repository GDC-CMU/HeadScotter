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
from .game import Game, GameState, MENU_ITEMS, PAUSE_ITEMS, RESULT_ITEMS

HUD_TEXT_COLOR = (255, 255, 255)
HUD_ACCENT_COLOR = (255, 210, 90)
HUD_DIM_COLOR = (210, 220, 230)
MENU_SELECT_COLOR = (255, 210, 90)
MENU_BG_TOP = (30, 42, 70)
MENU_BG_BOTTOM = (14, 20, 34)
MENU_ROW_BG = (48, 56, 74)
MENU_ROW_Y = 250
MENU_ROW_SPACING = 58
MENU_ROW_SIZE = 34
FOOTER_Y = 570
LEFT_TEAM_COLOR = (224, 196, 140)   # matches Scotty's placeholder coat
RIGHT_TEAM_COLOR = (150, 190, 235)  # matches the rival's placeholder color

_ANIM_INTERVAL = 0.12  # seconds per run-cycle frame

_font_cache = {}


def clear_caches() -> None:
    """Drop SDL-owned resources before a display/font lifetime ends."""
    _font_cache.clear()
    _menu_background.cache_clear()
    _menu_scene_veil.cache_clear()
    _menu_backplate.cache_clear()
    _scrim.cache_clear()
    _portrait.cache_clear()
    _goal_accent.cache_clear()
    _spinning_ball.cache_clear()
    _ball_stamp.cache_clear()
    _impact_ring.cache_clear()
    assets.clear_cache()


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
        _draw_stage(screen, game)
        screen.blit(_menu_scene_veil(), (0, 0))
        screen.blit(_menu_backplate(), (180, 65))
        _draw_menu(screen, game)
    elif game.state is GameState.HOW_TO_PLAY:
        _draw_menu_background(screen)
        _draw_how_to_play(screen, game)
    elif game.state in (GameState.MATCH, GameState.DEMO, GameState.PAUSED):
        _draw_match_scene(screen, game)
        if game.state is not GameState.PAUSED:
            _draw_phase_banner(screen, game)
        if game.state is GameState.DEMO:
            _draw_demo_banner(screen, game)
        elif game.state is GameState.PAUSED:
            _draw_pause(screen, game)
    elif game.state is GameState.RESULT:
        _draw_stage(screen, game)
        _draw_goals(screen, game)
        _draw_result(screen, game)


def _draw_match_scene(screen, game: Game) -> None:
    _draw_stage(screen, game)
    _draw_goals(screen, game)
    _draw_ball_motion(screen, game)
    _draw_players(screen, game)
    _draw_charge_indicator(screen, game.player_left, game.feedback.ready_remaining[0])
    _draw_charge_indicator(screen, game.player_right, game.feedback.ready_remaining[1])
    _draw_ball(screen, game)
    _draw_impacts(screen, game)
    _draw_hud(screen, game)


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
    clock = game.attract_clock * 0.4 if game.state is GameState.ATTRACT else game.anim_clock
    offset = int(clock * config.HOARDING_SCROLL_SPEED) % hoarding_w
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


def _draw_goals(screen, game: Game | None = None) -> None:
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
    if game is not None and game.feedback.goal_side is not None:
        fade = max(0.0, 1.0 - game.feedback.goal_age / config.GOAL_FEEDBACK_SECONDS)
        if fade:
            source, rect = (right, right_rect) if game.feedback.goal_side == "left" else (left, left_rect)
            glow = _goal_accent(source).copy()
            glow.set_alpha(round(160 * fade))
            screen.blit(glow, rect)


@lru_cache(maxsize=2)
def _goal_accent(source):
    result = source.copy()
    result.fill((255, 210, 90, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return result


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


def _draw_charge_indicator(screen, player, ready_remaining: float = 0.0) -> None:
    """Show charge, recovery and a brief ready cue, then get out of the way."""
    if player.kick_charge <= 0.0 and player.kick_cooldown <= 0.0 and ready_remaining <= 0.0:
        return

    head_top = player.y - config.HEAD_OFFSET_Y - config.HEAD_RADIUS
    rect = pygame.Rect(0, 0, _CHARGE_BAR_WIDTH, _CHARGE_BAR_HEIGHT)
    rect.midbottom = (round(player.x), round(head_top) - 8)

    pygame.draw.rect(screen, (20, 20, 24), rect, border_radius=3)
    if player.kick_charge > 0.0:
        fraction = player.charge_fraction
        color = _lerp_color(_CHARGE_BAR_COLOR_LOW, _CHARGE_BAR_COLOR_HIGH, fraction)
        label = "CHARGE"
    elif player.kick_cooldown > 0.0:
        total = config.KICK_COOLDOWN_SECONDS + config.POWER_SHOT_COOLDOWN_BONUS_SECONDS
        fraction = max(0.0, 1.0 - player.kick_cooldown / total)
        color = (150, 190, 235)
        label = "RECOVER"
    else:
        fraction = 1.0
        color = HUD_ACCENT_COLOR
        label = "READY"
    fill_width = round(_CHARGE_BAR_WIDTH * fraction)
    if fill_width > 0:
        fill_rect = pygame.Rect(rect.left, rect.top, fill_width, _CHARGE_BAR_HEIGHT)
        pygame.draw.rect(screen, color, fill_rect, border_radius=3)
    pygame.draw.rect(screen, (245, 245, 245), rect, 1, border_radius=3)
    _draw_text(screen, label, 15, color, (round(player.x), rect.top - 8))


def _draw_ball(screen, game: Game) -> None:
    ball = game.ball
    surface = _spinning_ball(assets.get("ball"), round(game.feedback.spin / 15) % 24)
    rect = surface.get_rect(center=(round(ball.x), round(ball.y)))
    screen.blit(surface, rect)


@lru_cache(maxsize=24)
def _spinning_ball(source, angle):
    return pygame.transform.rotate(source, -angle * 15)


@lru_cache(maxsize=64)
def _ball_stamp(source, size, color):
    silhouette = pygame.mask.from_surface(source).to_surface(
        setcolor=color, unsetcolor=(0, 0, 0, 0)
    )
    return pygame.transform.smoothscale(silhouette, size)


def _draw_ball_motion(screen, game: Game) -> None:
    ball = game.ball
    source = assets.get("ball")
    height = max(0.0, config.GROUND_Y - ball.y - ball.radius)
    scale = max(0.45, 1.0 - height / 350)
    shadow = _ball_stamp(source, (round(28 * scale), 5), (0, 0, 0, round(70 * scale)))
    screen.blit(shadow, shadow.get_rect(center=(round(ball.x), config.GROUND_Y + 3)))
    for mark in game.feedback.trail:
        fade = max(0.0, 1.0 - mark.age / config.BALL_TRAIL_SECONDS)
        size = max(4, round(16 * fade))
        alpha = round(90 * fade / 15) * 15
        stamp = _ball_stamp(source, (size, size), (*HUD_ACCENT_COLOR, alpha))
        screen.blit(stamp, stamp.get_rect(center=(round(mark.x), round(mark.y))))


@lru_cache(maxsize=96)
def _impact_ring(radius, color, alpha):
    surface = pygame.Surface((2 * radius + 4, 2 * radius + 4), pygame.SRCALPHA)
    pygame.draw.circle(surface, (*color, alpha), (radius + 2, radius + 2), radius, width=1)
    return surface


def _draw_impacts(screen, game: Game) -> None:
    for mark in game.feedback.impacts:
        progress = min(1.0, mark.age / config.IMPACT_FEEDBACK_SECONDS)
        strong = mark.kind in ("kick", "power") or mark.kind.startswith("head:")
        color = HUD_ACCENT_COLOR if strong else (170, 200, 220)
        alpha = round((150 if strong else 90) * (1.0 - progress) / 15) * 15
        radius = round(game.ball.radius + 2 + progress * 10)
        ring = _impact_ring(radius, color, alpha)
        screen.blit(ring, ring.get_rect(center=(round(mark.x), round(mark.y))))


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
    flash = max(0.0, 1.0 - game.feedback.goal_age / config.GOAL_FEEDBACK_SECONDS)
    left_color = _lerp_color(HUD_TEXT_COLOR, HUD_ACCENT_COLOR, flash) if game.feedback.goal_side == "left" else HUD_TEXT_COLOR
    right_color = _lerp_color(HUD_TEXT_COLOR, HUD_ACCENT_COLOR, flash) if game.feedback.goal_side == "right" else HUD_TEXT_COLOR
    _draw_text(screen, str(m.score_left), 32, left_color, (panel_rect.left + 46, panel_rect.top + 40))

    _draw_text(screen, right_name, 18, RIGHT_TEAM_COLOR, (panel_rect.right - 46, panel_rect.top + 14))
    _draw_text(screen, str(m.score_right), 32, right_color, (panel_rect.right - 46, panel_rect.top + 40))

    if m.sudden_death:
        _draw_text(screen, "SUDDEN DEATH", 16, HUD_ACCENT_COLOR, (cx, panel_rect.bottom - 10))
    else:
        _draw_text(screen, _format_clock(m.time_remaining), 22, HUD_ACCENT_COLOR, (cx, panel_rect.bottom - 12))


def _draw_phase_banner(screen, game: Game) -> None:
    m = game.match
    if m.phase is match_mod.MatchPhase.GOAL_CELEBRATION:
        word = _font(72).render("GOAL!", True, HUD_ACCENT_COLOR)
        arrival = max(0.0, 1.0 - game.feedback.goal_age / 0.18)
        scale = 1.0 + 0.12 * arrival * arrival
        word = pygame.transform.smoothscale(
            word, (round(word.get_width() * scale), round(word.get_height() * scale))
        )
        screen.blit(word, word.get_rect(center=(config.SCREEN_WIDTH // 2, 250)))
        if m.last_scoring_side is not None:
            name = _team_labels(game)[0 if m.last_scoring_side == "left" else 1]
            _draw_text(screen, f"{name} SCORES", 26, HUD_TEXT_COLOR, (400, 309))
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


@lru_cache(maxsize=1)
def _menu_scene_veil():
    surface = _menu_background().copy()
    surface.set_alpha(160)
    return surface


@lru_cache(maxsize=1)
def _menu_backplate():
    surface = pygame.Surface((440, 470), pygame.SRCALPHA)
    pygame.draw.rect(surface, (14, 20, 34, 225), surface.get_rect(), border_radius=10)
    return surface


def _draw_menu_row(screen, label: str, index: int, selected: bool,
                   *, first_y: int = MENU_ROW_Y, spacing: int = MENU_ROW_SPACING) -> None:
    """Stable label geometry; selection has both a marker and a filled row."""
    y = first_y + index * spacing
    if selected:
        rect = pygame.Rect(220, y - 24, 360, 48)
        pygame.draw.rect(screen, MENU_ROW_BG, rect, border_radius=6)
        pygame.draw.rect(screen, MENU_SELECT_COLOR, rect, width=1, border_radius=6)
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
    if game.state is GameState.ATTRACT and game.menu_index in (0, 1):
        labels = ("YOU", "CPU") if game.menu_index == 0 else ("P1", "P2")
        for x, label in zip((90, config.SCREEN_WIDTH - 90), labels):
            _draw_text(screen, label, 20, HUD_ACCENT_COLOR if label != "CPU" else RIGHT_TEAM_COLOR,
                       (x, feet_y + 22))


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
    _draw_text(screen, "Normal kicks lob. Charged shots are faster and flatter.", 22, HUD_DIM_COLOR, (400, 488))
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
    for index, label in enumerate(RESULT_ITEMS):
        _draw_menu_row(screen, label, index, index == game.result_index, first_y=425, spacing=58)
    _draw_footer(screen, game, back="MAIN MENU", navigate=True)
