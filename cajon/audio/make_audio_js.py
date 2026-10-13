#!/usr/bin/env python3
"""Turn an MP3 into an audio/*.js file the cajon app can load offline.

The app loads audio with a <script> tag (works from file:// with no internet,
unlike fetch), so each MP3 is wrapped as base64 in a tiny JS file.

Usage (from the Cajon folder):
  python3 audio/make_audio_js.py tracks/beatles.mp3 loop-beatles
  python3 audio/make_audio_js.py tracks/songs/song_flannel.mp3 song-flannel

Names: "loop-<style key>" for practice loops (TRACK_KEYS in the app),
       "song-<song key>" for full songs (SONG_AUDIO in the app).
"""
import base64, os, sys

if len(sys.argv) != 3:
    sys.exit(__doc__)
src, name = sys.argv[1], sys.argv[2]
b64 = base64.b64encode(open(src, 'rb').read()).decode('ascii')
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + '.js')
with open(out, 'w') as f:
    f.write(f'// Cajon practice app audio: {name} (MP3, base64). Made by audio/make_audio_js.py\n')
    f.write(f'(window.CAJON_AUDIO = window.CAJON_AUDIO || {{}})["{name}"] = "{b64}";\n')
print(f'wrote {out} ({len(b64):,} chars)')
