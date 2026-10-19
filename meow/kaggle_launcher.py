# ╔══════════════════════════════════════════════════════════════╗
# ║  🐈 MEOW — ONE CELL. Run this cell, open the link it prints.  ║
# ║  Every run pulls the newest Meow from GitHub automatically.  ║
# ╚══════════════════════════════════════════════════════════════╝
# Notebook settings (right panel): Accelerator = GPU T4 x2 · Internet = ON

MEOW_REPO = "tarunmeenaofficial-droid/Tarun-dev"   # GitHub repo that holds Meow
MEOW_BRANCH = "meow"                               # Meow lives on its own branch
MEOW_PATH = "meow/meow.py"

# Your keys. Keep this notebook PRIVATE. (Or leave "" and add them in Add-ons → Secrets with the same names.)
KEYS = {
    "NGROK_AUTH_TOKEN": "",
    "SERPER_API_KEY":   "",
    "TAVILY_API_KEY":   "",
    "GITHUB_TOKEN":     "",          # only needed if the repo is private
}

import os, sys, glob, subprocess, importlib, importlib.util, urllib.request, time, shutil
for k, v in KEYS.items():
    if v: os.environ[k] = v
os.environ["PIP_ROOT_USER_ACTION"] = "ignore"
W = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.getcwd()

def sh(cmd, quiet=True):
    r = subprocess.run(cmd, shell=True, capture_output=quiet, text=True)
    if r.returncode and quiet: print((r.stdout or "")[-1500:], (r.stderr or "")[-1500:])
    return r.returncode == 0

t0 = time.time()
# ---- 1. Python packages (only the missing ones) ----
PKGS = {"fitz": "pymupdf", "rapidocr_onnxruntime": "rapidocr_onnxruntime", "docx": "python-docx", "pptx": "python-pptx",
        "openpyxl": "openpyxl", "markdown": "markdown", "pillow_heif": "pillow-heif", "pyngrok": "pyngrok", "spandrel": "spandrel",
        "ddgs": "ddgs", "trafilatura": "trafilatura", "youtube_transcript_api": "youtube-transcript-api", "pdf2docx": "pdf2docx",
        "huggingface_hub": "huggingface_hub", "fastapi": "fastapi", "uvicorn": "uvicorn",
        "multipart": "python-multipart"}
miss = [p for m, p in PKGS.items() if importlib.util.find_spec(m) is None]
if miss:
    print("📦 Installing:", " ".join(miss)); sh(f"{sys.executable} -m pip install -q " + " ".join(miss))

# ---- 2. llama-cpp-python with CUDA (GPU) ----
def llama_gpu_ok():
    chk = "import llama_cpp, sys; sys.exit(0 if llama_cpp.llama_supports_gpu_offload() else 1)"
    return subprocess.run([sys.executable, "-c", chk], capture_output=True).returncode == 0

if not llama_gpu_ok():
    wheels = glob.glob("/kaggle/input/**/llama_cpp_python*.whl", recursive=True)
    if wheels:                                                      # fastest: your saved wheel (Kaggle dataset)
        print("⚡ Installing llama-cpp-python from your saved wheel…")
        sh(f"{sys.executable} -m pip install -q --force-reinstall --no-deps {wheels[0]}")
    if not llama_gpu_ok():
        print("⚡ Installing llama-cpp-python (CUDA build, prebuilt)…")
        cu = "cu124"
        sh(f"{sys.executable} -m pip install -q --force-reinstall --no-cache-dir --prefer-binary llama-cpp-python "
           f"--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/{cu}")
    if not llama_gpu_ok():
        print("🔧 No prebuilt GPU wheel fits — compiling with CUDA (one time, ~15-25 min). The wheel is saved to "
              f"{W}/wheels — add it as a Kaggle Dataset and next sessions install in seconds.")
        os.makedirs(f"{W}/wheels", exist_ok=True)
        ok = sh(f'CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=60;75" FORCE_CMAKE=1 {sys.executable} -m pip wheel '
                f'--no-deps --no-cache-dir llama-cpp-python -w {W}/wheels', quiet=False)
        built = glob.glob(f"{W}/wheels/llama_cpp_python*.whl")
        if ok and built: sh(f"{sys.executable} -m pip install -q --force-reinstall --no-deps {built[0]}")
    print("✅ llama-cpp-python GPU:", llama_gpu_ok())

# ---- 3. newest meow.py from GitHub (falls back to the last good copy) ----
dst = f"{W}/meow.py"
url = f"https://raw.githubusercontent.com/{MEOW_REPO}/{MEOW_BRANCH}/{MEOW_PATH}"
req = urllib.request.Request(url + f"?t={int(time.time())}", headers={"Cache-Control": "no-cache"})
if os.environ.get("GITHUB_TOKEN"):
    req = urllib.request.Request(f"https://api.github.com/repos/{MEOW_REPO}/contents/{MEOW_PATH}?ref={MEOW_BRANCH}",
                                 headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github.raw"})
try:
    code = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    compile(code, "meow.py", "exec")                                # never run a broken download
    open(dst, "w").write(code)
    v = next((l.split('"')[1] for l in code.splitlines() if l.startswith("MEOW_VERSION")), "?")
    print(f"⬇️  Got the newest Meow (v{v}) from github.com/{MEOW_REPO} ({MEOW_BRANCH})")
except Exception as e:
    if not os.path.exists(dst): raise SystemExit(f"❌ Couldn't download meow.py ({e}). Is Internet ON and the repo name right?")
    print(f"⚠️  GitHub unreachable ({e}) — using the last downloaded copy")

print(f"⏱️  Setup took {time.time() - t0:.0f}s — starting Meow…")
exec(compile(open(dst).read(), dst, "exec"), globals())
