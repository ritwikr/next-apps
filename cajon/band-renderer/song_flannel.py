"""Flannel Static — a full grunge song for the Songs tab (Pearl Jam-style band, 84 bpm, E minor).

Form (64 bars + final chord):
  Intro 4 · Verse 1 8 · Pre-chorus 4 · Chorus 8 · Verse 2 8 · Pre-chorus 4 · Chorus 8 ·
  Bridge 4 · Stops 4 · Last chorus 8 · Outro 4 · (final Em7 on bar 65's downbeat)

What makes it a song rather than a loop:
  - each section has its own part: sparse palm-mute verses, a building pre-chorus,
    wide open choruses, a half-time bridge, real band stops, and an ending chord
  - a sung-style melody (mellow lead) in the verses, a hook melody in the choruses,
    a harmony line + organ in the last chorus
  - the band leaves space in the bars where the cajon plays its fills
"""
import numpy as np
from dsp import nm, amp, chorus, stereo_delay, compress, peak, highpass, leslie
from instruments import Guitar, Bass, Lead, Organ
from common import root_midi, voicing, to_st
from styles import SHAPES, low_string, approach
from songkit import SongTimeline, automate, mixdown_song

SHAPES = dict(SHAPES, Am7=[-1, 0, 2, 0, 1, 0], E5=[0, 2, 2, -1, -1, -1], D5x=[-1, -1, 0, 2, 3, -1])
ROOT = {'Em7': 'E', 'Cadd9': 'C', 'Grock': 'G', 'Dsus4': 'D', 'D': 'D', 'Am7': 'A', 'C': 'C', 'G': 'G'}

BPM = 84
SECTIONS = [('Intro', 4), ('Verse 1', 8), ('Pre-chorus', 4), ('Chorus', 8), ('Verse 2', 8),
            ('Pre-chorus', 4), ('Chorus', 8), ('Bridge', 4), ('Stops', 4), ('Last chorus', 8),
            ('Outro', 4)]
VERSE = ['Em7', 'Cadd9', 'Grock', 'Dsus4', 'Em7', 'Cadd9', 'Grock', 'D']
PRE = ['Am7', 'C', 'Am7', 'D']
CHORUS = ['Grock', 'D', 'Em7', 'Cadd9', 'Grock', 'D', 'Cadd9', 'Dsus4']
BRIDGE = ['Cadd9', 'Em7', 'Cadd9', 'D']

# melodies: (bar, beat, note, beats, bend-from-below-in-semitones)
VERSE_MEL = [(0, 1, 'B3', .5, 0), (0, 1.5, 'D4', .5, 0), (0, 2, 'E4', 1.5, 0), (0, 3.5, 'D4', .5, 0),
             (1, 0, 'E4', 1, 0), (1, 1, 'G4', 1, 0), (1, 2, 'E4', 1.5, 0), (1, 3.5, 'D4', .5, 0),
             (2, 0, 'D4', 1, 0), (2, 1, 'B3', 1, 0), (2, 2, 'D4', 2, 1),
             (3, 0, 'A3', 3, 0),
             (4, 1, 'B3', .5, 0), (4, 1.5, 'D4', .5, 0), (4, 2, 'E4', 1, 0), (4, 3, 'G4', 1, 0),
             (5, 0, 'A4', 1.5, 2), (5, 1.5, 'G4', .5, 0), (5, 2, 'E4', 2, 0),
             (6, 0, 'D4', 1, 0), (6, 1, 'E4', 1, 0), (6, 2, 'G4', 1, 0), (6, 3, 'F#4', 1, 0),
             (7, 0, 'D4', 3, 0)]
VERSE2_MEL = VERSE_MEL[:12] + [(3, 0, 'A3', 1.5, 0), (3, 2, 'B3', .5, 0), (3, 2.5, 'D4', 1.5, 0),
             (4, 1, 'E4', .5, 0), (4, 1.5, 'G4', .5, 0), (4, 2, 'B4', 1, 2), (4, 3, 'A4', 1, 0),
             (5, 0, 'G4', 1.5, 0), (5, 1.5, 'E4', .5, 0), (5, 2, 'D4', 2, 0),
             (6, 0, 'D4', 1, 0), (6, 1, 'E4', 1, 0), (6, 2, 'G4', 1, 0), (6, 3, 'A4', 1, 0),
             (7, 0, 'F#4', 3, 1)]
PRE_MEL = [(0, 0, 'C4', 1, 0), (0, 1, 'E4', 1, 0), (0, 2, 'G4', 2, 0),
           (1, 0, 'G4', 1, 0), (1, 1, 'E4', 1, 0), (1, 2, 'C4', 2, 0),
           (2, 0, 'A4', 1, 0), (2, 1, 'G4', 1, 0), (2, 2, 'E4', 2, 0),
           (3, 0, 'F#4', 1, 0), (3, 1, 'A4', 1, 0), (3, 2, 'B4', 2, 2)]
HOOK = [(0, 0, 'D5', 1.5, 0), (0, 1.5, 'B4', .5, 0), (0, 2, 'D5', 1, 0), (0, 3, 'E5', 1, 0),
        (1, 0, 'F#5', 2, 2), (1, 2, 'E5', 1, 0), (1, 3, 'D5', 1, 0),
        (2, 0, 'B4', 3, 0), (2, 3.5, 'D5', .5, 0),
        (3, 0, 'E5', 1, 0), (3, 1, 'D5', 1, 0), (3, 2, 'B4', 2, 0),
        (4, 0, 'D5', 1.5, 0), (4, 1.5, 'B4', .5, 0), (4, 2, 'D5', 1, 0), (4, 3, 'E5', 1, 0),
        (5, 0, 'F#5', 1.5, 2), (5, 1.5, 'A5', .5, 0), (5, 2, 'G5', 2, 0),
        (6, 0, 'E5', 1, 0), (6, 1, 'D5', 1, 0), (6, 2, 'E5', 2, 2),
        (7, 0, 'D5', 2, 0)]
# diatonic harmony a third below the hook (last chorus only)
_E_MINOR = [nm(n) for n in ['E3', 'F#3', 'G3', 'A3', 'B3', 'C4', 'D4', 'E4', 'F#4', 'G4', 'A4',
                            'B4', 'C5', 'D5', 'E5', 'F#5', 'G5', 'A5']]


def third_below(m):
    i = _E_MINOR.index(m)
    return _E_MINOR[i - 2]


BRIDGE_MEL = [(0, 0, 'G4', 3, 2), (1, 0, 'B4', 2, 0), (1, 2, 'A4', 2, 0),
              (2, 0, 'G4', 2, 0), (2, 2, 'E4', 2, 0), (3, 0, 'F#4', 4, 1)]


def render():
    bars = sum(n for _, n in SECTIONS)
    tl = SongTimeline(BPM, bars, tail_s=5.5, seed=16)
    rl = Guitar(tl, t60=2.8, bright=0.6, jitter=0.006, seed=401, max_len=6.0)
    rr = Guitar(tl, t60=2.8, bright=0.6, jitter=0.006, seed=402, max_len=6.0)
    cln = Guitar(tl, t60=2.5, bright=0.6, jitter=0.004, seed=403, max_len=6.0)
    bass = Bass(tl, 'pick', seed=404)
    voice = Lead(tl, t60=5.0, bright=0.42, seed=405)     # sung-style melody
    hook = Lead(tl, t60=5.0, bright=0.6, seed=406)       # chorus hook
    harm = Lead(tl, t60=5.0, bright=0.55, seed=407)      # last-chorus harmony
    org = Organ(tl, drawbars=(0.6, 1.0, 0.4, 0.6, 0.0, 0.3, 0.0, 0.0), seed=408)
    B = tl.beat

    def mel(inst, bar0, notes, vel=0.7, vib=0.3, xpose=0):
        for (b, bt, n, d, bend) in notes:
            inst.note(tl.t(bar0 + b, bt), nm(n) + xpose, d * B * 0.97, vel, bend=bend,
                      bend_time=0.14, vib=vib)

    def bass_line(t0, r, nr, kind, b, vel=1.0):
        if kind == 'verse':
            for (bt, m, d, v) in [(0, r, 1.4, .9), (1.5, r, .45, .65), (2, r, .45, .8), (2.5, r, .45, .6),
                                  (3, r + 12, .45, .7), (3.5, approach(nr, b), .45, .7)]:
                bass.note(t0 + bt * B, m, d * B, v * vel)
        elif kind == 'eighths':
            for k in range(8):
                m = r if k < 7 else approach(nr, b)
                bass.note(t0 + k * B / 2, m, B * .44, (.9 if k % 2 == 0 else .72) * vel)
        elif kind == 'whole':
            bass.note(t0, r, B * 3.8, .85 * vel)

    def muted_chug(g, t0, sh, vel=1.0, start=2):
        g.strum(t0, sh, 'D', .8 * vel)
        for k in range(start, 8):
            g.strum(t0 + k * B / 2, sh, 'D', (.6 if k % 2 else .7) * vel, mute=True,
                    strings=[low_string(sh), low_string(sh) + 1], spread=.003)

    def arpeggio(t0, sh, ch, vel=1.0):
        ls = low_string(sh)
        for k, s in enumerate([ls, 3, 4, 5, 3, 4, 5, 4]):
            cln.fret(t0 + k * B / 2, s, sh[s], vel=(.6 if k in (0, 3, 6) else .47) * vel)
        if ch == 'Dsus4':
            cln.fret(t0 + 2.5 * B, 5, 2, vel=.55 * vel)

    def big_strums(t0, sh, vel=1.0, ring_from=None):
        pat = [(0, 'D', .95), (1, 'D', .8), (1.5, 'U', .7), (2.5, 'U', .7), (3, 'D', .85), (3.5, 'U', .72)]
        if ring_from is not None:      # leave room for the cajon fill: hit and let it ring
            pat = [(bt, d, v) for (bt, d, v) in pat if bt < ring_from] + [(ring_from, 'D', .9)]
        for (bt, d, v) in pat:
            for g in (rl, rr):
                g.strum(t0 + bt * B, sh, d, v * vel, strings=range(1, 6) if d == 'U' else None)

    bar = 0
    for (name, n) in SECTIONS:
        for i in range(n):
            t0 = tl.t(bar + i)
            if name == 'Intro':
                ch = VERSE[i]; sh = SHAPES[ch]
                arpeggio(t0, sh, ch, 0.95)
                if i >= 2:
                    muted_chug(rr, t0, sh, 0.7)
                    bass_line(t0, root_midi(ROOT[ch], 28, 40), root_midi(ROOT[VERSE[i + 1]], 28, 40), 'verse', i, 0.8)
            elif name.startswith('Verse'):
                ch = VERSE[i]; sh = SHAPES[ch]
                nxt = VERSE[i + 1] if i < 7 else PRE[0]
                arpeggio(t0, sh, ch, 0.85)
                muted_chug(rr, t0, sh, 0.9)
                if name == 'Verse 2':
                    muted_chug(rl, t0 + 0.004, sh, 0.75, start=1)
                bass_line(t0, root_midi(ROOT[ch], 28, 40), root_midi(ROOT[nxt], 28, 40), 'verse', i)
            elif name == 'Pre-chorus':
                ch = PRE[i]; sh = SHAPES[ch]
                ramp = 0.5 + 0.1 * i
                for k in range(8):
                    for g in (rl, rr):
                        g.strum(t0 + k * B / 2, sh, 'D', (ramp + (0.08 if k % 2 == 0 else 0)) * (1 + 0.04 * k * (i == 3)),
                                strings=None if k % 2 == 0 else range(0, 4), spread=.006)
                r = root_midi(ROOT[ch], 28, 40)
                for k in range(8):
                    m = r if not (i == 3 and k >= 4) else [r, r + 2, r + 4, r + 5][k - 4]
                    bass.note(t0 + k * B / 2, m, B * .44, .78 + .05 * i)
            elif name in ('Chorus', 'Last chorus'):
                ch = CHORUS[i]; sh = SHAPES[ch]
                nxt = CHORUS[i + 1] if i < 7 else 'Em7'
                last_bar = i == 7
                if last_bar:
                    big_strums(t0, SHAPES['Dsus4'], 1.0, ring_from=2)
                    rl.choke(t0 + 3.9 * B); rr.choke(t0 + 3.9 * B)
                    bass.note(t0, root_midi('D', 28, 40), B * 1.8, .9)
                    bass.note(t0 + 2 * B, root_midi('D', 28, 40), B * 1.8, .85)
                else:
                    big_strums(t0, sh, 1.08 if name == 'Last chorus' else 1.0)
                    bass_line(t0, root_midi(ROOT[ch], 28, 40), root_midi(ROOT[nxt], 28, 40), 'eighths', i)
                ls = low_string(sh)
                for k, s in enumerate([ls, 4, 5, 4]):
                    cln.fret(t0 + k * B, s, sh[s], vel=.4)
                if name == 'Last chorus':
                    org.chord(t0, voicing(ROOT[ch] if ch not in ('Em7',) else 'Em', 60, 3), tl.barlen * .97, .5)
            elif name == 'Bridge':
                ch = BRIDGE[i]; sh = SHAPES[ch]
                ls = low_string(sh)
                for k, s in enumerate([ls, 3, 4, 5]):
                    cln.fret(t0 + k * B, s, sh[s], vel=.55)
                rl.strum(t0, sh, 'D', .55, dur=tl.barlen * .95)
                bass_line(t0, root_midi(ROOT[ch], 28, 40), 0, 'whole', i)
            elif name == 'Stops':
                if i < 3:
                    ch = ['Em7', 'Cadd9', 'Grock'][i]; sh = SHAPES[ch]
                    for g in (rl, rr):
                        g.strum(t0, sh, 'D', .95, spread=.004)
                        g.choke(t0 + 0.9 * B)
                    bass.note(t0, root_midi(ROOT[ch], 28, 40), B * .85, .95)
                else:   # build bar under the cajon fill: D5 eighths, getting louder
                    for k in range(8):
                        for g in (rl, rr):
                            g.strum(t0 + k * B / 2, SHAPES['D5'], 'D', .55 + .055 * k, spread=.003)
                        bass.note(t0 + k * B / 2, root_midi('D', 28, 40), B * .44, .7 + .03 * k)
            elif name == 'Outro':
                ch = VERSE[i]; sh = SHAPES[ch]
                arpeggio(t0, sh, ch, 0.9 - 0.08 * i)
                muted_chug(rr, t0, sh, 0.75 - 0.07 * i)
                bass_line(t0, root_midi(ROOT[ch], 28, 40), root_midi(ROOT[VERSE[(i + 1) % 8]], 28, 40), 'verse', i, 0.85 - 0.06 * i)
        # melodies
        if name == 'Verse 1':
            mel(voice, bar, VERSE_MEL, .62, .3)
        elif name == 'Verse 2':
            mel(voice, bar, VERSE2_MEL, .64, .3)
        elif name == 'Pre-chorus':
            mel(voice, bar, PRE_MEL, .66, .3)
        elif name == 'Chorus':
            mel(hook, bar, HOOK, .78, .32)
        elif name == 'Last chorus':
            mel(hook, bar, HOOK, .82, .34)
            for (b, bt, nn, d, bend) in HOOK:
                harm.note(tl.t(bar + b, bt), third_below(nm(nn)), d * B * .97, .62, bend=bend, bend_time=.14, vib=.3)
        elif name == 'Bridge':
            mel(hook, bar, BRIDGE_MEL, .62, .4)
        elif name == 'Outro':
            mel(voice, bar, VERSE_MEL[:12], .55, .3)
        bar += n

    # ---- ending: one big Em7 on the downbeat after the last bar, left to ring
    tend = tl.t(bar)
    for g in (rl, rr):
        g.strum(tend, SHAPES['Em7'], 'D', 1.0, dur=5.0)
    cln.fret(tend, 5, 3, vel=.55, dur=5.0)
    bass.note(tend, root_midi('E', 28, 40), 4.5, 1.0)
    hook.note(tend, nm('E5'), 4.2, .75, bend=2.0, bend_time=.25, vib=.45)

    # ---- mix
    # section levels for the rhythm guitars (after the amp, so it is real volume,
    # not just more or less distortion): verses sit back, the pre-chorus swells,
    # choruses open up, the last chorus is the biggest
    def at(name, k=0):
        b = 0
        for (nm_, n) in SECTIONS:
            if nm_ == name:
                if k == 0: return b
                k -= 1
            b += n
    gtr_auto = [(0, .7), (at('Verse 1'), .62), (at('Pre-chorus') - .01, .62), (at('Pre-chorus'), .5),
                (at('Chorus') - .02, .92), (at('Chorus'), 1.0), (at('Verse 2') - .02, 1.0), (at('Verse 2'), .66),
                (at('Pre-chorus', 1) - .01, .66), (at('Pre-chorus', 1), .5), (at('Chorus', 1) - .02, .92),
                (at('Chorus', 1), 1.0), (at('Bridge') - .02, 1.0), (at('Bridge'), .7), (at('Stops'), 1.0),
                (at('Last chorus'), 1.12), (at('Outro') - .02, 1.12), (at('Outro'), .7), (bars, .7), (bars + 9, .9)]
    tracks = []
    for g, pan in ((rl, -0.8), (rr, 0.8)):
        x = amp(g.render() * 1.2, gain=6, bias=0.12, pre_mid=4, cab_lp=5000, presence=3)
        x = automate(tl, peak(x, 1500, -2.5, 0.9), gtr_auto)
        L, R = to_st(x, pan, 0.4); tracks.append(dict(L=L, R=R, send=0.13))
    x = cln.render()
    x = amp(x * 0.8, gain=1.6, bias=0.05, pre_mid=2, cab_lp=6500, presence=2)
    x = compress(x, -24, 3, 4, 120, 5)
    cl, cr = chorus(x, 1.5, 0.6, 0.35)
    tracks.append(dict(L=cl * 0.5, R=cr * 0.22, send=0.25))
    x = bass.render()
    L, R = to_st(x, 0, 1.3); tracks.append(dict(L=L, R=R, send=0.02))
    # sung-style melody: warm, barely driven, a touch of chorus + slap delay
    x = amp(voice.render() * 1.1, gain=2.4, bias=0.08, pre_mid=3, cab_lp=3800, presence=1)
    x = compress(x, -22, 3, 6, 160, 4)
    vl, vr = chorus(x, 1.0, 0.5, 0.2)
    vl, vr = stereo_delay(vl * 0.42, vr * 0.42, B * 0.75, 0.25, 0.18, lp=2600)
    tracks.append(dict(L=vl, R=vr, send=0.3))
    # chorus hook: singing overdrive
    x = amp(hook.render() * 1.4, gain=10, bias=0.12, pre_mid=7, cab_lp=5200, presence=3)
    x = compress(x, -20, 3, 5, 150, 3)
    ll, lr = to_st(x, 0.15, 0.36)
    ll, lr = stereo_delay(ll, lr, B * 0.75, 0.3, 0.2)
    tracks.append(dict(L=ll, R=lr, send=0.3))
    x = amp(harm.render() * 1.3, gain=9, bias=0.1, pre_mid=6, cab_lp=4800, presence=2.5)
    x = compress(x, -20, 3, 5, 150, 3)
    hl, hr = to_st(x, -0.45, 0.26)
    tracks.append(dict(L=hl, R=hr, send=0.3))
    x = org.render()
    ol, orr = leslie(x, 0.9, 0.5)
    tracks.append(dict(L=ol * 0.32, R=orr * 0.32, send=0.3))
    L, R = mixdown_song(tl, tracks, dict(t60=1.5, predelay=0.02, ret=0.45, damp_end=2200))
    return tl, (L, R)


META = dict(title='Flannel Static', style='pearljam', bpm=BPM, sections=SECTIONS)
