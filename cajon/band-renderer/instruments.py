"""Instruments: each collects note events for ONE loop cycle, then renders them
into a buffer that holds `cycles` identical copies (cycle 1 is pre-roll so that
cycle 2 already contains the tails ringing over from the loop end)."""
import numpy as np
from dsp import (SR, midi_hz, pluck, saw, svf_lp, lowpass, highpass, bandpass, peak,
                 compress, dcblock)

OPEN = [40, 45, 50, 55, 59, 64]           # E2 A2 D3 G3 B3 E4


class Timeline:
    def __init__(self, bpm, bars, cycles=2, seed=1):
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.barlen = 4 * self.beat
        self.bars = bars
        self.loop_s = bars * self.barlen
        self.loop_n = int(round(self.loop_s * SR))
        self.cycles = cycles
        self.n = self.loop_n * cycles + int(6 * SR)
        self.rng = np.random.default_rng(seed)
        import dsp
        dsp.LOOP_S = self.loop_n / SR

    def t(self, bar, beat=0.0):
        return bar * self.barlen + beat * self.beat

    def buf(self):
        return np.zeros(self.n)

    def place(self, buf, t, sig):
        """add sig at time t in every cycle"""
        for c in range(self.cycles + 1):
            s = int(round(t * SR)) + c * self.loop_n
            if s < 0:
                continue
            e = min(self.n, s + len(sig))
            if e > s:
                buf[s:e] += sig[:e - s]


def _fade(sig, rel_s=0.03):
    n = len(sig)
    r = min(n, int(rel_s * SR))
    if r > 0:
        sig[n - r:] *= np.linspace(1, 0, r) ** 2
    return sig


# ============================================================ guitars
class Guitar:
    """Six strings, strums, arpeggios, palm mutes, optional 12-string courses."""

    def __init__(self, tl, twelve=False, t60=2.6, bright=0.6, jitter=0.005, seed=11,
                 max_len=4.0):
        self.tl = tl
        self.twelve = twelve
        self.t60 = t60
        self.bright = bright
        self.jitter = jitter
        self.rng = np.random.default_rng(seed)
        self.ev = {s: [] for s in range(6)}
        self.max_len = max_len

    def _hum(self, t):
        return t + self.rng.normal(0, self.jitter)

    def note(self, t, string, midi, vel=0.7, mute=False, dur=None, t60=None, bright=None):
        self.ev[string].append(dict(t=self._hum(t), m=midi, v=vel, mute=mute, dur=dur,
                                    t60=t60, bright=bright))

    def fret(self, t, string, fret, **kw):
        self.note(t, string, OPEN[string] + fret, **kw)

    def strum(self, t, shape, d='D', vel=0.75, spread=None, strings=None, mute=False,
              dur=None):
        """shape: 6 frets low->high, -1 = not played. d: 'D' down / 'U' up."""
        idx = [i for i in range(6) if shape[i] >= 0 and (strings is None or i in strings)]
        if d == 'U':
            idx = idx[::-1]
            vel *= 0.8
        spread = spread if spread is not None else (0.010 if d == 'D' else 0.007)
        spread *= 1 + self.rng.normal(0, 0.15)
        t0 = self._hum(t)
        for k, s in enumerate(idx):
            v = vel * (1 + self.rng.normal(0, 0.07)) * (0.92 + 0.08 * (k == 0))
            self.ev[s].append(dict(t=t0 + k * spread, m=OPEN[s] + shape[s], v=max(0.05, v),
                                   mute=mute, dur=dur, t60=None, bright=None))

    def choke(self, t, strings=range(6)):
        for s in strings:
            self.ev[s].append(dict(t=t, m=None))

    def render(self):
        out = self.tl.buf()
        L = self.tl.loop_s
        for s in range(6):
            evs = sorted(self.ev[s], key=lambda e: e['t'])
            for i, e in enumerate(evs):
                if e['m'] is None:
                    continue
                nxt = evs[i + 1]['t'] if i + 1 < len(evs) else evs[0]['t'] + L
                length = min(nxt - e['t'], self.max_len)
                if e['dur'] is not None:
                    length = min(length, e['dur'])
                length = max(length, 0.03)
                t60 = e['t60'] or self.t60
                br = e['bright'] if e['bright'] is not None else self.bright
                v = e['v']
                if e['mute']:
                    t60, br, v = 0.11, br * 0.45, v * 0.85
                f = midi_hz(e['m'])
                sig = pluck(f, length + 0.03, v, t60, br, pickpos=0.13 + 0.1 * self.rng.random(),
                            rng=self.rng)
                if self.twelve:
                    if s <= 3:   # octave course
                        sig2 = pluck(f * 2, length + 0.03, v * 0.55, t60 * 0.8, min(1, br + 0.2),
                                     0.2, rng=self.rng)
                        sig = sig + np.concatenate([np.zeros(80), sig2[:-80]])
                    else:        # unison course, slightly detuned
                        sig2 = pluck(f * 1.0025, length + 0.03, v * 0.8, t60, br, 0.16, rng=self.rng)
                        sig = sig + np.concatenate([np.zeros(40), sig2[:-40]])
                self.tl.place(out, e['t'], _fade(sig))
        return dcblock(out)


# ============================================================ bass
class Bass:
    def __init__(self, tl, tone='finger', jitter=0.004, seed=21):
        self.tl = tl
        self.tone = tone
        self.jitter = jitter
        self.rng = np.random.default_rng(seed)
        self.ev = []

    def note(self, t, midi, dur, vel=0.8, slide_from=None):
        self.ev.append((t + self.rng.normal(0, self.jitter), midi, dur, vel * (1 + self.rng.normal(0, 0.05))))

    def render(self):
        out = self.tl.buf()
        pick = self.tone == 'pick'
        for (t, m, dur, v) in self.ev:
            f = midi_hz(m)
            n = int((dur + 0.04) * SR)
            s = pluck(f, dur + 0.04, v, 3.5, 0.55 if pick else 0.3, 0.12 if pick else 0.25, rng=self.rng)
            # sub layer keeps the fundamental solid
            tt = np.arange(n) / SR
            sub = np.sin(2 * np.pi * f * tt) * np.exp(-tt / 1.6) * np.minimum(1, tt / 0.006) * v * 0.55
            s = s[:n] + sub
            self.tl.place(out, t, _fade(s, 0.04))
        out = dcblock(out)
        out = np.tanh(out * (2.2 if pick else 1.4)) / 1.2
        out = lowpass(out, 2600 if pick else 1500, 0.8)
        out = peak(out, 90, 3.0, 0.9)
        out = peak(out, 700 if pick else 400, 2.5 if pick else -2.0, 1.0)
        out = highpass(out, 38)
        return compress(out, -18, 4.0, 5, 120, 4)


# ============================================================ keys
class EPiano:
    """FM electric piano (tine + bell)."""

    def __init__(self, tl, seed=31):
        self.tl = tl
        self.rng = np.random.default_rng(seed)
        self.ev = []

    def chord(self, t, midis, dur, vel=0.6):
        for k, m in enumerate(midis):
            self.ev.append((t + k * 0.004 + self.rng.normal(0, 0.004), m, dur, vel * (1 + self.rng.normal(0, 0.08))))

    def render(self):
        out = self.tl.buf()
        for (t, m, dur, v) in self.ev:
            f = midi_hz(m)
            n = int((dur + 0.35) * SR)
            tt = np.arange(n) / SR
            idx = (1.8 * v + 0.4) * np.exp(-tt / 0.35) + 0.25
            mod = np.sin(2 * np.pi * f * tt)
            car = np.sin(2 * np.pi * f * tt + idx * mod)
            tine = np.sin(2 * np.pi * f * 14.1 * tt) * np.exp(-tt / 0.02) * 0.15 * v
            env = np.exp(-tt / (1.4 - 0.3 * (m - 60) / 24)) * np.minimum(1, tt / 0.002)
            rel = np.ones(n)
            r0 = int(dur * SR)
            rel[r0:] = np.exp(-(np.arange(n - r0)) / (0.08 * SR))
            self.tl.place(out, t, (car * env * rel + tine) * v * 0.3)
        return out


class Organ:
    """Drawbar organ (tonewheel-ish additive) — pair with dsp.leslie()."""

    def __init__(self, tl, drawbars=(0.6, 1.0, 0.5, 0.7, 0.0, 0.3, 0.0, 0.15), seed=41):
        self.tl = tl
        self.db = drawbars
        self.rng = np.random.default_rng(seed)
        self.ev = []

    def chord(self, t, midis, dur, vel=0.5):
        for m in midis:
            self.ev.append((t, m, dur, vel))

    def render(self):
        out = self.tl.buf()
        ratios = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]
        for (t, m, dur, v) in self.ev:
            f = midi_hz(m)
            n = int((dur + 0.08) * SR)
            tt = np.arange(n) / SR
            s = np.zeros(n)
            for r, g in zip(ratios, self.db):
                if g > 0 and f * r < 9000:
                    s += g * np.sin(2 * np.pi * f * r * tt + self.rng.random() * 6.28)
            env = np.minimum(1, tt / 0.012)
            r0 = int(dur * SR)
            env[r0:] *= np.exp(-(np.arange(n - r0)) / (0.02 * SR))
            click = self.rng.uniform(-1, 1, n) * np.exp(-tt / 0.003) * 0.08
            self.tl.place(out, t, (s * env + click) * v * 0.12)
        return lowpass(out, 6000)


class Pad:
    """Detuned-saw string pad through a slowly moving low-pass."""

    def __init__(self, tl, cutoff=1400, voices=5, detune=0.10, attack=0.9, release=1.2, seed=51):
        self.tl, self.cut, self.voices, self.det = tl, cutoff, voices, detune
        self.att, self.rel = attack, release
        self.rng = np.random.default_rng(seed)
        self.ev = []

    def chord(self, t, midis, dur, vel=0.5):
        for m in midis:
            self.ev.append((t, m, dur, vel))

    def render(self):
        out = self.tl.buf()
        out2 = self.tl.buf()
        for (t, m, dur, v) in self.ev:
            f = midi_hz(m)
            n = int((dur + self.rel) * SR)
            tt = np.arange(n) / SR
            s = np.zeros(n)
            s2 = np.zeros(n)
            for k in range(self.voices):
                dc = (k - (self.voices - 1) / 2) / max(1, self.voices - 1) * 2 * self.det  # semitones
                fr = f * 2 ** (dc / 12) * (1 + 0.002 * np.sin(2 * np.pi * (0.2 + 0.1 * k) * tt))
                if k % 2 == 0:
                    s += saw(fr)
                if k % 2 == 1 or k == self.voices // 2:
                    s2 += saw(fr * 1.0006)
            ph = self.rng.random() * 6
            cut = self.cut * (0.7 + 0.3 * np.sin(2 * np.pi * 0.15 * tt + ph))
            env = np.minimum(1, tt / self.att)
            r0 = int(dur * SR)
            env[r0:] *= np.exp(-(np.arange(n - r0)) / (self.rel / 4 * SR))
            g = env * v * 0.25 * 2 / self.voices
            self.tl.place(out, t, svf_lp(s, cut, 0.9) * g)
            self.tl.place(out2, t, svf_lp(s2, cut, 0.9) * g)
        return out, out2


# ============================================================ lead guitar
class Lead:
    """Singing sustained lead: KS string with bends and delayed vibrato (run it
    through dsp.amp for overdrive)."""

    def __init__(self, tl, t60=5.0, bright=0.55, seed=61):
        self.tl, self.t60, self.bright = tl, t60, bright
        self.rng = np.random.default_rng(seed)
        self.ev = []

    def note(self, t, midi, dur, vel=0.7, bend=0.0, bend_time=0.12, vib=0.25, release_bend=0.0):
        """bend: start this many semitones BELOW the target and rise to it."""
        self.ev.append((t, midi, dur, vel, bend, bend_time, vib, release_bend))

    def render(self):
        out = self.tl.buf()
        for (t, m, dur, v, bend, bt, vib, rb) in self.ev:
            n = int((dur + 0.05) * SR)
            tt = np.arange(n) / SR
            semis = np.zeros(n)
            if bend:
                k = np.clip(tt / bt, 0, 1)
                semis -= bend * (1 - (3 * k * k - 2 * k * k * k))
            if rb:
                st = max(0.0, dur - 0.18)
                k = np.clip((tt - st) / 0.18, 0, 1)
                semis -= rb * k * k
            vib_env = np.clip((tt - 0.25) / 0.4, 0, 1) * vib
            semis += vib_env * np.sin(2 * np.pi * 5.2 * tt)
            f0 = midi_hz(m) * 2 ** (semis / 12)
            s = pluck(midi_hz(m), dur + 0.05, v, self.t60, self.bright, 0.2, rng=self.rng, f0_curve=f0)
            self.tl.place(out, t, _fade(s, 0.06))
        return dcblock(out)


# ============================================================ percussion (light)
class Tambourine:
    def __init__(self, tl, seed=71):
        self.tl = tl
        self.rng = np.random.default_rng(seed)
        self.ev = []

    def hit(self, t, vel=0.7, shake=False):
        self.ev.append((t + self.rng.normal(0, 0.004), vel * (1 + self.rng.normal(0, 0.1)), shake))

    def render(self):
        out = self.tl.buf()
        for (t, v, shake) in self.ev:
            n = int(0.25 * SR)
            tt = np.arange(n) / SR
            if shake:
                env = np.minimum(1, tt / 0.012) * np.exp(-tt / 0.045)
            else:
                env = np.exp(-tt / 0.07) * np.minimum(1, tt / 0.001)
            nz = self.rng.uniform(-1, 1, n)
            s = bandpass(nz, 9500, 1.2) + 0.6 * bandpass(nz, 6200, 3.0)
            jingles = sum(np.sin(2 * np.pi * f * tt + self.rng.random() * 6) * np.exp(-tt / d)
                          for f, d in [(5400, 0.05), (7100, 0.04), (8900, 0.035), (11200, 0.03)]) * 0.25
            self.tl.place(out, t, (s + jingles) * env * v * 0.35)
        return highpass(out, 3000)
