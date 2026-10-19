"""Run Meow's offline test-suite (fake model, mocked internet).
    python meow/tests/run_tests.py            # backend tests
    python meow/tests/run_tests.py --ui       # + browser tests (needs playwright and the JS libs in /tmp/meow_tests/libs)
Copies meow.py + fixtures to /tmp/meow_tests first, because the tests use that folder."""
import os, sys, shutil, subprocess, glob
HERE = os.path.dirname(os.path.abspath(__file__)); W = "/tmp/meow_tests"
os.makedirs(W, exist_ok=True)
shutil.copy(os.path.join(HERE, "..", "meow.py"), W)
for f in glob.glob(os.path.join(HERE, "fixtures", "*")): shutil.copy(f, W)
for f in glob.glob(os.path.join(HERE, "*.py")): shutil.copy(f, W)
tests = ["harness.py", "edit_test.py", "scan_test.py", "img_test.py", "real_test.py", "web_test.py", "reddit_test.py",
         "reddit_deep_test.py", "search2_test.py", "py_test.py", "tools2_test.py"]
if "--ui" in sys.argv: tests += ["ui5.py", "ui6.py"]
bad = []
for t in tests:
    r = subprocess.run([sys.executable, t], cwd=W, capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    ok = r.returncode == 0 and "Traceback (most recent call last):\n  File \"/tmp" not in out
    print(("✅" if ok else "❌"), t)
    if not ok: bad.append(t); print(out[-2500:])
sys.exit(1 if bad else 0)
