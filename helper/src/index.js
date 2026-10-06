/* Next Apps — sign-in helper (Cloudflare Worker)
 *
 * Why this exists: a website with no server of its own only gets a 1-hour pass
 * from Google, and renewing it means a Google pop-up. This helper does the
 * standard "web server" sign-in instead, so learners sign in once and the pass
 * is renewed quietly in the background.
 *
 * What it stores: NOTHING. The long-lasting renewal key Google gives us is
 * locked (AES-GCM encrypted) with a secret only this helper knows, and handed
 * back to the learner's own device. The helper can't read anyone's Drive on its
 * own — it only turns a locked key, sent by the device, into a fresh 1-hour pass.
 *
 * Endpoints (all POST, JSON):
 *   /exchange { code, redirect_uri }  → { access_token, expires_in, sealed, user }
 *   /refresh  { sealed }               → { access_token, expires_in }
 *   /revoke   { sealed }               → { ok: true }
 * Errors come back as { error: "<code>" } with a 4xx status.
 *
 * Settings (wrangler.toml [vars]): GOOGLE_CLIENT_ID, ALLOWED_ORIGINS,
 *   ALLOWED_REDIRECTS, ALLOWED_DOMAINS  (comma-separated lists)
 * Secrets (Cloudflare dashboard → Settings → Variables and Secrets):
 *   GOOGLE_CLIENT_SECRET, SEAL_KEY (32 random bytes, base64)
 */

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const REVOKE_URL = "https://oauth2.googleapis.com/revoke";
const DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file";

function list(s) { return String(s || "").split(",").map(x => x.trim()).filter(Boolean); }

function cors(env, origin) {
  const ok = list(env.ALLOWED_ORIGINS).includes(origin);
  return ok ? {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin"
  } : { "Vary": "Origin" };
}
function reply(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: Object.assign({ "Content-Type": "application/json", "Cache-Control": "no-store" }, headers)
  });
}

// ---- locking the renewal key -------------------------------------------------
function b64uEncode(bytes) {
  let s = ""; for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64uDecode(str) {
  const s = atob(String(str).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}
async function sealKey(env) {
  const raw = b64uDecode(String(env.SEAL_KEY || "").trim().replace(/=+$/, ""));
  if (raw.length !== 32) throw new Error("SEAL_KEY must be 32 bytes (base64)");
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}
async function seal(env, obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await sealKey(env), new TextEncoder().encode(JSON.stringify(obj))));
  const out = new Uint8Array(12 + ct.length); out.set(iv); out.set(ct, 12);
  return "v1." + b64uEncode(out);
}
async function unseal(env, sealed) {
  if (typeof sealed !== "string" || !sealed.startsWith("v1.")) return null;
  try {
    const all = b64uDecode(sealed.slice(3));
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: all.slice(0, 12) }, await sealKey(env), all.slice(12));
    return JSON.parse(new TextDecoder().decode(pt));
  } catch (e) { return null; }
}

// ---- talking to Google -----------------------------------------------------------
async function google(env, params) {
  const body = new URLSearchParams(Object.assign({ client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET }, params));
  const r = await fetch(TOKEN_URL, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
  let j = {}; try { j = await r.json(); } catch (e) {}
  return { ok: r.ok, status: r.status, j };
}
async function revokeToken(t) {
  if (!t) return;
  try { await fetch(REVOKE_URL, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ token: t }) }); } catch (e) {}
}
// The id_token comes straight from Google over HTTPS in the same reply, so reading
// its contents without re-checking the signature is safe here.
function idInfo(idToken) {
  try { return JSON.parse(new TextDecoder().decode(b64uDecode(String(idToken).split(".")[1]))); } catch (e) { return null; }
}

// ---- endpoints -----------------------------------------------------------------------
async function exchange(env, b) {
  if (!b.code || !list(env.ALLOWED_REDIRECTS).includes(b.redirect_uri)) return reply({ error: "bad_request" }, 400);
  const g = await google(env, { grant_type: "authorization_code", code: b.code, redirect_uri: b.redirect_uri });
  if (!g.ok) return reply({ error: "code_rejected" }, 400);
  const t = g.j, me = idInfo(t.id_token);
  const email = me && String(me.email || "").toLowerCase();
  const domain = email ? email.split("@")[1] : "";
  if (!me || !email || me.email_verified === false || !list(env.ALLOWED_DOMAINS).includes(domain)) {
    await revokeToken(t.refresh_token || t.access_token);
    return reply({ error: "domain", domains: list(env.ALLOWED_DOMAINS) }, 403);
  }
  if (!String(t.scope || "").split(" ").includes(DRIVE_SCOPE)) return reply({ error: "no_drive" }, 403);
  // Google only hands over the renewal key the first time someone agrees; if it's
  // missing, the app asks again with the consent screen showing.
  if (!t.refresh_token) return reply({ error: "need_consent", email }, 409);
  const sealed = await seal(env, { rt: t.refresh_token, email, at: Date.now() });
  return reply({
    access_token: t.access_token, expires_in: t.expires_in, sealed,
    user: { email, name: me.name || email, given: me.given_name || (me.name || email).split(" ")[0], picture: me.picture || "" }
  });
}
async function refresh(env, b) {
  const s = await unseal(env, b.sealed);
  if (!s || !s.rt) return reply({ error: "signin_needed" }, 401);
  const g = await google(env, { grant_type: "refresh_token", refresh_token: s.rt });
  if (!g.ok) {
    // invalid_grant = the key was withdrawn or ran out (e.g. after 7 days while the app is in Testing)
    if (g.j && g.j.error === "invalid_grant") return reply({ error: "signin_needed" }, 401);
    return reply({ error: "google_unavailable" }, 502);
  }
  return reply({ access_token: g.j.access_token, expires_in: g.j.expires_in, email: s.email });
}
async function revoke(env, b) {
  const s = await unseal(env, b.sealed);
  if (s && s.rt) await revokeToken(s.rt);
  return reply({ ok: true });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url), origin = req.headers.get("Origin") || "";
    const h = cors(env, origin);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
    if (url.pathname === "/" && req.method === "GET") return reply({ ok: true, service: "next-apps sign-in helper" }, 200, h);
    if (req.method !== "POST" || !list(env.ALLOWED_ORIGINS).includes(origin)) return reply({ error: "forbidden" }, 403, h);
    let b; try { b = await req.json(); } catch (e) { return reply({ error: "bad_request" }, 400, h); }
    let r;
    try {
      if (url.pathname === "/exchange") r = await exchange(env, b || {});
      else if (url.pathname === "/refresh") r = await refresh(env, b || {});
      else if (url.pathname === "/revoke") r = await revoke(env, b || {});
      else r = reply({ error: "not_found" }, 404);
    } catch (e) {
      r = reply({ error: "helper_error" }, 500);
    }
    for (const k in h) r.headers.set(k, h[k]);
    return r;
  }
};
