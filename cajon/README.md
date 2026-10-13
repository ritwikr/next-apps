# Cajon Groove Practice

A practice partner for learning the cajon. It runs in the browser and works offline.

**Live:** https://ritwikr.github.io/next-apps/cajon/

- **Practice:** a groove sequencer with beat highlighting (● bass, ✕ slap, plus hand strokes and ghost notes), a tempo slider, count-in, a one-minute timer and keyboard shortcuts.
- **Backing band:** drumless backing tracks in four styles (Jangle Pop-Rock, Riff Hard Rock, Spacey Prog, Grunge), arranged from Apple Loops. The style follows the groove automatically, or you can pick one yourself.
- **Switch drill:** alternate between two grooves every 4, 2 or 1 bars without stopping.
- **Compose:** build your own grooves and save them.
- **Songs:** play four full songs section by section from a groove sheet, each with its own arranged band.
- **Practice diary:** minutes played and best tempo per groove, saved in your browser.

All the cajon sounds are synthesised live with the Web Audio API. The backing music is arranged offline from Apple Loops by the Python code in `loop-renderer/` (see its README).

## Files

| Path | What it is |
| --- | --- |
| `index.html` | The whole app: one file, no build step, no dependencies. |
| `audio/*.js` | Backing loops (`loop-*.js`) and full songs (`song-*.js`), each an MP3 as base64. They load on demand through a script tag, so the app also works when opened straight from disk. |
| `audio/make_audio_js.py` | Turns an MP3 into an `audio/*.js` file. |
| `loop-renderer/` | Arranges Apple Loops into the songs and practice loops (stretch, key change, mix). How to rebuild is in its README. |
| `band-renderer/` | The earlier band synthesiser (no samples). `loop-renderer/` still uses its reverb, compressor and limiter. |

## Making new backing audio

See `loop-renderer/README.md`. In short: `python3 prepare.py`, then `python3 songs.py`, then `audio/make_audio_js.py` for each MP3, then update `TRACK_LOOP` / `SONG_AUDIO` in `index.html`.

## License

Code: [MIT](../LICENSE). Backing music in `audio/` is made with Apple Loops and used under Apple's GarageBand licence; it is not CC BY.
