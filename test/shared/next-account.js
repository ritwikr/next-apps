/* Next Apps — optional Google sign-in + saving to the learner's own Google Drive.
 *
 * Shared by every app. Without signing in, an app works exactly as before.
 * Spec: "Next Apps — Sign-in & Saving Spec" (Claude Docs).
 *
 * Firm rules this file keeps:
 *  - Work is always saved on the device first; Drive is an extra copy.
 *  - Guest work (today's saved data) is never changed or deleted by signing in/out.
 *  - Work that hasn't reached Drive is never wiped; it's set aside under the learner's name.
 *  - When the device and Drive disagree, keep both.
 */
(function(){
"use strict";

// ---- settings -------------------------------------------------------------
var CLIENT_ID = "76047242910-4p1uc2c3ismdv2jo3ahom8j4auipacvr.apps.googleusercontent.com";   // ← Google Cloud OAuth client ID (Web). Empty = sign-in shows "not set up yet".
var CFG = window.NEXT_ACCOUNT_CONFIG || {};
if (CFG.clientId) CLIENT_ID = CFG.clientId;
var PREFIX   = CFG.storagePrefix || "";                    // "test:" on the test copy
var DOMAINS  = CFG.domains || ["nextschool.org", "sunset.in"];
var IDLE_MS  = CFG.idleHours ? CFG.idleHours * 3600 * 1000 : 0;   // 0 = never sign out by itself (each learner has their own iPad)
var API      = CFG.apiBase || "https://www.googleapis.com";
var HELPER   = (CFG.helperUrl || "").replace(/\/+$/, "");    // the sign-in helper (Cloudflare Worker). Empty = sign-in shows "not set up yet".
var AUTH_URL = CFG.authUrl || "https://accounts.google.com/o/oauth2/v2/auth";
var REDIRECT = CFG.redirectUri || new URL("../signin/", location.href).href;   // Google sends learners back here
var DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file";
var SCOPES   = "openid email profile " + DRIVE_SCOPE;
var SYNC_DELAY = CFG.syncDelayMs || 4000;

// ---- storage helpers --------------------------------------------------------
function store(){ try { return window.localStorage; } catch(e) { return null; } }
function getRaw(k){ var s = store(); if (!s) return null; try { return s.getItem(PREFIX + k); } catch(e) { return null; } }
function setRaw(k, v){ var s = store(); if (!s) return false; try { s.setItem(PREFIX + k, v); return true; } catch(e) { return false; } }
function del(k){ var s = store(); if (s) try { s.removeItem(PREFIX + k); } catch(e) {} }
function getJ(k){ var r = getRaw(k); if (r == null) return null; try { return JSON.parse(r); } catch(e) { return null; } }
function setJ(k, v){ return setRaw(k, JSON.stringify(v)); }

var app = null;          // the registered app (one per page)
var user = getJ("nextacct.user");      // {email, name, given, picture}
var token = getJ("nextacct.token");    // {t, exp}  — a 1-hour pass, renewed quietly by the helper
var sealed = getJ("nextacct.sealed");  // the locked renewal key (only the helper can open it)
var needSignIn = false;                // the helper said the renewal key no longer works
var status = "guest";
var syncTimer = null, syncing = null, ui = {};

function spaceKey(k){ return user ? k + "@@" + user.email : k; }
function recKey(){ return "nextacct.sync." + app.app + "@@" + user.email; }
function tokenOk(){ return !!(token && token.t && token.exp > Date.now()); }
function isIPad(){ return /iPad/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1); }
function here(){ return isIPad() ? "this iPad" : "this device"; }

// ---- what apps call instead of localStorage for their artwork bundle ------
function getItem(k){
  // In a signed-in space, older "legacy" keys don't exist — only guests migrate old data.
  if (user && app && app.legacyKeys && app.legacyKeys.indexOf(k) >= 0) return null;
  return getRaw(spaceKey(k));
}
function setItem(k, v){
  setRaw(spaceKey(k), v);
  // Only real changes start a save to Drive (the app also saves when you just switch tabs etc.)
  if (user && app && k === app.key && !quietSave && unsyncedCount() > 0) scheduleSync();
}
var quietSave = false;
function flushQuietly(){ quietSave = true; try { app.flush(); } catch(e) {} quietSave = false; }

// ---- bundle + project helpers --------------------------------------------------
function readBundle(){ var r = getRaw(spaceKey(app.key)); if (r == null) return null; try { return JSON.parse(r); } catch(e) { return undefined; } }
function readGuestBundle(){ var r = getRaw(app.key); if (r == null) return null; try { return JSON.parse(r); } catch(e) { return null; } }
function writeBundle(b){ setRaw(spaceKey(app.key), JSON.stringify(b)); }
function clean(p){ var o = {}; for (var k in p) if (k !== "open" && k !== "undo" && k !== "redo") o[k] = p[k]; return o; }
function sig(p){ return JSON.stringify(clean(p)); }
function blank(p){ try { return app.isBlank ? !!app.isBlank(p) : false; } catch(e) { return false; } }
function newId(){ return "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
function readRec(){ var r = getJ(recKey()); if (!r || typeof r !== "object") r = {}; r.files = r.files || {}; return r; }
function writeRec(r){ setJ(recKey(), r); }

// How many artworks (or deletions) haven't reached Drive yet.
function unsyncedCount(){
  if (!user) return 0;
  var b = readBundle(); if (!b || !b.projects) return 0;
  var rec = readRec(), n = 0, ids = {};
  b.projects.forEach(function(p){
    ids[p.id] = 1;
    var r = rec.files[p.id];
    if (r ? r.sig !== sig(p) : !blank(p)) n++;
  });
  Object.keys(rec.files).forEach(function(pid){ if (!ids[pid]) n++; });   // a deletion still to be sent
  return n;
}

// ---- Google sign-in (full-page visit to Google, then quiet renewals via the helper) ----
// No pop-ups: tapping Sign in takes this page to Google and Google brings the learner
// straight back. After that the helper renews the 1-hour pass in the background.
function domainOk(email){
  var d = String(email || "").split("@")[1] || "";
  return DOMAINS.indexOf(d.toLowerCase()) >= 0;
}
function helper(path, body){
  return fetch(HELPER + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then(function(r){ return r.json().catch(function(){ return {}; }).then(function(j){ j._status = r.status; return j; }); });
}
// mode: "signin" (choose an account) or "again" (same learner, their renewal key stopped working)
function goToGoogle(mode, email){
  try { app.flush(); } catch(e) {}
  var a = new Uint8Array(16); crypto.getRandomValues(a);
  var state = Array.prototype.map.call(a, function(b){ return ("0" + b.toString(16)).slice(-2); }).join("");
  try { store().setItem("nextacct.return." + state, JSON.stringify({ url: location.href.split("#")[0], at: Date.now() })); } catch(e) {}
  setJ("nextacct.pending", { state: state, mode: mode, email: email || "", at: Date.now() });
  var p = { client_id: CLIENT_ID, redirect_uri: REDIRECT, response_type: "code", scope: SCOPES,
            access_type: "offline", include_granted_scopes: "true", state: state,
            // "consent" makes Google hand over a renewal key every time; "select_account" lets them pick
            prompt: mode === "again" ? "consent" : "select_account consent" };
  if (email) p.login_hint = email;
  location.assign(AUTH_URL + "?" + new URLSearchParams(p).toString());
}
// A fresh 1-hour pass, renewed quietly when needed.
var renewing = null;
function ensureToken(){
  if (tokenOk()) return Promise.resolve(token);
  if (!user) return Promise.reject({ auth: true });
  if (!sealed) { needSignIn = true; return Promise.reject({ auth: true }); }
  if (renewing) return renewing;
  renewing = helper("/refresh", { sealed: sealed }).then(function(j){
    if (j.error === "signin_needed") { needSignIn = true; throw { auth: true }; }
    if (!j.access_token) throw { http: j._status || 0 };
    if (j.email && user && j.email !== user.email) { needSignIn = true; throw { auth: true }; }
    needSignIn = false;
    token = { t: j.access_token, exp: Date.now() + ((+j.expires_in || 3600) - 120) * 1000 };
    setJ("nextacct.token", token);
    return token;
  }, function(){ throw { net: true }; });
  var r = renewing;
  renewing.then(function(){ renewing = null; }, function(){ renewing = null; });
  return r;
}

// ---- Drive API ------------------------------------------------------------------
function api(method, path, body, headers, retried){
  return ensureToken().then(function(){
    var h = { Authorization: "Bearer " + token.t };
    for (var k in headers || {}) h[k] = headers[k];
    var b = body;
    if (b && typeof b === "object" && !(headers && headers["Content-Type"])) { h["Content-Type"] = "application/json"; b = JSON.stringify(b); }
    return fetch(API + path, { method: method, headers: h, body: b });
  }).then(function(r){
    if (r.status === 401) {
      token = null; del("nextacct.token");
      if (!retried) return api(method, path, body, headers, true);   // pass ran out early — renew once and retry
      throw { auth: true };
    }
    if (!r.ok) throw { http: r.status };
    return r;
  });
}
function q(s){ return encodeURIComponent(s); }
function findOne(query){
  return api("GET", "/drive/v3/files?q=" + q(query) + "&fields=" + q("files(id)") + "&pageSize=1&spaces=drive")
    .then(function(r){ return r.json(); }).then(function(j){ return j.files && j.files[0] ? j.files[0].id : null; });
}
function makeFolder(name, props, parent){
  var m = { name: name, mimeType: "application/vnd.google-apps.folder", appProperties: props };
  if (parent) m.parents = [parent];
  return api("POST", "/drive/v3/files?fields=id", m).then(function(r){ return r.json(); }).then(function(j){ return j.id; });
}
function ensureFolder(rec){
  var check = rec.folderId
    ? api("GET", "/drive/v3/files/" + rec.folderId + "?fields=" + q("id,trashed")).then(function(r){ return r.json(); })
        .then(function(j){ return j.trashed ? null : j.id; }, function(e){ if (e && e.auth) throw e; return null; })
    : Promise.resolve(null);
  return check.then(function(id){
    if (id) return id;
    var F = "mimeType='application/vnd.google-apps.folder' and trashed=false and ";
    return findOne(F + "appProperties has { key='nextApps' and value='root' }").then(function(root){
      return root || makeFolder("Next Apps", { nextApps: "root" });
    }).then(function(root){
      return findOne(F + "appProperties has { key='nextApps' and value='folder' } and appProperties has { key='nextApp' and value='" + app.app + "' }")
        .then(function(f){ return f || makeFolder(app.label, { nextApps: "folder", nextApp: app.app }, root); });
    }).then(function(f){ rec.folderId = f; return f; });
  });
}
function listFiles(){
  var out = [], query = "appProperties has { key='nextApps' and value='art' } and appProperties has { key='nextApp' and value='" + app.app + "' } and trashed=false";
  function page(tok){
    return api("GET", "/drive/v3/files?q=" + q(query) + "&spaces=drive&pageSize=1000&fields=" + q("nextPageToken,files(id,name,createdTime,modifiedTime,appProperties)") + (tok ? "&pageToken=" + q(tok) : ""))
      .then(function(r){ return r.json(); }).then(function(j){
        out = out.concat(j.files || []);
        return j.nextPageToken ? page(j.nextPageToken) : out;
      });
  }
  return page(null);
}
function download(id){ return api("GET", "/drive/v3/files/" + id + "?alt=media").then(function(r){ return r.json(); }); }
function fileName(p){ return String(p.name || "Untitled").replace(/[\/\\]/g, "-") + ".json"; }
function upload(p, driveId, folderId){
  var meta = { name: fileName(p), mimeType: "application/json" };
  if (!driveId) { meta.parents = [folderId]; meta.appProperties = { nextApps: "art", nextApp: app.app, pid: p.id }; }
  var content = JSON.stringify({ app: app.app, format: 1, savedAt: new Date().toISOString(), project: clean(p) });
  var B = "nextapps" + Math.random().toString(36).slice(2);
  var body = "--" + B + "\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + JSON.stringify(meta) +
             "\r\n--" + B + "\r\nContent-Type: application/json\r\n\r\n" + content + "\r\n--" + B + "--";
  var path = driveId ? "/upload/drive/v3/files/" + driveId + "?uploadType=multipart&fields=" + q("id,createdTime,modifiedTime")
                     : "/upload/drive/v3/files?uploadType=multipart&fields=" + q("id,createdTime,modifiedTime");
  return api(driveId ? "PATCH" : "POST", path, body, { "Content-Type": "multipart/related; boundary=" + B })
    .then(function(r){ return r.json(); });
}
function trash(id){ return api("PATCH", "/drive/v3/files/" + id + "?fields=id", { trashed: true }); }

// ---- syncing ----------------------------------------------------------------------
function scheduleSync(){
  if (!user) return;
  if (needSignIn) { setStatus("paused"); return; }
  setStatus("pending");
  clearTimeout(syncTimer);
  syncTimer = setTimeout(function(){ sync().catch(function(){}); }, SYNC_DELAY);
}

// Full two-way sync of the signed-in space for this app.
function sync(){
  if (!user) return Promise.resolve();
  if (syncing) return syncing.then(function(){ return sync(); });
  if (navigator.onLine === false) { setStatus("offline"); return Promise.reject({ offline: true }); }
  clearTimeout(syncTimer);
  flushQuietly();
  if (unsyncedCount() > 0) setStatus("syncing");   // a check with nothing to send stays quiet
  var who = user.email;
  var start = readBundle();
  if (start === undefined) { setStatus("error"); return Promise.reject({ corrupt: true }); }   // never act on unreadable data
  start = start || { projects: [] };
  var local = (start.projects || []).slice(), localById = {};
  local.forEach(function(p){ localById[p.id] = p; });
  var rec = readRec();
  var spaceWasBlank = local.every(blank);
  var adds = [], replaces = {}, startSig = {};
  local.forEach(function(p){ startSig[p.id] = sig(p); });

  syncing = ensureToken().then(function(){ return ensureFolder(rec); }).then(function(folder){
    return listFiles().then(function(files){
      var onDrive = {};
      var chain = Promise.resolve();
      files.forEach(function(f){
        var pid = f.appProperties && f.appProperties.pid; if (!pid) return;
        onDrive[pid] = f;
        chain = chain.then(function(){
          var r = rec.files[pid], p = localById[pid];
          if (!p) {
            if (r && r.driveId === f.id) {            // deleted on this device → move to Drive's bin (recoverable)
              if (!local.length) return;                // safety: never bin things when the device has nothing
              return trash(f.id).then(function(){ delete rec.files[pid]; });
            }
            return download(f.id).then(function(d){    // new from Drive
              var np = d.project || {}; np.id = pid; np.open = spaceWasBlank;
              adds.push(np); rec.files[pid] = { driveId: f.id, sig: sig(np), mod: f.modifiedTime, created: f.createdTime };
            });
          }
          var driveChanged = !r || r.driveId !== f.id || r.mod !== f.modifiedTime;
          var localChanged = !r || sig(p) !== r.sig;
          if (!driveChanged && !localChanged) return;
          if (driveChanged && !localChanged) {
            return download(f.id).then(function(d){
              var np = d.project || {}; np.id = pid; np.open = p.open;
              replaces[pid] = np; rec.files[pid] = { driveId: f.id, sig: sig(np), mod: f.modifiedTime, created: f.createdTime };
            });
          }
          if (!driveChanged && localChanged) {
            return upload(p, f.id, folder).then(function(j){ rec.files[pid] = { driveId: j.id, sig: sig(p), mod: j.modifiedTime, created: j.createdTime }; });
          }
          // Changed in both places: keep both.
          return download(f.id).then(function(d){
            var dp = d.project || {};
            if (sig(Object.assign({}, dp, { id: pid })) === sig(p)) { rec.files[pid] = { driveId: f.id, sig: sig(p), mod: f.modifiedTime, created: f.createdTime }; return; }
            var copy = dp; copy.id = newId(); copy.name = (dp.name || "Untitled") + " (from Drive)"; copy.open = true;
            adds.push(copy);
            return upload(p, f.id, folder).then(function(j){ rec.files[pid] = { driveId: j.id, sig: sig(p), mod: j.modifiedTime, created: j.createdTime }; });
          });
        });
      });
      // On this device but not in Drive: send it (new, or deleted from Drive by hand — we never lose work).
      local.forEach(function(p){
        chain = chain.then(function(){
          if (onDrive[p.id]) return;
          if (blank(p) && !rec.files[p.id]) return;
          return upload(p, null, folder).then(function(j){ rec.files[p.id] = { driveId: j.id, sig: sig(p), mod: j.modifiedTime, created: j.createdTime }; });
        });
      });
      return chain.then(function(){
        // Forget records of things gone from both places.
        Object.keys(rec.files).forEach(function(pid){ if (!localById[pid] && !onDrive[pid] && !adds.some(function(a){ return a.id === pid; })) delete rec.files[pid]; });
      });
    });
  }).then(function(){
    if (!user || user.email !== who) return;     // signed out meanwhile — don't touch anything
    var changed = adds.length || Object.keys(replaces).length || !inDriveOrder(readBundle(), rec);
    if (changed) {
      // Apply onto the freshest bundle, so edits made during the sync aren't lost.
      flushQuietly();
      var b = readBundle() || JSON.parse(JSON.stringify(start));
      b.projects = b.projects || [];
      Object.keys(replaces).forEach(function(pid){
        var i = b.projects.findIndex(function(p){ return p.id === pid; });
        if (i < 0) return;
        if (sig(b.projects[i]) !== startSig[pid]) {   // edited during the sync → keep both
          var c = replaces[pid]; c.id = newId(); c.name = (c.name || "Untitled") + " (from Drive)"; c.open = true;
          adds.push(c); delete rec.files[pid];
        } else b.projects[i] = replaces[pid];
      });
      if (adds.length && spaceWasBlank) b.projects = b.projects.filter(function(p){ return !(blank(p) && !rec.files[p.id]); });
      b.projects = sortByDrive(b.projects.concat(adds), rec);
      if (!b.projects.some(function(p){ return p.id === b.activeId && p.open !== false; })) {
        var firstOpen = b.projects.filter(function(p){ return p.open !== false; })[0] || b.projects[0];
        if (firstOpen) { firstOpen.open = true; b.activeId = firstOpen.id; }
      }
      writeBundle(b);
      writeRec(rec);
      quietSave = true; try { app.reload(); } catch(e) {} quietSave = false;
      // The "(from Drive)" copies are new here; send them up next time round.
      if (adds.some(function(a){ return !rec.files[a.id]; })) scheduleSync();
    } else writeRec(rec);
    setStatus(unsyncedCount() ? "pending" : "synced");
  }, function(e){
    if (user && user.email === who) writeRec(rec);
    setStatus(e && e.auth ? "paused" : (navigator.onLine === false ? "offline" : "error"));
    throw e;
  });
  var p = syncing;
  syncing = p.then(function(){ syncing = null; }, function(){ syncing = null; });
  return p;
}

// Every device shows artworks in the same order: the order they first reached Drive.
// Ones not in Drive yet keep their place at the end.
function orderKey(p, rec, i){ var r = rec.files[p.id]; return [r && r.created ? r.created : "~", i]; }
function sortByDrive(list, rec){
  return list.map(function(p, i){ return { p: p, k: orderKey(p, rec, i) }; })
    .sort(function(a, b){ return a.k[0] < b.k[0] ? -1 : a.k[0] > b.k[0] ? 1 : a.k[1] - b.k[1]; })
    .map(function(x){ return x.p; });
}
function inDriveOrder(b, rec){
  if (!b || !b.projects) return true;
  var sorted = sortByDrive(b.projects, rec);
  return sorted.every(function(p, i){ return p === b.projects[i]; });
}

// ---- signing in ---------------------------------------------------------------------
function signIn(){
  closeMenu();
  if (!CLIENT_ID || !HELPER) { showModal({ title: "Sign-in isn't set up yet", body: "You can keep using " + app.label + " as normal. Everything saves on " + here() + ".", buttons: [{ label: "OK", primary: true }] }); return; }
  goToGoogle("signin");
}
function signInAgain(){
  closeMenu();
  if (!user) return;
  goToGoogle("again", user.email);
}

// Google has sent the learner back with "#na_auth=…" on the address.
function handleReturn(){
  var m = /[#&]na_auth=([^&]*)/.exec(location.hash);
  if (!m) return;
  try { history.replaceState(null, "", location.href.split("#")[0]); } catch(e) {}
  var res = null; try { res = JSON.parse(decodeURIComponent(m[1])); } catch(e) {}
  var pend = getJ("nextacct.pending"); del("nextacct.pending");
  if (!res || !pend || res.state !== pend.state) return;
  if (res.error) { if (res.error !== "access_denied") toast("Couldn't sign in. Please try again.", true); return; }
  var again = pend.mode === "again";
  var wait = showBusy("Signing you in…", "Just a moment.");
  helper("/exchange", { code: res.code, redirect_uri: REDIRECT }).then(function(j){
    closeModal(wait);
    if (j.error === "domain" || (j.user && !domainOk(j.user.email))) {
      showModal({ title: "Not available for this account yet", body: "Signing in is only open to " + DOMAINS.map(function(d){ return "@" + d; }).join(" and ") + " accounts for now. You can keep using " + app.label + " without signing in — your work saves on " + here() + ".", buttons: [{ label: "OK", primary: true }] });
      return;
    }
    if (j.error === "no_drive") {
      showModal({ title: "Drive permission needed", body: "To save your work to your account, please tick the box that lets Next Apps save to your Google Drive. Nothing else in your Drive is visible to the app.", buttons: [
        { label: "Not now" }, { label: "Try again", primary: true, onClick: function(){ again ? signInAgain() : signIn(); } } ] });
      return;
    }
    if (!j.access_token || !j.sealed || !j.user) { toast("Couldn't sign in. Please try again.", true); return; }
    if (again && user && j.user.email !== user.email) {
      toast("That's a different Google account. Please choose " + user.email + ".", true);
      return;
    }
    token = { t: j.access_token, exp: Date.now() + ((+j.expires_in || 3600) - 120) * 1000 };
    setJ("nextacct.token", token);
    sealed = j.sealed; setJ("nextacct.sealed", sealed);
    needSignIn = false;
    if (again && user) { render(); sync().then(function(){ toast("All set — saving to your Google Drive again."); }, function(){}); return; }
    user = { email: j.user.email.toLowerCase(), name: j.user.name, given: j.user.given, picture: j.user.picture || "" };
    setJ("nextacct.user", user);
    touch(true);
    return enterSpace();
  }, function(){
    closeModal(wait);
    toast(navigator.onLine === false ? "No internet right now. Please try signing in again when you're online." : "Couldn't sign in. Please try again.", true);
  });
}

// After sign-in: offer guest work once, then show this person's space and sync.
function enterSpace(){
  var hasSpace = getRaw(spaceKey(app.key)) != null;
  var offeredKey = "nextacct.offered." + app.app + "@@" + user.email;
  var start = (!hasSpace && !getJ(offeredKey)) ? offerGuestWork() : Promise.resolve();
  clearToasts();
  return start.then(function(){
    setJ(offeredKey, true);
    reloadApp();
    render();
    // Grey out the app while their work comes in from Drive, so it never looks like it's gone.
    var busy = showBusy("Getting your work from Google Drive…", "This takes a few seconds.");
    setStatus("loading");
    var done = false;
    var slow = setTimeout(function(){ if (!done) { done = true; closeModal(busy); toast("Still fetching your work from Google Drive — it'll appear here in a moment."); } }, 25000);
    function finish(){ clearTimeout(slow); if (!done) { done = true; closeModal(busy); } }
    return sync().then(function(){ finish(); toast("Signed in as " + user.given + ". Your work now saves to your Google Drive.", true); },
                       function(){ finish(); toast("Signed in as " + user.given + ". Saving to Drive will start shortly.", true); });
  });
}

// "Move any of these into your account?" — copies; the guest space is left untouched.
function offerGuestWork(force){
  var g = readGuestBundle();
  var items = (g && g.projects || []).filter(function(p){ return !blank(p); });
  if (!items.length) { if (force) toast("There are no guest artworks on " + here() + "."); return Promise.resolve(); }
  return new Promise(function(resolve){
    var list = document.createElement("div"); list.className = "na-pick";
    var boxes = [];
    items.forEach(function(p){
      var row = document.createElement("label"); row.className = "na-pickrow";
      var cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = !force; boxes.push(cb);
      var th = document.createElement("span"); th.className = "na-thumb";
      try { var t = app.thumb && app.thumb(p); if (t) th.appendChild(t); } catch(e) {}
      var nm = document.createElement("span"); nm.className = "na-pickname"; nm.textContent = p.name || "Untitled";
      row.appendChild(cb); row.appendChild(th); row.appendChild(nm); list.appendChild(row);
    });
    showModal({
      title: "Bring these into your account?",
      body: "These artworks are on " + here() + " but not in anyone's account. Tick the ones that are yours — they'll be copied into your account and your Drive. Anything you leave unticked stays here for guests.",
      content: list,
      buttons: [
        { label: "Not now", onClick: function(){ resolve(); } },
        { label: "Bring in ticked", primary: true, onClick: function(){
            var chosen = items.filter(function(p, i){ return boxes[i].checked; });
            if (chosen.length) {
              var b = readBundle();
              if (!b) { b = JSON.parse(JSON.stringify(g)); b.projects = []; }   // keep the app's other settings
              b.projects = b.projects || [];
              var have = {}; b.projects.forEach(function(p){ have[sig(p)] = 1; });
              var copies = chosen.filter(function(p){ return !have[sig(p)]; }).map(function(p){ var c = JSON.parse(JSON.stringify(p)); c.open = true; return c; });
              var existingIds = {}; b.projects.forEach(function(p){ existingIds[p.id] = 1; });
              copies.forEach(function(c){ if (existingIds[c.id]) c.id = newId(); });
              b.projects = b.projects.filter(function(p){ return !blank(p); }).concat(copies);
              if (!b.projects.some(function(p){ return p.id === b.activeId; }) && b.projects[0]) b.activeId = b.projects[0].id;
              writeBundle(b);
            }
            resolve();
        } }
      ]
    });
  });
}

// ---- signing out ----------------------------------------------------------------------
function signOut(){
  closeMenu();
  if (!user) return;
  try { app.flush(); } catch(e) {}
  var m = showModal({ title: "Signing out…", body: "Saving your work to Google Drive first.", buttons: [] });
  sync().then(function(){
    closeModal(m);
    if (unsyncedCount() === 0) finishSignOut(true);
    else askUnsynced();
  }, function(){ closeModal(m); askUnsynced(); });
}
function askUnsynced(){
  var n = unsyncedCount();
  if (n === 0) { finishSignOut(true); return; }
  showModal({
    title: n === 1 ? "1 artwork hasn't reached your Drive yet" : n + " artworks haven't reached your Drive yet",
    body: (needSignIn ? "Saving to Drive needs you to sign in again first." : "This usually means there's no internet right now.") + " If you sign out anyway, they stay on " + here() + ", hidden and set aside for you. Next time you sign in here, they'll go to your Drive.",
    buttons: [
      { label: "Download a backup", onClick: function(){ downloadBackup(); askUnsynced(); } },
      { label: "Sign out anyway", onClick: function(){ finishSignOut(false); } },
      { label: "Stay signed in", primary: true }
    ]
  });
}
// everythingSafe: all work is in Drive, so this device's copy can go.
// (We only forget the renewal key on this device. We don't cancel it with Google,
//  because that would also sign the learner out on their other devices.)
function finishSignOut(everythingSafe, auto){
  var name = user && user.given;
  clearToasts();   // old "signed in as…" notices no longer apply
  if (everythingSafe && user) { del(app.key + "@@" + user.email); del(recKey()); }
  user = null; token = null; sealed = null; needSignIn = false; clearTimeout(syncTimer);
  del("nextacct.user"); del("nextacct.token"); del("nextacct.sealed");
  reloadApp(); setStatus("guest"); render();
  if (auto) toast(name + " was signed out after " + (IDLE_MS / 3600000) + " hours away." + (everythingSafe ? "" : " Their unsaved work is set aside for them."), true);
  else toast(everythingSafe ? "Signed out. Your work is safe in your Google Drive." : "Signed out. Your unsaved work is set aside on " + here() + " for next time.", true);
}
// Tap on the status: sign in again if the renewal key stopped working, otherwise sync now.
function syncNow(){
  closeMenu();
  if (!user) return;
  if (needSignIn) { signInAgain(); return; }
  sync().catch(function(e){
    if (e && e.auth) return;   // the status now says "Sign in again"
    if (navigator.onLine === false) toast("No internet right now. Your work is safe on " + here() + ".");
    else toast("Couldn't reach Google Drive. Your work is safe on " + here() + ".");
  });
}

// ---- idle auto sign-out ------------------------------------------------------------------
var lastTouchSaved = 0;
function touch(force){
  var now = Date.now();
  if (!force && now - lastTouchSaved < 30000) return;
  lastTouchSaved = now; setJ("nextacct.lastActive", now);
}
function checkIdle(){
  if (!user || !IDLE_MS) return;
  var last = getJ("nextacct.lastActive") || 0;
  if (last && Date.now() - last > IDLE_MS) finishSignOut(unsyncedCount() === 0, true);
}

// ---- backup ------------------------------------------------------------------------------
function downloadBackup(){
  closeMenu();
  try { app.flush(); } catch(e) {}
  var spaces = { guest: readGuestBundle() };
  if (user) spaces[user.email] = readBundle();
  var data = { app: app.app, kind: "next-apps-backup", format: 1, exportedAt: new Date().toISOString(), spaces: spaces };
  var blob = new Blob([JSON.stringify(data)], { type: "application/json" });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = app.app + "-backup-" + new Date().toISOString().slice(0, 10) + ".json";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(function(){ URL.revokeObjectURL(a.href); }, 4000);
}
function restoreBackup(){
  closeMenu();
  var inp = document.createElement("input"); inp.type = "file"; inp.accept = ".json,application/json";
  inp.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
  document.body.appendChild(inp);
  inp.onchange = function(){
    var f = inp.files && inp.files[0]; inp.remove(); if (!f) return;
    var rd = new FileReader();
    rd.onload = function(){
      function tell(t, b){ showModal({ title: t, body: b, buttons: [{ label: "OK", primary: true }] }); }
      var d; try { d = JSON.parse(rd.result); } catch(e) { tell("That file isn't a backup", "Choose a file made with \u201cDownload all my work\u201d."); return; }
      var found = [];
      if (d && d.spaces) Object.keys(d.spaces).forEach(function(k){ var b = d.spaces[k]; if (b && b.projects) found = found.concat(b.projects); });
      else if (d && d.projects) found = d.projects;
      if (d && d.app && d.app !== app.app) { tell("That backup is from another app", "It was made in a different Next app. Open that app to restore it."); return; }
      try { app.flush(); } catch(e) {}
      var b = readBundle(); if (b === undefined) return;
      if (!b) { b = JSON.parse(JSON.stringify(readGuestBundle() || {})); b.projects = []; }
      b.projects = b.projects || [];
      var have = {}, ids = {}; b.projects.forEach(function(p){ have[sig(p)] = 1; ids[p.id] = 1; });
      var added = 0;
      found.forEach(function(p){
        if (!p || blank(p) || have[sig(p)]) return;
        var c = JSON.parse(JSON.stringify(p)); if (ids[c.id]) c.id = newId(); c.open = false;
        b.projects.push(c); have[sig(c)] = 1; ids[c.id] = 1; added++;
      });
      var total = found.filter(function(p){ return p && !blank(p); }).length;
      if (!added) { tell("Nothing new to add", total === 1 ? "The artwork in this backup is already here, unchanged." : total ? "All " + total + " artworks in this backup are already here, unchanged." : "This backup has no artworks in it."); return; }
      if (!b.projects.some(function(p){ return p.id === b.activeId; })) { b.projects[0].open = true; b.activeId = b.projects[0].id; }
      writeBundle(b); reloadApp();
      if (user) scheduleSync();
      var msg = "Restored " + added + (added === 1 ? " artwork" : " artworks") + (total > added ? " (" + (total - added) + " already here)" : "") + ".";
      if (app.showAll) { try { app.showAll(); toast(msg, true); return; } catch(e) {} }   // open the app's "All artworks" view so they're right there
      tell("Restored " + added + (added === 1 ? " artwork" : " artworks"), "Find " + (added === 1 ? "it" : "them") + " in All artworks." + (total > added ? " " + (total - added) + " other" + (total - added === 1 ? " was" : "s were") + " already here." : ""));
    };
    rd.readAsText(f);
  };
  inp.click();
}

function reloadApp(){ try { app.reload(); } catch(e) { if (window.console) console.error(e); } }

// ---- UI ------------------------------------------------------------------------------------
var CSS = "" +
".na-wrap{flex:0 0 auto;display:flex;align-items:center;gap:6px}" +
".na-status{height:36px;width:138px;justify-content:flex-start;overflow:hidden;display:flex;align-items:center;gap:6px;padding:0 10px;border-radius:10px;border:2px solid var(--line,#ddd);background:transparent;color:var(--muted,#777);font:inherit;font-weight:700;font-size:.74rem;cursor:pointer;white-space:nowrap}" +
".na-status svg{width:17px;height:17px;display:block;flex:0 0 auto}" +
".na-status.warn{color:var(--ink,#222);border-color:var(--ink,#222)}" +
".na-acct{height:36px;display:flex;align-items:center;gap:7px;padding:0 10px 0 4px;border-radius:10px;border:2px solid var(--line,#ddd);background:transparent;color:var(--ink,#222);font:inherit;font-weight:800;font-size:.78rem;cursor:pointer;white-space:nowrap}" +
".na-acct.out{padding:0 11px}" +
".na-acct svg{width:17px;height:17px;display:block}" +
".na-av{width:26px;height:26px;border-radius:50%;overflow:hidden;background:var(--accent,#222);color:var(--accent-ink,#fff);display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:800;flex:0 0 auto}" +
".na-av img{width:100%;height:100%;object-fit:cover;display:block}" +
"@media (max-width:699px){.na-status .na-txt{display:none}.na-status{padding:0 9px;width:auto}}" +
"@media (max-width:520px){.na-acct .na-txt{display:none}.na-acct{padding:0 4px}.na-acct.out{padding:0 9px}}" +
".na-menu{position:fixed;z-index:1003;width:250px;max-width:calc(100vw - 24px);background:var(--card,#fff);color:var(--ink,#222);border:1px solid var(--line,#ddd);border-radius:14px;box-shadow:0 12px 34px var(--shadow,rgba(0,0,0,.2));padding:8px;font-family:inherit}" +
".na-menu .na-who{padding:8px 10px 10px;border-bottom:1px solid var(--line,#ddd);margin-bottom:6px}" +
".na-menu .na-who b{display:block;font-size:.95rem}.na-menu .na-who small{color:var(--muted,#777);font-size:.78rem}" +
".na-menu .na-note{padding:6px 10px 8px;color:var(--muted,#777);font-size:.78rem;line-height:1.35}" +
".na-menu button{display:block;width:100%;text-align:left;padding:10px;border:0;border-radius:9px;background:transparent;color:inherit;font:inherit;font-weight:700;font-size:.88rem;cursor:pointer}" +
".na-menu button:hover{background:var(--teal,rgba(0,0,0,.06))}" +
".na-menu hr{border:0;border-top:1px solid var(--line,#ddd);margin:6px 0}" +
".na-back{position:fixed;inset:0;z-index:1004;background:rgba(10,8,16,.45);display:flex;align-items:center;justify-content:center;padding:16px}" +
".na-modal{width:100%;max-width:440px;max-height:calc(100dvh - 32px);overflow:auto;background:var(--card,#fff);color:var(--ink,#222);border-radius:18px;padding:22px;box-shadow:0 20px 50px rgba(0,0,0,.35);font-family:inherit}" +
".na-modal h3{margin:0 0 8px;font-size:1.1rem}" +
".na-modal p{margin:0 0 14px;color:var(--muted,#666);font-size:.9rem;line-height:1.45}" +
".na-btns{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;margin-top:16px}" +
".na-btns button{height:40px;padding:0 14px;border-radius:10px;border:2px solid var(--line,#ddd);background:transparent;color:var(--ink,#222);font:inherit;font-weight:800;font-size:.86rem;cursor:pointer}" +
".na-btns button.pri{background:var(--accent,#222);border-color:var(--accent,#222);color:var(--accent-ink,#fff)}" +
".na-busy{text-align:center;max-width:340px;display:flex;flex-direction:column;align-items:center}" +
".na-busy h3{order:2;margin:14px 0 4px}.na-busy p{order:3;margin:0}" +
".na-spin{order:1;width:34px;height:34px;border-radius:50%;border:3px solid var(--line,#ddd);border-top-color:var(--ink,#222);animation:na-spin .8s linear infinite}" +
"@keyframes na-spin{to{transform:rotate(360deg)}}" +
"@media (prefers-reduced-motion:reduce){.na-spin{animation-duration:2.4s}}" +
".na-pick{display:flex;flex-direction:column;gap:6px;max-height:46vh;overflow:auto}" +
".na-pickrow{display:flex;align-items:center;gap:10px;padding:6px 8px;border:1px solid var(--line,#ddd);border-radius:10px;cursor:pointer}" +
".na-pickrow input{width:20px;height:20px;flex:0 0 auto}" +
".na-thumb{width:44px;height:44px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;background:#fff;border-radius:6px;overflow:hidden}" +
".na-thumb canvas{max-width:100%;max-height:100%;image-rendering:pixelated;width:auto;height:auto}" +
".na-pickname{font-weight:700;font-size:.9rem}" +
".na-toasts{position:fixed;top:calc(58px + env(safe-area-inset-top));right:12px;z-index:1002;display:flex;flex-direction:column;gap:8px;width:300px;max-width:calc(100vw - 24px);pointer-events:none}" +
".na-toast{pointer-events:auto;display:flex;align-items:flex-start;gap:10px;background:var(--card,#fff);color:var(--ink,#222);border:1px solid var(--line,#ddd);padding:11px 8px 11px 14px;border-radius:12px;font-family:inherit;font-weight:700;font-size:.84rem;line-height:1.35;box-shadow:0 10px 30px var(--shadow,rgba(0,0,0,.25));transition:opacity .25s}" +
".na-toast span{flex:1 1 auto}" +
".na-tx{flex:0 0 auto;border:0;background:transparent;color:var(--muted,#777);font:inherit;font-size:.85rem;cursor:pointer;padding:0 6px;line-height:1.35}";

var ICON = {
  person: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  ok:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.5 19H7a5 5 0 1 1 1.6-9.7A6 6 0 0 1 20 11a4 4 0 0 1-2.5 8Z"/><path d="m9.5 14 2 2 3.5-3.5"/></svg>',
  busy:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.5 19H7a5 5 0 1 1 1.6-9.7A6 6 0 0 1 20 11a4 4 0 0 1-2.5 8Z"/><path d="M12 16v-4m0 0-2 2m2-2 2 2"/></svg>',
  off:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.5 19H7a5 5 0 1 1 1.6-9.7A6 6 0 0 1 20 11a4 4 0 0 1-2.5 8Z"/><path d="M12 11v3m0 2.5v.01"/></svg>'
};
var STATUS = {
  synced:  { icon: "ok",   text: "Saved to Drive", tip: function(){ return "Everything is saved to your Google Drive."; } },
  pending: { icon: "busy", text: "Saving…",        tip: function(){ return "Saving your latest changes to Google Drive."; } },
  loading: { icon: "busy", text: "Loading…",       tip: function(){ return "Getting your work from Google Drive."; } },
  syncing: { icon: "busy", text: "Saving…",        tip: function(){ return "Saving your latest changes to Google Drive."; } },
  paused:  { icon: "off",  warn: true, text: "Sign in again", tip: function(){ return "Your work is saved on " + here() + ". Sign in again to keep saving to Google Drive."; } },
  offline: { icon: "off",  warn: true, text: "Offline",      tip: function(){ return "No internet. Your work is saved on " + here() + " and goes to Drive when you're back online."; } },
  error:   { icon: "off",  warn: true, text: "Tap to retry", tip: function(){ return "Couldn't reach Google Drive. Your work is saved on " + here() + ". Tap to try again."; } }
};

function setStatus(s){ status = s; renderStatus(); }
function renderStatus(){
  if (!ui.status) return;
  if (!user) { ui.status.hidden = true; return; }
  var d = STATUS[status] || STATUS.synced;
  ui.status.hidden = false;
  ui.status.className = "na-status" + (d.warn ? " warn" : "");
  ui.status.innerHTML = ICON[d.icon] + '<span class="na-txt"></span>';
  ui.status.querySelector(".na-txt").textContent = d.text;
  ui.status.title = d.tip();
  ui.status.setAttribute("aria-label", d.tip());
}
function render(){
  if (!ui.acct) return;
  if (user) {
    ui.acct.className = "na-acct";
    ui.acct.innerHTML = '<span class="na-av"></span><span class="na-txt"></span>';
    var av = ui.acct.querySelector(".na-av");
    if (user.picture) { var img = document.createElement("img"); img.alt = ""; img.referrerPolicy = "no-referrer"; img.src = user.picture; img.onerror = function(){ av.textContent = (user.given || "?")[0].toUpperCase(); }; av.appendChild(img); }
    else av.textContent = (user.given || "?")[0].toUpperCase();
    ui.acct.querySelector(".na-txt").textContent = user.given;
    ui.acct.title = "Signed in as " + user.email;
    ui.acct.setAttribute("aria-label", "Account: " + user.email);
  } else {
    ui.acct.className = "na-acct out";
    ui.acct.innerHTML = ICON.person + '<span class="na-txt">Sign in</span>';
    ui.acct.title = "Sign in to save your work to your account";
    ui.acct.setAttribute("aria-label", "Sign in");
  }
  renderStatus();
}

var menuEl = null;
function closeMenu(){ if (menuEl) { menuEl.remove(); menuEl = null; } }
function openMenu(){
  if (menuEl) { closeMenu(); return; }
  var m = document.createElement("div"); m.className = "na-menu"; m.setAttribute("role", "menu");
  function item(label, fn){ var b = document.createElement("button"); b.textContent = label; b.addEventListener("click", fn); m.appendChild(b); }
  if (user) {
    var who = document.createElement("div"); who.className = "na-who";
    who.innerHTML = "<b></b><small></small>"; who.querySelector("b").textContent = user.name; who.querySelector("small").textContent = user.email;
    m.appendChild(who);
    item("Sync to Drive now", syncNow);
    item("Bring in guest artworks…", function(){ closeMenu(); try { app.flush(); } catch(e) {} offerGuestWork(true).then(function(){ reloadApp(); scheduleSync(); }); });
    m.appendChild(document.createElement("hr"));
    item("Download all my work", downloadBackup);
    item("Restore from a backup…", restoreBackup);
    m.appendChild(document.createElement("hr"));
    item("Sign out", signOut);
  } else {
    item("Sign in with Google", signIn);
    var n = document.createElement("div"); n.className = "na-note";
    n.textContent = "Optional. Saves your work to your own Google Drive so it follows you to any device. Open to " + DOMAINS.map(function(d){ return "@" + d; }).join(" and ") + " accounts for now.";
    m.appendChild(n);
    m.appendChild(document.createElement("hr"));
    item("Download all my work", downloadBackup);
    item("Restore from a backup…", restoreBackup);
  }
  document.body.appendChild(m); menuEl = m;
  var r = ui.acct.getBoundingClientRect(), w = m.offsetWidth;
  m.style.top = (r.bottom + 6) + "px";
  m.style.left = Math.max(12, Math.min(window.innerWidth - w - 12, r.right - w)) + "px";
}

var modalStack = [];
function showModal(o){
  closeMenu();
  var back = document.createElement("div"); back.className = "na-back";
  var box = document.createElement("div"); box.className = "na-modal"; box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true");
  var h = document.createElement("h3"); h.textContent = o.title; box.appendChild(h);
  if (o.body) { var p = document.createElement("p"); p.textContent = o.body; box.appendChild(p); }
  if (o.content) box.appendChild(o.content);
  if (o.buttons && o.buttons.length) {
    var row = document.createElement("div"); row.className = "na-btns";
    o.buttons.forEach(function(b){
      var el = document.createElement("button"); el.textContent = b.label; if (b.primary) el.className = "pri";
      el.addEventListener("click", function(){ closeModal(back); if (b.onClick) b.onClick(); });
      row.appendChild(el);
    });
    box.appendChild(row);
  }
  back.appendChild(box);
  // keep keys away from the app's drawing shortcuts while a box is open
  back.addEventListener("keydown", function(e){ e.stopPropagation(); });
  document.body.appendChild(back); modalStack.push(back);
  return back;
}
// A greyed-out screen with a spinner, for short waits. Close it with closeModal().
function showBusy(title, body){
  var spin = document.createElement("div"); spin.className = "na-spin"; spin.setAttribute("aria-hidden", "true");
  var m = showModal({ title: title, body: body, content: spin, buttons: [] });
  m.querySelector(".na-modal").className += " na-busy";
  m.querySelector(".na-modal").setAttribute("aria-busy", "true");
  return m;
}
function closeModal(el){ if (el && el.parentNode) el.remove(); modalStack = modalStack.filter(function(x){ return x !== el; }); }
// toast(msg) disappears by itself; toast(msg, true) stays until it's closed.
var toastBox = null;
function clearToasts(){ if (toastBox) toastBox.innerHTML = ""; }
function toast(msg, sticky){
  if (!toastBox) { toastBox = document.createElement("div"); toastBox.className = "na-toasts"; toastBox.setAttribute("role", "status"); toastBox.setAttribute("aria-live", "polite"); document.body.appendChild(toastBox); }
  var t = document.createElement("div"); t.className = "na-toast";
  var tx = document.createElement("span"); tx.textContent = msg; t.appendChild(tx);
  function bye(){ t.style.opacity = "0"; setTimeout(function(){ t.remove(); }, 250); }
  var x = document.createElement("button"); x.className = "na-tx"; x.textContent = "✕"; x.setAttribute("aria-label", "Dismiss"); x.addEventListener("click", bye); t.appendChild(x);
  toastBox.appendChild(t);
  while (toastBox.children.length > 3) toastBox.firstChild.remove();
  if (!sticky) setTimeout(bye, 4500);
}

// ---- register an app --------------------------------------------------------------------
function register(o){
  app = o;
  // Test copy: start from a copy of the live guest work, never touching the live data itself.
  if (PREFIX && CFG.seedFromLive) {
    var s = store();
    if (s && !getJ("nextacct.seeded." + o.app)) {
      CFG.seedFromLive.forEach(function(k){ try { var v = s.getItem(k); if (v != null && s.getItem(PREFIX + k) == null) s.setItem(PREFIX + k, v); } catch(e) {} });
      setJ("nextacct.seeded." + o.app, true);
    }
  }
  var st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);
  var wrap = document.createElement("div"); wrap.className = "na-wrap";
  ui.status = document.createElement("button"); ui.status.className = "na-status"; ui.status.hidden = true; ui.status.addEventListener("click", syncNow);
  ui.acct = document.createElement("button"); ui.acct.addEventListener("click", function(e){ e.stopPropagation(); openMenu(); });
  wrap.appendChild(ui.status); wrap.appendChild(ui.acct);
  (o.mount || document.body).appendChild(wrap);
  document.addEventListener("click", function(e){ if (menuEl && !menuEl.contains(e.target)) closeMenu(); });
  document.addEventListener("keydown", function(e){ if (e.key === "Escape") closeMenu(); });
  document.addEventListener("pointerdown", function(){ if (user) touch(false); }, true);
  document.addEventListener("keydown", function(){ if (user) touch(false); }, true);
  document.addEventListener("visibilitychange", function(){
    if (document.visibilityState !== "visible") return;
    checkIdle();
    if (user && !needSignIn) sync().catch(function(){});
  });
  window.addEventListener("online", function(){ if (user && !needSignIn) sync().catch(function(){}); else renderStatus(); });
  window.addEventListener("offline", function(){ if (user) setStatus("offline"); });

  if (user && IDLE_MS && getJ("nextacct.lastActive") && Date.now() - getJ("nextacct.lastActive") > IDLE_MS) {
    // Signed out after a long time away. (The app hasn't drawn anything yet, so it simply loads the guest space.)
    var name = user.given, safe = unsyncedCount() === 0;
    if (safe) { del(app.key + "@@" + user.email); del(recKey()); }
    user = null; token = null; sealed = null; del("nextacct.user"); del("nextacct.token"); del("nextacct.sealed");
    setTimeout(function(){ toast(name + " was signed out after " + (IDLE_MS / 3600000) + " hours away." + (safe ? "" : " Their unsaved work is set aside for them."), true); }, 600);
  }
  if (user) touch(true);
  if (user && !sealed && !tokenOk()) needSignIn = true;   // signed in with the older pop-up version
  status = user ? (needSignIn ? "paused" : "pending") : "guest";
  render();
  if (location.hash.indexOf("na_auth=") >= 0) handleReturn();
  else if (user && !needSignIn) setTimeout(function(){ sync().catch(function(){}); }, 800);
}

window.NextAccount = {
  register: register, getItem: getItem, setItem: setItem,
  // for testing / debugging
  _debug: { sync: function(){ return sync(); }, unsynced: unsyncedCount, state: function(){ return { user: user, token: token, sealed: sealed, needSignIn: needSignIn, status: status }; } }
};
})();
