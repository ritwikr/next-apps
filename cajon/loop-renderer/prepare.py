"""Step 1: read GarageBand's Apple Loops, note each loop's beats / key / tempo, and decode
it to a clean WAV (encoder priming trimmed, so every loop is exactly its length).

  python3 prepare.py ["/Library/Audio/Apple Loops/Apple/Apple Loops for GarageBand"]

Writes work/catalog.json and work/wav/<loop name>.wav
"""
import os, sys, json, struct, subprocess
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else '/Library/Audio/Apple Loops/Apple/Apple Loops for GarageBand'
WORK = os.path.join(HERE, 'work'); os.makedirs(os.path.join(WORK, 'wav'), exist_ok=True)

cat = {}
for fn in sorted(os.listdir(SRC)):
    if not fn.endswith('.caf'):
        continue
    name = fn[:-4]
    d = open(os.path.join(SRC, fn), 'rb').read()
    i, meta, pakt = 8, {}, None
    while i + 12 <= len(d):                       # walk the CAF chunks
        t = d[i:i + 4]; sz = struct.unpack('>q', d[i + 4:i + 12])[0]
        if sz < 0:
            sz = len(d) - i - 12
        b = d[i + 12:i + 12 + sz]
        if t == b'uuid' and b'beat count' in b:   # Apple Loops metadata: key/value strings
            parts = b[20:].split(b'\x00')
            for k, v in zip(parts[0::2], parts[1::2]):
                meta[k.decode()] = v.decode('latin1')
        if t == b'pakt':                          # valid frames + encoder priming
            npk, valid, prime, rem = struct.unpack('>qqii', b[:24])
            pakt = dict(valid=valid, prime=prime)
        i += 12 + sz
    if not meta.get('beat count'):
        continue
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', os.path.join(SRC, fn), '-f', 'f32le', '-ac', '2', '-ar', '44100', '-'],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2)
    if pakt and len(x) >= pakt['valid'] + pakt['prime'] - 50:
        x = x[pakt['prime']:pakt['prime'] + pakt['valid']]
    elif pakt:
        x = x[:pakt['valid']]
    sf.write(os.path.join(WORK, 'wav', name + '.wav'), x, 44100, subtype='FLOAT')
    beats = int(meta['beat count'])
    meta['tempo'] = round(beats * 60 * 44100 / len(x), 2)
    cat[name] = dict(meta=meta)
    print(f"{name:34s} {beats:3d} beats  {meta['tempo']:6.1f} bpm  {meta.get('key signature', ''):3s} {meta.get('key type', '')}")
json.dump(cat, open(os.path.join(WORK, 'catalog.json'), 'w'), indent=1)
print(len(cat), 'loops ->', WORK)
