"""Song-length (linear, non-looping) rendering for the Songs tab.

The loop renderer (styles.py) plays two identical cycles so tails wrap round the
loop seam. A song is different: it plays once, start to finish, and ends on a
real final chord. This module gives the same instruments a linear timeline and a
linear mixdown, plus small helpers for arranging by section.
"""
import numpy as np
from scipy.signal import fftconvolve
import dsp
from dsp import SR, make_ir, highpass, compress_st, highshelf
from instruments import Timeline
from common import limiter


class SongTimeline(Timeline):
    """Plays once. `bars` is the song length; `tail_s` leaves room for the last
    chord and the reverb to ring out."""

    def __init__(self, bpm, bars, tail_s=5.0, seed=1):
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.barlen = 4 * self.beat
        self.bars = bars
        self.loop_s = bars * self.barlen + tail_s      # used by instruments as "end of time"
        self.loop_n = int(round(bars * self.barlen * SR))
        self.cycles = 1
        self.n = self.loop_n + int(tail_s * SR)
        self.rng = np.random.default_rng(seed)
        dsp.LOOP_S = None                               # no LFO snapping needed

    def place(self, buf, t, sig):
        s = int(round(t * SR))
        if s < 0:
            sig = sig[-s:]; s = 0
        e = min(self.n, s + len(sig))
        if e > s:
            buf[s:e] += sig[:e - s]


def automate(tl, x, points):
    """Volume automation. points: [(bar, gain), ...] — linear ramps between them."""
    bars = np.array([p[0] for p in points], float)
    gains = np.array([p[1] for p in points], float)
    t = np.arange(len(x)) / SR / tl.barlen
    return x * np.interp(t, bars, gains)


def mixdown_song(tl, tracks, reverb, loud_db=-13.0, win_bars=8):
    """Linear mixdown. Normalises so the LOUDEST `win_bars` window (the big chorus)
    sits at `loud_db` RMS; quieter sections keep their natural level."""
    L = np.zeros(tl.n); R = np.zeros(tl.n)
    sL = np.zeros(tl.n); sR = np.zeros(tl.n)
    for tr in tracks:
        L += tr['L']; R += tr['R']
        sL += tr['L'] * tr.get('send', 0.15)
        sR += tr['R'] * tr.get('send', 0.15)
    ir = make_ir(reverb.get('t60', 1.6), reverb.get('predelay', 0.015),
                 damp_end=reverb.get('damp_end', 2000))
    mono = highpass((sL + sR) * 0.5, 180)
    ret = reverb.get('ret', 0.5)
    L += fftconvolve(mono, ir[0])[:tl.n] * ret
    R += fftconvolve(mono, ir[1])[:tl.n] * ret
    L, R = highpass(L, 32), highpass(R, 32)
    L, R = compress_st(L, R, -20, 2.0, 15, 180)
    L = highshelf(L, 8000, 1.0); R = highshelf(R, 8000, 1.0)
    w = int(win_bars * tl.barlen * SR)
    p = (L ** 2 + R ** 2) / 2
    cs = np.concatenate([[0], np.cumsum(p)])
    best = max((cs[i + w] - cs[i]) / w for i in range(0, max(1, len(p) - w), SR // 2))
    g = 10 ** (loud_db / 20) / np.sqrt(best)
    L, R = L * g, R * g
    L, R = limiter(L, R, 10 ** (-1.2 / 20), 64, 2000.0)
    # gentle fade at the very end of the tail
    f = int(1.5 * SR)
    L[-f:] *= np.linspace(1, 0, f) ** 2; R[-f:] *= np.linspace(1, 0, f) ** 2
    return L, R
