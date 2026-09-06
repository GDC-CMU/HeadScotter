# HeadScotter art and sound assets

All gameplay art is loaded from the PNG files in `assets/sprites/` through
the single loader in `headscotter/assets.py`. Nothing else in the codebase
draws gameplay sprites procedurally (the only exception is HUD/menu text,
drawn with pygame fonts as ordinary UI chrome, not gameplay art), and
nothing reads a sprite path directly -- every file below is declared once
in `headscotter.assets.SPRITE_SPECS` (name -> relative path -> nominal
pixel size). All sound effects follow the identical contract through
`headscotter/audio.py` -- see "Sound" below.

**To replace any piece of art, overwrite the file at the same path with
the same name, keeping (roughly) the same aspect ratio. No code changes
are required.** Every sprite is loaded once at first use, cached, and
scaled to its nominal size, so files of a different resolution still
work (they're rescaled), but keeping them native-sized avoids any blur
from upscaling.

Everything currently committed in `assets/sprites/` is a **placeholder**,
generated deterministically by `tools/generate_placeholders.py`. Re-run
that script any time you want to reset the stock look (for example after
adding a new logical sprite name to `SPRITE_SPECS`):

```
python tools/generate_placeholders.py
```

Missing or unreadable files never crash the game -- a bright magenta
placeholder with a crossed-out look is substituted, and a single warning
is printed to stderr, so an in-progress art pass never blocks testing.

## This is a side-view game -- no pitch markings, ever

HeadScotter draws a **side-view stadium**, not a top-down football pitch.
This is the single most important convention in the head-soccer genre: a
research pass over seven independent open-source implementations of it
found that **none of them draw a centre circle, halfway line, or
boundary rectangle**. If you are drawing new backdrop art, do not add
any of those -- they are exactly what makes a side-view scene read as an
aerial view instead. Pitch depth and interest come from the *stands*
(crowd, hoarding, floodlights), never from lines painted on the grass.

## Contrast and silhouette (read this before drawing new art)

This is the single most important lesson carried over from the club's
other cabinet games, learned from real play-testing: **a character drawn
in a dark, "natural" color disappears against a busy background from a
few feet away.** Both characters must stay legible under fair lighting,
at cabinet viewing distance, at all times:

- Keep both characters bright/saturated enough (or give them a strong
  outline) that they read clearly against the stadium/grass backdrop and
  against each other.
- Keep the two characters' **silhouettes** distinct, not just their
  colors -- Scotty is round-headed with two erect pointed ears and a
  rectangular beard; the rival is hard-edged/hexagonal with a single
  jagged crest and no ears at all. If you redraw either one, preserve
  (or exaggerate) that silhouette difference -- fill both solid black
  and confirm they're still distinguishable by shape alone -- so a
  colorblind visitor, or just a fast glance, can still tell them apart
  instantly.
- The ball must never blend into the grass or either character -- keep
  it light, with a visible dark pattern.

## Player geometry

Player sprites are anchored **feet-down**: the image's bottom-center
pixel is drawn at the character's feet position, which always sits on
`config.GROUND_Y`. The collidable "head" is a circle of radius
`HEAD_RADIUS` (32px) centered `HEAD_OFFSET_Y` (53px) above the feet
(`headscotter/config.py`) -- keep a replacement sprite's head roughly in
that same place so it still lines up with where the ball actually
bounces off it. The head is deliberately the dominant part of the
silhouette (~0.75 of total character height, per the genre's "big head"
convention), but there is a real, visible torso below it -- a shirt,
shorts, legs, and boots -- occupying the `HEAD_OFFSET_Y - HEAD_RADIUS`
gap the geometry leaves below the head (21px): "big head" means the
head dominates, not that the body is a ring or a sliver. All five poses
per character share one canvas size; art only facing **right** is
needed, since `headscotter/render.py` mirrors the sprite in code when a
character faces left.

| Files | Size | Used for |
|---|---|---|
| `scotty_idle.png` | 78x96 | Scotty (P1 / 1P human), standing still |
| `scotty_run_1.png`, `scotty_run_2.png` | 78x96 | Scotty running -- two-frame leg cycle |
| `scotty_jump.png` | 78x96 | Scotty airborne (jumping or falling) |
| `scotty_kick.png` | 78x96 | Scotty, briefly, on a kick attempt (including a miss) |
| `rival_idle.png` | 78x96 | The rival (CPU / P2), standing still |
| `rival_run_1.png`, `rival_run_2.png` | 78x96 | The rival running |
| `rival_jump.png` | 78x96 | The rival airborne |
| `rival_kick.png` | 78x96 | The rival, briefly, on a kick attempt (including a miss) |

**Scotty** is CMU's mascot, a Scottish Terrier, and is drawn to actually
read as one: a dark, shaggy coat, two erect pointed ears (not floppy),
a prominent rectangular beard/muzzle (a hard-edged block, not an
ellipse), and a bushy eyebrow tuft over the eye. Contrast against the
stadium and against the rival comes from the kit -- a bright CMU-red
shirt with white shorts -- not from the coat itself, the same
"dark coat needs a bright element somewhere" lesson as the club's other
games. Wears a real football kit: shirt, shorts, and boots, not just a
head.

**The rival** is a deliberately original, distinct opponent -- not a
copy of any commercial game's character, and not a recolour of Scotty's
shape. Its head is a hard-edged hexagonal "shield" with a pointed chin,
a single jagged dorsal crest instead of two ears, and two round eyes
(never a single visor covering half the face) -- a genuinely different
silhouette, not just a different colour. Wears a navy-and-white kit,
pairing with Scotty's red-and-cream as the genre's standard red-vs-blue
colour opposition. **Test any redraw of either character by filling it
solid black and comparing silhouettes side by side** -- if you cannot
tell which is which with colour removed, the shape hasn't changed enough.

## Ball

| File | Size | Used for |
|---|---|---|
| `ball.png` | 30x30 | The ball. Matches `BALL_RADIUS` in `headscotter/config.py` (diameter = 2 * radius). |

## The side-view stage

| File | Size | Used for |
|---|---|---|
| `bg_stadium.png` | 800x410 | Sky, floodlights, tiered stands, and a crowd. Static; drawn once per frame at `(0, 0)`, ending exactly where the hoarding begins (`config.HOARDING_Y`). |
| `bg_hoarding.png` | 560x50 | A scrolling advertising band, sitting directly above the grass at `config.HOARDING_Y`. `render.py` blits this twice with a wrapping horizontal offset (`config.HOARDING_SCROLL_SPEED`) for a continuous scroll -- a genre-standard trick, cheap and effective. |
| `ground.png` | 800x140 | The grass strip. **A single flat colour, no mowed stripes** -- the sourced genre convention (the research report found zero side-view implementations that draw stripes, a gradient, or perspective on the ground; mowed stripes are a top-down cue and were exactly the previous build's mistake). Drawn taller than the visible ground band and blitted starting `config.GROUND_VISUAL_MARGIN` (40px) *above* the actual collision line (`config.GROUND_SPRITE_Y`, not `config.GROUND_Y`) -- a second sourced trick (martinlhw/Head_Soccer) that leaves a sliver of grass visible behind the players instead of the ground starting exactly at their feet. This offset is purely a rendering detail; it never moves the real physics ground line. |

## Goals

| File | Size | Used for |
|---|---|---|
| `goal_left.png` | 80x200 | The left-hand goal, drawn in profile, flush with the left screen edge. Authored with the back of the net at the canvas's left edge (matching the screen boundary) and the front post at its right edge, opening into the pitch -- see `render._draw_goals()`, which anchors the image's bottom-left corner at `(config.PITCH_LEFT, config.GROUND_Y)`. |
| `goal_right.png` | 80x200 | The right-hand goal -- a separate file, not a code-mirrored copy of the left one, so a real art pass can give each end its own lighting/perspective if it wants to. Mirrored layout of `goal_left.png`; anchored by its bottom-right corner at `(config.PITCH_RIGHT, config.GROUND_Y)`. |

Both goals are sized to read as a real, credible net at full screen
size -- taller than a standing player (`GOAL_MOUTH_HEIGHT` is ~2.35x
`CHAR_HEIGHT`) -- matching the sourced genre convention, not shrunk to
hold down scoring. There is no goalkeeper anywhere in this game (see the
project's genre research report: no side-view head-soccer implementation
has one) -- each player defends their own goal directly; see
`headscotter/cpu.py` for how the CPU predicts reachable interceptions and
recovers against actual goal threats using the same field-player body.

## HUD

| File | Size | Used for |
|---|---|---|
| `scoreboard.png` | 260x70 | The compact HUD panel anchored at the top-center of the screen (`config.SCOREBOARD_TOP_Y`). `render.py` draws the score digits, team labels, and the clock/"SUDDEN DEATH" text on top of this panel as ordinary HUD text -- nothing about the score or clock is baked into the image itself. |

## Sound

All sound effects are loaded from the `.wav` files in `assets/sounds/`
through the single loader in `headscotter/audio.py` -- the audio
equivalent of `headscotter/assets.py`'s contract for art, and every file
below is declared once in `headscotter.audio.SOUND_SPECS`. **To replace
any sound, overwrite the file at the same path with the same name; no
code changes are required.**

Audio is entirely optional and degrades silently: if no audio device is
available or `pygame.mixer` encounters a device/driver error, the game
prints one warning to stderr and keeps running with no sound at all --
the cabinet must never fail to boot a game because of audio. Sound is
only ever turned on by the real game loop (`Game.init_display()`);
headless tests and the build-time placeholder/preview generator tools
never call it, so both stay silent and fully deterministic without any
special-casing.

Everything currently committed in `assets/sounds/` is a **placeholder**,
generated deterministically (fixed waveform formulas, never Python's
`random` module) by `tools/generate_sounds.py`:

```
python tools/generate_sounds.py
```

| File | Used for |
|---|---|
| `kick.wav` | An ordinary kick connecting (`players.normal_kick()`, on a fresh press), or a lightly charged power release. |
| `power_shot.wav` | A charged power shot connecting -- see "Power shot" below. Distinct from, and more dramatic than, an ordinary kick. |
| `bounce.wav` | A new incoming impact against ground/wall/ceiling, not floor support, rolling or separation (`physics.step_ball()`'s `on_bounce` hook). |
| `header.wav` | A new incoming head impact (`players.apply_head_collision()`'s impact hook), not overlap correction. Repeated substep corrections share one contact episode. |
| `goal.wav` | A goal is scored. |
| `whistle.wav` | Kickoff (the opening whistle and every restart after a goal) and full time. |
| `menu_move.wav` | Moving the menu selection up or down. |
| `menu_select.wav` | Confirming a menu selection. |

## Power shot

Holding A (keyboard C / Right Shift) charges a power shot; releasing it fires, with
strength interpolated continuously between an ordinary kick (an
immediate tap-and-release) and a full power shot (held for
`config.POWER_SHOT_CHARGE_SECONDS`) -- see `players.update_power_shot()`. A
small charge meter appears above a charging player's head
(`render._draw_charge_indicator()`) so the mechanic is discoverable
without a tutorial; it is drawn procedurally (a simple bar, like the
HUD's score/clock text), not a sprite, since it is dynamic gameplay
feedback rather than art. A fully-charged shot costs extra recovery time
(`config.POWER_SHOT_COOLDOWN_BONUS_SECONDS`) on top of its base recovery.
Normal X presses do not share that cooldown. Pausing cancels any uncommitted
charge, so an old release cannot fire on resume.

## Adding a brand-new sprite

1. Add an entry to `SPRITE_SPECS` in `headscotter/assets.py` (name,
   relative path, nominal size).
2. Add a matching generator function in `tools/generate_placeholders.py`
   so the placeholder set stays complete, then run the script.
3. Reference the new sprite by name from `headscotter/render.py` with
   `assets.get("your_new_name")`.

## Adding a brand-new sound

1. Add an entry to `SOUND_SPECS` in `headscotter/audio.py` (name ->
   relative path).
2. Add a matching generator function in `tools/generate_sounds.py` so
   the placeholder set stays complete, then run the script.
3. Play it from `headscotter/game.py` with `audio.play("your_new_name")`.
