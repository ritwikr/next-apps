"""Low-level DSP for the offline backing-band renderer.
Everything is numpy / numba; no samples, all physically-inspired synthesis."""
import numpy as np
from numba import njit
from scipy.signal import lfilter, fftconvolve, resample_poly

SR = 44100
LOOP_S = None   # set by Timeline so LFOs complete whole cycles per loop


def snap(rate):
    if not LOOP_S:
        return rate
    return max(1, round(rate * LOOP_S)) / LOOP_S


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


NOTE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def nm(name):
    """'E2' -> 40, 'F#3' -> 54, 'Bb2' -> 46"""
    s = NOTE[name[0]]
    rest = name[1:]
    if rest.startswith('#'):
        s += 1; rest = rest[1:]
    elif rest.startswith('b'):
        s -= 1; rest = rest[1:]
    return s + 12 * (int(rest) + 1)


# ---------------------------------------------------------------- strings
@njit(cache=True)
def _ks(exc, n_out, f0, loss, S):
    """Extended Karplus-Strong. f0 is per-sample (allows bends/vibrato)."""
    MAXL = 8192
    buf = np.zeros(MAXL)
    out = np.zeros(n_out)
    w = 0
    dprev = 0.0
    ne = exc.shape[0]
    for n in range(n_out):
        L = SR / f0[n] - S
        if L < 2.0:
            L = 2.0
        rp = w - L
        i0 = int(np.floor(rp))
        fr = rp - i0
        a = buf[i0 % MAXL]
        b = buf[(i0 + 1) % MAXL]
        d = a * (1.0 - fr) + b * fr
        v = (1.0 - S) * d + S * dprev
        dprev = d
        y = loss * v
        if n < ne:
            y += exc[n]
        buf[w] = y
        w = (w + 1) % MAXL
        out[n] = y
    return out


def pluck(freq, dur, vel=0.8, t60=3.0, bright=0.6, pickpos=0.18, rng=None,
          f0_curve=None):
    """One plucked string note. bright 0..1 (0 = dull thumb, 1 = sharp pick)."""
    rng = rng if rng is not None else np.random.default_rng()
    n = int(dur * SR)
    if n <= 0:
        return np.zeros(0)
    P = max(2, int(SR / freq))
    exc = rng.uniform(-1, 1, P)
    # excitation brightness: harder / brighter pick keeps more highs
    fc = 1100 + 7500 * bright ** 1.5 * (0.5 + 0.5 * vel)
    fc = min(fc, freq * 24)
    exc = np.concatenate([exc, np.zeros(P)])
    exc = lowpass(lowpass(exc, fc, 0.6), fc * 1.3, 0.6)
    # pick-position comb (removes harmonics that have a node at the pick point)
    k = max(1, int(P * pickpos))
    exc2 = exc.copy()
    exc2[k:] -= exc[:-k]
    exc = exc2
    exc = exc / (np.max(np.abs(exc)) + 1e-9) * vel
    S = 0.5 - 0.3 * bright             # loop low-pass amount
    loss = 10 ** (-3.0 / (freq * t60))
    f0 = np.full(n, float(freq)) if f0_curve is None else f0_curve[:n]
    y = _ks(exc, n, f0, loss, S)
    return y


# ---------------------------------------------------------------- oscillators
@njit(cache=True)
def _polyblep(t, dt):
    if t < dt:
        t /= dt
        return t + t - t * t - 1.0
    elif t > 1.0 - dt:
        t = (t - 1.0) / dt
        return t * t + t + t + 1.0
    return 0.0


@njit(cache=True)
def saw(freq_arr):
    n = freq_arr.shape[0]
    out = np.zeros(n)
    ph = np.random.random()
    for i in range(n):
        dt = freq_arr[i] / SR
        out[i] = 2.0 * ph - 1.0 - _polyblep(ph, dt)
        ph += dt
        if ph >= 1.0:
            ph -= 1.0
    return out


@njit(cache=True)
def svf_lp(x, cutoff, q):
    """State-variable low-pass with per-sample cutoff."""
    n = x.shape[0]
    out = np.zeros(n)
    lp = 0.0; bp = 0.0
    for i in range(n):
        f = 2.0 * np.sin(np.pi * min(cutoff[i], SR * 0.2) / SR)
        hp = x[i] - lp - q * bp
        bp += f * hp
        lp += f * bp
        out[i] = lp
    return out


# ---------------------------------------------------------------- filters (RBJ)
def _biquad(b, a, x):
    return lfilter(np.array(b) / a[0], np.array(a) / a[0], x)


def lowpass(x, f, q=0.707):
    w = 2 * np.pi * f / SR; al = np.sin(w) / (2 * q); c = np.cos(w)
    return _biquad([(1 - c) / 2, 1 - c, (1 - c) / 2], [1 + al, -2 * c, 1 - al], x)


def highpass(x, f, q=0.707):
    w = 2 * np.pi * f / SR; al = np.sin(w) / (2 * q); c = np.cos(w)
    return _biquad([(1 + c) / 2, -(1 + c), (1 + c) / 2], [1 + al, -2 * c, 1 - al], x)


def bandpass(x, f, q=1.0):
    w = 2 * np.pi * f / SR; al = np.sin(w) / (2 * q); c = np.cos(w)
    return _biquad([al, 0, -al], [1 + al, -2 * c, 1 - al], x)


def peak(x, f, gain_db, q=1.0):
    A = 10 ** (gain_db / 40); w = 2 * np.pi * f / SR; al = np.sin(w) / (2 * q); c = np.cos(w)
    return _biquad([1 + al * A, -2 * c, 1 - al * A], [1 + al / A, -2 * c, 1 - al / A], x)


def highshelf(x, f, gain_db):
    A = 10 ** (gain_db / 40); w = 2 * np.pi * f / SR; c = np.cos(w); s = np.sin(w)
    al = s / 2 * np.sqrt(2)
    b = [A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c),
         A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)]
    a = [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c),
         (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al]
    return _biquad(b, a, x)


def dcblock(x):
    return lfilter([1, -1], [1, -0.995], x)


# ---------------------------------------------------------------- amps & cabs
def amp(x, gain=8.0, bias=0.12, pre_mid=6.0, cab_lp=4800, presence=3.0, bass_cut=90):
    """Guitar amp + 4x12 cab approximation (oversampled asymmetric clipping)."""
    x = highpass(x, bass_cut)
    x = peak(x, 850, pre_mid, 0.8)
    xo = resample_poly(x, 4, 1) * gain
    y = np.tanh(xo + bias) - np.tanh(bias)
    y = np.tanh(1.4 * y) / np.tanh(1.4)       # second, softer stage
    y = resample_poly(y, 1, 4)[:len(x)]
    # cab: speaker roll-off, low thump, presence bump, boxy notch
    y = highpass(y, 75)
    y = peak(y, 120, 3.0, 0.9)
    y = peak(y, 420, -3.0, 1.2)
    y = peak(y, 2300, presence, 1.1)
    y = lowpass(y, cab_lp, 0.9)
    y = lowpass(y, cab_lp * 1.25, 0.6)
    return dcblock(y)


def acoustic_body(x):
    """Resonant wooden body: short IR of damped modes + a bit of air."""
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    ir = np.zeros(n)
    for f, g, tau in [(98, 1.0, 0.03), (196, 0.7, 0.025), (290, 0.45, 0.02),
                      (420, 0.35, 0.015), (560, 0.25, 0.012), (1100, 0.12, 0.008), (2400, 0.06, 0.005)]:
        ir += g * np.sin(2 * np.pi * f * t) * np.exp(-t / tau)
    ir *= 0.06
    ir[0] += 1.0
    y = fftconvolve(x, ir)[:len(x)]
    y = highshelf(y, 3500, 2.5)
    return highpass(y, 70)


# ---------------------------------------------------------------- dynamics
@njit(cache=True)
def compress(x, thresh_db, ratio, att_ms, rel_ms, makeup_db):
    n = x.shape[0]
    out = np.zeros(n)
    aa = np.exp(-1.0 / (att_ms * 0.001 * SR))
    ar = np.exp(-1.0 / (rel_ms * 0.001 * SR))
    env = 0.0
    th = 10 ** (thresh_db / 20)
    mk = 10 ** (makeup_db / 20)
    for i in range(n):
        v = abs(x[i])
        if v > env:
            env = aa * env + (1 - aa) * v
        else:
            env = ar * env + (1 - ar) * v
        g = 1.0
        if env > th:
            g = (th * (env / th) ** (1.0 / ratio)) / env
        out[i] = x[i] * g * mk
    return out


@njit(cache=True)
def compress_st(L, R, thresh_db, ratio, att_ms, rel_ms):
    n = L.shape[0]
    oL = np.zeros(n); oR = np.zeros(n)
    aa = np.exp(-1.0 / (att_ms * 0.001 * SR))
    ar = np.exp(-1.0 / (rel_ms * 0.001 * SR))
    env = 0.0
    th = 10 ** (thresh_db / 20)
    for i in range(n):
        v = max(abs(L[i]), abs(R[i]))
        if v > env:
            env = aa * env + (1 - aa) * v
        else:
            env = ar * env + (1 - ar) * v
        g = 1.0
        if env > th:
            g = (th * (env / th) ** (1.0 / ratio)) / env
        oL[i] = L[i] * g; oR[i] = R[i] * g
    return oL, oR


# ---------------------------------------------------------------- modulation fx
@njit(cache=True)
def mod_delay(x, base_ms, depth_ms, rate_hz, phase):
    n = x.shape[0]
    out = np.zeros(n)
    MAXL = 8192
    buf = np.zeros(MAXL)
    w = 0
    for i in range(n):
        buf[w] = x[i]
        d = (base_ms + depth_ms * np.sin(2 * np.pi * rate_hz * i / SR + phase)) * 0.001 * SR
        rp = w - d
        i0 = int(np.floor(rp)); fr = rp - i0
        out[i] = buf[i0 % MAXL] * (1 - fr) + buf[(i0 + 1) % MAXL] * fr
        w = (w + 1) % MAXL
    return out


def chorus(x, depth_ms=2.0, rate=0.6, mix=0.5):
    rate = snap(rate)
    L = x * (1 - mix) + mix * mod_delay(x, 9.0, depth_ms, rate, 0.0)
    R = x * (1 - mix) + mix * mod_delay(x, 11.0, depth_ms, snap(rate * 1.13), 1.9)
    return L, R


def leslie(x, rate=0.9, depth_ms=0.6):
    """Rotary-speaker-ish: doppler + amplitude wobble, opposite phase L/R."""
    rate = snap(rate)
    t = np.arange(len(x)) / SR
    L = mod_delay(x, 3.0, depth_ms, rate, 0.0) * (1 + 0.18 * np.sin(2 * np.pi * rate * t))
    R = mod_delay(x, 3.0, depth_ms, rate, np.pi) * (1 + 0.18 * np.sin(2 * np.pi * rate * t + np.pi))
    return L, R


def stereo_delay(L, R, time_s, fb=0.35, mix=0.3, lp=3500, loop_len=None):
    """Ping-pong delay (circular when loop_len given, so loops stay seamless)."""
    n = len(L)
    d = int(time_s * SR)
    mono = (L + R) * 0.5
    oL = np.zeros(n); oR = np.zeros(n)
    tap = mono.copy()
    g = mix
    for k in range(1, 9):
        tap = lowpass(tap, lp)
        sh = d * k
        seg = np.roll(tap, sh) if loop_len else np.concatenate([np.zeros(sh), tap[:-sh]])
        if k % 2:
            oL += g * seg
        else:
            oR += g * seg
        g *= fb
    return L + oL, R + oR


# ---------------------------------------------------------------- reverb
def make_ir(t60=1.8, predelay=0.015, damp_start=9000, damp_end=1800, er_gain=0.5, seed=7):
    rng = np.random.default_rng(seed)
    n = int(t60 * 1.1 * SR)
    t = np.arange(n) / SR
    irs = []
    for ch in range(2):
        noise = rng.standard_normal(n)
        # time-varying damping: filter in blocks with decreasing cutoff
        out = np.zeros(n)
        blk = 2048
        state = 0.0
        for s in range(0, n, blk):
            frac = min(1.0, s / n * 1.6)
            fc = damp_start * (damp_end / damp_start) ** frac
            a = np.exp(-2 * np.pi * fc / SR)
            seg, zf = lfilter([1 - a], [1, -a], noise[s:s + blk], zi=[state * a])
            state = seg[-1] if len(seg) else state
            out[s:s + blk] = seg
        env = np.exp(-6.9078 * t / t60)
        # slow onset so the tail blooms rather than clicks
        env *= np.minimum(1.0, t / 0.02)
        ir = out * env
        # early reflections
        er = np.zeros(n)
        for k in range(10):
            pos = int(rng.uniform(0.004, 0.07) * SR)
            er[pos] += rng.choice([-1, 1]) * er_gain * (1 - k / 12) * 3
        ir = ir + er * 0.25
        pd = int(predelay * SR)
        ir = np.concatenate([np.zeros(pd), ir])
        irs.append(ir / np.sqrt(np.sum(ir ** 2)))
    return irs


def reverb_circular(send_L, send_R, ir):
    """Convolve and wrap the tail back to the start, so a loop stays seamless."""
    n = len(send_L)
    mono = (send_L + send_R) * 0.5
    outs = []
    for ch in range(2):
        y = fftconvolve(mono, ir[ch])
        z = y[:n].copy()
        tail = y[n:]
        while len(tail):
            m = min(n, len(tail))
            z[:m] += tail[:m]
            tail = tail[m:]
        outs.append(z)
    return outs[0], outs[1]


def pan_gains(p):
    """equal-power pan, p in -1..1"""
    a = (p + 1) * np.pi / 4
    return np.cos(a), np.sin(a)
