# Cajon Groove Practice

A practice partner for learning the cajon. It runs in the browser and works offline.

**Live:** https://ritwikr.github.io/next-apps/cajon/

- **Practice:** a groove sequencer with beat highlighting (● bass, ✕ slap, plus hand strokes and ghost notes), a tempo slider, count-in, a one-minute timer and keyboard shortcuts.
- **Backing band:** original drumless backing tracks in four styles (Jangle Pop-Rock, Riff Hard Rock, Spacey Prog, Grunge). The style follows the groove automatically, or you can pick one yourself.
- **Switch drill:** alternate between two grooves every 4, 2 or 1 bars without stopping.
- **Compose:** build your own grooves and save them.
- **Songs:** play full songs section by section from a groove sheet.
- **Practice diary:** minutes played and best tempo per groove, saved in your browser.

All the cajon sounds are synthesised live with the Web Audio API. The backing music is original, rendered offline by the Python code in `band-renderer/`.

## Files

| Path | What it is |
| --- | --- |
| `index.html` | The whole app: one file, no build step, no dependencies. |
| `audio/*.js` | Backing loops (`loop-*.js`) and full songs (`song-*.js`), each an MP3 as base64. They load on demand through a script tag, so the app also works when opened straight from disk. |
| `audio/make_audio_js.py` | Turns an MP3 into an `audio/*.js` file. |
| `band-renderer/` | The offline band synthesiser (numpy, scipy, numba and ffmpeg). It uses Karplus-Strong guitars, an FM electric piano, a drawbar organ, pads and leads, with no samples. |

## Making new backing audio

```
cd band-renderer
python3 render.py pearljam            # a loop   -> out/pearljam.mp3 (+ meta json)
python3 song_render.py flannel        # a song   -> out/song_flannel.mp3 (+ json)
cd ..
python3 audio/make_audio_js.py band-renderer/out/pearljam.mp3 loop-pearljam
python3 audio/make_audio_js.py band-renderer/out/song_flannel.mp3 song-flannel
```

After re-rendering, update `TRACK_BASE` / `TRACK_LOOP` (for loops) or `SONG_AUDIO` (for songs) in `index.html` from the JSON the renderer writes.

## License

Code: [MIT](../LICENSE). Backing music in `audio/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), © Ritwik Roy.
