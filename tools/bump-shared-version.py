#!/usr/bin/env python3
"""Stamp every app with the current version of shared/next-account.js.
Run from the next-apps folder after changing the shared file:
    python3 tools/bump-shared-version.py
Browsers cache the shared file; the ?v= stamp makes sure everyone gets the new one."""
import hashlib, re, glob, os
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ver = hashlib.md5(open(os.path.join(root, "shared", "next-account.js"), "rb").read()).hexdigest()[:8]
for f in sorted(glob.glob(os.path.join(root, "*", "index.html")) + glob.glob(os.path.join(root, "test", "*", "index.html"))):
    s = open(f, encoding="utf-8").read()
    t = re.sub(r'(shared/next-account\.js\?v=)[0-9a-f]+', r'\g<1>' + ver, s)
    if t != s:
        open(f, "w", encoding="utf-8").write(t); print("stamped", os.path.relpath(f, root), ver)
