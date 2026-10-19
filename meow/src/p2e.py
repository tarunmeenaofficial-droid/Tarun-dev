
# ==========================================================
# CODE INTERPRETER (like ChatGPT's): a persistent Python session per chat.
# The model writes ```meow-python blocks; the server runs them, streams the output (text, tables, charts, files)
# back into the answer, and the model continues with the real results.
# ==========================================================
import subprocess, queue, sys as _sys, shutil

PY_TIMEOUT = 90            # seconds per run
PY_MAX_ROUNDS = 4          # code runs per answer
_PY_MARK = "\x00MEOW-RESULT\x00"

_KERNEL_SRC = r'''
import sys, os, io, json, ast, traceback, contextlib, uuid, time
os.environ.setdefault("MPLBACKEND", "Agg")
MARK = "\x00MEOW-RESULT\x00"
G = {"__name__": "__main__"}
real_out = sys.stdout

def _figs(out_dir):
    paths = []
    if "matplotlib.pyplot" in sys.modules:
        plt = sys.modules["matplotlib.pyplot"]
        plt.show = lambda *a, **k: None
        for n in plt.get_fignums():
            p = os.path.join(out_dir, f"figure_{uuid.uuid4().hex[:6]}.png")
            try:
                plt.figure(n).savefig(p, dpi=130, bbox_inches="tight", facecolor="white"); paths.append(p)
            except Exception:
                pass
        plt.close("all")
    return paths

def _show(v):
    try:
        import pandas as pd
        if isinstance(v, (pd.DataFrame, pd.Series)):
            with pd.option_context("display.max_rows", 40, "display.max_columns", 20, "display.width", 160):
                return repr(v)
    except Exception:
        pass
    try:
        if getattr(v, "shape", None) == () and hasattr(v, "item"): v = v.item()     # numpy scalar → plain number
    except Exception:
        pass
    r = repr(v)
    return r if len(r) < 4000 else r[:4000] + " …"

def _snap(d):
    out = {}
    for root, _, fs in os.walk(d):
        for f in fs:
            p = os.path.join(root, f)
            try: out[p] = os.path.getmtime(p)
            except OSError: pass
    return out

for line in sys.stdin:
    try:
        req = json.loads(line)
    except Exception:
        continue
    out_dir = req.get("out_dir") or os.getcwd(); os.makedirs(out_dir, exist_ok=True)
    G["FILES"] = req.get("files", {}); G["OUT_DIR"] = out_dir
    if "matplotlib.pyplot" in sys.modules: sys.modules["matplotlib.pyplot"].show = lambda *a, **k: None
    before = _snap(out_dir)
    buf = io.StringIO(); result, err = None, None
    t0 = time.time()
    try:
        import linecache
        src = req["code"]; linecache.cache["<cell>"] = (len(src), None, src.splitlines(True), "<cell>")
        tree = ast.parse(src, filename="<cell>", mode="exec")
        last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(compile(tree, "<cell>", "exec"), G)
            if last is not None:
                v = eval(compile(ast.Expression(last.value), "<cell>", "eval"), G)
                if v is not None: result = _show(v)
    except SystemExit:
        err = "SystemExit (exit() is ignored here)"
    except BaseException:
        et, ev, tb = sys.exc_info()
        while tb is not None and tb.tb_frame.f_code.co_filename == "<string>": tb = tb.tb_next   # hide the kernel itself
        lines = "".join(traceback.format_exception(et, ev, tb)).splitlines()
        err = "\n".join(l for l in lines if 'File "<frozen' not in l)[-3000:]
    figs = _figs(out_dir)
    after = _snap(out_dir)
    new = [p for p, m in after.items() if p not in figs and (p not in before or before[p] != m)]
    real_out.write(MARK + json.dumps({"stdout": buf.getvalue()[-8000:], "result": result, "error": err, "figures": figs,
                                      "files": new, "secs": round(time.time() - t0, 2)}) + "\n")
    real_out.flush()
'''


class PyKernel:
    def __init__(self, workdir):
        self.workdir = workdir; os.makedirs(workdir, exist_ok=True)
        self.proc = None; self.q = queue.Queue(); self.used = time.time()

    def start(self):
        env = dict(os.environ, MPLBACKEND="Agg", PYTHONUNBUFFERED="1")
        self.proc = subprocess.Popen([_sys.executable, "-u", "-c", _KERNEL_SRC], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, cwd=self.workdir, env=env, bufsize=1)
        self.q = queue.Queue()
        threading.Thread(target=self._pump, args=(self.proc, self.q), daemon=True).start()

    @staticmethod
    def _pump(proc, q):
        for line in proc.stdout:
            q.put(line)
        q.put(None)

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def kill(self):
        if self.proc is not None:
            try: self.proc.kill()
            except Exception: pass
        self.proc = None

    def run(self, code, files, timeout=PY_TIMEOUT, stop=lambda: False):
        if not self.alive(): self.start()
        self.used = time.time()
        out_dir = os.path.join(self.workdir, "out")
        self.proc.stdin.write(json.dumps({"code": code, "files": files, "out_dir": out_dir}) + "\n"); self.proc.stdin.flush()
        stray, t0 = [], time.time()
        while True:
            left = timeout - (time.time() - t0)
            if left <= 0 or stop():
                self.kill()
                return {"stdout": "".join(stray)[-4000:], "result": None, "figures": [], "files": [], "restarted": True,
                        "error": f"Stopped: the code ran longer than {timeout}s (session restarted, variables were reset)." if left <= 0 else "Stopped by user."}
            try:
                line = self.q.get(timeout=min(0.5, left))
            except queue.Empty:
                continue
            if line is None:
                self.proc = None
                return {"stdout": "".join(stray)[-4000:], "result": None, "figures": [], "files": [], "restarted": True,
                        "error": "The Python session crashed (out of memory?). It was restarted; variables were reset."}
            if line.startswith(_PY_MARK):
                res = json.loads(line[len(_PY_MARK):])
                if stray: res["stdout"] = "".join(stray) + res.get("stdout", "")
                return res
            stray.append(line)                                # output printed by C extensions / subprocesses


_KERNELS = {}


def kernel_for(chat_id):
    chat_id = re.sub(r"[^\w-]", "", chat_id or "default")[:40] or "default"
    k = _KERNELS.get(chat_id)
    if k is None:
        if len(_KERNELS) >= 4:                                # keep memory in check: drop the least recently used
            old = min(_KERNELS, key=lambda c: _KERNELS[c].used); _KERNELS.pop(old).kill()
        k = _KERNELS[chat_id] = PyKernel(os.path.join(WORK_DIR, "py", chat_id))
    return k


def _py_files(file_ids):
    out = {}
    for fid in dict.fromkeys(file_ids or []):
        r = FILES.get(fid)
        if r and r.get("origin") != "draft" and os.path.exists(r["path"]):
            out[r["name"]] = r["path"]; out[fid] = r["path"]
    return out


PY_BLOCK_RE = re.compile(r"```meow-python[^\n]*\n(.*?)\n?```", re.S)


def run_python(code, chat_id, file_ids, stop=lambda: False):
    """Run one cell; returns (markdown to append to the answer, list of new file records)."""
    res = kernel_for(chat_id).run(code, _py_files(file_ids), stop=stop)
    text = (res.get("stdout") or "").rstrip()
    if res.get("result") is not None: text = (text + "\n" if text else "") + res["result"]
    if res.get("error"): text = (text + "\n" if text else "") + res["error"]
    if len(text) > 6000: text = text[:2500] + "\n… (output trimmed) …\n" + text[-3000:]
    md = "\n```meow-output" + ("-error" if res.get("error") else "") + "\n" + (text or "(no output)") + "\n```\n"
    recs = []
    for p in res.get("figures", []) + res.get("files", []):
        try:
            if not os.path.isfile(p) or os.path.getsize(p) == 0: continue
            fid, dst = new_path(os.path.basename(p)); shutil.copy(p, dst)
            rec = register(fid, dst, os.path.basename(p), origin="tool"); recs.append(rec)
            if p in res.get("figures", []): md += f"\n![{rec['name']}](/api/files/{fid})\n"
        except Exception as e:
            print("⚠️  python output file:", e)
    return md, recs, res


FEATURES["python"] = True
