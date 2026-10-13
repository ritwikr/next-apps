"""Arrange Apple Loops into drumless backing songs / practice loops for the cajon app.

Every loop is time-stretched and pitch-shifted with Rubber Band (through ffmpeg) to the
song's tempo and key, cut to an exact whole number of beats, and then placed bar by bar.
"""
import os, sys, json, subprocess, hashlib
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'band-renderer'))   # shared mixing tools (reverb, compressor, limiter)
from dsp import SR, make_ir, highpass, lowpass, compress_st, highshelf, pan_gains
from common import limiter

WAV = os.path.join(HERE, 'work', 'wav')            # from prepare.py
PREP = os.path.join(HERE, 'work', 'prep')           # stretched / shifted loops are cached here
os.makedirs(PREP, exist_ok=True)
CAT = json.load(open(os.path.join(HERE, 'work', 'catalog.json')))


def beats_of(name):
    return int(CAT[name]['meta']['beat count'])


def prep(name, bpm, shift=0, transients='mixed'):
    """Loop `name` at `bpm`, shifted `shift` semitones. Returns (n, 2) float array that is
    exactly beats * 60 / bpm seconds long and loops seamlessly."""
    key = f'{name}|{bpm}|{shift}|{transients}'
    fn = os.path.join(PREP, hashlib.md5(key.encode()).hexdigest() + '.npy')
    if os.path.exists(fn):
        return np.load(fn)
    x, sr = sf.read(os.path.join(WAV, name + '.wav'), always_2d=True)
    assert sr == SR
    bc = beats_of(name)
    n_src = len(x)
    src_bpm = bc * 60 * SR / n_src
    n_out = int(round(bc * 60 / bpm * SR))
    if abs(src_bpm - bpm) < 1e-3 and shift == 0:
        y = x
    else:
        tiled = np.concatenate([x, x, x]).astype(np.float32)
        tmp_in = fn + '.in.wav'; tmp_out = fn + '.out.wav'
        sf.write(tmp_in, tiled, SR, subtype='FLOAT')
        af = (f'rubberband=tempo={bpm / src_bpm:.8f}:pitch={2 ** (shift / 12):.8f}'
              f':transients={transients}:pitchq=quality:channels=together:window=standard')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp_in, '-af', af,
                        '-c:a', 'pcm_f32le', tmp_out], check=True)
        y3, _ = sf.read(tmp_out, always_2d=True)
        os.remove(tmp_in); os.remove(tmp_out)
        # middle copy; find the exact offset by matching against the expected grid
        y = y3[n_out:2 * n_out]
        if len(y) < n_out:
            y = np.concatenate([y, np.zeros((n_out - len(y), 2))])
    if len(y) != n_out:   # native-tempo loop with rounding: trim / wrap
        y = np.concatenate([y, y])[:n_out] if len(y) < n_out else y[:n_out]
    y = np.asarray(y, float)
    if len(y) != len(x):
        y = np.roll(y, -_lag(x, y), axis=0)
    rms = np.sqrt(np.mean(y ** 2)) + 1e-9
    y = y * (10 ** (-20 / 20) / rms)        # every loop at -20 dBFS RMS, so gain_db is a real mix level
    np.save(fn, y)
    return y


def _lag(x, y, hop=64, maxms=60):
    """samples by which y's onsets come late relative to a time-scaled x (circular)"""
    import librosa
    oy = librosa.onset.onset_strength(y=y.mean(1), sr=SR, hop_length=hop)
    ox = librosa.onset.onset_strength(y=x.mean(1), sr=SR, hop_length=hop)
    ox = np.interp(np.linspace(0, len(ox) - 1, len(oy)), np.arange(len(ox)), ox)
    m = int(maxms / 1000 * SR / hop)
    ks = range(-m, m + 1)
    c = [np.dot(np.roll(ox, k), oy) for k in ks]
    return ks[int(np.argmax(c))] * hop


class Song:
    def __init__(self, bpm, bars, tail_s=6.0):
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.bar = 4 * self.beat
        self.bars = bars
        self.n_body = int(round(bars * self.bar * SR))
        self.n = self.n_body + int(tail_s * SR)
        self.tracks = {}      # track name -> dict(L, R, send, hp, lp)

    def s(self, bar):
        return int(round(bar * self.bar * SR))

    def track(self, tname, send=0.15, hp=None, lp=None):
        if tname not in self.tracks:
            self.tracks[tname] = dict(L=np.zeros(self.n), R=np.zeros(self.n), send=send, hp=hp, lp=lp)
        return self.tracks[tname]

    def _add(self, tname, sig, start, gain_db, pan):
        tr = self.tracks[tname]
        g = 10 ** (gain_db / 20)
        gl, gr = pan_gains(pan)
        gl, gr = gl * np.sqrt(2), gr * np.sqrt(2)
        e = min(self.n, start + len(sig))
        if e <= start:
            return
        seg = sig[:e - start]
        tr['L'][start:e] += seg[:, 0] * g * gl
        tr['R'][start:e] += seg[:, 1] * g * gr

    def place(self, tname, name, shift, bar, nbars, gain_db=0.0, pan=0.0, bpm=None,
              transients='mixed', fade_in_ms=4, fade_out_ms=40, offset_beats=0, ring=0.0, cut_beats=None):
        """Tile loop `name` from `bar` for `nbars` bars (loop restarts at `bar`).
        ring: extra beats to keep past the end, decaying (for a natural release)."""
        y = prep(name, bpm or self.bpm, shift, transients)
        if cut_beats:
            y = y[:int(round(cut_beats * 60 / (bpm or self.bpm) * SR))]
        length = self.s(bar + nbars) - self.s(bar)
        extra = int(ring * self.beat * SR)
        off = int(round(offset_beats * self.beat * SR)) % len(y)
        reps = (off + length + extra) // len(y) + 2
        sig = np.tile(y, (reps, 1))[off:off + length + extra].copy()
        fi = max(1, int(fade_in_ms * SR / 1000))
        sig[:fi] *= np.linspace(0, 1, fi)[:, None]
        if extra:
            env = np.exp(-np.linspace(0, 6, extra))
            sig[length:] *= env[:, None]
        fo = max(1, int(fade_out_ms * SR / 1000))
        sig[len(sig) - fo:] *= np.linspace(1, 0, fo)[:, None]
        self.track(tname)
        self._add(tname, sig, self.s(bar), gain_db, pan)

    def hit(self, tname, name, shift, bar, beat=0.0, take_beats=1.0, ring_s=1.5, gain_db=0.0, pan=0.0,
            src_beat=0.0, transients='mixed'):
        """A single stab: `take_beats` from `src_beat` of the loop, then a decay of `ring_s`."""
        y = prep(name, self.bpm, shift, transients)
        a = int(src_beat * self.beat * SR)
        k = int(take_beats * self.beat * SR)
        r = int(ring_s * SR)
        seg = np.tile(y, (3, 1))[a:a + k + r].copy()
        env = np.ones(len(seg))
        env[k:] = np.exp(-np.linspace(0, 7, len(seg) - k))
        seg *= env[:, None]
        seg[:64] *= np.linspace(0, 1, 64)[:, None]
        self.track(tname)
        self._add(tname, seg, self.s(bar + beat / 4), gain_db, pan)

    def automate(self, tname, points):
        """points: [(bar, gain_db)] linear-in-dB ramps for a track."""
        tr = self.tracks[tname]
        t = np.arange(self.n) / SR / self.bar
        db = np.interp(t, [p[0] for p in points], [p[1] for p in points])
        g = 10 ** (db / 20)
        tr['L'] *= g; tr['R'] *= g

    def mix(self, reverb=None, loud_db=-13.0, win_bars=8, master_hp=35):
        reverb = reverb or {}
        L = np.zeros(self.n); R = np.zeros(self.n)
        sL = np.zeros(self.n); sR = np.zeros(self.n)
        for tr in self.tracks.values():
            l, r = tr['L'], tr['R']
            if tr['hp']:
                l, r = highpass(l, tr['hp']), highpass(r, tr['hp'])
            if tr['lp']:
                l, r = lowpass(l, tr['lp']), lowpass(r, tr['lp'])
            L += l; R += r
            sL += l * tr['send']; sR += r * tr['send']
        ir = make_ir(reverb.get('t60', 1.6), reverb.get('predelay', 0.02), damp_end=reverb.get('damp_end', 2200))
        mono = highpass((sL + sR) * 0.5, 200)
        ret = reverb.get('ret', 0.45)
        L += fftconvolve(mono, ir[0])[:self.n] * ret
        R += fftconvolve(mono, ir[1])[:self.n] * ret
        L, R = highpass(L, master_hp), highpass(R, master_hp)
        L, R = compress_st(L, R, -18, 1.8, 20, 220)
        w = int(win_bars * self.bar * SR)
        p = (L ** 2 + R ** 2) / 2
        cs = np.concatenate([[0], np.cumsum(p)])
        best = max((cs[i + w] - cs[i]) / w for i in range(0, max(1, len(p) - w), SR // 2))
        g = 10 ** (loud_db / 20) / np.sqrt(best)
        L, R = L * g, R * g
        L, R = limiter(L, R, 10 ** (-1.2 / 20), 64, 2000.0)
        f = int(1.5 * SR)
        L[-f:] *= np.linspace(1, 0, f) ** 2; R[-f:] *= np.linspace(1, 0, f) ** 2
        return np.stack([L, R], 1)


def loop_mix(song, bars, reverb=None, target_rms_db=-14.5):
    """Mix a song object whose content is one seamless loop of `bars` bars, written twice
    (bars 0..2*bars). Returns exactly one loop, taken from the second pass so reverb
    and loop tails wrap naturally."""
    reverb = reverb or {}
    L = np.zeros(song.n); R = np.zeros(song.n)
    sL = np.zeros(song.n); sR = np.zeros(song.n)
    for tr in song.tracks.values():
        l, r = tr['L'], tr['R']
        if tr['hp']:
            l, r = highpass(l, tr['hp']), highpass(r, tr['hp'])
        if tr['lp']:
            l, r = lowpass(l, tr['lp']), lowpass(r, tr['lp'])
        L += l; R += r
        sL += l * tr['send']; sR += r * tr['send']
    ir = make_ir(reverb.get('t60', 1.6), reverb.get('predelay', 0.02), damp_end=reverb.get('damp_end', 2200))
    mono = highpass((sL + sR) * 0.5, 200)
    ret = reverb.get('ret', 0.45)
    L += fftconvolve(mono, ir[0])[:song.n] * ret
    R += fftconvolve(mono, ir[1])[:song.n] * ret
    L, R = highpass(L, 35), highpass(R, 35)
    L, R = compress_st(L, R, -18, 1.8, 20, 220)
    a, b = song.s(bars), song.s(2 * bars)
    L, R = L[a:b], R[a:b]
    rms = np.sqrt(np.mean((L ** 2 + R ** 2) / 2))
    g = 10 ** (target_rms_db / 20) / rms
    L, R = L * g, R * g
    pad = 2048
    WL = np.concatenate([L[-pad:], L, L[:pad]]); WR = np.concatenate([R[-pad:], R, R[:pad]])
    WL, WR = limiter(WL, WR, 10 ** (-1.5 / 20), 64, 2000.0)
    return np.stack([WL[pad:-pad], WR[pad:-pad]], 1)
