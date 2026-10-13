"""The four Songs-tab songs and four practice loops, arranged from Apple Loops.

Each song follows the section plan in the app's SONGS list exactly (same bars, same tempo),
so bar N of the audio is bar N of the groove sheet. Loops are layered only where they
were checked to agree harmonically (fit.py); different sections can use
different loop families. All four songs are in E, so loops are pitch-shifted to E.

  python3 songs.py iron flannel sunday tide     # full songs
  python3 songs.py loops                        # the four 16-bar practice loops

Then turn each MP3 into an app audio file (from the cajon folder):
  python3 audio/make_audio_js.py loop-renderer/out/song_iron.mp3 song-iron
  python3 audio/make_audio_js.py loop-renderer/out/zeppelin.mp3 loop-zeppelin
and copy the numbers printed here into SONG_AUDIO / TRACK_LOOP in index.html.
"""
import sys, json, subprocess, os
import numpy as np
import soundfile as sf
from loopkit import Song, loop_mix, SR

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)
PAD = 4096


def L(track, loop, shift=0, gain=0.0, pan=0.0, **kw):
    return dict(track=track, loop=loop, shift=shift, gain=gain, pan=pan, kw=kw)


def lay(song, bar, nbars, layers):
    for l in layers:
        song.place(l['track'], l['loop'], l['shift'], bar, nbars, l['gain'], l['pan'], **l['kw'])


def stops(song, bar, nbars, layers, take=0.75, ring=1.4):
    for b in range(bar, bar + nbars):
        for l in layers:
            song.hit(l['track'], l['loop'], l['shift'], b, 0, take, ring, l['gain'], l['pan'])


def ending(song, bar, layers, take=1.0, ring=4.0):
    for l in layers:
        song.hit(l['track'], l['loop'], l['shift'], bar, 0, take, ring, l['gain'], l['pan'])


def tracks_setup(song, spec):
    for name, kw in spec.items():
        song.track(name, **kw)


# ------------------------------------------------------------------ Iron Lantern
# Riff hard rock, 88 bpm, E. Razor Rock kit, with Hot Rod for the solo and extra weight.
IRON = dict(key='iron', title='Iron Lantern', bpm=88, style='zeppelin',
            sections=[('Intro riff', 4), ('Verse 1', 8), ('Chorus', 8), ('Verse 2', 8), ('Chorus', 8),
                      ('Solo', 8), ('Breakdown', 4), ('Last chorus', 8), ('Outro', 4)])
RR = 'Razor Rock '


def iron_parts():
    gtrL = L('gtrL', RR + 'Rhythm Guitar 01', gain=-1, pan=-0.5)
    gtrR = L('gtrR', RR + 'Rhythm Guitar 02', gain=-1, pan=0.5)
    return dict(
        verse=[gtrL, L('bass', RR + 'Bass Guitar 01', gain=-2)],
        verse2=[gtrL, L('gtrR', 'Hot Rod Rhythm Guitar', gain=-5, pan=0.5), L('bass', RR + 'Bass Guitar 03', gain=-2)],
        chorus=[L('gtrL', RR + 'Rhythm Guitar 01', gain=-3, pan=-0.5), gtrR,
                L('bass', RR + 'Bass Guitar 02', gain=-2), L('lead', RR + 'Lead Guitar 03', gain=-3, pan=0.1)],
        chorus2=[L('gtrL', RR + 'Rhythm Guitar 01', gain=-3, pan=-0.5), gtrR,
                 L('bass', RR + 'Bass Guitar 02', gain=-2), L('lead', RR + 'Lead Guitar 02', gain=-3, pan=-0.1)],
        solo=[gtrL, L('gtrR', RR + 'Rhythm Guitar 02', gain=-5, pan=0.5),
              L('bass', RR + 'Bass Guitar 01', gain=-2), L('lead', 'Hot Rod Lead Guitar 01', gain=0, pan=0.05)],
        riff=[L('gtrL', RR + 'Rhythm Guitar 03', gain=-1, pan=-0.25, cut_beats=4)],
        riffbass=[L('bass', RR + 'Bass Guitar 01', gain=-2)],
        hit=[L('gtrL', RR + 'Rhythm Guitar 03', gain=-1, pan=-0.25), L('gtrR', RR + 'Rhythm Guitar 03', gain=-4, pan=0.5),
             L('bass', RR + 'Bass Guitar 04', gain=-1)],
    )


def iron():
    sp = IRON; P = iron_parts()
    s = Song(sp['bpm'], 60)
    tracks_setup(s, dict(gtrL=dict(send=0.12, hp=90), gtrR=dict(send=0.12, hp=90), lead=dict(send=0.3, hp=150),
                         bass=dict(send=0.02, lp=4000)))
    lay(s, 0, 4, P['riff']); lay(s, 2, 2, P['riffbass'])
    lay(s, 4, 8, P['verse'])
    lay(s, 12, 8, P['chorus'])
    lay(s, 20, 8, P['verse2'])
    lay(s, 28, 8, P['chorus2'])
    lay(s, 36, 8, P['solo'])
    stops(s, 44, 4, P['hit'])
    lay(s, 48, 8, P['chorus'] + [L('gtrR', 'Hot Rod Rhythm Guitar', gain=-7, pan=0.7)])
    lay(s, 56, 4, P['riff'] + P['riffbass'])
    ending(s, 60, P['hit'])
    return s, dict(t60=1.4, ret=0.4)


def iron_loop():
    P = iron_parts(); s = Song(88, 48, tail_s=0)
    tracks_setup(s, dict(gtrL=dict(send=0.12, hp=90), gtrR=dict(send=0.12, hp=90), lead=dict(send=0.3, hp=150),
                         bass=dict(send=0.02, lp=4000)))
    for p in range(3):
        lay(s, 16 * p, 8, P['verse']); lay(s, 16 * p + 8, 8, P['chorus'])
    return s, dict(t60=1.4, ret=0.4)


# ------------------------------------------------------------------ Flannel Static
# Grunge, 84 bpm, E minor. Classic Attitude Rock riffs in the verses, Nitro Power kit in the
# choruses, Kick Start in the pre-chorus, Combustion for the half-time bridge.
FLANNEL = dict(key='flannel', title='Flannel Static', bpm=84, style='pearljam',
               sections=[('Intro', 4), ('Verse 1', 8), ('Pre-chorus', 4), ('Chorus', 8), ('Verse 2', 8),
                         ('Pre-chorus', 4), ('Chorus', 8), ('Bridge', 4), ('Stops', 4), ('Last chorus', 8),
                         ('Outro', 4)])
NP = 'Nitro Power '


def flannel_parts():
    bass = L('bass', NP + 'Bass Guitar', gain=-2)
    return dict(
        intro=[L('gtrL', 'Classic Attitude Rock 18', gain=-1, pan=-0.3)],
        verse=[L('gtrL', 'Classic Attitude Rock 01', gain=-1, pan=-0.4), bass],
        verse2=[L('gtrL', 'Classic Attitude Rock 01', gain=-1, pan=-0.4), bass,
                L('lead', NP + 'Lead Guitar', gain=-6, pan=0.2)],
        pre=[L('gtrR', 'Kick Start Rhythm Guitar', gain=-1, pan=0.4), L('bass', 'Kick Start Bass Guitar', gain=-2),
             L('gtrL', 'Classic Attitude Rock 18', gain=-6, pan=-0.5)],
        chorus=[L('gtrL', NP + 'Rhythm Guitar', gain=-1, pan=-0.5), L('gtrR', NP + 'Guitar Stabs', gain=-2, pan=0.5), bass],
        chorus2=[L('gtrL', NP + 'Rhythm Guitar', gain=-1, pan=-0.5), L('gtrR', NP + 'Guitar Stabs', gain=-2, pan=0.5), bass,
                 L('gtrC', 'Gearbox Rhythm Guitar', gain=-7, pan=0.0)],
        last=[L('gtrL', NP + 'Rhythm Guitar', gain=-1, pan=-0.5), L('gtrR', NP + 'Guitar Stabs', gain=-2, pan=0.5), bass,
              L('lead', 'Kick Start Lead Guitar', gain=-3, pan=0.1)],
        bridge=[L('gtrC', 'Combustion Rhythm Guitar', gain=-3, pan=0.15), L('bass', 'Combustion Bass Guitar', gain=-3),
                L('fx', 'Combustion Guitar Noise FX', gain=-12, pan=-0.4)],
        stop=[L('gtrL', NP + 'Rhythm Guitar', gain=-1, pan=-0.5), L('gtrR', NP + 'Guitar Stabs', gain=-2, pan=0.5),
              L('bass', NP + 'Bass Guitar', gain=-2)],
        end=[L('gtrL', 'Classic Attitude Rock 18', gain=-1, pan=-0.3), L('bass', NP + 'Bass Guitar', gain=-2)],
    )


FL_TR = dict(gtrL=dict(send=0.12, hp=90), gtrR=dict(send=0.12, hp=90), gtrC=dict(send=0.14, hp=100),
             lead=dict(send=0.3, hp=150), bass=dict(send=0.02, lp=4000), fx=dict(send=0.4, hp=200))


def flannel():
    P = flannel_parts(); s = Song(84, 64)
    tracks_setup(s, FL_TR)
    lay(s, 0, 4, P['intro'])
    lay(s, 4, 8, P['verse'])
    lay(s, 12, 4, P['pre'])
    lay(s, 16, 8, P['chorus'])
    lay(s, 24, 8, P['verse2'])
    lay(s, 32, 4, P['pre'])
    lay(s, 36, 8, P['chorus2'])
    lay(s, 44, 4, P['bridge'])
    stops(s, 48, 4, P['stop'])
    lay(s, 52, 8, P['last'])
    lay(s, 60, 4, P['end'])
    ending(s, 64, P['end'])
    return s, dict(t60=1.5, ret=0.4)


def flannel_loop():
    P = flannel_parts(); s = Song(84, 48, tail_s=0)
    tracks_setup(s, FL_TR)
    for p in range(3):
        lay(s, 16 * p, 8, P['verse']); lay(s, 16 * p + 8, 8, P['chorus'])
    return s, dict(t60=1.5, ret=0.4)


# ------------------------------------------------------------------ Sunday Paper
# Bright acoustic pop-rock, 96 bpm, E. Acoustic guitars, mandolin, jangly electric,
# bass, shaker and tambourine (no kit: the cajon is the drummer).
SUNDAY = dict(key='sunday', title='Sunday Paper', bpm=96, style='beatles',
              sections=[('Intro', 4), ('Verse 1', 8), ('Chorus', 8), ('Verse 2', 8), ('Chorus', 8),
                        ('Bridge', 8), ('Last chorus', 8), ('Outro', 4)])


def sunday_parts():
    ac1 = L('acL', 'Alt Pop Acoustic 01', gain=-1, pan=-0.35)
    bass = L('bass', 'Bright Tone Bass 02', gain=-3)
    shaker = L('perc', 'Shaker 01', gain=-12, pan=-0.45, transients='crisp')
    tamb = L('perc2', 'Tambourine 07', gain=-13, pan=0.5, transients='crisp')
    mando = L('mando', 'Cheerful Mandolin 07', gain=-4, pan=0.3)
    ep = L('keys', '70s Electric Piano 11', shift=4, gain=-7, pan=0.25)
    chorus = [L('acL', 'Alt Pop Acoustic 02', gain=-1, pan=-0.35), L('elec', 'Indie Rock Riffing 02', gain=-3, pan=0.4),
              L('mando', 'Cheerful Mandolin 07', gain=-6, pan=0.15), bass, tamb]
    return dict(
        intro=[L('mando', 'Cheerful Mandolin 07', gain=-1, pan=0.2), shaker],
        verse=[ac1, bass, shaker],
        verse2=[ac1, bass, shaker, ep],
        chorus=chorus,
        chorus2=chorus + [ep],
        bridge=[L('acL', 'Alt Pop Acoustic 03', gain=-2, pan=-0.3), L('dobro', 'Front Porch Dobro 01', shift=-5, gain=-3, pan=0.35),
                L('keys', 'Lounge Vibes 06', shift=-5, gain=-7, pan=0.1), shaker],
        last=chorus + [ep, L('vibes', 'Lounge Vibes 06', shift=-5, gain=-9, pan=-0.15)],
        outro=[ac1, L('mando', 'Cheerful Mandolin 07', gain=-3, pan=0.3), shaker],
        end=[ac1, L('mando', 'Cheerful Mandolin 07', gain=-3, pan=0.3)],
    )


SU_TR = dict(acL=dict(send=0.12, hp=80), elec=dict(send=0.18, hp=120), mando=dict(send=0.18, hp=150),
             bass=dict(send=0.02, lp=3500), perc=dict(send=0.08, hp=300), perc2=dict(send=0.1, hp=300),
             keys=dict(send=0.2, hp=120), dobro=dict(send=0.25, hp=120), vibes=dict(send=0.3, hp=150))


def sunday():
    P = sunday_parts(); s = Song(96, 56)
    tracks_setup(s, SU_TR)
    lay(s, 0, 4, P['intro'])
    lay(s, 4, 8, P['verse'])
    lay(s, 12, 8, P['chorus'])
    lay(s, 20, 8, P['verse2'])
    lay(s, 28, 8, P['chorus2'])
    lay(s, 36, 8, P['bridge'])
    lay(s, 44, 8, P['last'])
    lay(s, 52, 4, P['outro'])
    ending(s, 56, P['end'], take=1.0, ring=3.5)
    return s, dict(t60=1.6, ret=0.45)


def sunday_loop():
    P = sunday_parts(); s = Song(96, 48, tail_s=0)
    tracks_setup(s, SU_TR)
    for p in range(3):
        lay(s, 16 * p, 8, P['verse']); lay(s, 16 * p + 8, 8, P['chorus'])
    return s, dict(t60=1.6, ret=0.45)


# ------------------------------------------------------------------ Slow Tide
# Spacious, slow, 72 bpm, E minor. Pads, strings, electric piano, clean guitars and a
# bluesy lead in the drift section.
TIDE = dict(key='tide', title='Slow Tide', bpm=72, style='floyd',
            sections=[('Intro', 4), ('Verse 1', 8), ('Chorus', 8), ('Verse 2', 8), ('Chorus', 8),
                      ('Drift', 8), ('Last chorus', 8), ('Outro', 4)])


def tide_parts():
    pad = L('pad', 'Abstract Atmosphere 015', shift=-5, gain=-4, transients='smooth')
    pad_lo = L('pad', 'Abstract Atmosphere 015', shift=-5, gain=-9, transients='smooth')
    strings = L('str', 'Courier Strings', shift=2, gain=-9, pan=-0.2, transients='smooth')
    ep = L('keys', 'Upbeat Electric Piano 01', shift=4, gain=-2, pan=-0.25)
    bass = L('bass', 'Rock Bass 02', shift=4, gain=-3)
    chorus = [L('ens', 'Metro All', shift=-5, gain=-3, transients='smooth'), bass,
              L('gtr', 'Downtempo Funky Guitar', shift=2, gain=-5, pan=0.4), L('keys', 'Upbeat Electric Piano 01', shift=4, gain=-5, pan=-0.3)]
    return dict(
        intro=[pad, strings],
        verse=[ep, bass, pad_lo],
        verse2=[ep, bass, L('gtr', 'Hip Hop Mystery Guitar', gain=-6, pan=0.4), strings],
        chorus=chorus,
        chorus2=chorus + [L('vibes', 'Lounge Vibes 05', shift=2, gain=-8, pan=0.2)],
        drift=[pad, L('str', 'Courier Strings', shift=2, gain=-7, pan=-0.2, transients='smooth'),
               L('lead', 'Delta Blues Solo 08', gain=-2, pan=0.1), L('bass', 'Rock Bass 02', shift=4, gain=-6)],
        last=chorus + [L('vibes', 'Lounge Vibes 05', shift=2, gain=-8, pan=0.2), strings],
        outro=[pad, L('keys', 'Upbeat Electric Piano 01', shift=4, gain=-4, pan=-0.25)],
        end=[L('keys', 'Upbeat Electric Piano 01', shift=4, gain=-4, pan=-0.25), L('bass', 'Rock Bass 02', shift=4, gain=-5)],
    )


TI_TR = dict(pad=dict(send=0.35, hp=120), str=dict(send=0.35, hp=150), keys=dict(send=0.25, hp=100),
             bass=dict(send=0.03, lp=3000), ens=dict(send=0.3, hp=120), gtr=dict(send=0.3, hp=150),
             vibes=dict(send=0.4, hp=200), lead=dict(send=0.45, hp=150))


def tide():
    P = tide_parts(); s = Song(72, 56, tail_s=7)
    tracks_setup(s, TI_TR)
    lay(s, 0, 4, P['intro'])
    lay(s, 4, 8, P['verse'])
    lay(s, 12, 8, P['chorus'])
    lay(s, 20, 8, P['verse2'])
    lay(s, 28, 8, P['chorus2'])
    lay(s, 36, 8, P['drift'])
    lay(s, 44, 8, P['last'])
    lay(s, 52, 4, P['outro'])
    ending(s, 56, P['end'] + [L('pad', 'Abstract Atmosphere 015', shift=-5, gain=-6, transients='smooth')], take=1.5, ring=5.0)
    return s, dict(t60=2.6, ret=0.55, predelay=0.03)


def tide_loop():
    P = tide_parts(); s = Song(72, 48, tail_s=0)
    tracks_setup(s, TI_TR)
    for p in range(3):
        lay(s, 16 * p, 8, P['verse']); lay(s, 16 * p + 8, 8, P['chorus'])
    return s, dict(t60=2.6, ret=0.55, predelay=0.03)


SONGS = dict(iron=(IRON, iron), flannel=(FLANNEL, flannel), sunday=(SUNDAY, sunday), tide=(TIDE, tide))
LOOPS = dict(zeppelin=(88, iron_loop), pearljam=(84, flannel_loop), beatles=(96, sunday_loop), floyd=(72, tide_loop))


def mp3(wav, mp3_path):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav, '-c:a', 'libmp3lame', '-b:a', '128k', mp3_path], check=True)


def render_song(k):
    spec, fn = SONGS[k]
    s, rv = fn()
    st = s.mix(rv)
    st = np.concatenate([np.zeros((PAD, 2)), st])
    wav = f'{OUT}/song_{k}.wav'
    sf.write(wav, np.clip(st, -1, 1), SR, subtype='PCM_16')
    mp3(wav, f'{OUT}/song_{k}.mp3')
    meta = dict(title=spec['title'], bpm=spec['bpm'], bars=sum(b for _, b in spec['sections']),
                samples=int(st.shape[0]), pad=PAD, bar_s=240 / spec['bpm'])
    json.dump(meta, open(f'{OUT}/song_{k}.json', 'w'), indent=1)
    print(k, meta, flush=True)


def render_loop(k):
    bpm, fn = LOOPS[k]
    s, rv = fn()
    st = loop_mix(s, 16, rv)
    n = st.shape[0]
    sf.write(f'{OUT}/{k}_loop.wav', st, SR, subtype='PCM_16')
    padded = np.concatenate([st[-PAD:], st, st[:PAD]])
    sf.write(f'{OUT}/{k}_padded.wav', np.clip(padded, -1, 1), SR, subtype='PCM_16')
    mp3(f'{OUT}/{k}_padded.wav', f'{OUT}/{k}.mp3')
    meta = dict(bpm=bpm, bars=16, loop=n, pad=PAD)
    print(k, meta, flush=True)
    return meta


if __name__ == '__main__':
    args = sys.argv[1:] or ['iron', 'flannel', 'sunday', 'tide', 'loops']
    for a in args:
        if a == 'loops':
            meta = {k: render_loop(k) for k in LOOPS}
            json.dump(meta, open(f'{OUT}/loops_meta.json', 'w'), indent=1)
        else:
            render_song(a)
