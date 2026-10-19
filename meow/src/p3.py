
# ==========================================================
# PROMPTING
# ==========================================================
def _tool_catalog():
    lines = []
    for t in TOOLS.values():
        need = "no file" if not t["accepts"] else (f"files: {'/'.join(t['accepts'])}" + (" (several, in order)" if t["multi"] else " (one)"))
        ps = ", ".join(p["name"] for p in t["params"]) or "—"
        lines.append(f"- {t['op']} [{need}; params: {ps}] — {t['desc']}")
    return "\n".join(lines)


def system_prompt(think):
    today = datetime.datetime.now().strftime("%A, %d %B %Y")
    mode = (
        "THINK MODE is on: before answering, reason carefully in your thinking — work out what's really being asked, break the "
        "problem down, consider alternatives and edge cases, check every calculation and line of code, and catch your own "
        "mistakes. Then write a polished final answer that stands on its own (never mention your reasoning process)."
        if think else
        "FAST MODE is on: answer directly and efficiently. Keep it tight, but never trade away correctness."
    )
    py = ("" if not FEATURES.get("python") else """
PYTHON — you can run real Python code (a persistent Jupyter-like session: variables survive between runs). Use it whenever exact
computation beats mental maths: arithmetic beyond trivial, statistics, unit conversions, dates, data analysis on attached
CSV/Excel/JSON files, plots and charts, simulations, checking code you wrote. Write a block like this and STOP — the app runs it
and shows you the output, then you continue:
```meow-python
import pandas as pd
df = pd.read_csv(FILES["sales.csv"])      # FILES maps each attached file name → its path
df.describe()
```
- The last expression is displayed (like Jupyter). print() works. matplotlib figures are shown to the user automatically
  (plt.show() is optional); use clear titles, labels and a readable style. Save any file you want to give the user into OUT_DIR
  (e.g. df.to_excel(f"{OUT_DIR}/report.xlsx")) and it appears as a download card.
- Available: numpy, pandas, matplotlib, scipy, sympy, sklearn (if installed), openpyxl, PIL. No internet from Python.
- Never invent output. Read the real output before concluding; if there's an error, fix it and run again (max 3 tries).
- Don't use Python for things that need no computation (explanations, writing, simple facts).
""")
    return f"""You are Meow 🐈 — a brilliant, warm and genuinely helpful AI assistant with the calm focus of a grey cat. You're talking with {USER_NAME or 'the user'}. Today is {today}.

{mode}

HOW TO ANSWER (this matters most)
- First understand the real need behind the message: what would an expert friend say? Answer that, not just the literal words.
- Lead with the answer or the key insight in the first sentence or two. Then give the supporting detail, reasoning or steps.
- Match length and shape to the question. Casual message → short, natural, friendly reply in plain sentences. Quick factual
  question → a direct answer plus only the context that adds value. Explanations, comparisons, plans, research → well-organised
  answers with clear structure. Never pad. Never repeat the question back. No "Great question!", no "I hope this helps".
- Formatting: use Markdown when it truly aids reading — headings only for long multi-part answers, numbered steps for procedures,
  bullets for genuinely parallel items, tables for comparisons across several attributes, **bold** for the few things that
  matter most. Explanations read best as clear prose paragraphs; don't chop reasoning into fragmented bullets.
- Teach like the best teachers: build intuition first, then precision. Use a concrete example, a small worked case or a vivid
  analogy when an idea is abstract. Define jargon the first time if the user may not know it.
- For decisions and advice: give a clear recommendation and why, the key trade-offs, and when the other option wins.
  Be specific (names, numbers, versions, commands, prices with dates) rather than generic.
- For code: complete, runnable, idiomatic, with a language tag on every block. Explain the approach briefly and point out the
  non-obvious parts. When debugging, find the root cause, explain it in one or two lines, then give the fix. When editing a
  user's file, return the whole updated file in one block.
- Maths/science: show the key steps, LaTeX with $inline$ and $$display$$, units throughout, and a sanity check of the result.
- Be honest and calibrated. If you're unsure, say how sure you are. If something can't be known, say so. If the user's premise is
  wrong, say so kindly and explain. Never invent facts, quotes, sources, numbers, file contents or tool results.
- If a request is genuinely ambiguous and a wrong guess would waste effort, ask one short clarifying question; otherwise make the
  most reasonable assumption, state it in a few words, and proceed.
- End cleanly. Instead of generic offers, you may close with one specific, useful next step.
- Reply in the user's language and register — English, Hindi or Hinglish — mirroring how they write.
- FOLLOW-UPS: after research, learning, planning or open-ended answers, end with one final line exactly in this form:
  <<followups: short question 1 | short question 2 | short question 3>>
  (questions the user would naturally ask next, written in their voice). Skip it for chit-chat, quick facts, or code-only replies.

WEB
- The app can search the web, Reddit, YouTube, Wikipedia, research papers, GitHub and Stack Overflow for you (🌐 button: Auto,
  Web, Reddit, Deep research), and it reads any link the user pastes. When <web_results> or <link> content is attached, use it
  and cite it.
- When nothing is attached and the question needs fresh information (news, prices, recent releases), answer with what you know,
  say it may be outdated, and suggest turning on 🌐 Web.

FILES
- Attached file contents arrive inside <file> tags, with ids listed above them.
- Images arrive as an automated analysis (caption, OCR text, colours, EXIF) — you don't see pixels. Ground what you say about an
  image in that analysis, and say when a detail isn't covered by it.

DIAGRAMS — for flows, architectures, timelines, mind-maps or sequences, a ```mermaid block renders as a real diagram. For a web
page, UI or visual demo, a single self-contained ```html block gets a live Preview button.
{py}
TOOLS — you can edit, convert and create real files. To run one, put a block like this in your reply:
```meow-tool
{{"op": "pdf_watermark", "files": ["<file id>"], "params": {{"text": "CONFIDENTIAL"}}}}
```
The app runs it after your reply and shows a download card. Use "$last" as a file id to chain onto the previous tool's output. Several blocks run in order. Only use tools when the user wants a file changed, converted or created; say in one line what you're doing, and never claim a result before it runs. Use make_pdf for documents/reports the user wants as a PDF. To change words in a PDF use pdf_replace_text (it keeps the original font, size and colour); for images inside a PDF use the pdf_*_image tools with the image numbers listed in the file. For words inside photos, screenshots, posters or scanned pages use image_replace_text (it reads the image, cleans the background and redraws the text in a matching font); pdf_replace_text also falls back to this automatically for scanned PDFs. For hands-on edits, the user can open any PDF or image in the visual editor (✏️ on its file card).
Available tools:
{_tool_catalog()}"""


def file_context(file_ids, budget):
    recs = [FILES[i] for i in dict.fromkeys(file_ids) if i in FILES]
    if not recs:
        return ""

    def meta(r):
        m = r["meta"]; bits = [r["kind"]]
        if m.get("pages"): bits.append(f"{m['pages']} pages")
        if m.get("dims"): bits.append(m["dims"])
        if r["origin"] == "tool": bits.append("created by a tool")
        return ", ".join(bits)

    header = "Files in this chat (ids for tools):\n" + "\n".join(f"- {r['name']} — id={r['id']} ({meta(r)})" for r in recs)
    remaining = budget - ntok(header)
    blocks = {}
    for r in reversed([r for r in recs if r["origin"] != "tool"]):   # newest files get priority
        if remaining < 200:
            break
        if r.get("text") is None:
            extract(r)
        body = r["text"] or "(no extractable content)"
        t = ntok(body)
        if t > remaining - 40:
            body = trim_tokens(body, remaining - 60); t = remaining
        blocks[r["id"]] = f'<file name="{r["name"]}" id="{r["id"]}" type="{r["kind"]}">\n{body}\n</file>'
        remaining -= t + 30
    return header + "\n\n" + "\n\n".join(blocks[r["id"]] for r in recs if r["id"] in blocks)


def build_prompt(req, web_ctx=""):
    think = req.mode == "think"
    max_new = min(MAX_NEW_THINK if think else MAX_NEW_FAST, CTX // 2)
    budget = CTX - max_new - 64
    system = system_prompt(think) + (WEB_RULES if web_ctx else "")
    user = (req.prompt or "").strip() or (
        "Analyze the attached file(s) and give me a clear, well-organized overview of what's in them." if req.file_ids else "Hi!")
    sys_t = ntok(system)
    if ntok(user) > budget * 0.6:
        user = trim_tokens(user, int(budget * 0.6))
    avail = budget - sys_t - ntok(user)
    if web_ctx:
        if ntok(web_ctx) > int(avail * 0.7): web_ctx = trim_tokens(web_ctx, int(avail * 0.7)) + "\n</web_results>"
        avail -= ntok(web_ctx) + 8
    fctx = file_context(req.file_ids, int(avail * 0.75)) if req.file_ids else ""
    avail -= ntok(fctx)
    turns = []
    for m in reversed(req.history[-24:]):
        role, c = m.get("role"), str(m.get("content") or "")
        if role not in ("user", "assistant") or not c.strip():
            continue
        if role == "assistant":
            c = THINK_RE.sub("", c).strip()
        t = ntok(c) + 10
        if t > avail:
            break
        turns.insert(0, (role, c)); avail -= t
    ctx = "\n\n".join(x for x in (fctx, web_ctx) if x)
    user_full = f"{ctx}\n\n---\n\n{user}" if ctx else user
    return system, turns, user_full, max_new, think


def chatml(system, turns, user, think):
    s = f"<|im_start|>system\n{system}<|im_end|>\n"
    for role, c in turns:
        s += f"<|im_start|>{role}\n{c}<|im_end|>\n"
    s += f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
    # Native Qwen thinking switch: open a think block, or pre-close it for fast mode
    return s + ("<think>\n" if think else "<think>\n\n</think>\n\n")


def sse(obj):
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

# ==========================================================
# API
# ==========================================================
app = FastAPI(title="Meow")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------- password gate, activity tracking, power-off ----------
import hashlib, hmac
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
MEOW_PASSWORD = os.environ.get("MEOW_PASSWORD", "")
STATE = {"last": time.time(), "started": time.time(), "shutdown": False}
BATCH = os.environ.get("MEOW_BATCH") == "1"


def _auth_token():
    return hashlib.sha256(("meow-auth:" + MEOW_PASSWORD).encode()).hexdigest()[:40]


LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meow · sign in</title><style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse at top,#1e1240,#05050d 70%);
font-family:Inter,system-ui,sans-serif;color:#e8e8f5}form{width:min(340px,88vw);padding:30px 26px;border-radius:22px;background:rgba(255,255,255,.05);
border:1px solid rgba(167,139,250,.25);text-align:center;box-shadow:0 30px 80px -20px rgba(124,58,237,.45)}h1{margin:6px 0 4px;font-size:1.6rem}
p{margin:0 0 20px;color:#9a9cc0;font-size:.9rem}input{width:100%;box-sizing:border-box;padding:12px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.15);
background:rgba(0,0,0,.35);color:#fff;font-size:1rem;outline:none}input:focus{border-color:#a78bfa}button{margin-top:14px;width:100%;padding:12px;border:0;
border-radius:12px;background:linear-gradient(135deg,#7c3aed,#2563eb);color:#fff;font-size:1rem;font-weight:600;cursor:pointer}.err{color:#fca5a5;font-size:.85rem;margin-top:10px}
</style></head><body><form method="post" action="/login"><div style="font-size:2.6rem">🐈</div><h1>Meow</h1><p>Enter your password</p>
<input type="password" name="password" autofocus autocomplete="current-password"><button>Open Meow</button>__ERR__</form></body></html>"""


@app.middleware("http")
async def _gate(request: Request, call_next):
    path = request.url.path
    if path != "/api/health": STATE["last"] = time.time()
    if MEOW_PASSWORD and path not in ("/login", "/api/health", "/favicon.ico"):
        if not hmac.compare_digest(request.cookies.get("meow_auth", ""), _auth_token()):
            if path.startswith("/api/"): return JSONResponse({"detail": "Login required — reload the page"}, status_code=401)
            return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(LOGIN_HTML.replace("__ERR__", ""))


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    if MEOW_PASSWORD and hmac.compare_digest(str(form.get("password", "")), MEOW_PASSWORD):
        r = RedirectResponse("/", status_code=303)
        https = request.headers.get("x-forwarded-proto", "") == "https" or request.url.scheme == "https"
        r.set_cookie("meow_auth", _auth_token(), max_age=30 * 86400, httponly=True, samesite="lax", secure=https)
        return r
    time.sleep(1.2)                                        # slow down guessing
    return HTMLResponse(LOGIN_HTML.replace("__ERR__", '<div class="err">Wrong password</div>'), status_code=401)


@app.post("/api/shutdown")
def shutdown():
    STATE["shutdown"] = True
    if not BATCH and globals().get("MEOW_SERVER") is not None:
        threading.Timer(1.0, lambda: setattr(MEOW_SERVER, "should_exit", True)).start()
    return {"ok": True, "batch": BATCH}


def announce(msg, url=None):
    """Push a phone/desktop notification through ntfy.sh (topic = MEOW_NTFY_TOPIC). Tap it to open Meow."""
    topic = os.environ.get("MEOW_NTFY_TOPIC", "").strip()
    if not topic: return
    try:
        import requests
        h = {"Title": "Meow", "Tags": "cat", "Priority": "high" if url else "default"}
        if url: h["Click"] = url; h["Actions"] = f"view, Open Meow, {url}"
        requests.post(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"), headers=h, timeout=10)
    except Exception as e:
        print("⚠️  notification failed:", e)


class ChatReq(BaseModel):
    prompt: str = ""
    mode: str = "fast"
    history: list = []
    file_ids: List[str] = []
    rid: str = ""
    web: str = "off"          # off | auto | web | reddit | deep
    chat_id: str = ""


class ToolReq(BaseModel):
    op: str = ""
    files: List[str] = []
    params: dict = {}
    raw: str = ""
    last: str = ""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(MEOW_HTML.replace("__USER_NAME__", html.escape(USER_NAME or "")))


@app.get("/api/health")
def health():
    return {"status": "online", "version": MEOW_VERSION, "batch": BATCH, "auth": bool(MEOW_PASSWORD),
            "changelog": MEOW_CHANGELOG[:8], "model": GGUF_FILENAME, "model_short": MODEL_LABEL, "ctx": CTX,
            "chatml": USE_CHATML, "files": len(FILES), **FEATURES}


@app.get("/api/tools")
def list_tools():
    return {"tools": [{k: v for k, v in t.items() if k != "fn"} for t in TOOLS.values()]}


@app.get("/api/files")
def list_files():
    return {"files": [public(r) for r in sorted(FILES.values(), key=lambda r: -r["created"]) if r["origin"] != "draft"]}


@app.get("/api/files/{fid}")
def get_file(fid: str, dl: int = 0):
    rec = FILES.get(fid)
    if not rec or not os.path.exists(rec["path"]):
        raise HTTPException(404, "File not found (server may have restarted)")
    mt = mimetypes.guess_type(rec["name"])[0] or "application/octet-stream"
    return FileResponse(rec["path"], media_type=mt, filename=rec["name"],
                        content_disposition_type="attachment" if dl else "inline")


@app.get("/api/thumb/{fid}")
def thumb(fid: str, size: int = 400):
    rec = FILES.get(fid)
    if not rec or rec["kind"] not in ("image", "pdf"):
        raise HTTPException(404)
    size = max(64, min(int(size), 2000))
    tp = os.path.join(WORK_DIR, f".thumb_{fid}_{size}.jpg")
    if not os.path.exists(tp):
        try:
            if rec["kind"] == "pdf":
                with fitz.open(rec["path"]) as d:
                    pix = d[0].get_pixmap(dpi=int(72 * min(3, max(0.5, size / 600))))
                    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            else:
                im = ImageOps.exif_transpose(Image.open(rec["path"]))
            im = _flatten(im); im.thumbnail((size, size), Image.LANCZOS); im.save(tp, "JPEG", quality=85)
        except Exception:
            raise HTTPException(404)
    return FileResponse(tp, media_type="image/jpeg")


@app.post("/api/upload")
async def upload(files: List[UploadFile] = File(...)):
    out = []
    for f in files:
        data = await f.read()
        rec = await run_in_threadpool(ingest, f.filename or "file", data)
        out.append(public(rec))
    return {"files": out}


@app.post("/api/tool")
async def api_tool(req: ToolReq):
    try:
        op, fids, params = req.op, req.files, req.params
        if req.raw:
            d = json.loads(req.raw.strip(), strict=False)
            op, fids, params = d.get("op", ""), d.get("files") or [], d.get("params") or {}
            if isinstance(fids, str): fids = [fids]
        fids = [req.last if f == "$last" else f for f in fids]
        rec, msg = await run_in_threadpool(run_tool, op, fids, params)
        return {"ok": True, "op": op, "file": public(rec), "message": msg}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Tool call wasn't valid JSON ({e.msg})."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/stop")
def stop(d: dict):
    if d.get("rid"): STOP.add(d["rid"])
    return {"ok": True}


@app.post("/api/chat")
def chat(req: ChatReq):
    def gen():
        if not LLM_LOCK.acquire(blocking=False):
            yield sse({"status": "Waiting for the GPU…"})
            LLM_LOCK.acquire()
        try:
            web_ctx, wm, q = "", (req.web or "off").lower(), (req.prompt or "").strip()
            urls = URL_RE.findall(q)
            do_search = bool(q) and wm in ("auto", "web", "reddit", "deep") and (wm != "auto" or bool(AUTO_SEARCH_RE.search(re.sub(URL_RE, " ", q))))
            if urls or do_search:
                mx = min(MAX_NEW_THINK if req.mode == "think" else MAX_NEW_FAST, CTX // 2)
                big = wm in ("deep", "reddit")
                wb = max(700, int(min(8500 if big else 5000, (CTX - mx - 2600) * (0.8 if big else 0.65))))
                try:
                    for ev in web_research(q, req.history, wm, wb, req.rid, urls=urls, search=do_search):
                        if "_ctx" in ev: web_ctx = ev["_ctx"]
                        else: yield sse(ev)
                except Exception as e:
                    print("⚠️  web research failed:", e)
                    yield sse({"search": {"stage": "error", "error": str(e)[:200]}})
            if req.rid and req.rid in STOP:
                return
            if req.file_ids:
                yield sse({"status": "Reading your files…"})
            system, turns, user, max_new, think = build_prompt(req, web_ctx)
            yield sse({"status": ""})
            stopped = lambda: bool(req.rid and req.rid in STOP)
            n, t_first = 0, None
            if USE_CHATML:
                if think:
                    yield sse({"t": "<think>\n"})
                base = chatml(system, turns, user, think)
                acc, scan_from, rounds = "", 0, 0
                py_on = bool(FEATURES.get("python"))
                while True:
                    budget_left = max_new - n
                    room = CTX - ntok(base + acc) - 16
                    if budget_left < 32 or room < 64: break
                    stream = llm.create_completion(
                        prompt=base + acc, max_tokens=min(budget_left, room), stream=True,
                        temperature=0.6 if think else 0.7, top_p=0.95 if think else 0.8, top_k=20, min_p=0.0,
                        presence_penalty=0.5 if think else 0.3, repeat_penalty=1.0,
                        stop=["<|im_end|>", "<|endoftext|>", "<|im_start|>", "```meow-output"])
                    code = None
                    for ch in stream:
                        if stopped(): break
                        tok = ch["choices"][0].get("text", "")
                        if not tok: continue
                        if t_first is None: t_first = time.time()
                        n += 1; acc += tok
                        yield sse({"t": tok})
                        if py_on and "`" in tok and "```meow-python" in acc[scan_from:]:
                            te = acc.find("</think>")
                            if think and te < 0: continue                         # still thinking — never run code from thoughts
                            m = PY_BLOCK_RE.search(acc, max(scan_from, te + 8 if think else 0))
                            if m:
                                code = m.group(1); extra = len(acc) - m.end()
                                if extra > 0: acc = acc[:m.end()]; yield sse({"rollback": extra})   # drop text after the fence
                                scan_from = m.end(); break
                    if code is None or stopped() or rounds >= PY_MAX_ROUNDS: break
                    rounds += 1
                    if not acc.endswith("\n"): acc += "\n"; yield sse({"t": "\n"})
                    yield sse({"status": "Running Python…"})
                    try:
                        md, recs, _res = run_python(code, req.chat_id or req.rid, req.file_ids, stop=stopped)
                    except Exception as e:
                        md, recs = f"\n```meow-output error\nCouldn't run the code: {e}\n```\n", []
                    acc += md; scan_from = len(acc)
                    yield sse({"t": md})
                    if recs: yield sse({"files": [public(r) for r in recs]})
                    yield sse({"status": ""})
            else:
                msgs = [{"role": "system", "content": system}] + [{"role": r, "content": c} for r, c in turns] + \
                       [{"role": "user", "content": user + (" /think" if think else " /no_think")}]
                stream = llm.create_chat_completion(messages=msgs, max_tokens=max_new, stream=True,
                                                    temperature=0.6 if think else 0.7, top_p=0.95 if think else 0.8)
                for ch in stream:
                    if stopped(): break
                    tok = ch["choices"][0]["delta"].get("content", "") or ""
                    if tok:
                        if t_first is None: t_first = time.time()
                        n += 1
                        yield sse({"t": tok})
            dt = (time.time() - t_first) if t_first else 0
            yield sse({"stats": {"tokens": n, "secs": round(dt, 1), "tps": round(n / dt, 1) if dt > 0 else 0}})
        except Exception as e:
            yield sse({"t": f"\n\n⚠️ **Server error:** `{e}`"})
        finally:
            STOP.discard(req.rid)
            LLM_LOCK.release()
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ==========================================================
# LAUNCH (background server + public ngrok link)
# ==========================================================
if __name__ == "__main__":
    from pyngrok import ngrok
    _old = globals().get("MEOW_SERVER")
    if _old is not None:                         # re-running the cell: stop the old server cleanly
        _old.should_exit = True
        if globals().get("MEOW_THREAD"): MEOW_THREAD.join(timeout=10)
    try: ngrok.kill()
    except Exception: pass

    warm_up_media()                              # fonts + LaMa download in the background
    MEOW_SERVER = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning"))
    MEOW_THREAD = threading.Thread(target=MEOW_SERVER.run, daemon=True)
    MEOW_THREAD.start()
    for _ in range(60):
        if MEOW_SERVER.started: break
        time.sleep(0.25)

    _tok = NGROK_AUTH_TOKEN if NGROK_AUTH_TOKEN and "PASTE" not in NGROK_AUTH_TOKEN else None
    if not _tok:
        try:
            from kaggle_secrets import UserSecretsClient
            _tok = UserSecretsClient().get_secret("NGROK_AUTH_TOKEN")
        except Exception:
            pass
    if _tok: ngrok.set_auth_token(_tok)

    try:
        public_url = ngrok.connect(PORT).public_url
    except Exception as _e:                      # ngrok failed → free Cloudflare tunnel, no token needed
        print(f"⚠️  ngrok failed ({str(_e)[:90]}…) — switching to Cloudflare tunnel")
        import subprocess
        if not os.path.exists("./cloudflared"):
            os.system("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared && chmod +x cloudflared")
        MEOW_CF = subprocess.Popen(["./cloudflared", "tunnel", "--url", f"http://localhost:{PORT}", "--no-autoupdate"],
                                   stderr=subprocess.PIPE, text=True)
        public_url = "(waiting for Cloudflare…)"
        for _line in MEOW_CF.stderr:
            _m = re.search(r"https://[\w-]+\.trycloudflare\.com", _line)
            if _m: public_url = _m.group(); break
    print("=" * 66)
    print(f"🐈  MEOW IS LIVE  (v{MEOW_VERSION})")
    print(f"🌌  Open: {public_url}")
    print(f"🧠  Model: {MODEL_LABEL} · context {CTX:,} tokens · {'ChatML' if USE_CHATML else 'chat template'}")
    print("=" * 66)
    print(f"MEOW_URL {public_url}", flush=True)                 # machine-readable line for start_meow.py
    STATE["last"] = time.time()
    announce(f"Meow v{MEOW_VERSION} is live 🐈 — tap to open" + (" (password protected)" if MEOW_PASSWORD else ""), public_url)

    if BATCH:                                                # started remotely (start_meow.py / GitHub button)
        _idle = float(os.environ.get("MEOW_IDLE_MIN", "40")) * 60
        _maxh = float(os.environ.get("MEOW_MAX_HOURS", "8")) * 3600
        print(f"🕒  Auto power-off after {_idle / 60:.0f} min without use (max {_maxh / 3600:.0f} h) to save GPU hours.", flush=True)
        while True:
            time.sleep(15)
            _now = time.time()
            _why = ("you pressed Power off" if STATE["shutdown"] else
                    f"no use for {_idle / 60:.0f} min" if _now - STATE["last"] > _idle and not LLM_LOCK.locked() else
                    "time limit reached" if _now - STATE["started"] > _maxh else None)
            if _why:
                print(f"⏻  Shutting down: {_why}", flush=True)
                announce(f"Meow is off ({_why}). GPU released — start it again anytime.")
                MEOW_SERVER.should_exit = True; time.sleep(3)
                try: ngrok.kill()
                except Exception: pass
                break
