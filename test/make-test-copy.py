#!/usr/bin/env python3
"""Make the Pixel Pad TEST copy from the live Pixel Pad.
Usage (from the next-apps folder): python3 test/make-test-copy.py .
Reads  pixel-pad/index.html (never changes it)
Writes test/pixel-pad/index.html

The test copy uses the same shared sign-in code (shared/next-account.js) but keeps
its own separate storage ("test:" prefix, seeded once from a copy of the live work)
and its own sign-in return page (test/signin/). Handy for trying changes to the
sign-in code before learners see them.
"""
import sys, os, re, urllib.parse
root = sys.argv[1] if len(sys.argv) > 1 else "."
s = open(os.path.join(root, "pixel-pad", "index.html"), encoding="utf-8").read()

def sub(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        sys.exit("expected %d of %r, found %d" % (count, old[:60], n))
    s = s.replace(old, new)

# 1. title + favicon mark the test copy (yellow tile, dark pixels — easy to tell apart in tabs)
sub("<title>Pixel Pad</title>", "<title>TEST · Pixel Pad</title>")
TEST_ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
  '<rect x="1" y="1" width="30" height="30" rx="7" fill="#FFD43B" stroke="#2C2740" stroke-width="2"/>'
  + "".join('<rect x="%d" y="%d" width="5" height="5" rx="1" fill="#2C2740"/>' % xy
            for xy in [(5,5),(16,5),(10,11),(21,11),(5,16),(16,16),(10,21),(21,21)])
  + '</svg>')
if len(re.findall(r'<link rel="icon" href="[^"]*">', s)) != 1: sys.exit("expected 1 favicon link")
s = re.sub(r'<link rel="icon" href="[^"]*">', lambda m: '<link rel="icon" href="data:image/svg+xml,' + urllib.parse.quote(TEST_ICON, safe="") + '">', s)

# 2. separate test storage + the shared code one folder further up
sub('<script src="../shared/next-account.js?v=',
    '<script>window.NEXT_ACCOUNT_CONFIG={storagePrefix:"test:", seedFromLive:["pixelpad-v2","pixelpad-v1"]};</script>\n'
    '<script src="../../shared/next-account.js?v=')

out = os.path.join(root, "test", "pixel-pad")
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(s)
print("wrote", os.path.join(out, "index.html"))
