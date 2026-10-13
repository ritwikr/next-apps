import numpy as np
from numba import njit
from dsp import SR, pan_gains, make_ir, compress_st, highpass, lowpass, highshelf, peak
from scipy.signal import fftconvolve

PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
QUAL = {'': [0, 4, 7], 'm': [0, 3, 7], '7': [0, 4, 7, 10], 'm7': [0, 3, 7, 10],
        'sus4': [0, 5, 7], '5': [0, 7], 'add9': [0, 4, 7, 14], 'maj7': [0, 4, 7, 11],
        'sus2': [0, 2, 7]}


def parse(ch):
    r = PC[ch[0]]
    q = ch[1:]
    if q.startswith('b'):
        r -= 1; q = q[1:]
    elif q.startswith('#'):
        r += 1; q = q[1:]
    return r % 12, QUAL[q]


def root_midi(ch, lo=28, hi=40):
    """bass root inside [lo, hi)"""
    r, _ = parse(ch)
    m = lo + ((r - lo) % 12)
    return m


def voicing(ch, center=64, n=3):
    """close voicing of chord tones near `center`"""
    r, iv = parse(ch)
    pcs = sorted(set((r + i) % 12 for i in iv))
    notes = []
    for m in range(center - 7, center + 9):
        if m % 12 in pcs:
            notes.append(m)
    # choose n notes nearest to the center, keeping the root
    notes.sort(key=lambda m: abs(m - center))
    pick = sorted(notes[:n + 1])[:n + 1]
    return sorted(pick[:n]) if len(pick) > n else sorted(pick)


def to_st(mono, pan=0.0, gain=1.0):
    gl, gr = pan_gains(pan)
    return mono * gain * gl, mono * gain * gr


@njit(cache=True)
def limiter(L, R, ceil, look, rel):
    n = L.shape[0]
    oL = np.zeros(n); oR = np.zeros(n)
    gains = np.ones(n)
    for i in range(n):
        p = max(abs(L[i]), abs(R[i]))
        if p > ceil:
            gains[i] = ceil / p
    # min over lookahead window, then smooth release
    g = np.ones(n)
    for i in range(n):
        m = 1.0
        for k in range(look):
            j = i + k
            if j < n and gains[j] < m:
                m = gains[j]
        g[i] = m
    cur = 1.0
    ar = np.exp(-1.0 / rel)
    for i in range(n):
        if g[i] < cur:
            cur = g[i]
        else:
            cur = ar * cur + (1 - ar) * g[i]
        oL[i] = L[i] * cur; oR[i] = R[i] * cur
    return oL, oR


def mixdown(tl, tracks, reverb, target_rms_db=-14.5):
    """tracks: list of dicts {L,R,send}. reverb: dict(t60, predelay, ret, damp_end)"""
    L = np.zeros(tl.n); R = np.zeros(tl.n)
    sL = np.zeros(tl.n); sR = np.zeros(tl.n)
    for tr in tracks:
        L += tr['L']; R += tr['R']
        sL += tr['L'] * tr.get('send', 0.15)
        sR += tr['R'] * tr.get('send', 0.15)
    ir = make_ir(reverb.get('t60', 1.6), reverb.get('predelay', 0.015),
                 damp_end=reverb.get('damp_end', 2000))
    mono = (sL + sR) * 0.5
    mono = highpass(mono, 180)
    rvL = fftconvolve(mono, ir[0])[:tl.n]
    rvR = fftconvolve(mono, ir[1])[:tl.n]
    ret = reverb.get('ret', 0.5)
    L += rvL * ret; R += rvR * ret
    # take the steady-state cycle
    a, b = tl.loop_n, 2 * tl.loop_n
    L, R = L[a - 44100:b + 44100], R[a - 44100:b + 44100]   # 1 s margins for filter settle
    # master: glue compression, gentle tilt, loudness, limiter
    L, R = highpass(L, 32), highpass(R, 32)
    L, R = compress_st(L, R, -20, 2.0, 15, 180)
    L = highshelf(L, 8000, 1.0); R = highshelf(R, 8000, 1.0)
    L, R = L[44100:-44100], R[44100:-44100]
    rms = np.sqrt(np.mean((L ** 2 + R ** 2) / 2))
    g = 10 ** (target_rms_db / 20) / rms
    L, R = L * g, R * g
    ceil = 10 ** (-1.5 / 20)
    # limiter on a wrapped copy so the loop seam is treated like any other point
    pad = 2048
    WL = np.concatenate([L[-pad:], L, L[:pad]]); WR = np.concatenate([R[-pad:], R, R[:pad]])
    WL, WR = limiter(WL, WR, ceil, 64, 2000.0)
    return WL[pad:-pad], WR[pad:-pad]
