#!/usr/bin/env python3
"""
🐈 Start Meow with one click — no Kaggle tab needed.

    python start_meow.py            start Meow on a Kaggle GPU and open it in your browser
    python start_meow.py setup      one-time: cache the model + GPU engine on Kaggle (makes every start ~5× faster)
    python start_meow.py status     is Meow running?
    python start_meow.py logs       show the Kaggle log

The first run asks for your keys and saves them in meow_config.json NEXT TO THIS FILE (keep that file private).
It uses the Kaggle API to start a private notebook with a GPU T4×2, waits for the public link, opens it and sends a
notification to your phone (ntfy app). Meow powers itself off after a while without use, so GPU hours aren't wasted.
In GitHub Actions the same script reads everything from environment variables (repo secrets) instead.
"""
import json, os, re, secrets, subprocess, sys, tempfile, time, urllib.request, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "meow_config.json")
REPO, BRANCH = "tarunmeenaofficial-droid/Tarun-dev", "meow"
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/meow"
SERVER_SLUG, CACHE_SLUG = "meow-server", "meow-cache"
CI = bool(os.environ.get("GITHUB_ACTIONS"))

FIELDS = [  # (config key, env var, question, required)
    ("kaggle_username", "KAGGLE_USERNAME", "Your Kaggle username (kaggle.com/<username>)", True),
    ("kaggle_token", "KAGGLE_TOKEN", "Kaggle API token (kaggle.com/settings → API → Generate New Token)", True),
    ("NGROK_AUTH_TOKEN", "NGROK_AUTH_TOKEN", "ngrok auth token (Enter to skip → free Cloudflare link)", False),
    ("SERPER_API_KEY", "SERPER_API_KEY", "Serper API key (Enter to skip)", False),
    ("TAVILY_API_KEY", "TAVILY_API_KEY", "Tavily API key (Enter to skip)", False),
    ("MEOW_PASSWORD", "MEOW_PASSWORD", "Choose a password for Meow (Enter to skip — anyone with the link could use it)", False),
]


def say(*a): print(*a, flush=True)


def load_cfg():
    cfg = {}
    if os.path.exists(CFG_PATH):
        cfg = json.load(open(CFG_PATH, encoding="utf-8"))
    for key, env, q, req in FIELDS:
        if os.environ.get(env): cfg[key] = os.environ[env]
        if key not in cfg and not CI:
            v = input(f"{q}: ").strip()
            cfg[key] = v
        if req and not cfg.get(key): sys.exit(f"❌ {key} is required.")
    cfg.setdefault("ntfy_topic", os.environ.get("MEOW_NTFY_TOPIC") or "meow-" + secrets.token_hex(8))
    cfg.setdefault("idle_minutes", int(os.environ.get("MEOW_IDLE_MIN", 40)))
    cfg.setdefault("max_hours", int(os.environ.get("MEOW_MAX_HOURS", 8)))
    if not CI:
        json.dump(cfg, open(CFG_PATH, "w", encoding="utf-8"), indent=2)
    return cfg


def kaggle_api(cfg):
    tok = cfg["kaggle_token"].strip()
    if tok.startswith("{"):                                   # pasted the whole kaggle.json
        j = json.loads(tok); cfg["kaggle_username"] = cfg.get("kaggle_username") or j["username"]; tok = j["key"]
    if re.fullmatch(r"[0-9a-f]{32}", tok):                   # legacy key (kaggle.json style)
        os.environ["KAGGLE_USERNAME"], os.environ["KAGGLE_KEY"] = cfg["kaggle_username"], tok
    else:                                                     # new-style API token
        os.environ["KAGGLE_API_TOKEN"] = tok
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError:
        say("📦 Installing the Kaggle API (one time)…")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kaggle"], check=True)
        from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi(); api.authenticate()
    return api


def fetch(name):
    """Newest file from GitHub; falls back to the copy next to this script."""
    try:
        return urllib.request.urlopen(f"{RAW}/{name}?t={int(time.time())}", timeout=20).read().decode("utf-8")
    except Exception:
        return open(os.path.join(HERE, name), encoding="utf-8").read()


def status(api, slug):
    try:
        s = api.kernels_status(slug)
        return str(getattr(s, "status", s)).split(".")[-1].lower()
    except Exception as e:
        return "missing" if "404" in str(e) or "not found" in str(e).lower() else f"unknown ({str(e)[:60]})"


def push(api, folder, meta, code, timeout=None):
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, meta["code_file"]), "w", encoding="utf-8").write(code)
    json.dump(meta, open(os.path.join(folder, "kernel-metadata.json"), "w"), indent=2)
    return api.kernels_push(folder, timeout=timeout)


def meta_for(user, slug, title, sources=()):
    return {"id": f"{user}/{slug}", "title": title, "code_file": f"{slug.replace('-', '_')}.py", "language": "python",
            "kernel_type": "script", "is_private": "true", "enable_gpu": "true", "enable_internet": "true",
            "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "competition_sources": [], "model_sources": [],
            "kernel_sources": list(sources)}


def setup(cfg, api):
    user = cfg["kaggle_username"]
    say("📦 Starting the one-time cache job on Kaggle: it downloads the model (~15 GB) and prepares the GPU engine,")
    say("   then saves both so every Meow start can skip that work. Takes ~15-40 min — you can close this window.")
    code = fetch("kaggle/cache_kernel.py")
    with tempfile.TemporaryDirectory() as d:
        r = push(api, d, meta_for(user, CACHE_SLUG, CACHE_SLUG), code)
    say(f"✅ Started: https://www.kaggle.com/code/{user}/{CACHE_SLUG}  (status: python start_meow.py status)")
    if getattr(r, "error", None): say("⚠️ ", r.error)


def start(cfg, api, open_browser=True):
    user = cfg["kaggle_username"]; sid = f"{user}/{SERVER_SLUG}"
    st = status(api, sid)
    if st in ("running", "queued"):
        say(f"ℹ️  Meow is already {st}. Looking for its link…")
    else:
        cache_ok = status(api, f"{user}/{CACHE_SLUG}") == "complete"
        if not cache_ok: say("💡 Tip: run `python start_meow.py setup` once — starts become much faster.")
        keys = {k: cfg.get(k, "") for k in ("NGROK_AUTH_TOKEN", "SERPER_API_KEY", "TAVILY_API_KEY")}
        extra = {"MEOW_BATCH": "1", "MEOW_PASSWORD": cfg.get("MEOW_PASSWORD", ""), "MEOW_NTFY_TOPIC": cfg["ntfy_topic"],
                 "MEOW_IDLE_MIN": str(cfg["idle_minutes"]), "MEOW_MAX_HOURS": str(cfg["max_hours"])}
        launcher = fetch("kaggle_launcher.py")
        launcher = re.sub(r"KEYS = \{.*?\n\}", "KEYS = " + json.dumps({**keys, **extra}, indent=4), launcher, count=1, flags=re.S)
        with tempfile.TemporaryDirectory() as d:
            r = push(api, d, meta_for(user, SERVER_SLUG, SERVER_SLUG, [f"{user}/{CACHE_SLUG}"] if cache_ok else []), launcher,
                     timeout=str(int(cfg["max_hours"] * 3600 + 900)))
        if getattr(r, "error", None): sys.exit(f"❌ Kaggle refused the start: {r.error}")
        say(f"🚀 Meow is starting on a Kaggle GPU T4×2 (private notebook: https://www.kaggle.com/code/{sid})")
        say(f"📱 Phone notification: install the ntfy app and subscribe to topic  {cfg['ntfy_topic']}")
    url = wait_for_url(api, sid, cfg["ntfy_topic"])
    if not url: sys.exit("❌ Meow didn't come up — run `python start_meow.py logs` to see why.")
    say("=" * 60); say(f"🐈 MEOW IS LIVE:  {url}"); say("=" * 60)
    if CI and os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(f"## 🐈 Meow is live\n\n**[Open Meow]({url})**\n")
    if open_browser and not CI:
        webbrowser.open(url)
    return url


def wait_for_url(api, sid, topic, limit=60 * 45):
    t0, since, last_stage = time.time(), int(time.time()) - 5, ""
    stages = [("Installing", "📦 installing packages"), ("llama-cpp", "⚡ preparing the GPU engine"),
              ("Got the newest", "⬇️  downloaded the newest Meow"), ("Loading", "🧠 loading the model onto the GPU"),
              ("Model loaded", "✅ model loaded — opening the tunnel")]
    while time.time() - t0 < limit:
        try:                                                 # 1) the notification Meow sends when it's live
            raw = urllib.request.urlopen(f"https://ntfy.sh/{topic}/json?poll=1&since={since}", timeout=15).read().decode()
            for line in raw.splitlines():
                m = json.loads(line)
                if m.get("click"): return m["click"]
        except Exception:
            pass
        try:                                                 # 2) the Kaggle log
            log = api.kernels_logs(sid)
            m = re.findall(r"MEOW_URL (https://\S+)", log)
            if m: return m[-1]
            done = [label for key, label in stages if key in log]
            if done and done[-1] != last_stage: last_stage = done[-1]; say("   " + last_stage)
        except Exception:
            pass
        st = status(api, sid)
        if st in ("error", "cancelacknowledged", "cancelrequested", "complete"):
            say(f"⚠️  The Kaggle run ended with status: {st}"); return None
        time.sleep(15)
    return None


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "start").lower()
    cfg = load_cfg(); api = kaggle_api(cfg)
    user = cfg["kaggle_username"]
    if cmd == "setup": setup(cfg, api)
    elif cmd == "status":
        say("Meow server:", status(api, f"{user}/{SERVER_SLUG}"), "| cache:", status(api, f"{user}/{CACHE_SLUG}"))
    elif cmd == "logs":
        say(api.kernels_logs(f"{user}/{SERVER_SLUG}")[-6000:])
    else:
        start(cfg, api)
    if not CI and os.name == "nt" and len(sys.argv) < 2:
        input("\nPress Enter to close this window…")


if __name__ == "__main__":
    main()
