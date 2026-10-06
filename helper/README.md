# Sign-in helper

A tiny [Cloudflare Worker](https://developers.cloudflare.com/workers/) that lets
learners **sign in once and stay signed in**.

A website with no server of its own only gets a 1-hour pass from Google, and
renewing it needs a Google pop-up. This helper does Google's standard
"web server" sign-in instead, so the pass is renewed quietly in the background.

**It stores nothing.** Google's long-lasting renewal key is locked (AES-GCM)
with a secret only this helper knows and handed back to the learner's own
device. The helper can't read anyone's Drive by itself — it only turns a locked
key, sent by the device, into a fresh 1-hour pass. Learners' work goes straight
from their device to their own Google Drive; it never passes through here.

| Endpoint | Sends | Gets back |
| --- | --- | --- |
| `POST /exchange` | `{ code, redirect_uri }` | `{ access_token, expires_in, sealed, user }` |
| `POST /refresh` | `{ sealed }` | `{ access_token, expires_in }` |
| `POST /revoke` | `{ sealed }` | `{ ok: true }` |

Only requests from the sites in `ALLOWED_ORIGINS` are accepted, and only
accounts in `ALLOWED_DOMAINS` can sign in.

## Setup (one time)

1. Deploy: Cloudflare dashboard → Workers & Pages → Create → **Import a
   repository** → this repo, root directory `helper`. It redeploys on every push.
2. Settings → Variables and Secrets → add two **secrets**:
   - `GOOGLE_CLIENT_SECRET` — from the Google Cloud OAuth client
   - `SEAL_KEY` — 32 random bytes, base64 (`openssl rand -base64 32`)
3. In Google Cloud → Credentials → the OAuth client, add the sign-in return
   pages as **Authorized redirect URIs** (they're listed in `ALLOWED_REDIRECTS`
   in `wrangler.toml`).

Changing `SEAL_KEY` signs everyone out (they just sign in again).
