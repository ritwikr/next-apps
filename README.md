# Next School — Apps

A small collection of self-contained, browser-based learning tools built with
learners at [Next School](https://nextschool.io). Each app is a single HTML file
with no build step and no dependencies — open it in any browser and it runs.

**Live:** https://ritwikr.github.io/next-apps/

## The apps

| App | What it does |
| --- | --- |
| [Room Blocks Planner](./room-blocks-planner/) | Quickly plan a room: add furniture and work out all four wall elevations. |
| [Pixel Pad](./pixel-pad/) | An ultra-simple pixel-art drawing pad. |
| [Pixel Mosaic](./pixel-mosaic/) | Design a physical mosaic-tile artwork by laying out real catalogue tiles on a pixel grid. |

## Optional sign-in

Every app works without an account (work saves in the browser). Learners can
optionally sign in with Google once to save their work to their **own Google
Drive**, shared across all the apps:

- `shared/next-account.js` — the sign-in + Drive saving code every app uses.
  After changing it, run `python3 tools/bump-shared-version.py`.
- `signin/` — the page Google sends learners back to.
- `helper/` — a tiny Cloudflare Worker that keeps learners signed in. Stores nothing.
- `privacy/` — the privacy policy.
- `test/` — a test copy of Pixel Pad with separate storage, for trying changes first.

## Running locally

Each app is standalone. Either open its `index.html` directly, or serve the
folder with any static server, e.g.:

```
python3 -m http.server
```

then visit http://localhost:8000.

## Contributing

These are teaching tools that grow with classroom feedback. Issues and pull
requests are welcome.

## License

[MIT](./LICENSE) — free to use, adapt, and share.
