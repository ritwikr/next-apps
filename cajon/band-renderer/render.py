import sys, json, subprocess, time
import numpy as np
from scipy.io import wavfile
from dsp import SR
from styles import STYLES

PAD = 4096      # wrap-around padding either side so MP3 edge artefacts sit outside the loop
out = {}
keys = sys.argv[1:] or list(STYLES)
for k in keys:
    t = time.time()
    tl, (L, R) = STYLES[k]()
    n = tl.loop_n
    assert len(L) == n, (len(L), n)
    st = np.stack([L, R], 1)
    wavfile.write(f'out/{k}_loop.wav', SR, (st * 32767).astype(np.int16))
    padded = np.concatenate([st[-PAD:], st, st[:PAD]])
    wavfile.write(f'out/{k}_padded.wav', SR, (padded * 32767).astype(np.int16))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f'out/{k}_padded.wav',
                    '-c:a', 'libmp3lame', '-b:a', '128k', f'out/{k}.mp3'], check=True)
    rms = 20 * np.log10(np.sqrt(np.mean(st ** 2)))
    out[k] = dict(bpm=tl.bpm, bars=tl.bars, loop_samples=n, loop_s=n / SR, pad_s=PAD / SR,
                  rms_db=round(rms, 1), peak=round(float(np.max(np.abs(st))), 3))
    print(k, out[k], f'{time.time() - t:.1f}s', flush=True)
json.dump(out, open('out/meta_' + '_'.join(keys) + '.json', 'w'), indent=1)
