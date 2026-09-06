# HeadScotter art assets

All gameplay art is loaded from the PNG files in `assets/sprites/` through
the single loader in `headscotter/assets.py`. Nothing else in the codebase
draws gameplay sprites procedurally (the only exception is HUD/menu text,
drawn with pygame fonts as ordinary UI chrome, not gameplay art), and
nothing reads a sprite path directly -- every file below is declared once
in `headscotter.assets.SPRITE_SPECS` (name -> relative path -> nominal
pixel size).

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
  colors -- Scotty has floppy ears and a snout; the rival has antenna and
  a visor and no ears at all. If you redraw either one, preserve (or
  exaggerate) that silhouette difference so a colorblind visitor, or
  just a fast glance, can still tell them apart instantly.
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
convention) -- the body below it is small, almost a stub, on purpose.
All five poses per character share one canvas size; art only facing
**right** is needed, since `headscotter/render.py` mirrors the sprite in
code when a character faces left.

| Files | Size | Used for |
|---|---|---|
| `scotty_idle.png` | 72x90 | Scotty (P1 / 1P human), standing still |
| `scotty_run_1.png`, `scotty_run_2.png` | 72x90 | Scotty running -- two-frame leg cycle |
| `scotty_jump.png` | 72x90 | Scotty airborne (jumping or falling) |
| `scotty_kick.png` | 72x90 | Scotty, briefly, right after a kick connects |
| `rival_idle.png` | 72x90 | The rival (CPU / P2), standing still |
| `rival_run_1.png`, `rival_run_2.png` | 72x90 | The rival running |
| `rival_jump.png` | 72x90 | The rival airborne |
| `rival_kick.png` | 72x90 | The rival, briefly, right after a kick connects |

**Scotty** is CMU's mascot, a Scottish Terrier, drawn big-headed
head-soccer style: floppy pointed ears, a snout, a shaggy fur texture,
and a CMU-red collar stripe, on a warm cream/tan coat for contrast.

**The rival** is a deliberately original, distinct opponent -- not a
copy of any commercial game's character -- with a completely different
silhouette from Scotty: antenna instead of ears, one wide visor instead
of a snout, and a rectangular jersey body instead of a rounded one, in
cool blue-grey with orange trim.

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
`headscotter/cpu.py`'s `CPU_MAX_ADVANCE_FRACTION` for how the CPU
opponent's defensive positioning does that job instead.

## HUD

| File | Size | Used for |
|---|---|---|
| `scoreboard.png` | 260x70 | The compact HUD panel anchored at the top-center of the screen (`config.SCOREBOARD_TOP_Y`). `render.py` draws the score digits, team labels, and the clock/"SUDDEN DEATH" text on top of this panel as ordinary HUD text -- nothing about the score or clock is baked into the image itself. |

## Adding a brand-new sprite

1. Add an entry to `SPRITE_SPECS` in `headscotter/assets.py` (name,
   relative path, nominal size).
2. Add a matching generator function in `tools/generate_placeholders.py`
   so the placeholder set stays complete, then run the script.
3. Reference the new sprite by name from `headscotter/render.py` with
   `assets.get("your_new_name")`.
