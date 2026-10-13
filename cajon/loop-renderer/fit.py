"""Step 2 (when choosing loops): which loops sound right together?

  python3 fit.py E "Alt Pop Acoustic 01" "Cheerful Mandolin 07" "Bright Tone Bass 02"

Each loop is moved to the given key (from its own key) and lined up beat by beat. The
number is how much of one loop's sound sits a semitone away from the other's (a clash).
Rough guide: under 0.08 sits well together, 0.08-0.15 is OK for a lead line,
over 0.15 is likely to sound wrong. A loop played against itself a semitone off scores 0.5-0.8.
"""
import os, sys, json, pickle
import numpy as np, soundfile as sf, librosa

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
C = json.load(open(os.path.join(WORK, 'catalog.json')))
PC = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'Ab': 8, 'A': 9, 'Bb': 10, 'B': 11}
CACHE = os.path.join(WORK, 'chroma.pkl')
cache = pickle.load(open(CACHE, 'rb')) if os.path.exists(CACHE) else {}


def shift_to(name, key):
    k = C[name]['meta'].get('key signature', '')
    if k not in PC:
        return 0
    s = (PC[key] - PC[k]) % 12
    return s - 12 if s > 6 else s


def beat_chroma(name):
    if name not in cache:
        x, sr = sf.read(os.path.join(WORK, 'wav', name + '.wav')); x = x.mean(1)
        bc = int(C[name]['meta']['beat count']); spb = len(x) / bc
        h = librosa.effects.harmonic(x, margin=3)
        ch = librosa.feature.chroma_cqt(y=h, sr=sr, hop_length=512, fmin=librosa.note_to_hz('C1'), n_octaves=7, norm=None)
        B = []
        for b in range(bc):
            s = int(b * spb / 512); e = max(s + 1, int((b + 1) * spb / 512))
            v = ch[:, s:e].mean(1); v = v / (v.max() + 1e-9); B.append(v ** 4)
        cache[name] = np.array(B).T
        pickle.dump(cache, open(CACHE, 'wb'))
    return cache[name]


def clash(a, b, sa, sb, beats=32):
    A = np.roll(beat_chroma(a), sa, 0); B = np.roll(beat_chroma(b), sb, 0)
    A = np.tile(A, (1, beats // A.shape[1] + 1))[:, :beats]; B = np.tile(B, (1, beats // B.shape[1] + 1))[:, :beats]
    A = A / (A.sum(0) + 1e-9); B = B / (B.sum(0) + 1e-9)
    return float((A * (np.roll(B, 1, 0) + np.roll(B, -1, 0))).sum(0).mean())


if __name__ == '__main__':
    key, names = sys.argv[1], sys.argv[2:]
    sh = {n: shift_to(n, key) for n in names}
    print(' ' * 31 + ' '.join(f'{n[:6]:>6s}' for n in names))
    for a in names:
        print(f'{a[:26]:26s}{sh[a]:+3d}  ' + ' '.join(f'{clash(a, b, sh[a], sh[b]):6.2f}' for b in names))
