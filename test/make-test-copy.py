#!/usr/bin/env python3
"""Make the Pixel Pad test copy (with sign-in) from the live Pixel Pad.
Usage (from the next-apps folder): python3 test/make-test-copy.py .
Reads  pixel-pad/index.html (never changes it)
Writes test/pixel-pad/index.html
"""
import sys, os
root = sys.argv[1] if len(sys.argv) > 1 else "."
src = open(os.path.join(root, "pixel-pad", "index.html"), encoding="utf-8").read()
s = src

def sub(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        sys.exit("expected %d of %r, found %d" % (count, old[:60], n))
    s = s.replace(old, new)

# 1. title + favicon mark the test copy (yellow tile, dark pixels — easy to tell apart in tabs)
sub("<title>Pixel Pad</title>", "<title>TEST · Pixel Pad</title>")
import re, urllib.parse
TEST_ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
  '<rect x="1" y="1" width="30" height="30" rx="7" fill="#FFD43B" stroke="#2C2740" stroke-width="2"/>'
  + "".join('<rect x="%d" y="%d" width="5" height="5" rx="1" fill="#2C2740"/>' % xy
            for xy in [(5,5),(16,5),(10,11),(21,11),(5,16),(16,16),(10,21),(21,21)])
  + '</svg>')
n_before = len(re.findall(r'<link rel="icon" href="[^"]*">', s))
if n_before != 1: sys.exit("expected 1 favicon link, found %d" % n_before)
s = re.sub(r'<link rel="icon" href="[^"]*">', lambda m: '<link rel="icon" href="data:image/svg+xml,' + urllib.parse.quote(TEST_ICON, safe="") + '">', s)

# 2. load the shared sign-in module before the app script
sub("<script>\n(function(){\n  \"use strict\";\n  var KEY=\"pixelpad-v1\";",
    "<script>window.NEXT_ACCOUNT_CONFIG={storagePrefix:\"test:\", seedFromLive:[\"pixelpad-v2\",\"pixelpad-v1\"]};</script>\n"
    "<script src=\"../shared/next-account.js\"></script>\n"
    "<script>\n(function(){\n  \"use strict\";\n  var KEY=\"pixelpad-v1\";")

# 3. artwork bundle goes through NextAccount (guest space = same data as before)
sub("localStorage.setItem(KEY2,", "NextAccount.setItem(KEY2,")
sub("localStorage.getItem(KEY2)", "NextAccount.getItem(KEY2)")
sub("localStorage.getItem(KEY)", "NextAccount.getItem(KEY)")

# 4. a place in the top bar for the account button
sub('<span class="lbl">All artworks</span></button>\n  </div>',
    '<span class="lbl">All artworks</span></button>\n    <div id="naMount" style="display:contents"></div>\n  </div>')

# 5. register before the first load
sub("  // ---- init ----\n  load();",
    """  // ---- account: optional sign-in, saving to the learner's Google Drive ----
  NextAccount.register({
    app:"pixel-pad", label:"Pixel Pad", key:KEY2, legacyKeys:[KEY],
    mount:document.getElementById("naMount"),
    flush:function(){ commitActive(); save(); },
    reload:function(){ closeFiles(); exitPaste(); projects=[]; activeId=null; seq=0; load(); loadProject(activeProj()); },
    isBlank:function(p){ return !(p.model||[]).some(function(v){ return v; }); },
    thumb:function(p){ return thumbOf({cols:p.cols, rows:p.rows, model:p.model||[]}); }
  });

  // ---- init ----
  load();""")

out = os.path.join(root, "test", "pixel-pad")
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(s)
print("wrote", os.path.join(out, "index.html"))
