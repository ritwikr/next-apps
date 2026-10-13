"""Render full songs for the Songs tab.

  python3 song_render.py flannel        -> out/song_flannel.mp3 + out/song_flannel.json

The MP3 starts with PAD samples of silence (so the encoder's start-up never eats
the first note); the app skips PAD (+ the decoder's 1105-sample delay if present).
"""
import sys, json, subprocess, time, importlib
import numpy as np
from scipy.io import wavfile
from dsp import SR

PAD = 4096
KBPS = '128k'
for key in sys.argv[1:]:
    t = time.time()
    mod = importlib.import_module('song_' + key)
    tl, (L, R) = mod.render()
    st = np.stack([L, R], 1)
    st = np.concatenate([np.zeros((PAD, 2)), st])
    wavfile.write(f'out/song_{key}.wav', SR, (np.clip(st, -1, 1) * 32767).astype(np.int16))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f'out/song_{key}.wav',
                    '-c:a', 'libmp3lame', '-b:a', KBPS, f'out/song_{key}.mp3'], check=True)
    meta = dict(mod.META, samples=int(st.shape[0]), pad=PAD, song_s=tl.loop_n / SR,
                bar_s=tl.barlen, peak=round(float(np.abs(st).max()), 3))
    json.dump(meta, open(f'out/song_{key}.json', 'w'), indent=1)
    print(key, meta, f'{time.time() - t:.1f}s', flush=True)
