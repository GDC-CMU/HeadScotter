#!/usr/bin/env python
"""Regenerate the committed placeholder sound-effect .wav files
deterministically.

Every waveform here is synthesised from fixed formulas (sine sweeps,
trapezoid envelopes, and a deterministic hash-noise function -- never
Python's ``random`` module, whose exact output is not a documented
cross-version guarantee), so running this script twice in a row leaves
``git status`` clean. Run it whenever a new logical sound is added to
``headscotter.audio.SOUND_SPECS``, or any time you want to reset
``assets/sounds/`` back to the stock placeholder set.

Real sound can replace any file here with zero code changes -- see
``assets/README.md``.
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from headscotter.audio import ASSETS_ROOT, SOUND_SPECS  # noqa: E402

SAMPLE_RATE = 22050


def _pseudo_noise(i: int) -> float:
    """A deterministic hash-noise function (the classic "sin hash"
    trick) -- never Python's ``random`` module, so this is reproducible
    independent of any RNG implementation detail. Returns a value in
    [-1, 1]."""
    x = math.sin(i * 12.9898) * 43758.5453
    return 2.0 * (x - math.floor(x)) - 1.0


def _sweep_tone(freq_start: float, freq_end: float, duration: float, decay_k: float = 6.0, amp: float = 0.9):
    """A sine tone whose frequency glides linearly from ``freq_start``
    to ``freq_end`` over ``duration`` seconds, under an exponential
    decay envelope -- phase is accumulated incrementally so the sweep
    has no discontinuities/clicks."""
    n = max(1, int(duration * SAMPLE_RATE))
    samples = [0.0] * n
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = freq_start + (freq_end - freq_start) * (t / duration)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        env = math.exp(-decay_k * t / duration)
        samples[i] = amp * env * math.sin(phase)
    return samples


def _trapezoid_tone(freq: float, duration: float, amp: float = 0.7, attack: float = 0.01, release: float = 0.02):
    """A steady tone with a linear attack and release -- reads as a
    sustained note (e.g. a whistle) rather than a decaying pluck."""
    n = max(1, int(duration * SAMPLE_RATE))
    samples = [0.0] * n
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        if t < attack:
            env = t / attack
        elif t > duration - release:
            env = max(0.0, (duration - t) / release)
        else:
            env = 1.0
        samples[i] = amp * env * math.sin(phase)
    return samples


def _noise_burst(duration: float, decay_k: float = 12.0, amp: float = 0.5):
    n = max(1, int(duration * SAMPLE_RATE))
    samples = [0.0] * n
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-decay_k * t / duration)
        samples[i] = amp * env * _pseudo_noise(i)
    return samples


def _silence(duration: float):
    return [0.0] * max(0, int(duration * SAMPLE_RATE))


def _pad(samples, length: int):
    if len(samples) >= length:
        return samples[:length]
    return samples + [0.0] * (length - len(samples))


def _mix(*sample_lists):
    length = max((len(s) for s in sample_lists), default=0)
    out = [0.0] * length
    for s in sample_lists:
        for i, v in enumerate(s):
            out[i] += v
    peak = max((abs(v) for v in out), default=0.0)
    if peak > 1.0:
        out = [v / peak for v in out]
    return out


def _concat(*sample_lists):
    out = []
    for s in sample_lists:
        out.extend(s)
    return out


def _write_wav(path: Path, samples) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = b"".join(struct.pack("<h", max(-32768, min(32767, int(round(s * 32767.0))))) for s in samples)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(frames)


# --- Individual sound designs --------------------------------------------------------
def make_kick():
    tone = _sweep_tone(380, 140, 0.10, decay_k=8.0, amp=0.8)
    click = _pad(_noise_burst(0.02, decay_k=20.0, amp=0.5), len(tone))
    return _mix(tone, click)


def make_power_shot():
    # A rising "charge" whoosh, then a punchier impact than an ordinary kick.
    whoosh = _sweep_tone(150, 450, 0.12, decay_k=2.0, amp=0.45)
    impact = _sweep_tone(480, 130, 0.22, decay_k=6.0, amp=0.95)
    click = _pad(_noise_burst(0.05, decay_k=14.0, amp=0.6), len(impact))
    return _concat(whoosh, _mix(impact, click))


def make_bounce():
    tone = _sweep_tone(180, 90, 0.09, decay_k=14.0, amp=0.6)
    click = _pad(_noise_burst(0.02, decay_k=25.0, amp=0.25), len(tone))
    return _mix(tone, click)


def make_header():
    tone = _sweep_tone(260, 140, 0.07, decay_k=16.0, amp=0.7)
    click = _pad(_noise_burst(0.015, decay_k=28.0, amp=0.3), len(tone))
    return _mix(tone, click)


def make_goal():
    # A cheerful four-note ascending arpeggio.
    notes = [523.25, 659.25, 783.99, 1046.50]
    return _concat(*[_sweep_tone(f, f, 0.14, decay_k=5.0, amp=0.75) for f in notes])


def make_whistle():
    toot = _trapezoid_tone(2800, 0.15, amp=0.6)
    return _concat(toot, _silence(0.07), toot)


def make_menu_move():
    return _sweep_tone(700, 700, 0.045, decay_k=10.0, amp=0.5)


def make_menu_select():
    return _concat(
        _trapezoid_tone(500, 0.07, amp=0.55, attack=0.005, release=0.02),
        _trapezoid_tone(750, 0.09, amp=0.6, attack=0.005, release=0.03),
    )


GENERATORS = {
    "kick": make_kick,
    "power_shot": make_power_shot,
    "bounce": make_bounce,
    "header": make_header,
    "goal": make_goal,
    "whistle": make_whistle,
    "menu_move": make_menu_move,
    "menu_select": make_menu_select,
}


def main() -> int:
    missing = sorted(set(SOUND_SPECS) - set(GENERATORS))
    if missing:
        raise SystemExit(f"no placeholder generator registered for: {missing}")

    for name, rel_path in sorted(SOUND_SPECS.items()):
        samples = GENERATORS[name]()
        out_path = ASSETS_ROOT / rel_path
        _write_wav(out_path, samples)
        print(f"wrote {out_path.relative_to(REPO_ROOT)}")

    print(f"generated {len(SOUND_SPECS)} placeholder sounds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
