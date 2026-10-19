# 🐈 Meow cache job (runs once on Kaggle, started by `python start_meow.py setup`).
# Downloads the model and a GPU build of llama-cpp-python into /kaggle/working. Kaggle saves that folder as this
# notebook's output, and every Meow start attaches it — so no 15 GB download and no compiling each time.
import os, re, sys, glob, subprocess, urllib.request, time
W = "/kaggle/working"
RAW = "https://raw.githubusercontent.com/tarunmeenaofficial-droid/Tarun-dev/meow/meow/meow.py"
src = urllib.request.urlopen(RAW, timeout=60).read().decode()
REPO_ID = re.search(r'^REPO_ID = "([^"]+)"', src, re.M).group(1)
GGUF = re.search(r'^GGUF_FILENAME = "([^"]+)"', src, re.M).group(1)
pip = lambda *a: subprocess.run([sys.executable, "-m", "pip", *a], check=False)

t0 = time.time()
pip("install", "-q", "-U", "huggingface_hub")
os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"
from huggingface_hub import hf_hub_download
print(f"⬇️  {REPO_ID}/{GGUF}", flush=True)
hf_hub_download(repo_id=REPO_ID, filename=GGUF, local_dir=f"{W}/model")
print(f"✅ model saved ({os.path.getsize(f'{W}/model/{GGUF}') / 1e9:.1f} GB) in {time.time() - t0:.0f}s", flush=True)

DEPS = ["diskcache>=5.6.1", "jinja2>=2.11.3", "typing-extensions>=4.5.0", "numpy>=1.20.0"]   # llama-cpp-python's own deps


def ok(show=False):
    r = subprocess.run([sys.executable, "-c", "import llama_cpp,sys; print('llama_cpp', llama_cpp.__version__); "
                        "sys.exit(0 if llama_cpp.llama_supports_gpu_offload() else 1)"], capture_output=True, text=True)
    if show or r.returncode: print((r.stdout + r.stderr)[-1500:], flush=True)
    return r.returncode == 0


def cuda_env():
    env = dict(os.environ, CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=60;75", FORCE_CMAKE="1")
    for d in ("/usr/local/cuda/bin", *sorted(glob.glob("/usr/local/cuda-*/bin"), reverse=True)):
        if os.path.exists(f"{d}/nvcc"):
            env["CUDACXX"] = f"{d}/nvcc"; env["PATH"] = f"{d}:{env.get('PATH', '')}"
            env["CUDA_HOME"] = os.path.dirname(d); break
    return env


os.makedirs(f"{W}/wheels", exist_ok=True)
pip("install", "-q", *DEPS)
pip("download", "-q", "--no-deps", "--only-binary=:all:", "llama-cpp-python", "-d", f"{W}/wheels",
    "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cu124")
whl = glob.glob(f"{W}/wheels/llama_cpp_python*.whl")
if whl: pip("install", "-q", "--force-reinstall", "--no-deps", whl[0])
if not (whl and ok()):
    for w in whl: os.remove(w)
    print("🔧 compiling llama-cpp-python with CUDA (15-25 min)…", flush=True)
    env = cuda_env(); print("   nvcc:", env.get("CUDACXX", "NOT FOUND"), flush=True)
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", "-v", "--no-deps", "--no-cache-dir", "llama-cpp-python", "-w", f"{W}/wheels"],
                       env=env, capture_output=True, text=True)
    if r.returncode: print("❌ compile failed — last lines:\n" + (r.stdout + r.stderr)[-4000:], flush=True)
    whl = glob.glob(f"{W}/wheels/llama_cpp_python*.whl")
    if whl: pip("install", "-q", "--force-reinstall", "--no-deps", whl[0])
ok(show=True)
print("✅ GPU engine:", os.path.basename(whl[0]) if whl else None, "| GPU offload:", ok(), flush=True)
print(f"🎉 Cache ready in {(time.time() - t0) / 60:.0f} min. Every Meow start now skips the download.", flush=True)
