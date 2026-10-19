"""Builds ../meow.py (the single file Kaggle runs) from the parts in this folder.
Run:  python meow/src/build.py      Then check: node --check /tmp/meow.js (the page's JavaScript)."""
import os, re, ast
HERE = os.path.dirname(os.path.abspath(__file__))
r = lambda f: open(os.path.join(HERE, f), encoding="utf-8").read()
p3 = r("p3.py"); cut = p3.index("# ==========================================================\n# LAUNCH")
h1 = r("h1.html").replace('<div id="toasts"></div>', r("h1b.html") + '<div id="toasts"></div>')
h2 = r("h2.html").replace("/* ---------------- boot ---------------- */", r("ed.js") + "\n/* ---------------- boot ---------------- */")
h = h1 + h2; assert '"""' not in h
out = (r("p1.py") + r("p2.py") + r("p2b.py") + r("p2c.py") + r("p2d.py") + r("p2e.py") + r("p2f.py") + r("p2g.py")
       + '\n# ==========================================================\n# FRONTEND (single page)\n# ==========================================================\nMEOW_HTML = r"""' + h + '"""\n'
       + p3[:cut] + r("p3b.py") + "\n" + p3[cut:])
ast.parse(out)
for bad in ("3d4310", "tvly-dev-", "3Bw3pk"):
    assert bad not in out, "a private key slipped into meow.py — remove it"
open(os.path.join(HERE, "..", "meow.py"), "w", encoding="utf-8").write(out)
js = re.search(r"<script>\n(.*?)</script>", out, re.S).group(1)
open("/tmp/meow.js", "w").write(js)
print(len(out.splitlines()), "lines → meow/meow.py")
