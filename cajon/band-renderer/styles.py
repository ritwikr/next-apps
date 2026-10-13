import numpy as np
from dsp import (SR, amp, acoustic_body, chorus, leslie, stereo_delay, compress, highpass,
                 lowpass, peak, highshelf)
from instruments import (Timeline, Guitar, Bass, EPiano, Organ, Pad, Lead, Tambourine, OPEN)
from common import parse, root_midi, voicing, to_st, mixdown
from dsp import nm

SHAPES = {
    'C': [-1, 3, 2, 0, 1, 0], 'Am': [-1, 0, 2, 2, 1, 0], 'F': [1, 3, 3, 2, 1, 1],
    'G': [3, 2, 0, 0, 0, 3], 'Grock': [3, 2, 0, 0, 3, 3], 'Dm': [-1, -1, 0, 2, 3, 1],
    'Dm7': [-1, -1, 0, 2, 1, 1], 'G7': [3, 2, 0, 0, 0, 1], 'Em': [0, 2, 2, 0, 0, 0],
    'Bb': [-1, 1, 3, 3, 3, 1], 'Gsus4': [3, 3, 0, 0, 1, 3], 'Em7': [0, 2, 2, 0, 3, 3],
    'Cadd9': [-1, 3, 2, 0, 3, 3], 'Dsus4': [-1, -1, 0, 2, 3, 3], 'D': [-1, -1, 0, 2, 3, 2],
    'A': [-1, 0, 2, 2, 2, 0], 'Asus4': [-1, 0, 2, 2, 3, 0], 'Gm': [3, 5, 5, 3, 3, 3],
    'A5': [-1, 0, 2, 2, -1, -1], 'G5': [3, 5, 5, -1, -1, -1], 'D5': [-1, 5, 7, 7, -1, -1],
    'C5': [-1, 3, 5, 5, -1, -1], 'E5': [0, 2, 2, -1, -1, -1],
    'Dsus2': [-1, -1, 0, 2, 3, 0], 'Fmaj7': [-1, -1, 3, 2, 1, 0],
}
CHORD_NAME = {'Grock': 'G', 'Gsus4': 'Gsus4', 'Em7': 'Em7', 'Cadd9': 'Cadd9', 'Dsus4': 'Dsus4',
              'Dsus2': 'Dsus2', 'Fmaj7': 'Fmaj7'}


def cname(s):
    n = CHORD_NAME.get(s, s)
    return {'Dsus2': 'Dsus2', 'Fmaj7': 'Fmaj7'}.get(n, n)


def low_string(shape):
    return next(i for i in range(6) if shape[i] >= 0)


def pick_string(midi, prefer_low=True):
    for s in range(6):
        f = midi - OPEN[s]
        if 0 <= f <= 5:
            return s, f
    for s in range(5, -1, -1):
        f = midi - OPEN[s]
        if 0 <= f <= 15:
            return s, f
    return 0, max(0, midi - OPEN[0])


def approach(next_root, k):
    """a passing note leading into next_root"""
    return next_root - 1 if k % 2 == 0 else next_root + 2


# ======================================================================== BEATLES
def beatles():
    tl = Timeline(bpm=96, bars=16, seed=3)
    A = ['C', 'Am', 'F', 'G', 'C', 'Am', 'Dm7', 'G7']
    B = ['F', 'G', 'Em', 'Am', 'F', 'G', 'Bb', 'Gsus4']
    prog = A + B
    rick = Guitar(tl, twelve=True, t60=2.2, bright=0.75, jitter=0.004, seed=101)
    acou = Guitar(tl, t60=1.8, bright=0.65, jitter=0.006, seed=102)
    bass = Bass(tl, 'finger', seed=103)
    ep = EPiano(tl, seed=104)
    org = Organ(tl, drawbars=(0.0, 0.9, 0.0, 0.6, 0.0, 0.25, 0.0, 0.0), seed=105)
    tam = Tambourine(tl, seed=106)
    strum = [(0, 'D', 1.0), (1, 'D', 0.8), (1.5, 'U', 0.7), (2.5, 'U', 0.65), (3, 'D', 0.8), (3.5, 'U', 0.7)]
    for b, ch in enumerate(prog):
        sh = SHAPES[ch]
        name = ch
        t0 = tl.t(b)
        sec_b = b >= 8
        last = b == 15
        # --- 12-string: jangly arpeggio in A, strums in B
        if not sec_b:
            ls = low_string(sh)
            order = [ls, 3, 4, 5, 4, 3, 5, 4]
            for k, s in enumerate(order):
                if sh[s] < 0:
                    s = 3
                rick.fret(t0 + k * tl.beat / 2, s, sh[s], vel=0.62 if k % 2 == 0 else 0.5)
        else:
            if last:
                rick.strum(t0, sh, 'D', 0.85)
                rick.strum(t0 + 2 * tl.beat, SHAPES['G'], 'D', 0.8)
                rick.strum(t0 + 3 * tl.beat, SHAPES['G'], 'D', 0.8)
                rick.strum(t0 + 3.5 * tl.beat, SHAPES['G'], 'U', 0.7)
            else:
                for (bt, d, v) in [(0, 'D', 0.85), (1.5, 'U', 0.6), (2, 'D', 0.75), (2.5, 'U', 0.6),
                                   (3, 'D', 0.7), (3.5, 'U', 0.62)]:
                    rick.strum(t0 + bt * tl.beat, sh, d, v, strings=range(1, 6) if d == 'U' else None)
        # --- acoustic strum (softer in A)
        lvl = 0.55 if not sec_b else 0.75
        for (bt, d, v) in strum:
            shp = SHAPES['G'] if (last and bt >= 2) else sh
            acou.strum(t0 + bt * tl.beat, shp, d, v * lvl, strings=range(2, 6) if d == 'U' else None)
        # --- bass: melodic, McCartney-ish
        r = root_midi(cname(name) if name != 'Gsus4' else 'G', 31, 43)
        nxt = prog[(b + 1) % 16]
        nr = root_midi(cname(nxt) if nxt != 'Gsus4' else 'G', 31, 43)
        fifth = r + 7
        if not sec_b:
            bass.note(t0, r, tl.beat * 1.35, 0.85)
            bass.note(t0 + 1.5 * tl.beat, r, tl.beat * 0.45, 0.6)
            bass.note(t0 + 2 * tl.beat, fifth, tl.beat * 0.9, 0.75)
            bass.note(t0 + 3 * tl.beat, r + 12 if b % 2 else fifth - 2 if parse(cname(name) if name != 'Gsus4' else 'G')[1][1] == 4 else fifth, tl.beat * 0.45, 0.65)
            bass.note(t0 + 3.5 * tl.beat, approach(nr, b), tl.beat * 0.45, 0.7)
        else:
            for k in range(8):
                m = [r, r, r + 12, r, fifth, fifth, r, approach(nr, b)][k]
                bass.note(t0 + k * tl.beat / 2, m, tl.beat * 0.42, 0.8 if k % 2 == 0 else 0.62)
        # --- piano-ish EP: quarter "stabs" on 2 & 4 in A, pushed chords in B
        v = voicing(cname(name) if name not in ('Gsus4',) else 'Gsus4', 62, 3)
        if not sec_b:
            ep.chord(t0 + 1 * tl.beat, v, tl.beat * 0.4, 0.55)
            ep.chord(t0 + 3 * tl.beat, v, tl.beat * 0.4, 0.55)
        else:
            ep.chord(t0, v, tl.beat * 1.4, 0.6)
            ep.chord(t0 + 1.5 * tl.beat, v, tl.beat * 0.4, 0.5)
            ep.chord(t0 + 2.5 * tl.beat, v, tl.beat * 1.3, 0.55)
            org.chord(t0, voicing(cname(name) if name != 'Gsus4' else 'Gsus4', 67, 3), tl.barlen * 0.98, 0.5)
        # --- tambourine: 2 & 4, plus shaken 8ths in B
        for bt in (1, 3):
            tam.hit(t0 + bt * tl.beat, 0.8 if sec_b else 0.6)
        if sec_b:
            for k in (1, 3, 5, 7):
                tam.hit(t0 + k * tl.beat / 2, 0.32, shake=True)
    # 12-string pickup lick into the top of the loop
    t0 = tl.t(15)
    for k, m in enumerate(['D5', 'B4', 'A4', 'G4']):
        s, f = pick_string(nm(m))
        rick.fret(t0 + (2 + k * 0.5) * tl.beat, 4 if nm(m) >= 59 else 3, nm(m) - OPEN[4 if nm(m) >= 59 else 3], vel=0.7)

    tracks = []
    x = rick.render()
    x = compress(highpass(x, 140), -22, 4, 3, 90, 7)
    x = highshelf(peak(x, 2800, 2.5, 0.8), 7000, 1.5)
    cl, cr = chorus(x, 1.2, 0.7, 0.25)
    tracks.append(dict(L=cl * 0.62 * 0.95, R=cr * 0.62 * 0.25, send=0.22))
    x = acoustic_body(acou.render())
    x = compress(highpass(x, 110), -22, 3, 5, 120, 5)
    L, R = to_st(x, 0.55, 0.7); tracks.append(dict(L=L, R=R, send=0.15))
    x = bass.render()
    L, R = to_st(x, 0, 0.95); tracks.append(dict(L=L, R=R, send=0.02))
    x = ep.render()
    x = highpass(x, 150)
    L, R = to_st(x, -0.1, 0.55); tracks.append(dict(L=L, R=R, send=0.2))
    x = org.render()
    ol, orr = leslie(x, 0.8, 0.5)
    tracks.append(dict(L=ol * 0.5, R=orr * 0.5, send=0.25))
    x = tam.render()
    L, R = to_st(x, 0.4, 0.55); tracks.append(dict(L=L, R=R, send=0.18))
    return tl, mixdown(tl, tracks, dict(t60=1.3, predelay=0.012, ret=0.45, damp_end=2500))


# ======================================================================== ZEPPELIN
RIFF_A = [(0, 'A2', 2), (3, 'A2', 1), (4, 'C3', 2), (6, 'D3', 1), (8, 'E3', 3), (11, 'D3', 1), (12, 'C3', 2), (14, 'A2', 2)]
RIFF_B = [(0, 'A2', 2), (3, 'A2', 1), (4, 'C3', 2), (6, 'D3', 2), (8, 'G2', 3), (11, 'A2', 5)]
RIFF_C = [(0, 'D3', 2), (3, 'D3', 1), (4, 'C3', 2), (6, 'A2', 2), (8, 'G2', 2), (10, 'E2', 6)]


def zeppelin():
    tl = Timeline(bpm=88, bars=16, seed=4)
    s16 = tl.beat / 4
    gl = Guitar(tl, t60=3.0, bright=0.6, jitter=0.006, seed=201)
    gr = Guitar(tl, t60=3.0, bright=0.6, jitter=0.006, seed=202)
    bass = Bass(tl, 'pick', seed=203)
    org = Organ(tl, drawbars=(0.8, 1.0, 0.7, 0.8, 0.3, 0.5, 0.0, 0.3), seed=204)
    lead = Lead(tl, t60=4.0, bright=0.6, seed=205)
    riff_bars = [RIFF_A, RIFF_B, RIFF_A, RIFF_C, RIFF_A, RIFF_B, RIFF_A, None]
    for b in range(8):
        t0 = tl.t(b)
        riff = riff_bars[b]
        if riff is None:   # turnaround hits: D5 - C5 - A5 (ring)
            for (bt, ch, dur) in [(0, 'D5', 0.7), (1, 'C5', 0.7), (2, 'A5', 2.0)]:
                for g in (gl, gr):
                    g.strum(t0 + bt * tl.beat, SHAPES[ch], 'D', 0.9, dur=dur * tl.beat)
                bass.note(t0 + bt * tl.beat, root_midi(ch[0], 28, 40), dur * tl.beat * 0.95, 0.9)
            continue
        for (st, n, ln) in riff:
            m = nm(n)
            s, f = pick_string(m)
            dur = ln * s16 * 0.92
            for g, dv in ((gl, 0.0), (gr, 0.0)):
                g.fret(t0 + st * s16, s, f, vel=0.85, dur=dur)
                if ln >= 2 and s < 5:    # fatten longer notes with the fifth
                    g.fret(t0 + st * s16 + 0.004, s + 1, f + 2 if s != 3 else f + 3, vel=0.7, dur=dur)
            bass.note(t0 + st * s16, m - 12, dur, 0.9)
    B = ['A5', 'G5', 'D5', 'D5', 'A5', 'G5', 'C5', 'E5']
    for i, ch in enumerate(B):
        b = 8 + i
        t0 = tl.t(b)
        sh = SHAPES[ch]
        # chug: open accent + palm-muted 8ths
        pat = [(0, False, 0.95), (0.5, True, 0.7), (1, True, 0.7), (1.5, False, 0.85),
               (2.5, True, 0.7), (3, False, 0.85), (3.5, True, 0.7)]
        if ch == 'C5':
            pat = [(0, False, 0.9), (1, True, 0.7), (1.5, True, 0.7)]
        for (bt, mute, v) in pat:
            for g in (gl, gr):
                g.strum(t0 + bt * tl.beat, sh, 'D', v, mute=mute, spread=0.004)
        if ch == 'C5':
            for (bt, v) in [(2, 0.9), (3, 0.85), (3.5, 0.8)]:
                for g in (gl, gr):
                    g.strum(t0 + bt * tl.beat, SHAPES['D5'], 'D', v, spread=0.004)
        r = root_midi(ch[0], 28, 40)
        for k in range(8):
            rr = r if not (ch == 'C5' and k >= 4) else root_midi('D', 28, 40)
            bass.note(t0 + k * tl.beat / 2, rr + (12 if k == 5 else 0), tl.beat * 0.44, 0.9 if k % 2 == 0 else 0.75)
        vc = {'A5': 'A', 'G5': 'G', 'D5': 'D', 'C5': 'C', 'E5': 'E'}[ch]
        org.chord(t0, voicing(vc + ('' if vc in 'GDC' else ''), 60, 3) + [nm('A2') if vc == 'A' else root_midi(vc, 36, 48)],
                  tl.barlen * 0.97, 0.55)
    # bluesy lead in the last 4 bars
    L = lambda bar, bt: tl.t(bar, bt)
    for (bar, bt, n, d, bend) in [(12, 0.5, 'A4', 1.4, 2.0), (12, 2, 'C5', 0.5, 0), (12, 2.5, 'A4', 1.2, 0),
                                  (13, 0, 'G4', 0.5, 0), (13, 0.5, 'A4', 1.3, 1.0), (13, 2, 'E4', 1.8, 0),
                                  (14, 0, 'C5', 0.5, 0), (14, 0.5, 'D5', 1.3, 2.0), (14, 2, 'C5', 0.5, 0),
                                  (14, 2.5, 'A4', 1.3, 0), (15, 0, 'E5', 2.6, 2.0)]:
        lead.note(L(bar, bt), nm(n), d * tl.beat, 0.8, bend=bend, vib=0.3)

    tracks = []
    xl = amp(gl.render() * 1.4, gain=9, bias=0.15, pre_mid=5, cab_lp=5200, presence=3)
    xr = amp(gr.render() * 1.4, gain=9, bias=0.1, pre_mid=6, cab_lp=4800, presence=2.5)
    xl, xr = peak(xl, 1500, -2.5, 0.9), peak(xr, 1600, -2.5, 0.9)
    L1, R1 = to_st(xl, -0.85, 0.42); L2, R2 = to_st(xr, 0.85, 0.42)
    tracks += [dict(L=L1, R=R1, send=0.14), dict(L=L2, R=R2, send=0.14)]
    x = bass.render()
    L, R = to_st(x, 0, 1.3); tracks.append(dict(L=L, R=R, send=0.02))
    x = org.render()
    x = np.tanh(x * 2.5) / 2.0
    ol, orr = leslie(x, 5.8, 0.35)
    tracks.append(dict(L=ol * 0.38, R=orr * 0.38, send=0.2))
    x = amp(lead.render() * 1.5, gain=14, bias=0.12, pre_mid=8, cab_lp=5000, presence=3)
    x = compress(x, -20, 3, 5, 150, 3)
    ll, lr = to_st(x, 0.15, 0.36)
    ll, lr = stereo_delay(ll, lr, tl.beat * 0.75, 0.3, 0.22)
    tracks.append(dict(L=ll, R=lr, send=0.3))
    return tl, mixdown(tl, tracks, dict(t60=1.7, predelay=0.02, ret=0.45, damp_end=2200))


# ======================================================================== FLOYD
def floyd():
    tl = Timeline(bpm=72, bars=16, seed=5)
    A = ['Dm', 'Bb', 'F', 'C', 'Dm', 'Bb', 'Gm', 'A']
    B = ['Bb', 'F', 'C', 'Dm', 'Bb', 'F', 'Gm', 'Asus4']
    prog = A + B
    arp = Guitar(tl, t60=3.2, bright=0.5, jitter=0.004, seed=301)
    bass = Bass(tl, 'finger', seed=302)
    pad = Pad(tl, cutoff=1300, voices=5, detune=0.12, attack=1.2, release=1.8, seed=303)
    org = Organ(tl, drawbars=(0.7, 1.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0), seed=304)
    lead = Lead(tl, t60=6.0, bright=0.5, seed=305)
    for b, ch in enumerate(prog):
        t0 = tl.t(b)
        sh = SHAPES[ch]
        ls = low_string(sh)
        # 8th-note arpeggio, dotted-8th delay added later
        order = [ls, 2, 3, 4, 5, 4, 3, 2] if b < 8 else [ls, 3, 4, 5, ls, 3, 4, 5]
        for k, s in enumerate(order):
            if sh[s] < 0:
                s = 3
            arp.fret(t0 + k * tl.beat / 2, s, sh[s], vel=0.6 if k in (0, 4) else 0.48)
        name = 'A' if ch == 'Asus4' else ch
        r = root_midi(name, 28, 40)
        nr = root_midi('A' if prog[(b + 1) % 16] == 'Asus4' else prog[(b + 1) % 16], 28, 40)
        if b < 8:
            bass.note(t0, r, tl.beat * 1.9, 0.85)
            bass.note(t0 + 2 * tl.beat, r + 7 if r + 7 < 43 else r - 5, tl.beat * 1.4, 0.7)
            bass.note(t0 + 3.5 * tl.beat, approach(nr, b + 1), tl.beat * 0.45, 0.6)
        else:
            for (bt, m, d) in [(0, r, 1.4), (1.5, r, 0.45), (2, r + 12, 0.9), (3, r + 7 if r + 7 < 45 else r - 5, 0.5), (3.5, approach(nr, b), 0.45)]:
                bass.note(t0 + bt * tl.beat, m, d * tl.beat, 0.8)
        pv = voicing(ch if ch != 'Asus4' else 'Asus4', 60, 3)
        pad.chord(t0, pv + [pv[0] + 12], tl.barlen * 0.95, 0.55 if b < 8 else 0.7)
        if b >= 8:
            org.chord(t0, voicing(name if ch != 'Asus4' else 'Asus4', 55, 3), tl.barlen * 0.97, 0.45)
        if ch == 'Asus4':   # resolve sus4 -> A on beat 3
            arp.fret(t0 + 2 * tl.beat, 4, 2, vel=0.55)
    # Soaring lead over section B (original phrase, Gilmour-flavoured bends)
    for (bar, bt, n, d, bend, rb) in [
            (8, 1, 'D5', 2.0, 2.0, 0), (8, 3.5, 'F5', 0.5, 0, 0),
            (9, 0, 'C5', 3.2, 0, 0),
            (10, 0.5, 'E5', 1.5, 2.0, 0), (10, 2, 'D5', 1.0, 0, 0), (10, 3, 'C5', 1.0, 0, 0),
            (11, 0, 'A4', 3.5, 0, 0),
            (12, 0, 'F5', 2.0, 2.0, 0), (12, 2.5, 'D5', 1.3, 0, 0),
            (13, 0, 'C5', 2.0, 0, 0), (13, 2.5, 'A4', 1.3, 0, 0),
            (14, 0, 'A#4', 2.0, 1.0, 0), (14, 2, 'D5', 2.0, 0, 0),
            (15, 0, 'E5', 3.0, 2.0, 2.0)]:
        lead.note(tl.t(bar, bt), nm(n.replace('A#', 'Bb')) if 'A#' in n else nm(n), d * tl.beat, 0.75, bend=bend,
                  bend_time=0.18, vib=0.35, release_bend=rb)

    tracks = []
    x = arp.render()
    x = compress(highpass(x, 120), -24, 3, 4, 120, 5)
    cl, cr = chorus(x, 1.8, 0.5, 0.45)
    cl, cr = stereo_delay(cl * 0.5, cr * 0.5, tl.beat * 0.75, 0.38, 0.35, lp=3000)
    cl, cr = cl * 0.9, cr * 0.9
    tracks.append(dict(L=cl * 1.0 + cr * 0.15, R=cr * 0.55, send=0.3))
    x = bass.render()
    L, R = to_st(x, 0, 0.72); tracks.append(dict(L=L, R=R, send=0.04))
    pl, pr = pad.render()
    pl, pr = highpass(pl, 110), highpass(pr, 110)
    tracks.append(dict(L=pl * 0.6, R=pr * 0.6, send=0.4))
    x = org.render()
    ol, orr = leslie(x, 0.7, 0.5)
    tracks.append(dict(L=ol * 0.33, R=orr * 0.33, send=0.35))
    x = amp(lead.render() * 1.3, gain=7, bias=0.1, pre_mid=5, cab_lp=4200, presence=2)
    x = compress(x, -22, 4, 8, 250, 4)
    ll, lr = to_st(x, 0.1, 0.34)
    ll, lr = stereo_delay(ll, lr, 0.45, 0.4, 0.3, lp=2800)
    tracks.append(dict(L=ll, R=lr, send=0.45))
    return tl, mixdown(tl, tracks, dict(t60=3.0, predelay=0.03, ret=0.55, damp_end=1800))


# ======================================================================== PEARL JAM
def pearljam():
    tl = Timeline(bpm=84, bars=16, seed=6)
    A = ['Em7', 'Cadd9', 'Grock', 'Dsus4', 'Em7', 'Cadd9', 'Grock', 'D']
    B = ['Cadd9', 'Grock', 'D', 'Em7', 'Cadd9', 'Grock', 'D', 'Dsus4']
    prog = A + B
    rl = Guitar(tl, t60=2.8, bright=0.6, jitter=0.006, seed=401)
    rr = Guitar(tl, t60=2.8, bright=0.6, jitter=0.006, seed=402)
    cln = Guitar(tl, t60=2.5, bright=0.6, jitter=0.004, seed=403)
    bass = Bass(tl, 'pick', seed=404)
    lead = Lead(tl, t60=5.0, bright=0.6, seed=405)
    ROOT = {'Em7': 'E', 'Cadd9': 'C', 'Grock': 'G', 'Dsus4': 'D', 'D': 'D'}
    for b, ch in enumerate(prog):
        t0 = tl.t(b)
        sh = SHAPES[ch]
        sec_b = b >= 8
        r = root_midi(ROOT[ch], 28, 40)
        nr = root_midi(ROOT[prog[(b + 1) % 16]], 28, 40)
        if not sec_b:
            # verse: ringing chord on 1, palm-muted low-string 8ths (right), clean arpeggio (left)
            rr.strum(t0, sh, 'D', 0.8)
            for k in range(2, 8):
                rr.strum(t0 + k * tl.beat / 2, sh, 'D', 0.6 if k % 2 else 0.7, mute=True,
                         strings=[low_string(sh), low_string(sh) + 1], spread=0.003)
            ls = low_string(sh)
            for k, s in enumerate([ls, 3, 4, 5, 3, 4, 5, 4]):
                cln.fret(t0 + k * tl.beat / 2, s, sh[s], vel=0.6 if k in (0, 3, 6) else 0.47)
            if ch == 'Dsus4':   # sus4 -> D on beat 3
                cln.fret(t0 + 2.5 * tl.beat, 5, 2, vel=0.55)
            for (bt, m, d, v) in [(0, r, 1.4, 0.9), (1.5, r, 0.45, 0.65), (2, r, 0.45, 0.8),
                                  (2.5, r, 0.45, 0.6), (3, r + 12, 0.45, 0.7), (3.5, approach(nr, b), 0.45, 0.7)]:
                bass.note(t0 + bt * tl.beat, m, d * tl.beat, v)
        else:
            last = b == 15
            pat = [(0, 'D', 0.95), (1, 'D', 0.8), (1.5, 'U', 0.7), (2.5, 'U', 0.7), (3, 'D', 0.85), (3.5, 'U', 0.72)]
            for (bt, d, v) in pat:
                shp = SHAPES['D'] if (last and bt >= 2) else sh
                for g in (rl, rr):
                    g.strum(t0 + bt * tl.beat, shp, d, v, strings=range(1, 6) if d == 'U' else None)
            ls = low_string(sh)
            for k, s in enumerate([ls, 4, 5, 4]):
                cln.fret(t0 + k * tl.beat, s, sh[s], vel=0.42)
            for k in range(8):
                m = r if k < 7 else approach(nr, b)
                bass.note(t0 + k * tl.beat / 2, m, tl.beat * 0.44, 0.9 if k % 2 == 0 else 0.72)
    for (bar, bt, n, d, bend) in [
            (8, 0, 'E5', 1.4, 2.0), (8, 1.5, 'D5', 0.5, 0), (8, 2, 'B4', 1.9, 0),
            (9, 0, 'D5', 1.0, 0), (9, 1, 'B4', 1.0, 0), (9, 2, 'G4', 1.9, 0),
            (10, 0, 'A4', 1.0, 0), (10, 1, 'F#4', 1.0, 0), (10, 2, 'B4', 1.9, 2.0),
            (11, 0, 'G4', 3.0, 0), (11, 3.5, 'E4', 0.5, 0),
            (12, 0, 'E5', 2.0, 2.0), (12, 2.5, 'G5', 1.4, 0),
            (13, 0, 'F#5', 1.4, 0), (13, 1.5, 'E5', 0.5, 0), (13, 2, 'D5', 1.9, 0),
            (14, 0, 'A4', 1.0, 0), (14, 1, 'D5', 1.0, 0), (14, 2, 'F#5', 1.9, 2.0),
            (15, 0, 'E5', 1.4, 0), (15, 1.5, 'D5', 2.4, 0)]:
        lead.note(tl.t(bar, bt), nm(n), d * tl.beat, 0.75, bend=bend, vib=0.3)

    tracks = []
    for g, pan in ((rl, -0.8), (rr, 0.8)):
        x = amp(g.render() * 1.2, gain=6, bias=0.12, pre_mid=4, cab_lp=5000, presence=3)
        x = peak(x, 1500, -2.5, 0.9)
        L, R = to_st(x, pan, 0.4); tracks.append(dict(L=L, R=R, send=0.13))
    x = cln.render()
    x = amp(x * 0.8, gain=1.6, bias=0.05, pre_mid=2, cab_lp=6500, presence=2)   # edge-of-breakup clean
    x = compress(x, -24, 3, 4, 120, 5)
    cl, cr = chorus(x, 1.5, 0.6, 0.35)
    tracks.append(dict(L=cl * 0.5, R=cr * 0.2, send=0.25))
    x = bass.render()
    L, R = to_st(x, 0, 1.3); tracks.append(dict(L=L, R=R, send=0.02))
    x = amp(lead.render() * 1.4, gain=10, bias=0.12, pre_mid=7, cab_lp=5200, presence=3)
    x = compress(x, -20, 3, 5, 150, 3)
    ll, lr = to_st(x, 0.2, 0.33)
    ll, lr = stereo_delay(ll, lr, tl.beat * 0.75, 0.3, 0.2)
    tracks.append(dict(L=ll, R=lr, send=0.3))
    return tl, mixdown(tl, tracks, dict(t60=1.5, predelay=0.02, ret=0.45, damp_end=2200))


STYLES = dict(beatles=beatles, zeppelin=zeppelin, floyd=floyd, pearljam=pearljam)
