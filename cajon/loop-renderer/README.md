# Loop renderer

Makes the cajon app's backing music from **Apple Loops** (the loops that come with GarageBand). No drum loops are used: the cajon is the drummer. Shakers and tambourines are the only percussion.

It replaced `band-renderer/` (synthesised instruments) in October 2026. `band-renderer/` stays because this folder borrows its reverb, compressor and limiter.

## What it makes

| File | What | Tempo | Built from |
| --- | --- | --- | --- |
| `song_iron` | Iron Lantern, riff rock | 88 | Razor Rock kit, Hot Rod solo |
| `song_flannel` | Flannel Static, grunge | 84 | Classic Attitude Rock, Nitro Power, Kick Start, Combustion |
| `song_sunday` | Sunday Paper, acoustic pop-rock | 96 | Alt Pop Acoustic, Cheerful Mandolin, Indie Rock Riffing, Bright Tone Bass, Front Porch Dobro, shaker, tambourine |
| `song_tide` | Slow Tide, slow and spacious | 72 | Abstract Atmosphere, Courier Strings, Metro, Upbeat Electric Piano, Rock Bass, Downtempo Funky Guitar, Delta Blues Solo |
| `beatles` `zeppelin` `floyd` `pearljam` | 16-bar practice loops (verse + chorus of the songs above) | 96 / 88 / 72 / 84 | same |

Each song follows its section plan in the app's `SONGS` list bar for bar, so the music changes exactly where the groove sheet does. All four are in E.

## How to rebuild

Needs Python 3 with numpy, scipy, numba, soundfile, librosa, and ffmpeg built with Rubber Band (`ffmpeg -filters | grep rubberband`).

```
cd loop-renderer
python3 prepare.py                 # reads GarageBand's loops -> work/
python3 songs.py                   # all songs + loops -> out/*.mp3 (+ numbers for index.html)
cd ..
python3 audio/make_audio_js.py loop-renderer/out/song_iron.mp3 song-iron
python3 audio/make_audio_js.py loop-renderer/out/zeppelin.mp3 loop-zeppelin   # etc.
```

Then copy the printed `samples` into `SONG_AUDIO` and the loop lengths into `TRACK_LOOP` in `index.html`.

## How it works

1. **prepare.py** reads each loop's own notes (beats, key, tempo) and decodes it to an exact-length WAV.
2. **loopkit.py** stretches a loop to the song tempo and moves it to the song key with Rubber Band, lines its first beat up with the grid, and evens out the volume of all loops so mix levels mean something.
3. **songs.py** is the arrangement: which loops play in which section, how loud, left or right. Stop hits and the last chord are cut from the first beat of a loop and left to ring.
4. **fit.py** checks whether loops will sound right together before you layer them. Loops are only stacked where the check says they fit; different sections can use different loop families.

## Changing a song

Edit the section lists in `songs.py` (for example swap `Alt Pop Acoustic 01` for `02`), run `fit.py` on the new set of loops, then re-render. `prepare.py` prints every loop with its tempo and key.

## Licence

These songs are built from Apple Loops, so they are not CC BY like the old synthesised tracks. Apple's GarageBand licence lets you use the loops royalty-free in your own music and share that music. It does not let you hand out the loops on their own, or repackage them as samples, sound effects or "music beds". Finished songs played inside an app look like normal use, but check the licence wording before publishing the public repo. The raw loops are never committed (`work/` is ignored).
