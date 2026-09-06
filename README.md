# HeadScotter

An original head-soccer arcade game starring **Scotty**, the CMU
mascot, and a rival opponent, built for the CMU-Q arcade cabinet and its
[ArcadeLauncher](https://github.com/GDC-CMU/ArcadeLauncher).

Head soccer is a genre; this project's art, characters, name, and layout
are original and don't reproduce any specific commercial game.

![Main menu](docs/screenshots/menu.png)

## What it is

- A real, navigable **main menu** (1 Player / 2 Players / How to Play /
  Exit to Gallery), not just a "press start" splash.
- **1 Player** (versus a CPU opponent) and **2 Players** (head to head)
  modes, chosen from the menu.
- A **90-second match**, most goals wins, **sudden death** (next goal
  wins) if the score is tied at full time.
- Immediate normal kicks, jumping, and a separate hold/release power shot.
- Normal kicks create aerial lobs and high, decaying rebounds; charged shots
  travel faster and flatter.
- A resumable **pause menu** with Resume selected by default and Main Menu
  for explicitly abandoning a match.
- Completely silent gameplay, menus and demos; no audio device is initialized.
- A direct **Rematch / Main Menu** result flow, keeping the selected player mode.
- Bounded ball motion/impact feedback and clear power charge, recovery and
  ready cues; presentation never changes collision geometry.
- A **beatable, active 1v1 opponent**: it intercepts moving balls across the
  pitch, recovers against incoming goal threats, jumps past blocking players,
  and sets up forward headers and normal/power shots. It uses the same bodies,
  speed, jump and actions as a human, with delayed, imperfect observations.
- A self-playing **attract-mode demo** (CPU vs CPU, using the real
  match/physics/AI systems) after 15 seconds of idling on the menu.
- **All gameplay art is swappable PNGs** -- see
  [`assets/README.md`](assets/README.md).

![A match in progress](docs/screenshots/match_in_play.png)

![A goal](docs/screenshots/goal_celebration.png)

![The result screen](docs/screenshots/result.png)

## Controls

### Arcade cabinet

Two identical joysticks are wired to the cabinet. In **1 Player**, either
stick controls the human; in **2 Players**, stick 1 (device index 0)
controls the left player and stick 2 (device index 1) controls the
right player.

| Input | Action |
|---|---|
| Joystick axis 0 (left/right) | Move |
| Button 2 (X) | Normal kick **on press**; every fresh press attempts a kick |
| Button 3 (Y) | Jump |
| Button 1 (A) | Hold to charge a power shot; release to strike |
| Button 9 (Start) | Select menu item / Resume |
| Button 0 (B) / Button 5 (P1) | Pause during a match; resume while paused; otherwise back one level |

Normal kicks show a pose even on a miss; only an in-range ball receives an
impulse. Holding X does not repeat. Power-shot recovery never blocks normal X
presses. A remains a select alias on the main menu, but **not** while paused.

### Keyboard (development)

| Player | Move | Jump | Normal kick (press) | Power (hold/release) |
|---|---|---|---|---|
| 1 | `A` / `D` | `W` | `X` / `S` | `C` |
| 2 | Left / Right arrows | Up arrow | Down arrow / `/` | Right Shift |

`Enter`/`Space` confirm menu selections; `Esc`/`Backspace` are aliases
for the back button above.

### Pause and returning to the gallery

Either player's B/P1, or `Esc`, pauses any match phase, including kickoff
and goal celebration. **Resume** is selected first; **Main Menu** abandons
the match without recording a high score. Start/Enter selects; B/P1/Esc
resumes directly. Positions, velocities, clocks, cooldowns, and CPU decisions
stay frozen while paused. Unreleased power charges are cancelled. Release
held action/select controls before using them again after a transition.

Back from How to Play or results returns to the menu. Any demo input wakes
the menu without selecting anything. Back at the root menu, or its Exit to
Gallery entry, returns to the launcher. There is no network dependency at runtime.

On the result screen, **Rematch** is selected first. Start/Enter begins a fresh
match in the same 1P/2P mode, resetting score, actors and transient effects while
retaining high scores. Choose Main Menu or press Back to
leave instead. A held confirmation cannot immediately act in the next match.

Run windowed during development with:

```
$env:HEADSCOTTER_WINDOWED = "1"   # PowerShell
python main.py
```

## Architecture

Pure game logic is fully separated from rendering, so it's unit-testable
without a display:

```
main.py                  entrypoint at repo root
headscotter/
  config.py              every tunable constant (physics, timing, input, layout)
  physics.py              ball gravity/bounce/collision -- no pygame import
  players.py              player movement, jump, kick -- no pygame import
  world.py                joint bounded motion and solid world contacts -- no pygame import
  cpu.py                   the 1P opponent's AI -- no pygame import
  match.py                 clock, scoring, sudden death, high-score file -- no pygame import
  input.py                 two joysticks + keyboard -> game actions -- no pygame import
  feedback.py              bounded cosmetic motion/impact state -- no gameplay RNG
  game.py                  the state machine (only pygame-touching module besides render/assets)
  assets.py                the single point of PNG access
  render.py                draws only from assets.py surfaces
tools/generate_placeholders.py   regenerates the committed placeholder art deterministically
tools/generate_preview.py        regenerates the ArcadeLauncher gallery-card preview loop
tests/                    headless unit tests (SDL_VIDEODRIVER=dummy)
assets/                   sprites + assets/README.md (the art-swap contract)
assets/preview/           gallery attract-mode preview loop (see below)
docs/screenshots/         what it currently looks like
```

`config.py`, `physics.py`, `players.py`, `world.py`, `cpu.py`,
`match.py`, `input.py`, and `feedback.py` never import pygame -- enforced by
`tests/test_layering.py` -- so the ball physics, match rules, CPU
behaviour and input resolution are all testable with
plain `unittest`, no display required.

## Tuning the physics

Normal-kick launch and ground restitution are tuned for above-head aerial play,
not a shallow floor chip. The higher floor rebound has a separate settling
threshold so subpixel chatter stops without deadening ordinary head contacts.
Player gravity/jump, body dimensions and the ball speed cap remain unchanged.

Players and the ball advance together in bounded physics steps, with all
contacts resolved before rendering. Heads and torsos remain solid during
kicks, including rebounds into the kicker. Moving colliders transfer relative
normal motion, and shots inherit the kicker's movement.

When players squeeze a ball against each other or the pitch, blocked motion
is constrained instead of parking the ball inside a collider or snapping it
to another part of the field. Visual impact feedback represents contact episodes;
resting support and rolling friction do not emit repeated effects. Input edges and charge
time are consumed once per input update, independently of physics step count.
The nominal post/crossbar corners also use circle contact: the old
bottom-edge-only opening test could leave a rising ball parked at the opening.
Goal lines and dimensions are unchanged; the centre scores after the ball
clears the solid post, rather than passing through its lower corner.

Every physics constant -- gravity, bounce restitution (ground/wall/head
separately), air drag, ground friction, kick impulse/angle/cooldown,
player speed/jump velocity, ball mass-ish tuning, and the CPU's reaction
delay/aim error -- is a named, commented constant in
`headscotter/config.py`. Nothing is hard-coded elsewhere. This is by
design: ball physics is the single thing most likely to need a
after-the-fact tuning pass once people are actually playing it on the
cabinet.

### CPU tactics

The CPU observes both the ball and opponent every **0.18 seconds**. Between
observations it predicts their motion from that stale snapshot: the actual
ball gravity, drag and rebounds, and the opponent's last observed movement
and jump. It cannot read future input or see an unobserved deflection.

There is no fixed defensive leash or timeout before chasing a ball. The CPU
looks for a reachable intercept, sets up on the useful side of the ball, and
recovers when an incoming shot threatens its goal. A blocked route triggers
a jump timed from the existing 85px bodies and human jump arc. It commits
until clear rather than reversing midway, and waits when another jumper
prevents a safe crossing.

For headers it evaluates reachable contact points using the real head rebound,
then moves/stops in the air to meet the ball. Normal kicks use this frame's
resulting facing; controlled distant/blocked attacks can use the existing
hold/release power shot. It leaves room for rebounds rather than crowding the
ball between two heads, and does not flatten a steep rising ball into a low
kick. These are tactical choices, not extra speed, powers or a goalkeeper.

Only `CPU_*` constants control these decisions. Tests exercise real live
crossings, headers, threat clearances, attacks against a stationary player,
mirrored opponents, and finite matches. Score averages are not used to weaken
the opponent or retune the human/game-wide physics.

## Attract-mode preview (`assets/preview/`)

The ArcadeLauncher's gallery plays a short looping animation *inside this
game's card* while the cabinet idles -- it cannot run our own game loop
to produce that (it's a separate process), so we ship a small
pre-rendered clip instead. `assets/preview/manifest.json` lists an
ordered sequence of `frame_NNN.png` files (200x150, 12fps, 20 frames / ~1.67s loop)
played on repeat; see the launcher's own preview contract for the full
rules. This is entirely optional/read-only from the launcher's side --
the launcher never runs this repo's code to produce it.

The clip is generated, not hand-drawn: `tools/generate_preview.py` drives
the real attract-mode demo (the same CPU-vs-CPU match shown in-game after
15s idle) headlessly through the real render path, time-lapsing a complete
kickoff-to-kickoff rally with the CPU's real movement, headers and separated
normal/power actions. The generator finds that rally from the fixed seed instead
of retaining stale goal timestamps. It is fully deterministic (fixed RNG seed, fixed
simulated timestep, no wall-clock or persisted state involved) -- running
it twice leaves `git status` clean. Regenerate after any art or physics
change that would make the loop stop matching how the game actually
plays:

```
python tools/generate_preview.py
```

For a bounded UI review without changing the gallery preview or source sprites:

```
python tools/generate_preview.py --ui-output <artifact-directory>
```

This captures main/help/pause/result and live power-charge frames at 800x600,
plus offscreen 1920x1080 letterboxed versions for scaling review. It does not
open cabinet controls or write high scores.

## Development

```
pip install -r requirements.txt
python -m unittest discover -s tests -v      # headless, no display needed
python tools/generate_placeholders.py         # regenerate placeholder art
python tools/generate_preview.py              # regenerate the gallery preview loop
python main.py                                # run the game (HEADSCOTTER_WINDOWED=1 for a window)
```